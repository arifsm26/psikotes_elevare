# backend/crud.py
from sqlalchemy.orm import Session, joinedload # <-- TAMBAHKAN joinedload DI SINI

from sqlalchemy import func
from datetime import datetime, date 
import uuid
import json
from typing import Optional, List
from security import get_password_hash
from sqlalchemy import or_ 
from typing import Dict

import models
import schemas

import io
import csv

# --- Fungsi untuk Peserta ---

def get_package_by_code(db: Session, access_code: str):
    """Mencari TestPackage berdasarkan access_code yang aktif."""
    return db.query(models.TestPackage).filter(
        models.TestPackage.access_code == access_code,
        models.TestPackage.is_active == True
    ).first()


def get_participant_by_token(db: Session, token: str):
    """Mencari Participant berdasarkan session_token."""
    return db.query(models.Participant).filter(models.Participant.session_token == token).first()


def get_participant_by_test_number(db: Session, test_package_id: int, test_number: str):
    """Mencari Participant berdasarkan test_number dalam satu paket tes."""
    return db.query(models.Participant).filter(
        models.Participant.test_package_id == test_package_id,
        models.Participant.test_number == test_number
    ).first()


def get_session_status(db: Session, participant_id: int):
    """Mengambil status semua sesi tes milik seorang peserta."""
    return db.query(models.TestSession).filter(models.TestSession.participant_id == participant_id).all()



# Di dalam backend/crud.py

def create_participant_session(db: Session, request: schemas.SessionCreateRequest):
    """
    Membuat record Participant dan TestSession baru berdasarkan tes dari PAKET TES.
    """
    
    # 1. Validasi paket tes DAN pastikan relasi 'tests' dimuat (eager loading)
    db_package = db.query(models.TestPackage).options(
        joinedload(models.TestPackage.tests_association).joinedload(models.PackageTestAssociation.test)
    ).filter(
        models.TestPackage.access_code == request.access_code,
        models.TestPackage.is_active == True
    ).first()
    
    if not db_package:
        return {"error": "package_not_found"}

    # 2. Cek duplikasi nomor tes
    existing_participant = get_participant_by_test_number(db, test_package_id=db_package.id, test_number=request.test_number)
    if existing_participant:
        return {"error": "test_number_exists"}

    # 3. Ambil daftar tes langsung dari paket yang sudah dimuat
    db.refresh(db_package)
    
    tests_in_package = db_package.tests # Menggunakan @property 'tests'
    print("\n--- [DEBUG] Membuat Sesi untuk Paket:", db_package.name, "---")
    print(f"Total tes yang ditemukan di paket: {len(tests_in_package)}")
    for i, test in enumerate(tests_in_package):
        print(f"  {i+1}. Test ID: {test.id}, Nama: {test.name}")
    print("--------------------------------------------------\n")

    if not tests_in_package:
        return {"error": "package_has_no_tests"}

    if not tests_in_package:
        return {"error": "package_has_no_tests"}

    # 4. Buat Participant baru
    session_token = str(uuid.uuid4())
    db_participant = models.Participant(
        name=request.name,
        test_number=request.test_number,
        birth_date=request.birth_date,
        address=request.address,
        registration_number=request.registration_number,
        job=request.job,
        sim_type=request.sim_type,
        sim_status=request.sim_status,
        test_location=request.test_location,
        test_package_id=db_package.id,
        session_token=session_token
    )
    db.add(db_participant)
    db.commit()
    db.refresh(db_participant)

    # 5. Buat TestSession untuk SETIAP tes yang ada di paket
    for test in tests_in_package:
        # Tambahkan print() untuk debugging
        print(f"--- Membuat TestSession untuk Participant ID: {db_participant.id}, Test ID: {test.id} ({test.name}) ---")
        db_test_session = models.TestSession(participant_id=db_participant.id, test_id=test.id, status='not_started')
        db.add(db_test_session)
    db.commit()

    # Muat ulang participant untuk respons
    reloaded_participant = db.query(models.Participant).options(
         joinedload(models.Participant.package)
         .joinedload(models.TestPackage.tests_association)
         .joinedload(models.PackageTestAssociation.test)
    ).filter(models.Participant.id == db_participant.id).first()
    
    return {"participant": reloaded_participant}


def save_participant_answers(db: Session, participant_id: int, submission: schemas.TestSubmissionRequest):
    """Simpan jawaban peserta dan hitung total skor."""
    total_score = 0

    # Cek status sesi tes
    session = db.query(models.TestSession).filter(
        models.TestSession.participant_id == participant_id,
        models.TestSession.test_id == submission.test_id
    ).first()

    if session and session.status == 'completed':
        return session.score  # Sudah selesai, kembalikan skor lama

    # Simpan jawaban
    for answer in submission.answers:
        if answer.answer_text is not None and not answer.selected_option_ids:
            # Jawaban essay
            
            # --- Auto Scoring Logic for Essay ---
            question = db.query(models.Question).filter(models.Question.id == answer.question_id).first()
            auto_score = 0
            if question and question.question_type in ['essay', 'short_answer']:
                user_text_lower = answer.answer_text.lower()
                best_score = 0
                for opt in question.options:
                    if opt.text:
                        # Dukung pemisahan kata kunci menggunakan koma
                        keywords = [k.strip().lower() for k in opt.text.split(',')]
                        for keyword in keywords:
                            if keyword and keyword in user_text_lower:
                                if opt.score and opt.score > best_score:
                                    best_score = opt.score
                auto_score = best_score
                total_score += auto_score

            db_answer = models.ParticipantAnswer(
                participant_id=participant_id,
                question_id=answer.question_id,
                answer_text=answer.answer_text,
                score=auto_score
            )
            db.add(db_answer)
        else:
            # Cek tipe soal
            question = db.query(models.Question).filter(models.Question.id == answer.question_id).first()
            is_disc = question and question.question_type == 'disc'

            # Jawaban pilihan ganda / disc
            for idx, option_id in enumerate(answer.selected_option_ids):
                # Untuk DISC, simpan status Most/Least di answer_text berdasarkan urutan
                disc_text = None
                if is_disc:
                    disc_text = "most" if idx == 0 else "least"
                    
                db_answer = models.ParticipantAnswer(
                    participant_id=participant_id,
                    question_id=answer.question_id,
                    selected_option_id=option_id,
                    answer_text=disc_text
                )
                db.add(db_answer)

                # Hitung skor dari pilihan
                option = db.query(models.AnswerOption).filter(models.AnswerOption.id == option_id).first()
                if option and option.score:
                    total_score += option.score

    # Update status sesi dan jalankan modular skoring
    if session:
        db.commit() # Simpan semua jawaban ke DB terlebih dahulu

        # Ambil info test dan participant untuk modular skoring
        test = db.query(models.Test).filter(models.Test.id == submission.test_id).first()
        participant = db.query(models.Participant).filter(models.Participant.id == participant_id).first()
        test_package_id = participant.test_package_id if participant else 0

        # Ambil jawaban beserta relasinya dari DB untuk dilempar ke modul skoring
        question_ids = [a.question_id for a in submission.answers]
        saved_answers = db.query(models.ParticipantAnswer).options(
            joinedload(models.ParticipantAnswer.selected_option),
            joinedload(models.ParticipantAnswer.question)
        ).filter(
            models.ParticipantAnswer.participant_id == participant_id,
            models.ParticipantAnswer.question_id.in_(question_ids)
        ).all()

        # Panggil Modular Scoring
        from scoring import get_scorer
        scoring_module = test.scoring_module if test and test.scoring_module else 'default'
        scorer_class = get_scorer(scoring_module)

        if scoring_module != 'default':
            # Jika menggunakan modul khusus (IST, PAPI, dll)
            score_result = scorer_class.calculate_score(
                participant_answers=saved_answers,
                test_package_id=test_package_id,
                participant_id=participant_id,
                db_session=db
            )
            # Anda bisa memproses dictionary 'score_result' di sini 
            # misalnya menyimpan ke kolom-kolom spesifik di TestResult nantinya.
            # Untuk sesi, kita pakai overall_score
            total_score = int(score_result.get("total_correct", total_score))

        # Update Session
        session.status = 'completed'
        session.score = total_score
        db.commit()
        db.refresh(session)

    return total_score


