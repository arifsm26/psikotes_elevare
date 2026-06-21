# backend/admin_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from fastapi.responses import StreamingResponse
import io
import csv
from fastapi import UploadFile, File
from pathlib import Path
import shutil
from datetime import datetime, date 
from typing import Optional

from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from typing import List  # <-- TAMBAHKAN BARIS 
from config import settings


import models
import crud, schemas, security
from database import get_db

router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="admin/token")


async def get_current_active_admin_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    # --- Debugging prints (biarkan saja untuk sekarang) ---
    print("\n--- VALIDATING TOKEN ---")
    print(f"Token received: Bearer {token[:10]}...")
    print(f"VALIDATING with SECRET_KEY ending in: ...{settings.SECRET_KEY[-6:]}")
    # --------------------------------------------------------

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str = payload.get("sub")
        if email is None:
            # Jika 'sub' tidak ada di dalam token
            print("!!! JWT DECODE FAILED: 'sub' (email) not found in token payload.")
            raise credentials_exception
        
        print(f"Token decoded successfully. Email: {email}")

    except JWTError as e:
        # Jika token tidak valid (kadaluarsa, signature salah, dll.)
        print(f"!!! JWT DECODE FAILED: {e}")
        raise credentials_exception
    
    admin = crud.get_admin_by_email(db, email=email)
    if admin is None or not admin.is_active:
        print(f"!!! ADMIN NOT FOUND OR INACTIVE for email: {email}")
        raise credentials_exception
        
    return admin


@router.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), # <-- UBAH INI
    db: Session = Depends(get_db)
):
    # 'username' sekarang diakses dari form_data.username
    admin = crud.get_admin_by_email(db, email=form_data.username)
    if not admin or not security.verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
 
    # Buat token dengan data tambahan (peran)
    token_data = {"sub": admin.email, "roles": [admin.role]}
    access_token = security.create_access_token(data=token_data)

    return {"access_token": access_token, "token_type": "bearer"}

