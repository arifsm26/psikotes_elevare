# backend/participant_router.py

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

# Impor dari file-file lokal
import crud
import models
import schemas
from database import get_db

# --- DEPENDENCY UNTUK OTENTIKASI PESERTA ---
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

router = APIRouter(
    tags=["participant"]
)

def _get_tests_from_template(participant: models.Participant):
    if not participant.package or not participant.package.psychogram_template:
        return set()
    
    template = participant.package.psychogram_template
    sub_aspects_in_template = [sub for aspect in template.aspects for sub in aspect.sub_aspects]
    
    # BENAR: Lakukan loop di dalam 'sub.tests' (plural)
    unique_tests = {test for sub in sub_aspects_in_template for test in sub.tests if test is not None}
    
    return unique_tests

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
            raise HTTPException(status_code=404, detail="Access code is not valid or inactive.")
        if result["error"] == "test_number_exists":
            raise HTTPException(status_code=400, detail="Test number already registered for this test package.")
    
    # Cukup kembalikan objek SQLAlchemy, Pydantic akan mengurus sisanya
#    return result["participant"]
    db_participant = result["participant"]
    
    # Ambil daftar tes dari template
    tests_in_session = _get_tests_from_template(db_participant)
    
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

@router.get("/sessions/status", response_model=schemas.SessionStatusResponse)
def get_session_status(db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    test_sessions = crud.get_session_status(db, participant_id=participant.id)
    test_statuses = [schemas.TestStatus(id=s.test.id, name=s.test.name, status=s.status, score=s.score) for s in test_sessions]
    return schemas.SessionStatusResponse(
        participant_name=participant.name,
        package_name=participant.package.name,
        tests=test_statuses
    )

@router.get("/tests/{test_id}/preview", response_model=schemas.TestPreviewResponse)
def get_test_preview(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
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

@router.get("/tests/{test_id}/questions", response_model=List[schemas.Question])
def get_test_questions(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    return crud.get_questions_for_test(db, test_id=test_id)

@router.post("/sessions/tests/{test_id}/start", response_model=schemas.StartTimeResponse)
def start_test(test_id: int, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    session = crud.start_test_session(db, participant_id=participant.id, test_id=test_id)
    if not session:
        raise HTTPException(status_code=404, detail="Test session not found or already completed.")
    
    return schemas.StartTimeResponse(
        start_time=session.start_time,
        duration_minutes=session.test.duration_minutes
    )

@router.post("/sessions/submit-answers", response_model=schemas.TestSubmissionResponse)
def submit_answers(submission: schemas.TestSubmissionRequest, db: Session = Depends(get_db), participant: models.Participant = Depends(get_current_participant)):
    final_score = crud.save_participant_answers(db, participant_id=participant.id, submission=submission)
    return {"message": "Answers submitted successfully", "score": final_score}

@router.get("/verify", response_model=schemas.VerificationResult)
def verify_participant_result(
    id: str,
    db: Session = Depends(get_db)
):
    participant = crud.get_participant_by_test_number_public(db, test_number=id)
    if not participant:
        raise HTTPException(status_code=404, detail="Hasil tes dengan nomor ini tidak ditemukan.")

    result = db.query(models.TestResult).filter(models.TestResult.participant_id == participant.id).first()
    
    return schemas.VerificationResult(
        name=participant.name,
        test_number=participant.test_number,
        package_name=participant.package.name,
        test_date=participant.created_at,
        conclusion=result.overall_score if result else "Belum Dianalisis"
    )