def start_test_session(db: Session, participant_id: int, test_id: int):
    """Memulai sesi tes, mencatat waktu mulai."""
    session = db.query(models.TestSession).filter(
        models.TestSession.participant_id == participant_id,
        models.TestSession.test_id == test_id
    ).first()

    # --- TAMBAHKAN LOGGING DI SINI ---
    print("\n--- [DEBUG] Mencoba memulai sesi tes ---")
    print(f"Mencari TestSession untuk Participant ID: {participant_id} dan Test ID: {test_id}")
    if session:
        print("  -> Sesi DITEMUKAN. Status saat ini:", session.status)
    else:
        print("  -> Sesi TIDAK DITEMUKAN. Mengembalikan None.")
    print("----------------------------------------\n")
    # ------------------------------------

    if not session:
        return None # Ini yang menyebabkan 404

    if session.status == 'not_started':
        session.status = 'in_progress'
        session.start_time = datetime.utcnow()
        db.commit()
        db.refresh(session)

    return session

def get_test_preview_data(db: Session, test_id: int):
    """Ambil detail tes dan contoh soal untuk halaman preview."""
    test = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not test:
        return None

    example_question = db.query(models.Question).filter(
        models.Question.test_id == test_id,
        models.Question.is_example == True
    ).first()

    return {
        "test": test,
        "example_question": example_question
    }


def get_questions_for_test(db: Session, test_id: int):
    """Ambil semua pertanyaan untuk sebuah tes (kecuali contoh)."""
    return db.query(models.Question).filter(
        models.Question.test_id == test_id,
        models.Question.is_example == False
    ).order_by(models.Question.order).all()


# --- Fungsi untuk Admin ---

def get_admin_by_email(db: Session, email: str):
    """Cari AdminUser berdasarkan email."""
    return db.query(models.AdminUser).filter(models.AdminUser.email == email).first()


def get_test_packages(db: Session, current_admin: models.AdminUser, skip: int = 0, limit: int = 100):
    # 1. Mulai dengan query dasar
    query = db.query(models.TestPackage).options(
        joinedload(models.TestPackage.gerai),
        joinedload(models.TestPackage.tests_association).joinedload(models.PackageTestAssociation.test)
    )

    # --- LOGIKA FILTER AKSES BARU YANG LEBIH KETAT ---
    # Prioritas 1: Superadmin bisa melihat semua
    if current_admin.role == 'superadmin':
        pass 
    # Prioritas 2: Jika admin terikat pada gerai, HANYA lihat paket gerai itu.
    elif current_admin.gerai_id:
        query = query.filter(models.TestPackage.gerai_id == current_admin.gerai_id)
    # Prioritas 3: Jika bukan superadmin dan tidak punya gerai (berarti Psikolog),
    # lihat semua paket miliknya dan milik semua bawahannya.
    else:
        owner_ids = [child.id for child in current_admin.children]
        owner_ids.append(current_admin.id)
        query = query.filter(models.TestPackage.owner_id.in_(owner_ids))

    return query.order_by(models.TestPackage.name).offset(skip).limit(limit).all()


def get_test_packages_count(db: Session, current_admin: models.AdminUser):
    """Menghitung total jumlah paket tes BERDASARKAN hak akses admin."""
    
    # 1. Mulai dengan query dasar
    query = db.query(models.TestPackage)

    # 2. Terapkan logika filter akses yang SAMA seperti di get_test_packages
    if current_admin.role == 'superadmin':
        # Superadmin bisa melihat semua
        pass 
    elif current_admin.gerai_id:
        # Jika user adalah admin gerai, hanya lihat paket dari gerai tersebut
        query = query.filter(models.TestPackage.gerai_id == current_admin.gerai_id)
    else:
        # Jika user adalah psikolog (tanpa gerai), lihat semua paket di bawah owner-nya
        owner_ids = [child.id for child in current_admin.children]
        owner_ids.append(current_admin.id)
        query = query.filter(models.TestPackage.owner_id.in_(owner_ids))

    # 3. Kembalikan hasil hitungan dari query yang sudah difilter
    return query.count()


def create_test_package(
    db: Session, 
    package: schemas.TestPackageCreate, 
    owner_id: int, 
    current_admin: models.AdminUser # <-- TAMBAHKAN PARAMETER INI
):
    """Membuat paket tes baru dengan logika penentuan gerai_id."""
    
    gerai_id_to_set = None
    if current_admin.gerai_id:
        # Jika yang membuat adalah Admin Gerai, gerai_id paket = gerai_id admin
        gerai_id_to_set = current_admin.gerai_id
    elif package.gerai_id:
        # Jika yang membuat adalah Psikolog & dia memilih gerai dari dropdown di frontend
        gerai_id_to_set = package.gerai_id

    # Buat objek paket tes dasar
    db_package = models.TestPackage(
        name=package.name,
        access_code=package.access_code,
        is_active=package.is_active,
        psychogram_template_id=package.psychogram_template_id,
        owner_id=owner_id,
        gerai_id=gerai_id_to_set # <-- Simpan gerai_id yang sudah ditentukan
    )
    db.add(db_package)
    db.commit()
    db.refresh(db_package)

    # --- LOGIKA SINKRONISASI DENGAN LOGGING ---
    if db_package.psychogram_template_id:
        print("\n--- [DEBUG] Sinkronisasi CREATE_PACKAGE ---")
        print(f"Template ID dipilih: {db_package.psychogram_template_id}")

        associations = get_associations_for_template(db, template_id=db_package.psychogram_template_id)
        print(f"Ditemukan {len(associations)} asosiasi tes di template.")
        
        unique_tests_from_template = {assoc.test for assoc in associations if assoc.test}
        print(f"Ditemukan {len(unique_tests_from_template)} tes unik untuk ditambahkan.")

        if unique_tests_from_template:
            for index, test in enumerate(unique_tests_from_template):
                print(f"  -> Menambahkan Test ID: {test.id} ke Paket ID: {db_package.id}")
                association = models.PackageTestAssociation(
                    test_package_id=db_package.id,
                    test_id=test.id,
                    test_order=index + 1
                )
                db.add(association)
            db.commit()
        else:
            print("Tidak ada tes untuk disinkronkan.")
        print("-------------------------------------------\n")

    return db_package

# Di dalam backend/crud.py

def get_test_package_by_id(db: Session, package_id: int):
    """Mengambil detail satu paket tes dengan semua relasi yang diperlukan."""
    
    print(f"\n--- [DEBUG] CRUD: Memuat detail untuk Paket ID: {package_id} ---")

    result = db.query(models.TestPackage).options(
        # Eager load relasi-relasi penting
        joinedload(models.TestPackage.psychogram_template),
        joinedload(models.TestPackage.gerai),
        joinedload(models.TestPackage.owner),
        joinedload(models.TestPackage.tests_association).joinedload(models.PackageTestAssociation.test)
    ).filter(models.TestPackage.id == package_id).first()

    if result:
        print(f"  -> Paket ditemukan: {result.name}")
        print(f"  -> Jumlah tes terhubung (dari tests_association): {len(result.tests_association)}")
        # Properti 'tests' akan secara otomatis menggunakan hasil dari 'tests_association'
        print(f"  -> Jumlah tes (dari @property): {len(result.tests)}")
    else:
        print("  -> Paket TIDAK ditemukan.")
    
    print("----------------------------------------------------------\n")
    
    return result