async def get_current_superadmin(
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    if current_admin.role != 'superadmin':
        raise HTTPException(
            status_code=403, detail="Not enough permissions. Superadmin role required."
        )
    return current_admin


@router.post("/packages/", response_model=schemas.TestPackage)
def create_new_test_package(
    package: schemas.TestPackageCreate,
    db: Session = Depends(get_db),
    # current_admin: models.AdminUser = Depends(get_current_superadmin)
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
    
):
    try:
        return crud.create_test_package(db=db, package=package, owner_id=current_admin.id, current_admin=current_admin)
    except IntegrityError:
        db.rollback() # Penting untuk membatalkan transaksi yang gagal
        raise HTTPException(
            status_code=400,
            detail="Access code already exists."
        )



@router.get("/packages/", response_model=schemas.TestPackageListResponse)
def read_all_test_packages(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # Panggil fungsi yang sudah diperbarui dengan current_admin
    packages = crud.get_test_packages(db, current_admin=current_admin, skip=skip, limit=limit)
    
    # Anda juga perlu fungsi count yang terfilter
    total_count = crud.get_test_packages_count(db, current_admin=current_admin) # Asumsi Anda punya fungsi ini

    return {"total_count": total_count, "packages": packages}


@router.get("/packages/{package_id}", response_model=schemas.TestPackage)
def read_single_test_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # Cukup panggil fungsi CRUD untuk mendapatkan data
    db_package = crud.get_test_package_by_id(db, package_id=package_id)
    if db_package is None:
        raise HTTPException(status_code=404, detail="Test Package not found")
    
    # Kembalikan objeknya. Pydantic akan mengurus konversi ke JSON,
    # termasuk memanggil @property 'tests'
    return db_package




@router.get("/tests/master-list", response_model=schemas.MasterTestListResponse)
def get_master_test_list(
    skip: int = 0,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    tests = db.query(models.Test).order_by(models.Test.id).offset(skip).limit(limit).all()
    total_count = crud.get_master_tests_count(db)
    return {"total_count": total_count, "tests": tests}


@router.post("/packages/{package_id}/tests/{test_id}", response_model=schemas.TestPackage)
def add_a_test_to_a_package(
    package_id: int,
    test_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Menambahkan sebuah tes ke dalam sebuah paket tes."""
    updated_package = crud.add_test_to_package(db, package_id=package_id, test_id=test_id)
    if updated_package is None:
        raise HTTPException(status_code=404, detail="Package or Test not found")
    return updated_package



@router.get("/tests/{test_id}/questions", response_model=List[schemas.Question])
def read_questions_for_a_test(
    test_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Membaca SEMUA pertanyaan untuk sebuah tes (termasuk contoh)."""
    # Kita gunakan fungsi yang sudah ada, tapi panggilannya dari admin router
    return crud.get_all_questions_for_test_admin(db, test_id=test_id)

@router.post("/tests/{test_id}/questions", response_model=schemas.Question)
def create_a_question_for_a_test(
    test_id: int,
    question: schemas.QuestionCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Membuat pertanyaan baru beserta pilihan jawabannya untuk sebuah tes."""
    return crud.create_question_for_test(db, test_id=test_id, question=question)



@router.post("/tests/", response_model=schemas.Test)
def create_new_master_test(
    test: schemas.TestCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.create_master_test(db=db, test=test)

@router.put("/tests/{test_id}", response_model=schemas.Test)
def update_a_master_test(
    test_id: int,
    test: schemas.TestUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_test = crud.update_master_test(db=db, test_id=test_id, test=test)
    if updated_test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    return updated_test


# Di dalam admin_router.py

# Di dalam backend/admin_router.py

@router.get("/participants/", response_model=schemas.ParticipantListResponse)
def read_all_participants(
    skip: int = 0, 
    limit: int = 10,
    start_date: Optional[date] = None, # <-- Parameter baru
    end_date: Optional[date] = None,   # <-- Parameter baru
    search: Optional[str] = None,
    package_id: Optional[int] = None,
    overall_status: Optional[str] = None, 
    result_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengambil daftar peserta dengan filter, hak akses, dan data status yang lengkap."""

    # 1. Panggil fungsi CRUD untuk mendapatkan data mentah dan total hitungan
    participants_data, total_count = crud.get_all_participants(
        db=db, 
        current_admin=current_admin,
        start_date=start_date, # <-- Teruskan ke CRUD
        end_date=end_date,     # <-- Teruskan ke CRUD
        overall_status=overall_status,
        result_type=result_type,
        skip=skip, 
        limit=limit, 
        search=search, 
        package_id=package_id
    )

    # 2. Siapkan list kosong untuk menampung hasil yang sudah diformat
    formatted_participants = []

    # 3. Lakukan loop pada setiap peserta untuk memformat dan menambahkan data status
    for p in participants_data:
        # Tentukan status pengerjaan keseluruhan
        total_sessions = len(p.sessions)
        completed_sessions = sum(1 for s in p.sessions if s.status == 'completed')
        
        overall_status = "Baru" # Default untuk peserta yang belum pernah memulai tes
        if total_sessions > 0:
            if completed_sessions == total_sessions:
                overall_status = "Selesai"
            elif completed_sessions > 0 or any(s.status == 'in_progress' for s in p.sessions):
                overall_status = "Sedang Mengerjakan"
        
        # Ambil data hasil (laporan) jika ada
        result = p.results[0] if p.results else None
        
        # Buat objek Pydantic yang lengkap dan tambahkan ke list
        formatted_participants.append(schemas.ParticipantResult(
            id=p.id, 
            name=p.name, 
            test_number=p.test_number, 
            registration_number=p.registration_number, 
            birth_date=p.birth_date, 
            job=p.job, 
            address=p.address,
            sim_type=p.sim_type,
            sim_status=p.sim_status,
            test_location=p.test_location,
            created_at=p.created_at, 
            package_name=p.package.name if p.package else "N/A",
            
            # Kirim data status baru yang sudah dihitung
            overall_status=overall_status,
            conclusion=result.overall_score if result else "Belum Diproses",
            setu_status=result.setu_status if result else "Belum Dikirim"
        ))

    # 4. Kembalikan respons akhir
    return {"total_count": total_count, "participants": formatted_participants}

# Di dalam backend/admin_router.py

@router.get("/participants/{participant_id}", response_model=schemas.ParticipantDetail)
def read_participant_details(
    participant_id: int, db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # crud.get_participant_details sudah memuat semua relasi yang kita butuhkan (sessions, results)
    participant = crud.get_participant_details(db, participant_id=participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    # Format sesi agar sesuai (tidak berubah)
    sessions_status = [
        schemas.TestStatus(id=s.test.id, name=s.test.name, status=s.status, score=s.score)
        for s in participant.sessions
    ]

    # ====================================================================
    # --- TAMBAHKAN LOGIKA UNTUK MENGHITUNG STATUS & HASIL DI SINI ---
    # ====================================================================

    # Tentukan status pengerjaan keseluruhan (logika yang sama seperti di read_all_participants)
    total_sessions = len(participant.sessions)
    completed_sessions = sum(1 for s in participant.sessions if s.status == 'completed')
    overall_status = "Baru"
    if total_sessions > 0:
        if completed_sessions == total_sessions:
            overall_status = "Selesai"
        elif completed_sessions > 0 or any(s.status == 'in_progress' for s in participant.sessions):
            overall_status = "Sedang Mengerjakan"

    # Ambil data hasil (laporan) jika ada
    result = participant.results[0] if participant.results else None

    # ====================================================================
    
    # Pydantic akan mengonversi 'participant' ke skema,
    # kita tidak perlu mengubah baris return ini.
    return schemas.ParticipantDetail(
        id=participant.id, 
        name=participant.name, 
        birth_date=participant.birth_date, 
        test_number=participant.test_number, 
        registration_number = participant.registration_number, 
        job = participant.job, 
        address = participant.address,
        sim_type=participant.sim_type,
        sim_status=participant.sim_status,
        test_location=participant.test_location,
        created_at=participant.created_at, 
        package_name=participant.package.name if participant.package else "N/A",
        sessions=sessions_status,

        # --- SERTAKAN NILAI-NILAI BARU DI SINI ---
        overall_status=overall_status,
        conclusion=result.overall_score if result else "Belum Diproses",
        setu_status=result.setu_status if result else "Belum Dikirim"
    )


@router.get("/participants/{participant_id}/download-answers")
def download_participant_answers(
    participant_id: int, db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    participant = crud.get_participant_details(db, participant_id=participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    answers = crud.get_participant_answers_for_export(db, participant_id=participant_id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # --- PERUBAHAN UTAMA DI SINI ---
    # Tulis header baru
    writer.writerow(["No", "Kode", "Jawaban", "Isi Jawaban"])
    
    # Tulis data jawaban dengan format baru
    for index, answer in enumerate(answers):
        no = index + 1
        kode = answer.question_id
        jawaban_huruf = ""
        isi_jawaban = ""

        if answer.selected_answer: # Jika ini jawaban pilihan ganda
            parts = answer.selected_answer.split('. ', 1)
            if len(parts) == 2:
                jawaban_huruf = parts[0]
                isi_jawaban = parts[1]
            else:
                isi_jawaban = answer.selected_answer
        elif answer.answer_text: # Jika ini jawaban essay
            jawaban_huruf = "" # Atau "ESSAY"
            isi_jawaban = answer.answer_text

        writer.writerow([no, kode, jawaban_huruf, isi_jawaban])
    # ---------------------------------
        
    output.seek(0)
    
    headers = {
        "Content-Disposition": f"attachment; filename={participant.name}_{participant.test_number}.csv"
    }
    
    return StreamingResponse(output, headers=headers, media_type="text/csv")


@router.get("/participants/{participant_id}/tests/{test_id}/download")
def download_answers_per_test(
    participant_id: int, test_id: int, db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    participant = crud.get_participant_details(db, participant_id=participant_id)
    test = crud.get_master_test(db, test_id=test_id)
    if not participant or not test:
        raise HTTPException(status_code=404, detail="Participant or Test not found")

    answers = crud.get_participant_answers_for_test_export(db, participant_id, test_id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # --- PERUBAHAN UTAMA DI SINI ---
    writer.writerow(["No", "Kode", "Jawaban", "Isi Jawaban"])
    
    for index, answer in enumerate(answers):
        no = answer.question_order
        # no = index + 1
        kode = answer.question_id
        jawaban_huruf = ""
        isi_jawaban = ""

        if answer.selected_answer:
            parts = answer.selected_answer.split('. ', 1)
            if len(parts) == 2:
                jawaban_huruf = parts[0]
                isi_jawaban = parts[1]
            else:
                isi_jawaban = answer.selected_answer
        elif answer.answer_text:
            isi_jawaban = answer.answer_text

        writer.writerow([no, kode, jawaban_huruf, isi_jawaban])
    # ---------------------------------

    output.seek(0)
    
    # Nama file yang lebih sesuai
    safe_test_name = test.name.replace(' ', '_')
    headers = {
        "Content-Disposition": f"attachment; filename={participant.name}_{safe_test_name}.csv"
    }
    return StreamingResponse(output, headers=headers, media_type="text/csv")
#periksa admin_router.py nya

@router.get("/tests/{test_id}/preview", response_model=schemas.TestPreviewResponse)
def get_test_preview(
    test_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    preview_data = crud.get_test_preview_data(db, test_id=test_id)
    if not preview_data or not preview_data["test"]:
        raise HTTPException(status_code=404, detail="Test not found.")
    
    test = preview_data["test"]
    return schemas.TestPreviewResponse(
        id=test.id,
        name=test.name,
        description=test.description,
        duration_minutes=test.duration_minutes,
        memorization_duration_seconds=test.memorization_duration_seconds,
        stimulus_text=test.stimulus_text,
        stimulus_image_url=test.stimulus_image_url,
        example_question=preview_data["example_question"]
    )


@router.delete("/questions/{question_id}", status_code=204)
def delete_a_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    success = crud.delete_question(db, question_id=question_id)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return None # Return None untuk 204 No Content


@router.put("/tests/{test_id}/toggle-active", response_model=schemas.Test)
def toggle_a_master_test_active(
    test_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_test = crud.toggle_master_test_active(db, test_id=test_id)
    if updated_test is None:
        raise HTTPException(status_code=404, detail="Test not found")
    return updated_test


@router.put("/questions/{question_id}", response_model=schemas.Question)
def update_a_question(
    question_id: int,
    question: schemas.QuestionUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_question = crud.update_question(db, question_id=question_id, question_data=question)
    if updated_question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return updated_question


@router.put("/participants/{participant_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_a_participant(
    participant_id: int, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    success = crud.deactivate_participant(db, participant_id=participant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return None


@router.post("/upload-image")
def upload_question_image(
    file: UploadFile = File(...),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # Tentukan direktori penyimpanan
    UPLOAD_DIRECTORY = Path("static/images")
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True) # Buat direktori jika belum ada

    # Buat nama file yang aman (misal, menggunakan timestamp + nama asli)
    # Ini mencegah tumpang tindih nama file
    timestamp = int(datetime.now().timestamp())
    safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
    
    file_path = UPLOAD_DIRECTORY / safe_filename
    
    # Simpan file ke disk
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()
        
    # Kembalikan URL publik yang bisa diakses oleh frontend
    public_url = f"/{UPLOAD_DIRECTORY}/{safe_filename}"
    
    return {"file_url": public_url}


@router.post("/participants/{participant_id}/generate-report", response_model=schemas.TestResult)
def generate_a_participant_report(
    participant_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Menganalisis hasil tes peserta dan menyimpan laporannya."""
    report = crud.generate_participant_report(db, participant_id=participant_id)
    
    # --- LOGIKA PENANGANAN ERROR YANG BENAR ---
    if isinstance(report, dict) and "error" in report:
        # Kasus ini terjadi jika crud mengembalikan dict error
        raise HTTPException(status_code=400, detail=report["error"])
    elif report is None:
        # Kasus ini terjadi jika participant tidak ditemukan
        raise HTTPException(status_code=404, detail="Participant not found")
    
    # Jika 'report' adalah objek TestResult, maka berhasil
    return report


# Di dalam admin_router.py
@router.put("/results/{result_id}/notes", response_model=schemas.TestResult)
def update_psychologist_notes(
    result_id: int,
    payload: schemas.PsychologistNotesUpdate, # <-- Baris yang tadi error
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # Panggil fungsi CRUD
    updated_result = crud.save_psychologist_notes(db, result_id=result_id, notes=payload.notes)
    if not updated_result:
        raise HTTPException(status_code=404, detail="Test Result not found")
    return updated_result



# ...
@router.get("/tests/{test_id}/interpretation-rules", response_model=List[schemas.InterpretationRule])
#def read_interpretation_rules_for_test(
#    test_id: int,
#    db: Session = Depends(get_db),
#    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
#):
#    return crud.get_rules_for_test(db, test_id=test_id)

@router.get("/sub-aspects/{sub_aspect_id}/interpretation-rules", response_model=List[schemas.InterpretationRule])
def read_interpretation_rules_for_sub_aspect(
    sub_aspect_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.get_rules_for_sub_aspect(db, sub_aspect_id=sub_aspect_id)


@router.post("/interpretation-rules/", response_model=schemas.InterpretationRule)
def create_new_interpretation_rule(
    rule: schemas.InterpretationRuleCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.create_interpretation_rule(db, rule=rule)

@router.delete("/interpretation-rules/{rule_id}", status_code=204)
def delete_an_interpretation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    success = crud.delete_interpretation_rule(db, rule_id=rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Interpretation rule not found")
    return None

# Endpoint untuk Aspek dan Sub-Aspek
@router.get("/aspects/", response_model=List[schemas.Aspect])
def read_all_aspects(db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_active_admin_user)):
    return crud.get_all_aspects(db)

# GET Aspek berdasarkan Template
@router.get("/templates/{template_id}/aspects/", response_model=List[schemas.Aspect])
def read_aspects_for_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.get_aspects_for_template(db, template_id=template_id)

# POST Aspek ke Template
@router.post("/templates/{template_id}/aspects/", response_model=schemas.Aspect)
def create_new_aspect_for_template(
    template_id: int,
    aspect: schemas.AspectCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.create_aspect(db, aspect=aspect, template_id=template_id)

# DELETE Aspek
@router.delete("/aspects/{aspect_id}", status_code=204)
def delete_an_aspect(
    aspect_id: int, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    crud.delete_aspect(db, aspect_id=aspect_id)
    return None


@router.post("/sub-aspects/", response_model=schemas.SubAspect)
def create_new_sub_aspect(sub_aspect: schemas.SubAspectCreate, db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_active_admin_user)):
    return crud.create_sub_aspect(db, sub_aspect=sub_aspect)


# --- CARI ENDPOINT INI ---
@router.get("/sub-aspects/", response_model=List[schemas.SubAspect])
def read_all_sub_aspects( # Nama endpoint ini sekarang membingungkan, sebaiknya diganti
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    # --- UBAH PEMANGGILAN INI ---
    # return crud.get_all_sub_aspects(db) --> SALAH
    return crud.get_all_master_sub_aspects(db) # --> BENAR
    
@router.delete("/sub-aspects/{sub_aspect_id}", status_code=204)
def delete_a_sub_aspect(sub_aspect_id: int, db: Session = Depends(get_db), current_admin: models.AdminUser = Depends(get_current_active_admin_user)):
    crud.delete_sub_aspect(db, sub_aspect_id=sub_aspect_id)
    return None


# Endpoint untuk Template Psikogram
@router.post("/psychogram-templates/", response_model=schemas.PsychogramTemplate)
def create_new_psychogram_template(
    template: schemas.PsychogramTemplateCreate, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.create_psychogram_template(db, template=template)



@router.get("/psychogram-templates/", response_model=List[schemas.PsychogramTemplate])
def read_all_psychogram_templates(
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.get_all_psychogram_templates(db)

@router.put("/packages/{package_id}", response_model=schemas.TestPackage)
def update_a_test_package(
    package_id: int, 
    package: schemas.TestPackageUpdate, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_package = crud.update_test_package(db, package_id=package_id, package_data=package)
    if not updated_package:
        raise HTTPException(status_code=404, detail="Test Package not found")
    return updated_package


@router.post("/sub-aspects/{sub_aspect_id}/tests/{test_id}", response_model=schemas.SubAspect)
def add_test_association_to_sub_aspect(
    sub_aspect_id: int, test_id: int, db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.associate_test_to_sub_aspect(db, sub_aspect_id, test_id)

@router.delete("/sub-aspects/{sub_aspect_id}/tests/{test_id}", response_model=schemas.SubAspect)
def remove_test_association_from_sub_aspect(
    sub_aspect_id: int, test_id: int, db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    return crud.disassociate_test_from_sub_aspect(db, sub_aspect_id, test_id)


@router.get("/sub-aspects/{sub_aspect_id}", response_model=schemas.SubAspect)
def read_single_sub_aspect(
    sub_aspect_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    db_sub_aspect = crud.get_sub_aspect_by_id(db, sub_aspect_id=sub_aspect_id)
    if db_sub_aspect is None:
        raise HTTPException(status_code=404, detail="Sub-Aspect not found")
    return db_sub_aspect


@router.put("/packages/{package_id}/test-order", response_model=schemas.TestPackage)
def update_test_order(
    package_id: int,
    payload: schemas.TestOrderUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_package = crud.update_test_order_in_package(db, package_id, payload.test_ids)
    if not updated_package:
        raise HTTPException(status_code=404, detail="Package not found")
    return updated_package


@router.get("/me", response_model=schemas.AdminProfile)
def read_users_me(current_admin: models.AdminUser = Depends(get_current_active_admin_user)):
    """Mengambil profil admin yang sedang login."""
    return current_admin

@router.put("/me", response_model=schemas.AdminProfile)
def update_users_me(
    profile_data: schemas.AdminProfileUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengupdate profil admin yang sedang login."""
    update_data = profile_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(current_admin, key, value)
    db.commit()
    db.refresh(current_admin)
    return current_admin


@router.get("/users/", response_model=List[schemas.AdminProfile])
def read_all_admin_users(
    db: Session = Depends(get_db),
    current_superadmin: models.AdminUser = Depends(get_current_superadmin)
):
    """Hanya Superadmin: Mengambil daftar semua admin."""
    return crud.get_all_admins(db)

@router.post("/users/", response_model=schemas.AdminProfile)
def create_new_admin_user(
    admin_data: schemas.AdminUserCreate,
    db: Session = Depends(get_db),
    current_superadmin: models.AdminUser = Depends(get_current_superadmin)
):
    """Hanya Superadmin: Membuat admin/psikolog baru."""
    db_admin = crud.create_admin_user(db, admin=admin_data)
    if db_admin is None:
        raise HTTPException(status_code=400, detail="Email already registered")
    return db_admin


@router.get(
    "/participants/{participant_id}/report",
    response_model=schemas.TestResult,
    tags=["Admin - Results & Reports"]
)
def get_participant_report_admin(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: models.AdminUser = Depends(get_current_active_admin_user)
):
    """
    Mengambil laporan hasil tes yang sudah ada untuk seorang peserta.
    Jika laporan belum dibuat, akan mengembalikan 404 Not Found.
    """
    report = crud.get_participant_report_by_id(db, participant_id=participant_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Laporan untuk peserta ini belum dibuat."
        )
    return report

@router.put("/results/{result_id}", response_model=schemas.TestResult, tags=["Admin - Results & Reports"])
def manually_update_report(
    result_id: int,
    payload: schemas.ReportUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """
    Endpoint untuk admin/psikolog mengubah kategori sub-aspek dan kesimpulan
    pada laporan yang sudah ada.
    """
    updated_report = crud.update_report_manual(db, result_id=result_id, report_data=payload)
    if not updated_report:
        raise HTTPException(status_code=404, detail="Test Result not found")
    
    return updated_report

@router.put("/results/{result_id}/full-update", response_model=schemas.TestResult, tags=["Admin - Results & Reports"])
def full_update_report(
    result_id: int,
    payload: schemas.ReportFullUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """
    Endpoint untuk menyimpan semua isian draft narasi laporan.
    """
    updated_report = crud.update_report_full_manual(db, result_id=result_id, report_data=payload)
    if not updated_report:
        raise HTTPException(status_code=404, detail="Test Result not found")
    return updated_report


@router.post("/gerai/", response_model=schemas.Gerai, tags=["Admin - Gerai"])
def create_new_gerai(
    gerai_data: schemas.GeraiCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user) # Nanti bisa diperketat ke superadmin
):
    """Membuat gerai baru."""
    existing_gerai = crud.get_gerai_by_name(db, name=gerai_data.name)
    if existing_gerai:
        raise HTTPException(status_code=400, detail="Nama gerai sudah terdaftar.")
    return crud.create_gerai(db, gerai=gerai_data)

# Di dalam backend/admin_router.py

@router.get("/gerai/", response_model=List[schemas.Gerai], tags=["Admin - Gerai"])
def read_all_gerai(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """
    Mengambil daftar gerai berdasarkan hak akses admin.
    - Superadmin/Psikolog: Mendapatkan semua gerai.
    - Admin Gerai: Hanya mendapatkan gerai miliknya sendiri.
    """
    # --- LOGIKA HAK AKSES BARU ---
    
    # Jika admin terikat pada gerai tertentu, hanya kembalikan gerai itu
    if current_admin.gerai_id:
        gerai = crud.get_gerai(db, gerai_id=current_admin.gerai_id)
        if not gerai:
            # Kasus aneh jika gerai admin sudah dihapus, kembalikan list kosong
            return []
        return [gerai] # Kembalikan sebagai list berisi satu item

    # Jika tidak (berarti superadmin atau psikolog), kembalikan semua gerai
    else:
        return crud.get_all_gerai(db)

@router.put("/gerai/{gerai_id}", response_model=schemas.Gerai, tags=["Admin - Gerai"])
def update_a_gerai(
    gerai_id: int,
    gerai_data: schemas.GeraiCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Memperbarui data sebuah gerai."""
    updated_gerai = crud.update_gerai(db, gerai_id=gerai_id, gerai_data=gerai_data)
    if not updated_gerai:
        raise HTTPException(status_code=404, detail="Gerai tidak ditemukan.")
    return updated_gerai

@router.delete("/gerai/{gerai_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin - Gerai"])
def delete_a_gerai(
    gerai_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Menghapus sebuah gerai."""
    success = crud.delete_gerai(db, gerai_id=gerai_id)
    if not success:
        raise HTTPException(status_code=404, detail="Gerai tidak ditemukan.")
    return None # Return None untuk status 204

# backend/admin_router.py



# Di dalam admin_router.py

# Pastikan dependensi ini sudah diimpor di bagian atas file

@router.get("/master-sub-aspects/", response_model=List[schemas.SubAspect], tags=["Admin - Psychogram"])
def read_all_master_sub_aspects(
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user) # <-- PERBAIKAN
):
    return crud.get_all_master_sub_aspects(db)

@router.post("/master-sub-aspects/", response_model=schemas.SubAspect, tags=["Admin - Psychogram"])
def create_new_master_sub_aspect(
    sub_aspect: schemas.SubAspectCreateMaster, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user) # <-- PERBAIKAN
):
    # Tambahkan pengecekan duplikasi
    existing = db.query(models.SubAspect).filter(models.SubAspect.name == sub_aspect.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama master sub-aspek sudah ada.")
    return crud.create_master_sub_aspect(db, sub_aspect)

@router.post("/aspects/{aspect_id}/sub-aspects/{sub_aspect_id}", response_model=schemas.Aspect, tags=["Admin - Psychogram"])
def add_sub_aspect_to_aspect(
    aspect_id: int, 
    sub_aspect_id: int, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user) # <-- PERBAIKAN
):
    return crud.associate_sub_aspect_to_aspect(db, aspect_id, sub_aspect_id)

@router.delete("/aspects/{aspect_id}/sub-aspects/{sub_aspect_id}", response_model=schemas.Aspect, tags=["Admin - Psychogram"])
def remove_sub_aspect_from_aspect(
    aspect_id: int, 
    sub_aspect_id: int, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user) # <-- PERBAIKAN
):
    return crud.disassociate_sub_aspect_from_aspect(db, aspect_id, sub_aspect_id)


# Di dalam backend/admin_router.py

@router.patch("/results/{result_id}/type", response_model=schemas.TestResult, tags=["Admin - Results & Reports"])
def change_report_type(
    result_id: int,
    payload: schemas.ReportTypeUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengubah status laporan antara 'automatic' dan 'manual' (VIP)."""
    updated_report = crud.update_report_result_type(db, result_id=result_id, result_type=payload.result_type)
    if not updated_report:
        raise HTTPException(status_code=404, detail="Test Result not found.")
    return updated_report



# Di dalam admin_router.py

@router.post("/participants/{participant_id}/send-to-setu", tags=["Admin - Integrations"])
def send_participant_data_to_setu(
    participant_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengirim data laporan peserta ke API SETU dan mencatat statusnya."""
    
    participant = crud.get_participant_details(db, participant_id=participant_id)
    report = crud.get_participant_report_by_id(db, participant_id=participant_id)

    if not participant or not report:
        raise HTTPException(status_code=404, detail="Data peserta atau laporan tidak ditemukan.")

    payload = crud.format_report_for_setu(participant, report)
    if not payload:
        raise HTTPException(status_code=400, detail="Gagal memformat data laporan.")

    # ==========================================================
    # --- PERBAIKAN UTAMA DI SINI ---
    # Tangkap kedua nilai yang dikembalikan ke dalam 'success' dan 'message'
    # ==========================================================
    success, message = external_apis.send_data_to_setu([payload])
    
    # Update status di database dengan 'message' yang sudah ditangkap
    crud.update_test_result_setu_status(db, result_id=report.id, status=message)
    
    if not success:
        # Kirim pesan error yang lebih spesifik ke frontend
        raise HTTPException(status_code=502, detail=f"Gagal mengirim ke SETU: {message}")
        
    return {"status": True, "message": f"Data berhasil dikirim. Status: {message}"}

@router.get("/participants/download/csv", tags=["Admin - Participants"]) # <-- PATH BARU
def download_participants_as_csv( # <-- NAMA FUNGSI BARU
    search: Optional[str] = None,
    package_id: Optional[int] = None, # <-- Kembalikan ke int
    result_type: Optional[str] = None,
    gerai_id: Optional[int] = None,   # <-- Kembalikan ke int
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengekspor daftar peserta yang difilter ke file CSV."""
    
    # Blok logging kita masih ada untuk verifikasi
    print("\n--- [DEBUG] Masuk ke endpoint /participants/download/csv ---")
    print(f"Parameter diterima:")
    print(f"  - search: {search} (tipe: {type(search)})")
    print(f"  - package_id: {package_id} (tipe: {type(package_id)})")
    print(f"  - result_type: {result_type} (tipe: {type(result_type)})")
    print(f"  - gerai_id: {gerai_id} (tipe: {type(gerai_id)})")
    print("----------------------------------------------------------\n")

    try:
        participants_to_export = crud.get_participants_for_export(
            db=db, 
            current_admin=current_admin, 
            result_type=result_type, 
            search=search, 
            package_id=package_id, # Langsung gunakan nilai int
            gerai_id=gerai_id # Langsung gunakan nilai int
        )

        output = io.StringIO()
        writer = csv.writer(output)
        

        writer.writerow([
            "ID Peserta", "Nama Peserta", "NIK", "Tanggal Lahir", "Pekerjaan", "Alamat",
            "No Handphone", "Tanggal Tes", "Paket Tes", "Gerai", "Kesimpulan", "Jalur Hasil"
        ])

        for p in participants_to_export:
            has_result = p.results and len(p.results) > 0
            
            writer.writerow([
                p.id,
                p.name,
                p.test_number,
                p.birth_date,
                p.job,
                p.address,
                p.registration_number,
                p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                p.package.name if p.package else "N/A",
                p.package.gerai.name if p.package and p.package.gerai else "N/A",
                
                # Gunakan 'has_result' untuk pengecekan yang aman
                p.results[0].overall_score if has_result else "Belum Diproses",
                p.results[0].result_type if has_result else "automatic"
            ])
            # ------------------------------------
            
        output.seek(0)

        filename = "export_peserta.csv"
        headers = {"Content-Disposition": f"attachment; filename={filename}"}
        
        return StreamingResponse(output, headers=headers, media_type="text/csv")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Terjadi error internal saat mencoba mengekspor data.")


# backend/admin_router.py

@router.get("/templates/{template_id}/test-associations", response_model=List[schemas.TestAssociation], tags=["Admin - Psychogram"])
def read_test_associations(
    template_id: int, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Mengambil semua asosiasi tes untuk sebuah template psikogram."""
    return crud.get_associations_for_template(db, template_id=template_id)

@router.post("/templates/{template_id}/test-associations", response_model=schemas.TestAssociation, tags=["Admin - Psychogram"])
def create_test_association(
    template_id: int, 
    payload: schemas.TestAssociationCreate, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Menghubungkan sebuah Master Tes ke sebuah Sub-Aspek di dalam konteks Template ini."""
    return crud.add_test_association_to_template(db, template_id, payload.sub_aspect_id, payload.test_id)

@router.delete("/templates/{template_id}/sub-aspects/{sub_aspect_id}/tests/{test_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Admin - Psychogram"])
def delete_test_association(
    template_id: int,
    sub_aspect_id: int,
    test_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    """Memutuskan hubungan sebuah tes dari sebuah sub-aspek di dalam konteks Template ini."""
    success = crud.remove_test_association_from_template(db, template_id, sub_aspect_id, test_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asosiasi tidak ditemukan.")

@router.delete("/interpretation-rules/{rule_id}")
def delete_interpretation_rule(rule_id: int, db: Session = Depends(get_db)):
    # Asumsikan crud.delete_interpretation_rule ada, jika tidak, kita bisa implementasi
    # Placeholder:
    rule = db.query(models.InterpretationRule).filter(models.InterpretationRule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return {"message": "Aturan berhasil dihapus"}
    raise HTTPException(status_code=404, detail="Aturan tidak ditemukan")

# ==========================================
# ENDPOINTS NORM TABLE & SCORING MAPPING
# ==========================================

@router.get("/norm-tables", response_model=List[schemas.NormTable])
def get_norm_tables(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_norm_tables(db, skip=skip, limit=limit)

@router.post("/norm-tables", response_model=schemas.NormTable)
def create_norm_table(norm_table: schemas.NormTableCreate, db: Session = Depends(get_db)):
    return crud.create_norm_table(db, norm_table=norm_table)

@router.get("/norm-tables/{table_id}", response_model=schemas.NormTable)
def get_norm_table(table_id: int, db: Session = Depends(get_db)):
    table = crud.get_norm_table(db, norm_table_id=table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Norm table not found")
    return table

@router.put("/norm-tables/{table_id}", response_model=schemas.NormTable)
def update_norm_table(table_id: int, norm_table: schemas.NormTableUpdate, db: Session = Depends(get_db)):
    return crud.update_norm_table(db, norm_table_id=table_id, norm_table=norm_table)

@router.delete("/norm-tables/{table_id}")
def delete_norm_table(table_id: int, db: Session = Depends(get_db)):
    crud.delete_norm_table(db, norm_table_id=table_id)
    return {"message": "Norm table deleted successfully"}

@router.post("/norm-tables/{table_id}/data", response_model=schemas.NormData)
def add_norm_data(table_id: int, data: schemas.NormDataCreate, db: Session = Depends(get_db)):
    return crud.add_norm_data(db, norm_table_id=table_id, data=data)

@router.delete("/norm-data/{data_id}")
def delete_norm_data(
    data_id: int, 
    db: Session = Depends(database.get_db),
    admin_user: models.AdminUser = Depends(auth.get_current_admin_user)
):
    crud.delete_norm_data(db=db, data_id=data_id)
    return {"message": "Norm data deleted successfully"}

@router.put("/norm-data/{data_id}", response_model=schemas.NormData)
def update_norm_data(
    data_id: int,
    norm_data: schemas.NormDataUpdate,
    db: Session = Depends(database.get_db),
    admin_user: models.AdminUser = Depends(auth.get_current_admin_user)
):
    db_data = db.query(models.NormData).filter(models.NormData.id == data_id).first()
    if not db_data:
        raise HTTPException(status_code=404, detail="Norm data not found")
        
    db_data.raw_score_min = norm_data.raw_score_min
    db_data.raw_score_max = norm_data.raw_score_max
    db_data.standard_score = norm_data.standard_score
    db_data.category = norm_data.category
    
    db.commit()
    db.refresh(db_data)
    return db_data

@router.get("/psychogram-templates/{template_id}/scoring-mappings", response_model=List[schemas.ScoringMapping])
def get_scoring_mappings(template_id: int, db: Session = Depends(get_db)):
    return crud.get_scoring_mappings(db, template_id=template_id)

@router.post("/scoring-mappings", response_model=schemas.ScoringMapping)
def create_scoring_mapping(mapping: schemas.ScoringMappingCreate, db: Session = Depends(get_db)):
    return crud.create_scoring_mapping(db, mapping=mapping)

@router.delete("/scoring-mappings/{mapping_id}")
def delete_scoring_mapping(mapping_id: int, db: Session = Depends(get_db)):
    crud.delete_scoring_mapping(db, mapping_id=mapping_id)
    return {"message": "Scoring mapping deleted successfully"}

@router.get("/participants/{participant_id}/tests/{test_id}/essay-answers", response_model=List[schemas.EssayAnswerResponse])
def get_essay_answers(
    participant_id: int,
    test_id: int, 
    db: Session = Depends(get_db), 
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    answers = crud.get_essay_answers_by_test(db, participant_id=participant_id, test_id=test_id)
    res = []
    for a in answers:
        res.append(schemas.EssayAnswerResponse(
            id=a.id,
            question_text=a.question.text,
            answer_text=a.answer_text,
            score=a.score,
            options=a.question.options
        ))
    return res

@router.put("/answers/{answer_id}/score", response_model=schemas.EssayAnswerResponse)
def update_essay_score_endpoint(
    answer_id: int, 
    payload: schemas.UpdateEssayScoreRequest, 
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(get_current_active_admin_user)
):
    updated_answer = crud.update_essay_score(db, answer_id=answer_id, new_score=payload.score)
    if not updated_answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    return schemas.EssayAnswerResponse(
        id=updated_answer.id,
        question_text=updated_answer.question.text,
        answer_text=updated_answer.answer_text,
        score=updated_answer.score,
        options=updated_answer.question.options
    )