# backend/participant_router.py (VERSI FINAL BERSIH)

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import json

import crud, models, schemas
from database import get_db

# --- DEPENDENCY OTENTIKASI PESERTA ---
async def get_current_participant(
    authorization: str = Header(..., alias="Authorization"), 
    db: Session = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token = authorization.split(" ")[1]
    participant = crud.get_participant_by_token(db, token=token)
    if not participant:
        raise HTTPException(status_code=401, detail="Invalid session token")
    return participant
# -----------------------------------------------

router = APIRouter(tags=["participant"])

@router.post("/packages/validate", response_model=schemas.PackageValidateResponse)
def validate_test_package(request: schemas.PackageValidateRequest, db: Session = Depends(get_db)):
    db_package = crud.get_package_by_code(db, access_code=request.access_code)
    if not db_package:
        return {"valid": False, "package_name": None}
    return {"valid": True, "package_name": db_package.name}

@router.post("/sessions/create", response_model=schemas.SessionCreateResponse)
def create_session(request: schemas.SessionCreateRequest, db: Session = Depends(get_db)):
    result = crud.create_participant_session(db, request=request)
    if "error" in result:
        if result["error"] == "package_not_found":
            raise HTTPException(status_code=404, detail="Access code is not valid.")
        if result["error"] == "test_number_exists":
            raise HTTPException(status_code=400, detail="Test number already registered.")
    return result["participant"]

@router.post("/sessions/resume", response_model=schemas.SessionCreateResponse)
def resume_session(request: schemas.SessionResumeRequest, db: Session = Depends(get_db)):
    db_package = crud.get_package_by_code(db, access_code=request.access_code)
    if not db_package:
        raise HTTPException(status_code=404, detail="Access code not valid.")
    
    db_participant = crud.get_participant_by_test_number(db, test_package_id=db_package.id, test_number=request.test_number)
    if not db_participant:
        raise HTTPException(status_code=404, detail="Test number not found.")

    db_participant.session_token = str(uuid.uuid4())
    db.commit()
    db.refresh(db_participant)
    return db_participant



#@router.get("/sessions/status", response_model=schemas.SessionStatusResponse)
#def get_session_status(db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
#    test_sessions = crud.get_session_status(db, participant_id=participant.id)
    # Gunakan eager loading atau akses relasi dengan aman
#    test_statuses = [
#        schemas.TestStatus(id=s.test.id, name=s.test.name, status=s.status, score=s.score) 
#        for s in test_sessions if s.test # Pengaman jika relasi test null
#    ]
#    return schemas.SessionStatusResponse(
#        participant_name=participant.name,
#        package_name=participant.package.name,
#        tests=test_statuses
#    )

# GANTI FUNGSI LAMA DENGAN VERSI BARU INI

@router.get("/sessions/status", response_model=schemas.SessionStatusResponse)
def get_session_status(db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    # 1. Ambil semua sesi tes milik peserta
    all_sessions = crud.get_session_status(db, participant_id=participant.id)
    
    # 2. Buat "peta" untuk mencari status & skor dengan cepat berdasarkan test_id
    session_map = {session.test_id: session for session in all_sessions}

    # 3. Ambil daftar tes yang SUDAH TERURUT dari paket tes
    #    Ini akan menggunakan @property tests dan relasi order_by yang sudah kita buat
    ordered_tests = participant.package.tests

    # 4. Bangun daftar status tes DENGAN URUTAN YANG BENAR
    test_statuses = []
    for test in ordered_tests:
        session = session_map.get(test.id)
        if session:
            # Jika sesi ditemukan, gunakan status dan skor dari sesi tersebut
            test_statuses.append(schemas.TestStatus(
                id=test.id, 
                name=test.name, 
                status=session.status, 
                score=session.score
            ))
        else:
            # Fallback jika karena suatu alasan sesi tidak dibuat
            test_statuses.append(schemas.TestStatus(
                id=test.id, 
                name=test.name, 
                status='not_started', 
                score=None
            ))

    return schemas.SessionStatusResponse(
        participant_name=participant.name,
        package_name=participant.package.name,
        tests=test_statuses # Sekarang 'tests' ini sudah dalam urutan yang benar
    )


@router.get("/tests/{test_id}/preview", response_model=schemas.TestPreviewResponse)
def get_test_preview(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    preview_data = crud.get_test_preview_data(db, test_id=test_id)
    if not preview_data or not preview_data["test"]:
        raise HTTPException(status_code=404, detail="Test not found.")
    test = preview_data["test"]
    # Bangun respons secara eksplisit untuk keandalan
    return schemas.TestPreviewResponse(
        id=test.id, name=test.name, description=test.description, duration_minutes=test.duration_minutes,
        memorization_duration_seconds=test.memorization_duration_seconds,
        stimulus_text=test.stimulus_text, stimulus_image_url=test.stimulus_image_url,
        example_question=preview_data["example_question"]
    )

@router.get("/tests/{test_id}/questions", response_model=List[schemas.Question])
def get_test_questions(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    return crud.get_questions_for_test(db, test_id=test_id)

@router.post("/sessions/tests/{test_id}/start", response_model=schemas.StartTimeResponse)
def start_test(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    session = crud.start_test_session(db, participant_id=participant.id, test_id=test_id)
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found or already completed.")
    
    # Bangun respons secara eksplisit
    return {
        "start_time": session.start_time,
        "duration_minutes": session.test.duration_minutes
    }

@router.post("/sessions/submit-answers", response_model=schemas.TestSubmissionResponse)
def submit_answers(submission: schemas.TestSubmissionRequest, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    final_score = crud.save_participant_answers(db, participant_id=participant.id, submission=submission)
    return {"message": "Answers submitted successfully", "score": final_score}

@router.get("/verify", response_model=schemas.VerificationResult)
def verify_participant_result(id: str, db: Session = Depends(get_db)):
    participant = crud.get_participant_by_test_number_public(db, test_number=id)
    if not participant:
        raise HTTPException(status_code=404, detail="Hasil tes dengan nomor ini tidak ditemukan.")
    result = db.query(models.TestResult).filter(models.TestResult.participant_id == participant.id).first()
    return schemas.VerificationResult(
        name=participant.name,
        test_number=participant.test_number,
        package_name=participant.package.name,
        test_date=participant.created_at,
        conclusion=result.overall_score if result else "Belum Dianalisis",
        sim_type=participant.sim_type,
        sim_status=participant.sim_status,
        test_location=participant.test_location
    )

@router.get("/gerai", response_model=List[schemas.Gerai], tags=["Participant - Public"])
def read_public_gerai_list(db: Session = Depends(get_db)):
    """Endpoint publik untuk mengambil daftar semua gerai."""
    return crud.get_all_gerai(db)


@router.get("/sessions/my-report", response_model=schemas.ParticipantReportResponse)
def get_my_report(
    db: Session = Depends(get_db), 
    participant: models.Participant = Depends(get_current_participant)
):
    """
    Endpoint untuk peserta mengambil hasil psikotes mereka.
    Jika hasil belum ada dan semua tes sudah selesai, hasil akan dibuat secara otomatis.
    """
    # Cek 1: Apakah laporan sudah ada di database?
    # Kita gunakan participant.id dari dependency yang sudah pasti ada
    report = crud.get_participant_report_by_id(db, participant_id=participant.id)

    if not report:
        # Laporan belum ada, mari kita cek apakah bisa dibuat.
        # Cek 2: Apakah semua tes yang diperlukan sudah selesai?
        
        required_test_ids = {test.id for test in participant.package.tests}
        
        completed_test_ids = {
            session.test_id for session in participant.sessions 
            if session.status == 'completed'
        }

        if not required_test_ids.issubset(completed_test_ids):
            # Jika belum selesai, kembalikan status pending dengan data lengkap dari 'participant'
            return schemas.ParticipantReportResponse(
                report_status='pending',
                package_name=participant.package.name,
                test_date=participant.created_at,
                participant_name=participant.name,
                participant_test_number=participant.test_number,
                participant_birth_date=participant.birth_date,
                participant_job=participant.job,
                sim_type=participant.sim_type,
                sim_status=participant.sim_status,
                test_location=participant.test_location,
                participant_address=participant.address,       
                psychologist_notes="Harap selesaikan semua tes untuk melihat hasil."
            )
        
        # Jika sudah selesai, buat laporannya
        report = crud.generate_participant_report(db, participant_id=participant.id)
        
        if not report or (isinstance(report, dict) and "error" in report):
            raise HTTPException(
                status_code=500, 
                detail="Gagal membuat laporan. Konfigurasi paket tes mungkin tidak lengkap."
            )

    # --- Bagian ini akan berjalan jika laporan SUDAH ADA atau BARU SAJA DIBUAT ---
    
    # Ambil info psikolog. 'participant' dari dependency sudah memiliki relasi ini.
    psychologist_name = None
    psychologist_sipp = None
    psychologist_city = None
    psychologist_signature_url = None
    if participant.package and participant.package.owner:
        owner = participant.package.owner
        psychologist_name = owner.full_name
        psychologist_sipp = owner.sipp_number
        psychologist_city = owner.city
        psychologist_signature_url = owner.signature_image_url
        
    # Parsing detail laporan dari JSON
    report_details_data = None
    if report.interpretation_summary:
        try:
            parsed_summary = json.loads(report.interpretation_summary)
            if 'aspects' in parsed_summary:
                report_details_data = parsed_summary['aspects']
        except json.JSONDecodeError:
            report_details_data = []

    # Kembalikan respons dengan data lengkap. SEMUA data peserta diambil dari 'participant'.
    return schemas.ParticipantReportResponse(
        report_status='ready',
        package_name=participant.package.name,
        test_date=participant.created_at,
        generated_at=report.generated_at,
        conclusion=report.overall_score,
        psychologist_notes=report.psychologist_notes,
        
        participant_name=participant.name,
        participant_test_number=participant.test_number,
        participant_birth_date=participant.birth_date,
        participant_job=participant.job,
        sim_type=participant.sim_type,
        sim_status=participant.sim_status,
        test_location=participant.test_location,
        participant_address=participant.address,
        
        report_details=report_details_data,
        psychologist_name=psychologist_name,
        psychologist_sipp=psychologist_sipp,
        psychologist_city=psychologist_city,
        psychologist_signature_url=psychologist_signature_url
    )