def update_test_package(db: Session, package_id: int, package_data: schemas.TestPackageUpdate):
    db_package = get_test_package_by_id(db, package_id=package_id)
    if not db_package:
        return None

    template_changed = (db_package.psychogram_template_id != package_data.psychogram_template_id)
    
    update_data = package_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_package, key, value)
    
    db.commit()

    if template_changed and package_data.psychogram_template_id:
        db.query(models.PackageTestAssociation).filter(
            models.PackageTestAssociation.test_package_id == package_id
        ).delete(synchronize_session=False)
        db.commit()

        # --- LOGGING YANG SUDAH ADA / DIPERBARUI ---
        print("\n--- [DEBUG] Sinkronisasi UPDATE_PACKAGE ---")
        print(f"Template ID baru: {package_data.psychogram_template_id}")

        associations = get_associations_for_template(db, template_id=package_data.psychogram_template_id)
        print(f"Ditemukan {len(associations)} asosiasi tes di template.")
        
        if associations:
            for i, assoc in enumerate(associations):
                test_name = assoc.test.name if assoc.test else "TEST TIDAK ADA (NULL)"
                print(f"  - Asosiasi {i+1}: SubAspect ID {assoc.sub_aspect_id} -> Test ID {assoc.test_id} ({test_name})")

        unique_tests_from_template = {assoc.test for assoc in associations if assoc.test}
        print(f"Ditemukan {len(unique_tests_from_template)} tes unik untuk ditambahkan.")

        if unique_tests_from_template:
            print("Memulai proses penambahan tes ke paket...")
            for index, test in enumerate(unique_tests_from_template):
                print(f"  -> Menambahkan Test ID: {test.id} ke Paket ID: {package_id}")
                association = models.PackageTestAssociation(
                    test_package_id=package_id,
                    test_id=test.id,
                    test_order=index + 1
                )
                db.add(association)
            db.commit()
            print("Proses penambahan tes selesai.")
        else:
            print("Tidak ada tes unik yang ditemukan, tidak ada yang ditambahkan.")
        
        print("-------------------------------------------\n")

    db.refresh(db_package)
    return db_package

def get_all_master_tests(db: Session):
    return db.query(models.Test).all()


def get_master_test(db: Session, test_id: int):
    return db.query(models.Test).filter(models.Test.id == test_id).first()


def create_master_test(db: Session, test: schemas.TestCreate):
    db_test = models.Test(**test.dict())
    db.add(db_test)
    db.commit()
    db.refresh(db_test)
    return db_test


def update_master_test(db: Session, test_id: int, test: schemas.TestUpdate):
    db_test = get_master_test(db, test_id=test_id)
    if not db_test:
        return None

    update_data = test.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_test, key, value)
    db.commit()
    db.refresh(db_test)
    return db_test


def toggle_master_test_active(db: Session, test_id: int):
    db_test = get_master_test(db, test_id=test_id)
    if db_test:
        db_test.is_active = not db_test.is_active
        db.commit()
        db.refresh(db_test)
    return db_test


def get_master_tests_count(db: Session):
    return db.query(models.Test).count()


# --- Fungsi CRUD untuk Pertanyaan ---

def create_question_for_test(db: Session, test_id: int, question: schemas.QuestionCreate):
    db_question = models.Question(
        test_id=test_id,
        text=question.text,
        order=question.order,
        is_example=question.is_example,
        image_url=question.image_url,
        question_type=question.question_type
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)

    for option_in in question.options:
        db_option = models.AnswerOption(
            question_id=db_question.id,
            **option_in.dict()
        )
        db.add(db_option)

    db.commit()
    db.refresh(db_question)
    return db_question


def update_question(db: Session, question_id: int, question_data: schemas.QuestionUpdate):
    db_question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not db_question:
        return None

    # Update data utama
    update_data = question_data.dict(exclude={"options"})
    for key, value in update_data.items():
        setattr(db_question, key, value)

    # Sinkronisasi opsi jawaban
    if question_data.question_type == 'multiple_choice':
        existing_options = {opt.id: opt for opt in db_question.options}
        incoming_ids = {opt.id for opt in question_data.options if opt.id is not None}

        # Hapus opsi yang tidak ada di input
        for opt_id in existing_options:
            if opt_id not in incoming_ids:
                db.delete(existing_options[opt_id])

        # Tambahkan/Update opsi baru
        for option_in in question_data.options:
            option_dict = option_in.dict()
            if option_in.id is not None:
                db.query(models.AnswerOption).filter(models.AnswerOption.id == option_in.id).update(option_dict)
            else:
                new_option = models.AnswerOption(question_id=question_id, **option_dict)
                db.add(new_option)
    else:  # Essay: hapus semua opsi
        db.query(models.AnswerOption).filter(models.AnswerOption.question_id == question_id).delete()

    db.commit()
    db.refresh(db_question)
    return db_question


def delete_question(db: Session, question_id: int):
    db_question = db.query(models.Question).filter(models.Question.id == question_id).first()
    if not db_question:
        return False

    # Hapus jawaban peserta dan pilihan
    db.query(models.ParticipantAnswer).filter(models.ParticipantAnswer.question_id == question_id).delete(synchronize_session=False)
    db.query(models.AnswerOption).filter(models.AnswerOption.question_id == question_id).delete(synchronize_session=False)
    db.delete(db_question)
    db.commit()
    return True


def get_all_questions_for_test_admin(db: Session, test_id: int):
    """Ambil semua pertanyaan (termasuk contoh) untuk admin."""
    return db.query(models.Question).filter(
        models.Question.test_id == test_id
    ).order_by(models.Question.order).all()


# --- Fungsi CRUD untuk Interpretasi ---

def get_interpretation(db: Session, test_id: int, score: int) -> Optional[models.InterpretationRule]:
    """Cari aturan interpretasi berdasarkan test_id dan skor."""
    if score is None:
        return None
    return db.query(models.InterpretationRule).filter(
        models.InterpretationRule.test_id == test_id,
        models.InterpretationRule.min_score <= score,
        models.InterpretationRule.max_score >= score
    ).first()

def get_interpretation_for_sub_aspect(db: Session, sub_aspect_id: int, score: int):
    return db.query(models.InterpretationRule).filter(
        models.InterpretationRule.sub_aspect_id == sub_aspect_id,
        models.InterpretationRule.min_score <= score,
        models.InterpretationRule.max_score >= score        
# ... (sisa filter min/max score)
    ).first()


# Ganti fungsi lama get_rules_for_test dengan ini
def get_rules_for_sub_aspect(db: Session, sub_aspect_id: int):
    return db.query(models.InterpretationRule).filter(models.InterpretationRule.sub_aspect_id == sub_aspect_id).all()

def create_interpretation_rule(db: Session, rule: schemas.InterpretationRuleCreate):
    db_rule = models.InterpretationRule(**rule.dict())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def update_interpretation_rule(db: Session, rule_id: int, rule_data: schemas.InterpretationRuleCreate):
    db_rule = db.query(models.InterpretationRule).filter(models.InterpretationRule.id == rule_id).first()
    if not db_rule:
        return None

    update_data = rule_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_rule, key, value)
        
    db.commit()
    db.refresh(db_rule)
    return db_rule


def delete_interpretation_rule(db: Session, rule_id: int):
    db_rule = db.query(models.InterpretationRule).filter(models.InterpretationRule.id == rule_id).first()
    if db_rule:
        db.delete(db_rule)
        db.commit()
        return True
    return False

# --- Fungsi CRUD untuk Psikogram ---

def get_all_psychogram_templates(db: Session):
    return db.query(models.PsychogramTemplate).order_by(models.PsychogramTemplate.name).all()


def create_psychogram_template(db: Session, template: schemas.PsychogramTemplateCreate):
    db_template = models.PsychogramTemplate(**template.dict())
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template


def get_all_aspects(db: Session):
    return db.query(models.Aspect).order_by(models.Aspect.order).all()

def get_aspects_for_template(db: Session, template_id: int):
    # 1. Ambil aspek & sub-aspek
    aspects = db.query(models.Aspect).options(
        joinedload(models.Aspect.sub_aspects)
    ).filter(models.Aspect.template_id == template_id).order_by(models.Aspect.order).all()
    
    # 2. Ambil test associations untuk template ini beserta objek Test-nya
    test_assocs = db.query(models.TemplateSubAspectTest).options(
        joinedload(models.TemplateSubAspectTest.test)
    ).filter(models.TemplateSubAspectTest.template_id == template_id).all()
    
    # 3. Kelompokkan tests berdasarkan sub_aspect_id
    tests_by_sub_aspect = {}
    for assoc in test_assocs:
        if assoc.sub_aspect_id not in tests_by_sub_aspect:
            tests_by_sub_aspect[assoc.sub_aspect_id] = []
        tests_by_sub_aspect[assoc.sub_aspect_id].append(assoc.test)
        
    # 4. Inject tests ke dalam objek SubAspect agar bisa dibaca oleh Pydantic (schemas)
    for aspect in aspects:
        for sub in aspect.sub_aspects:
            setattr(sub, 'tests', tests_by_sub_aspect.get(sub.id, []))
            
    return aspects

def create_aspect(db: Session, aspect: schemas.AspectCreate, template_id: int):
    db_aspect = models.Aspect(
        name=aspect.name,
        order=aspect.order,
        template_id=template_id
    )
    db.add(db_aspect)
    db.commit()
    db.refresh(db_aspect)
    return db_aspect


def create_sub_aspect(db: Session, sub_aspect: schemas.SubAspectCreate):
    db_sub_aspect = models.SubAspect(**sub_aspect.dict())
    db.add(db_sub_aspect)
    db.commit()
    db.refresh(db_sub_aspect)
    return db_sub_aspect


def update_sub_aspect(db: Session, sub_aspect_id: int, sub_aspect: schemas.SubAspectUpdate):
    db_sub_aspect = db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()
    if not db_sub_aspect:
        return None

    update_data = sub_aspect.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_sub_aspect, key, value)
    db.commit()
    db.refresh(db_sub_aspect)
    return db_sub_aspect


def delete_aspect(db: Session, aspect_id: int):
    # Hapus sub-aspek terlebih dahulu
    db.query(models.SubAspect).filter(models.SubAspect.aspect_id == aspect_id).delete()
    # Hapus aspek
    db_aspect = db.query(models.Aspect).filter(models.Aspect.id == aspect_id).first()
    if db_aspect:
        db.delete(db_aspect)
        db.commit()
        return True
    return False


def delete_sub_aspect(db: Session, sub_aspect_id: int):
    db_sub_aspect = db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()
    if db_sub_aspect:
        db.delete(db_sub_aspect)
        db.commit()
        return True
    return False



# /opt/psikotes_app/backend/crud.py

import re

def safe_eval(expr, env_vars):
    if not expr:
        return 0
    try:
        # Ganti [VAR_NAME] dengan nilainya dari env_vars
        def replace_var(match):
            var_name = match.group(1)
            # Ambil nilai, default 0 jika tidak ada
            return str(env_vars.get(var_name, 0))
        
        parsed_expr = re.sub(r'\[(.*?)\]', replace_var, str(expr))
        
        # Definisikan fungsi yang diizinkan (misal SUM)
        def custom_sum(*args):
            return sum(args)
            
        allowed_locals = {
            "SUM": custom_sum,
            "sum": custom_sum
        }
        
        # Evaluasi dengan globals kosong untuk keamanan
        result = eval(parsed_expr, {"__builtins__": None}, allowed_locals)
        
        # Jika hasil float tapi sebenarnya int, ubah ke int
        if isinstance(result, float) and result.is_integer():
            return int(result)
        return result
    except Exception as e:
        print(f"Error evaluating formula '{expr}' (parsed as '{parsed_expr}'): {e}")
        return 0

def generate_participant_report(db: Session, participant_id: int):
    # 1. Ambil detail peserta
    participant = get_participant_details(db, participant_id=participant_id)
    if not participant:
        return None

    # 2. Hapus laporan lama agar tidak duplikat
    db.query(models.TestResult).filter(models.TestResult.participant_id == participant_id).delete()

    # 3. Ambil semua aspek & sub-aspek untuk psikogram
    all_aspects = db.query(models.Aspect).order_by(models.Aspect.order).all()
    
    report_data = {"aspects": []}
    final_conclusion = "Dipertimbangkan"
    total_score_sum = 0
    completed_tests_count = 0

    # 3.1. Persiapkan Environment Variabel
    env_vars = {}
    for session in participant.sessions:
        if session.status == 'completed' and session.score is not None:
            env_vars[f"TEST_{session.test_id}_RAW"] = session.score

            # Injeksi Nilai Rinci dari Modul Skoring (Misal IST: IST_SE_SW, IST_IQ)
            test = db.query(models.Test).filter(models.Test.id == session.test_id).first()
            if test and getattr(test, 'scoring_module', 'default') != 'default':
                try:
                    from scoring import get_scorer
                    scorer_class = get_scorer(test.scoring_module)
                    
                    saved_answers = db.query(models.ParticipantAnswer).join(models.Question).options(
                        joinedload(models.ParticipantAnswer.selected_option),
                        joinedload(models.ParticipantAnswer.question)
                    ).filter(
                        models.ParticipantAnswer.participant_id == participant_id,
                        models.Question.test_id == session.test_id
                    ).all()
                    
                    # Kita bisa panggil hitung ulang (cepat karena ini hanya saat laporan di-generate)
                    test_package_id = participant.test_package_id if hasattr(participant, 'test_package_id') else 0
                    score_result = scorer_class.calculate_score(
                        participant_answers=saved_answers,
                        test_package_id=test_package_id,
                        participant_id=participant_id,
                        db_session=db
                    )
                    
                    if "details" in score_result:
                        details = score_result["details"]
                        prefix = test.scoring_module.upper() # misal "IST"
                        
                        if "standard_scores" in details:
                            for subtest, sw in details["standard_scores"].items():
                                env_vars[f"{prefix}_{subtest}_SW"] = sw
                                
                        if "raw_scores" in details:
                            for subtest, rw in details["raw_scores"].items():
                                env_vars[f"{prefix}_{subtest}_RW"] = rw
                                
                        if "gest_ws" in details:
                            env_vars[f"{prefix}_GEST"] = details["gest_ws"]
                            
                        if "ss" in details:
                            env_vars[f"{prefix}_SS"] = details["ss"]
                            
                        if "iq_score" in score_result:
                            env_vars[f"{prefix}_IQ"] = score_result["iq_score"]
                except Exception as e:
                    print(f"Error fetching modular scores for report: {e}")

    # 3.2. Ambil Mapping Template
    template = participant.package.psychogram_template if participant.package else None
    mappings = []
    if template:
        mappings = db.query(models.ScoringMapping).filter(models.ScoringMapping.psychogram_template_id == template.id).all()
        
    sub_aspect_mappings = {m.sub_aspect_id: m for m in mappings if m.target_type == 'sub_aspect'}
    iq_mapping = next((m for m in mappings if m.target_type == 'iq'), None)

    for aspect in all_aspects:
        aspect_report = {"name": aspect.name, "sub_aspects": []}
        
        for sub_aspect in sorted(aspect.sub_aspects, key=lambda x: x.name):
            sub_aspect_report = {"name": sub_aspect.name, "category": "C"}
            
            # Cari test_id yang di-mapping via test_associations (untuk fallback)
            mapped_test_id = None
            if template:
                for assoc in template.test_associations:
                    if assoc.sub_aspect_id == sub_aspect.id:
                        mapped_test_id = assoc.test_id
                        break

            # Cek Scoring Mapping Dinamis (Memprioritaskan rumus dinamis)
            mapping = sub_aspect_mappings.get(sub_aspect.id)
            if mapping and mapping.formula_expression:
                # Evaluasi formula
                raw_val = safe_eval(mapping.formula_expression, env_vars)
                
                if mapping.norm_table_id:
                    # Cari norma
                    norm_data = db.query(models.NormData).filter(
                        models.NormData.norm_table_id == mapping.norm_table_id,
                        models.NormData.raw_score_min <= raw_val,
                        models.NormData.raw_score_max >= raw_val
                    ).first()
                    
                    if norm_data:
                        final_sw = norm_data.standard_score
                        sub_aspect_report["category"] = norm_data.category.upper() if norm_data.category else "C"
                    else:
                        final_sw = raw_val # fallback
                        sub_aspect_report["category"] = "C"
                else:
                    final_sw = raw_val
                    
                # Simpan ke env_vars untuk digunakan di rumus IQ
                env_vars[f"SUBASPECT_{sub_aspect.id}_SW"] = final_sw
                if mapped_test_id:
                    env_vars[f"TEST_{mapped_test_id}_SW"] = final_sw
                    
                if sub_aspect_report["category"] in ["R", "K"]:
                    final_conclusion = "Tidak Disarankan"
                    
            else:
                # Fallback ke logika lama (InterpretationRule)
                session = None
                if mapped_test_id:
                    session = next(
                        (s for s in participant.sessions if s.test_id == mapped_test_id and s.status == 'completed'),
                        None
                    )
                
                if session and session.score is not None:
                    total_score_sum += session.score
                    completed_tests_count += 1
                    
                    rule = db.query(models.InterpretationRule).filter(
                        models.InterpretationRule.test_id == mapped_test_id,
                        models.InterpretationRule.min_score <= session.score,
                        models.InterpretationRule.max_score >= session.score
                    ).first()
                    
                    if rule and rule.category:
                        sub_aspect_report["category"] = rule.category.upper()
                        if sub_aspect_report["category"] in ["R", "K"]:
                            final_conclusion = "Tidak Disarankan"
                    else:
                        sub_aspect_report["category"] = "C"
                        
                    env_vars[f"SUBASPECT_{sub_aspect.id}_SW"] = session.score
                    env_vars[f"TEST_{mapped_test_id}_SW"] = session.score

            aspect_report["sub_aspects"].append(sub_aspect_report)
        report_data["aspects"].append(aspect_report)

    # 3.5 Kalkulasi Khusus DISC
    disc_answers = db.query(models.ParticipantAnswer, models.AnswerOption).join(
        models.Question, models.ParticipantAnswer.question_id == models.Question.id
    ).join(
        models.AnswerOption, models.ParticipantAnswer.selected_option_id == models.AnswerOption.id
    ).filter(
        models.ParticipantAnswer.participant_id == participant_id,
        models.Question.question_type == 'disc'
    ).all()

    if disc_answers:
        most_counts = {"D": 0, "I": 0, "S": 0, "C": 0, "*": 0}
        least_counts = {"D": 0, "I": 0, "S": 0, "C": 0, "*": 0}
        
        for ans, opt in disc_answers:
            cat = opt.category.upper() if opt.category else "*"
            if cat not in most_counts:
                cat = "*" # Fallback jika ada kategori aneh
                
            if ans.answer_text == "most":
                most_counts[cat] += 1
            elif ans.answer_text == "least":
                least_counts[cat] += 1
                
        change_counts = {
            "D": most_counts["D"] - least_counts["D"],
            "I": most_counts["I"] - least_counts["I"],
            "S": most_counts["S"] - least_counts["S"],
            "C": most_counts["C"] - least_counts["C"],
            "*": most_counts["*"] - least_counts["*"]
        }
        
        report_data["disc_data"] = {
            "graph_1_most": most_counts,
            "graph_2_least": least_counts,
            "graph_3_change": change_counts
        }

    # 4. Hitung IQ 
    iq_val = 90
    iq_cat = "Average"
    
    if iq_mapping and iq_mapping.formula_expression:
        iq_raw = safe_eval(iq_mapping.formula_expression, env_vars)
        if iq_mapping.norm_table_id:
            norm_data = db.query(models.NormData).filter(
                models.NormData.norm_table_id == iq_mapping.norm_table_id,
                models.NormData.raw_score_min <= iq_raw,
                models.NormData.raw_score_max >= iq_raw
            ).first()
            if norm_data:
                iq_val = norm_data.standard_score
                iq_cat = norm_data.category if norm_data.category else "Average"
            else:
                iq_val = iq_raw
        else:
            iq_val = iq_raw
    else:
        # Fallback IQ Sederhana (Contoh Rumus Lama)
        iq_val = 90 + (total_score_sum // (completed_tests_count if completed_tests_count > 0 else 1))
        if iq_val > 110: iq_cat = "High Average"
        elif iq_val < 90: iq_cat = "Low Average"

    # 5. Siapkan Narasi Default
    default_iq_text = f"Hasil pemeriksaan menunjukkan bahwa {participant.name} memiliki kapasitas intelektual yang berada pada taraf {iq_cat}."
    default_pers_text = "Berdasarkan hasil asesmen, subjek menunjukkan profil kepribadian yang..."

    # --- BAGIAN YANG TADI ERROR INDENTASI ---
    db_result = models.TestResult(
        participant_id=participant.id,
        test_package_id=participant.test_package_id,
        target_position="",
        iq_score=iq_val,
        iq_category=iq_cat,
        iq_narrative=default_iq_text,
        personality_type="",
        personality_narrative=default_pers_text,
        strengths_list="- Memiliki kemauan belajar yang baik",
        weaknesses_list="- Perlu meningkatkan ketelitian",
        overall_score=f"{iq_val}",
        conclusion=final_conclusion,
        development_suggestions="Disarankan untuk mengikuti pelatihan...",
        interpretation_summary=json.dumps(report_data)
    )

    db.add(db_result)
    db.commit()
    db.refresh(db_result)

    return db_result

def save_psychologist_notes(db: Session, result_id: int, notes: str):
    """Simpan catatan psikolog ke laporan hasil."""
    db_result = db.query(models.TestResult).filter(models.TestResult.id == result_id).first()
    if db_result:
        db_result.psychologist_notes = notes
        db.commit()
        db.refresh(db_result)
    return db_result


def get_participant_details(db: Session, participant_id: int):
    return db.query(models.Participant).options(
        # Muat relasi bersarang: Participant -> Package -> Template
        joinedload(models.Participant.package)
        .joinedload(models.TestPackage.psychogram_template)
        # Dari template, muat juga semua asosiasi tes-nya
        .joinedload(models.PsychogramTemplate.test_associations),

        # Muat juga struktur Aspek -> Sub-Aspek
        joinedload(models.Participant.package)
        .joinedload(models.TestPackage.psychogram_template)
        .joinedload(models.PsychogramTemplate.aspects)
        .joinedload(models.Aspect.sub_aspects),
        
        # Muat juga sesi tes peserta
        joinedload(models.Participant.sessions)
        .joinedload(models.TestSession.test)
    ).filter(models.Participant.id == participant_id).first()


def get_participant_answers_for_export(db: Session, participant_id: int):
    """Ekspor semua jawaban peserta ke CSV."""
    return db.query(
        models.Question.order.label("question_order"),
        models.Question.id.label("question_id"),
        models.Test.name.label("test_name"),
        models.Question.text.label("question_text"),
        models.ParticipantAnswer.answer_text,
        models.AnswerOption.text.label("selected_answer"),
        models.AnswerOption.score.label("answer_score")
    ).join(models.Question, models.ParticipantAnswer.question_id == models.Question.id)\
     .join(models.Test, models.Question.test_id == models.Test.id)\
     .outerjoin(models.AnswerOption, models.ParticipantAnswer.selected_option_id == models.AnswerOption.id)\
     .filter(models.ParticipantAnswer.participant_id == participant_id)\
     .order_by(models.Question.order).all()


def get_participant_answers_for_test_export(db: Session, participant_id: int, test_id: int):
    """Ekspor jawaban peserta per tes ke CSV."""
    return db.query(
        models.Question.order.label("question_order"),
        models.Question.id.label("question_id"),
        models.Question.text.label("question_text"),
        models.ParticipantAnswer.answer_text,
        models.AnswerOption.text.label("selected_answer"),
        models.AnswerOption.score.label("answer_score")
    ).join(models.Question, models.ParticipantAnswer.question_id == models.Question.id)\
     .outerjoin(models.AnswerOption, models.ParticipantAnswer.selected_option_id == models.AnswerOption.id)\
     .filter(
        models.ParticipantAnswer.participant_id == participant_id,
        models.Question.test_id == test_id
     ).order_by(models.Question.order).all()

def deactivate_participant(db: Session, participant_id: int) -> bool:
    """Menonaktifkan seorang peserta (soft delete)."""
    db_participant = db.query(models.Participant).filter(models.Participant.id == participant_id).first()
    if db_participant:
        db_participant.is_active = False
        db.commit()
        return True
    return False


# --- Fungsi untuk Admin ---


def get_all_participants(
    db: Session,
    current_admin: models.AdminUser,
    start_date: Optional[date] = None, # <-- Parameter baru
    end_date: Optional[date] = None, 
    result_type: Optional[str] = None,
    skip: int = 0, 
    limit: int = 10, 
    search: Optional[str] = None, 
    overall_status: Optional[str] = None, # <-- Parameter baru
    package_id: Optional[int] = None
):
    # 1. Mulai dari Participant
    query = db.query(models.Participant).options(
        joinedload(models.Participant.package),
        joinedload(models.Participant.results), # Eager load hasil
        joinedload(models.Participant.sessions) # Eager load sesi
    )

    query = query.filter(models.Participant.is_active == True)
    # --- PERBAIKAN LOGIKA QUERY FINAL ---
    # Lakukan JOIN ke TestPackage terlebih dahulu untuk filter hak akses
    query = query.join(models.Participant.package)

    # Terapkan filter hak akses SEBELUM JOIN yang kompleks
    if current_admin.role == 'superadmin':
        pass
    elif current_admin.gerai_id:
        query = query.filter(models.TestPackage.gerai_id == current_admin.gerai_id)
    else:
        owner_ids = [child.id for child in current_admin.children]
        owner_ids.append(current_admin.id)
        query = query.filter(models.TestPackage.owner_id.in_(owner_ids))
    
    if start_date:
        query = query.filter(models.Participant.created_at >= start_date)
    if end_date:
        # Tambahkan 1 hari ke end_date untuk membuatnya inklusif
        from datetime import timedelta
        end_date_inclusive = end_date + timedelta(days=1)
        query = query.filter(models.Participant.created_at < end_date_inclusive)
    

    if overall_status:
        # Menghitung total dan sesi yang selesai untuk setiap peserta
        total_sessions_subq = db.query(func.count(models.TestSession.id)).filter(models.TestSession.participant_id == models.Participant.id).scalar_subquery()
        completed_sessions_subq = db.query(func.count(models.TestSession.id)).filter(
            models.TestSession.participant_id == models.Participant.id,
            models.TestSession.status == 'completed'
        ).scalar_subquery()

        if overall_status == 'Selesai':
            query = query.filter(total_sessions_subq > 0, completed_sessions_subq == total_sessions_subq)
        elif overall_status == 'Sedang Mengerjakan':
            query = query.filter(completed_sessions_subq > 0, completed_sessions_subq < total_sessions_subq)
        elif overall_status == 'Baru':
            query = query.filter(completed_sessions_subq == 0)

    # Terapkan filter paket jika ada
    if package_id is not None:
        query = query.filter(models.Participant.test_package_id == package_id)

    # Lakukan LEFT JOIN ke TestResult SETELAH filter utama
    query = query.outerjoin(models.TestResult, models.Participant.id == models.TestResult.participant_id)

    # Terapkan filter result_type
    if result_type:
        if result_type == 'automatic':
            query = query.filter(or_(models.TestResult.result_type == 'automatic', models.TestResult.id.is_(None)))
        elif result_type == 'manual':
            query = query.filter(models.TestResult.result_type == 'manual')
        elif result_type == 'Belum Dikirim':
            query = query.filter(models.TestResult.setu_status.is_(None))
        elif result_type == 'Terkirim':
            query = query.filter(models.TestResult.setu_status == 'Terkirim')
        elif result_type == 'Gagal':
             # Cari yang statusnya mengandung kata 'Gagal'
            query = query.filter(models.TestResult.setu_status.like('Gagal%'))

    # Terapkan filter search terakhir
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (models.Participant.name.like(search_term)) |
            (models.Participant.test_number.like(search_term))
        )
    
    # Hitung total SEBELUM pagination
    total_count = query.count()

    # Terapkan pagination dan kembalikan hasilnya
    results = query.order_by(models.Participant.id.desc()).offset(skip).limit(limit).all()
    
    return results, total_count



def get_participant_by_test_number_public(db: Session, test_number: str):
    """Ambil peserta berdasarkan nomor tes (untuk verifikasi publik)."""
    return db.query(models.Participant).options(joinedload(models.Participant.package)).filter(
        models.Participant.test_number == test_number
    ).first()


def get_sub_aspect_by_id(db: Session, sub_aspect_id: int):
    return db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()

def associate_test_to_sub_aspect(db: Session, sub_aspect_id: int, test_id: int):
    sub_aspect = get_sub_aspect_by_id(db, sub_aspect_id=sub_aspect_id)
    test = get_master_test(db, test_id=test_id)
    if sub_aspect and test and test not in sub_aspect.tests:
        sub_aspect.tests.append(test)
        db.commit()
    return sub_aspect

def disassociate_test_from_sub_aspect(db: Session, sub_aspect_id: int, test_id: int):
    sub_aspect = get_sub_aspect_by_id(db, sub_aspect_id=sub_aspect_id)
    test = get_master_test(db, test_id=test_id)
    if sub_aspect and test and test in sub_aspect.tests:
        sub_aspect.tests.remove(test)
        db.commit()
    return sub_aspect


def update_test_order_in_package(db: Session, package_id: int, test_ids: List[int]):
    db_package = get_test_package_by_id(db, package_id=package_id)
    if not db_package:
        return None

    # Hapus semua asosiasi tes yang lama untuk paket ini
    db.query(models.PackageTestAssociation).filter(
        models.PackageTestAssociation.test_package_id == package_id
    ).delete(synchronize_session=False)
    db.commit()

    # Buat ulang asosiasi dengan urutan baru
    for index, test_id in enumerate(test_ids):
        # Buat objek asosiasi baru
        new_association = models.PackageTestAssociation(
            test_package_id=package_id,
            test_id=test_id,
            test_order=index + 1 # Urutan dimulai dari 1
        )
        db.add(new_association)
    
    db.commit()
    
    # Muat ulang paket untuk mendapatkan data terbaru
    return get_test_package_by_id(db, package_id=package_id)




def add_test_to_package(db: Session, package_id: int, test_id: int):
    db_package = get_test_package_by_id(db, package_id=package_id)
    test_to_add = get_master_test(db, test_id=test_id)

    if not db_package or not test_to_add:
        return None # Paket atau tes tidak ditemukan

    # Cek apakah asosiasi sudah ada untuk mencegah duplikasi
    existing_association = db.query(models.PackageTestAssociation).filter_by(
        test_package_id=package_id,
        test_id=test_id
    ).first()
    
    if existing_association:
        return db_package # Jika sudah ada, tidak perlu melakukan apa-apa

    # Hitung urutan berikutnya
    max_order = db.query(func.max(models.PackageTestAssociation.test_order)).filter_by(
        test_package_id=package_id
    ).scalar() or 0
    
    # Buat record asosiasi baru
    new_association = models.PackageTestAssociation(
        test_package_id=package_id,
        test_id=test_id,
        test_order=max_order + 1
    )
    db.add(new_association)
    db.commit()
    
    # Muat ulang paket untuk mendapatkan data terbaru
    return get_test_package_by_id(db, package_id=package_id)


def get_all_admins(db: Session):
    return db.query(models.AdminUser).all()

def create_admin_user(db: Session, admin: schemas.AdminUserCreate):
    # Cek apakah email sudah ada
    existing_admin = get_admin_by_email(db, email=admin.email)
    if existing_admin:
        return None # Kembalikan None jika email sudah terdaftar

    hashed_password = get_password_hash(admin.password)
    db_admin = models.AdminUser(
        email=admin.email,
        hashed_password=hashed_password,
        role=admin.role,
        full_name=admin.full_name,
        parent_id=admin.parent_id,
        gerai_id=admin.gerai_id
    )
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin


def get_participant_report_by_id(db: Session, participant_id: int) -> Optional[models.TestResult]:
    """
    Mengambil hasil tes (laporan) yang sudah digenerate untuk seorang peserta.
    Fungsi ini juga memuat relasi ke peserta dan package owner (psikolog).
    """
    return db.query(models.TestResult).options(
        joinedload(models.TestResult.participant)
        .joinedload(models.Participant.package)
        .joinedload(models.TestPackage.owner) # Memuat info psikolog
    ).filter(models.TestResult.participant_id == participant_id).first()

def update_report_manual(db: Session, result_id: int, report_data: schemas.ReportUpdateRequest) -> Optional[models.TestResult]:
    """
    Memperbarui laporan hasil tes secara manual oleh admin/psikolog.
    """
    db_result = db.query(models.TestResult).filter(models.TestResult.id == result_id).first()
    
    if not db_result:
        return None

    # Update skor keseluruhan (kesimpulan)
    db_result.overall_score = report_data.overall_score

    # Konversi data Pydantic kembali ke format JSON string untuk disimpan
    # Kita menggunakan .dict() dari Pydantic model
    summary_dict = {"aspects": [aspect.dict() for aspect in report_data.aspects]}
    db_result.interpretation_summary = json.dumps(summary_dict, ensure_ascii=False)
    db_result.result_type = 'manual'
    
    db.commit()
    db.refresh(db_result)
    
    return db_result

def update_report_full_manual(db: Session, result_id: int, report_data: schemas.ReportFullUpdateRequest) -> Optional[models.TestResult]:
    db_result = db.query(models.TestResult).filter(models.TestResult.id == result_id).first()
    
    if not db_result:
        return None

    update_dict = report_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(db_result, key, value)
    
    db_result.result_type = 'manual'
    
    db.commit()
    db.refresh(db_result)
    
    return db_result


def get_gerai_by_name(db: Session, name: str) -> Optional[models.Gerai]:
    """Cari gerai berdasarkan nama."""
    return db.query(models.Gerai).filter(models.Gerai.name == name).first()

def get_gerai(db: Session, gerai_id: int) -> Optional[models.Gerai]:
    """Cari gerai berdasarkan ID."""
    return db.query(models.Gerai).filter(models.Gerai.id == gerai_id).first()

def get_all_gerai(db: Session, skip: int = 0, limit: int = 100) -> List[models.Gerai]:
    """Ambil semua data gerai."""
    return db.query(models.Gerai).order_by(models.Gerai.name).offset(skip).limit(limit).all()

def create_gerai(db: Session, gerai: schemas.GeraiCreate) -> models.Gerai:
    """Buat gerai baru."""
    db_gerai = models.Gerai(name=gerai.name, address=gerai.address)
    db.add(db_gerai)
    db.commit()
    db.refresh(db_gerai)
    return db_gerai

def update_gerai(db: Session, gerai_id: int, gerai_data: schemas.GeraiCreate) -> Optional[models.Gerai]:
    """Perbarui data gerai."""
    db_gerai = get_gerai(db, gerai_id)
    if db_gerai:
        db_gerai.name = gerai_data.name
        db_gerai.address = gerai_data.address
        db.commit()
        db.refresh(db_gerai)
    return db_gerai

def delete_gerai(db: Session, gerai_id: int) -> bool:
    """Hapus gerai."""
    db_gerai = get_gerai(db, gerai_id)
    if db_gerai:
        db.delete(db_gerai)
        db.commit()
        return True
    return False


# backend/crud.py

# Tambahkan fungsi-fungsi ini untuk mengelola Master Sub-Aspek
def get_all_master_sub_aspects(db: Session):
    return db.query(models.SubAspect).order_by(models.SubAspect.name).all()

def create_master_sub_aspect(db: Session, sub_aspect: schemas.SubAspectCreateMaster):
    db_sub_aspect = models.SubAspect(
        name=sub_aspect.name, 
        minimum_category=sub_aspect.minimum_category,
        description=sub_aspect.description,
        low_score_description=sub_aspect.low_score_description,
        high_score_description=sub_aspect.high_score_description
    )
    db.add(db_sub_aspect)
    db.commit()
    db.refresh(db_sub_aspect)
    return db_sub_aspect

def update_master_sub_aspect(db: Session, sub_aspect_id: int, sub_aspect: schemas.SubAspectCreateMaster):
    db_sub_aspect = db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()
    if not db_sub_aspect:
        return None
    db_sub_aspect.name = sub_aspect.name
    db_sub_aspect.minimum_category = sub_aspect.minimum_category
    db_sub_aspect.description = sub_aspect.description
    db_sub_aspect.low_score_description = sub_aspect.low_score_description
    db_sub_aspect.high_score_description = sub_aspect.high_score_description
    db.commit()
    db.refresh(db_sub_aspect)
    return db_sub_aspect

# Fungsi untuk asosiasi
def associate_sub_aspect_to_aspect(db: Session, aspect_id: int, sub_aspect_id: int):
    aspect = db.query(models.Aspect).filter(models.Aspect.id == aspect_id).first()
    sub_aspect = db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()
    if aspect and sub_aspect and sub_aspect not in aspect.sub_aspects:
        aspect.sub_aspects.append(sub_aspect)
        db.commit()
    return aspect

def disassociate_sub_aspect_from_aspect(db: Session, aspect_id: int, sub_aspect_id: int):
    aspect = db.query(models.Aspect).filter(models.Aspect.id == aspect_id).first()
    sub_aspect = db.query(models.SubAspect).filter(models.SubAspect.id == sub_aspect_id).first()
    if aspect and sub_aspect and sub_aspect in aspect.sub_aspects:
        aspect.sub_aspects.remove(sub_aspect)
        db.commit()
    return aspect

# Di dalam backend/crud.py

def update_report_result_type(db: Session, result_id: int, result_type: str) -> Optional[models.TestResult]:
    """Hanya memperbarui tipe hasil (misal: dari automatic ke manual)."""
    db_result = db.query(models.TestResult).filter(models.TestResult.id == result_id).first()
    if db_result:
        db_result.result_type = result_type
        db.commit()
        db.refresh(db_result)
    return db_result

# Di dalam backend/crud.py
def get_participants_for_export(
    db: Session,
    current_admin: models.AdminUser,
    result_type: Optional[str] = None,
    search: Optional[str] = None, 
    package_id: Optional[int] = None,
    gerai_id: Optional[int] = None
):
    """Mengambil semua data peserta yang cocok dengan filter untuk diekspor (VERSI EAGER LOADING)."""
    
    # --- QUERY DENGAN EAGER LOADING ---
    # 1. Mulai dari Participant dan definisikan SEMUA relasi yang akan kita butuhkan
    query = db.query(models.Participant).options(
        # Muat 'package' dan di dalamnya muat 'gerai'
        joinedload(models.Participant.package).joinedload(models.TestPackage.gerai),
        # Muat relasi 'results'
        joinedload(models.Participant.results)
    )
    
    # 2. Lakukan JOIN yang diperlukan untuk filtering
    query = query.join(models.Participant.package)
    query = query.outerjoin(models.TestResult, models.Participant.id == models.TestResult.participant_id)

    # 3. Terapkan semua filter (logika ini tidak berubah)
    if current_admin.role == 'superadmin':
        if gerai_id:
            query = query.filter(models.TestPackage.gerai_id == gerai_id)
    # Filter Hak Akses & Gerai
    if current_admin.role == 'superadmin':
        if gerai_id:
            query = query.filter(models.TestPackage.gerai_id == gerai_id)
    elif current_admin.gerai_id:
        query = query.filter(models.TestPackage.gerai_id == current_admin.gerai_id)
    else: 
        owner_ids = [child.id for child in current_admin.children]
        owner_ids.append(current_admin.id)
        query = query.filter(models.TestPackage.owner_id.in_(owner_ids))
        if gerai_id:
            query = query.filter(models.TestPackage.gerai_id == gerai_id)

    # Filter Tipe Hasil
    if result_type:
        if result_type == 'automatic':
            query = query.filter(or_(models.TestResult.result_type == 'automatic', models.TestResult.id.is_(None)))
        elif result_type == 'manual':
            query = query.filter(models.TestResult.result_type == 'manual')
        elif result_type == 'Belum Dikirim':
            query = query.filter(models.TestResult.setu_status.is_(None))
        elif result_type == 'Terkirim':
            query = query.filter(models.TestResult.setu_status == 'Terkirim')
        elif result_type == 'Gagal':
             # Cari yang statusnya mengandung kata 'Gagal'
            query = query.filter(models.TestResult.setu_status.like('Gagal%'))
        
    # Filter Paket
    if package_id is not None:
        query = query.filter(models.Participant.test_package_id == package_id)

    # Filter Search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (models.Participant.name.like(search_term)) |
            (models.Participant.test_number.like(search_term))
        )

     # Logging query untuk verifikasi
    from sqlalchemy.dialects import mysql
    print("\n--- [DEBUG] Final SQL Query for Export (Eager) ---")
    print(query.statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    print("--------------------------------------------------\n")
    
    return query.order_by(models.Participant.id.desc()).all() 

SUB_ASPECT_MAPPING = {
    'Berpikir Praktis': 'berpikir_praktis',
    'Berpikir Analitis': 'berpikir_analitis',
    # 'Sensor Rambu': 'sensor_rambu', # Tambahkan jika Anda punya field ini
    'Ketahanan': 'ketahanan',
    'Stabilitas Emosi': 'stabilitas_emosi',
    'Pengendalian Diri': 'pengendalian_diri',
    'Prososial': 'prososial',
}

def format_report_for_setu(participant: models.Participant, report: models.TestResult) -> Optional[Dict]:
    """Mengubah data laporan menjadi format yang sesuai untuk API SETU."""
    if not report.interpretation_summary:
        return None
    
    try:
        summary = json.loads(report.interpretation_summary)
        
        # Buat dictionary score
        score_dict = {}
        for aspect in summary.get("aspects", []):
            for sub in aspect.get("sub_aspects", []):
                # Gunakan mapping untuk mendapatkan kunci yang benar
                setu_key = SUB_ASPECT_MAPPING.get(sub.get("name"))
                if setu_key:
                    # API SETU sepertinya menggunakan 'Baik', 'Cukup', 'Kurang'
                    # Sesuaikan jika kategori Anda berbeda (misal: A, B, C)
                    category = sub.get("category", "").upper()
                    if category == "B":
                        score_dict[setu_key] = "Baik" # Sesuaikan mapping ini
                    elif category == "C":
                        score_dict[setu_key] = "Cukup"
                    elif category == "K":
                        score_dict[setu_key] = "Kurang"
                    else:
                        score_dict[setu_key] = "N/A"
        
        # Tambahkan hasil_akhir
        score_dict["hasil_akhir"] = report.overall_score

        # Bangun payload akhir
        payload = {
            "nik": participant.test_number,
            "nama": participant.name,
            "gol_sim": participant.sim_type, # Asumsi 'sim_type' Anda cocok dengan 'gol_sim'
            "jenis_sim": participant.sim_status, # Asumsi 'sim_status' Anda cocok
            "score": score_dict,
            "result_type": report.result_type # Mengambil 'automatic' atau 'manual'
        }
        return payload

    except json.JSONDecodeError:
        return None



# backend/crud.py

def get_associations_for_template(db: Session, template_id: int) -> List[models.TemplateSubAspectTest]:
    """Mengambil semua asosiasi tes untuk sebuah template."""
    return db.query(models.TemplateSubAspectTest).options(
        joinedload(models.TemplateSubAspectTest.sub_aspect),
        joinedload(models.TemplateSubAspectTest.test)
    ).filter(models.TemplateSubAspectTest.template_id == template_id).all()

def add_test_association_to_template(db: Session, template_id: int, sub_aspect_id: int, test_id: int) -> models.TemplateSubAspectTest:
    """Membuat asosiasi baru antara template, sub-aspek, dan tes."""
    # Cek apakah asosiasi sudah ada
    existing = db.query(models.TemplateSubAspectTest).filter_by(
        template_id=template_id, sub_aspect_id=sub_aspect_id, test_id=test_id
    ).first()
    if existing:
        return existing # Jika sudah ada, kembalikan yang sudah ada

    association = models.TemplateSubAspectTest(
        template_id=template_id, sub_aspect_id=sub_aspect_id, test_id=test_id
    )
    db.add(association)
    db.commit()
    db.refresh(association)
    return association
    
def remove_test_association_from_template(db: Session, template_id: int, sub_aspect_id: int, test_id: int) -> bool:
    """Menghapus asosiasi tes dari sebuah template."""
    association = db.query(models.TemplateSubAspectTest).filter_by(
        template_id=template_id, sub_aspect_id=sub_aspect_id, test_id=test_id
    ).first()
    
    if association:
        db.delete(association)
        db.commit()
        return True
    return False



    # Di dalam crud.py

def update_test_result_setu_status(db: Session, result_id: int, status: str):
    """Memperbarui kolom setu_status pada sebuah hasil tes."""
    db_result = db.query(models.TestResult).filter(models.TestResult.id == result_id).first()
    if db_result:
        db_result.setu_status = status
        db.commit()

# --- CRUD FOR NORM TABLE & SCORING MAPPING ---

def get_norm_tables(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.NormTable).offset(skip).limit(limit).all()

def get_norm_table(db: Session, norm_table_id: int):
    return db.query(models.NormTable).filter(models.NormTable.id == norm_table_id).first()

def create_norm_table(db: Session, norm_table: schemas.NormTableCreate):
    db_norm = models.NormTable(name=norm_table.name, description=norm_table.description)
    db.add(db_norm)
    db.commit()
    db.refresh(db_norm)
    for data_item in norm_table.data:
        db_data = models.NormData(**data_item.dict(), norm_table_id=db_norm.id)
        db.add(db_data)
    db.commit()
    db.refresh(db_norm)
    return db_norm

def update_norm_table(db: Session, norm_table_id: int, norm_table: schemas.NormTableUpdate):
    db_norm = db.query(models.NormTable).filter(models.NormTable.id == norm_table_id).first()
    if db_norm:
        if norm_table.name is not None:
            db_norm.name = norm_table.name
        if norm_table.description is not None:
            db_norm.description = norm_table.description
        db.commit()
        db.refresh(db_norm)
    return db_norm

def delete_norm_table(db: Session, norm_table_id: int):
    db_norm = db.query(models.NormTable).filter(models.NormTable.id == norm_table_id).first()
    if db_norm:
        db.delete(db_norm)
        db.commit()

def add_norm_data(db: Session, norm_table_id: int, data: schemas.NormDataCreate):
    db_data = models.NormData(**data.dict(), norm_table_id=norm_table_id)
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data

def delete_norm_data(db: Session, norm_data_id: int):
    db_data = db.query(models.NormData).filter(models.NormData.id == norm_data_id).first()
    if db_data:
        db.delete(db_data)
        db.commit()

def get_scoring_mappings(db: Session, template_id: int):
    return db.query(models.ScoringMapping).filter(models.ScoringMapping.psychogram_template_id == template_id).all()

def create_scoring_mapping(db: Session, mapping: schemas.ScoringMappingCreate):
    db_mapping = models.ScoringMapping(**mapping.dict())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return db_mapping

def delete_scoring_mapping(db: Session, mapping_id: int):
    db_mapping = db.query(models.ScoringMapping).filter(models.ScoringMapping.id == mapping_id).first()
    if db_mapping:
        db.delete(db_mapping)
        db.commit()

def get_essay_answers_by_test(db: Session, participant_id: int, test_id: int):
    # Ambil semua ParticipantAnswer untuk participant_id dan question_id milik test_id yang bertipe essay
    answers = db.query(models.ParticipantAnswer).join(models.Question).filter(
        models.ParticipantAnswer.participant_id == participant_id,
        models.Question.test_id == test_id,
        models.Question.question_type.in_(['essay', 'short_answer'])
    ).all()
    
    return answers

def update_essay_score(db: Session, answer_id: int, new_score: int):
    answer = db.query(models.ParticipantAnswer).filter(models.ParticipantAnswer.id == answer_id).first()
    if not answer:
        return None
    
    answer.score = new_score
    db.commit()
    
    # Recalculate total score for the session
    question = db.query(models.Question).filter(models.Question.id == answer.question_id).first()
    if question:
        session = db.query(models.TestSession).filter(
            models.TestSession.participant_id == answer.participant_id,
            models.TestSession.test_id == question.test_id
        ).first()
        
        if session:
            # Re-sum all scores
            all_answers = db.query(models.ParticipantAnswer).join(models.Question).filter(
                models.ParticipantAnswer.participant_id == session.participant_id,
                models.Question.test_id == session.test_id
            ).all()
            
            new_total = 0
            for a in all_answers:
                if a.selected_option_id:
                    # get score from option
                    opt = db.query(models.AnswerOption).filter(models.AnswerOption.id == a.selected_option_id).first()
                    if opt and opt.score:
                        new_total += opt.score
                elif a.score is not None:
                    new_total += a.score
            
            session.score = new_total
            db.commit()
            
    return answer