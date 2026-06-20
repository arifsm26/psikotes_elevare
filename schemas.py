# backend/schemas.py (VERSI FINAL BERSIH)

from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from fastapi.security import OAuth2PasswordBearer

# ===================================================================
# SKEMA OTENTIKASI
# ===================================================================
oauth2_scheme_participant = OAuth2PasswordBearer(tokenUrl="/api/token_placeholder")

# ===================================================================
# SKEMA DASAR & BERSAMA (digunakan di banyak tempat)
# ===================================================================

class Test(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    is_active: bool
    require_all_answers: bool
    memorization_duration_seconds: Optional[int] = None
    stimulus_text: Optional[str] = None
    stimulus_image_url: Optional[str] = None
    class Config: from_attributes = True


class SubAspect(BaseModel):
    id: int
    name: str
    # order: int # <-- HAPUS BARIS INI
    minimum_category: str
    tests: List[Test] = []
    
    class Config:
        from_attributes = True


class Aspect(BaseModel):
    id: int
    name: str
    order: int
    
    # Perubahan utama: sub_aspects sekarang adalah daftar dari skema SubAspect
    sub_aspects: List[SubAspect] = []

    class Config:
        from_attributes = True

class PsychogramTemplate(BaseModel):
    id: int
    name: str
    aspects: List[Aspect] = []
    class Config: from_attributes = True

class TestPackage(BaseModel):
    id: int
    name: str
    access_code: str
    is_active: bool = True
    psychogram_template: Optional[PsychogramTemplate] = None
    tests: List[Test] = [] # Ini akan diisi oleh @property di model
    gerai_id: Optional[int] = None
    class Config: from_attributes = True



class GeraiBase(BaseModel):
    name: str
    address: Optional[str] = None

class GeraiCreate(GeraiBase):
    pass

class Gerai(GeraiBase):
    id: int

    class Config:
        from_attributes = True



# ===================================================================
# SKEMA UNTUK ALUR PESERTA
# ===================================================================

class PackageValidateRequest(BaseModel):
    access_code: str

class PackageValidateResponse(BaseModel):
    valid: bool
    package_name: Optional[str] = None

class SessionCreateRequest(BaseModel):
    access_code: str
    name: str
    test_number: str
    birth_date: Optional[date] = None
    registration_number: Optional[str] = None
    job: Optional[str] = None
    address: Optional[str] = None
    
    # --- TAMBAHKAN FIELD-FIELD INI ---
    sim_type: Optional[str] = None
    sim_status: Optional[str] = None
    test_location: Optional[str] = None
    # -----------------------------------

class SessionResumeRequest(BaseModel):
    access_code: str
    test_number: str

class SessionCreateResponse(BaseModel):
    session_token: str
    name: str
    package: TestPackage # Gunakan skema TestPackage yang sudah lengkap

    class Config:
        from_attributes = True
        
class TestStatus(BaseModel):
    id: int
    name: str
    status: str
    score: Optional[int] = None
    class Config: from_attributes = True
        
class SessionStatusResponse(BaseModel):
    participant_name: str
    package_name: str
    tests: List[TestStatus]

class StartTimeResponse(BaseModel):
    start_time: datetime
    duration_minutes: int
    class Config: from_attributes = True

class AnswerSubmit(BaseModel):
    question_id: int
    selected_option_ids: List[int] = []
    answer_text: Optional[str] = None

class TestSubmissionRequest(BaseModel):
    test_id: int
    answers: List[AnswerSubmit]

class TestSubmissionResponse(BaseModel):
    message: str
    score: int

class EssayAnswerResponse(BaseModel):
    id: int
    question_text: str
    answer_text: Optional[str] = None
    score: Optional[int] = None
    options: List["AnswerOptionDetail"] = []
    class Config: from_attributes = True

class UpdateEssayScoreRequest(BaseModel):
    score: int

class AnswerOptionDetail(BaseModel):
    id: int
    text: str
    score: int
    category: Optional[str] = None
    is_correct: bool
    image_url : Optional[str] = None
    class Config: from_attributes = True
    
class Question(BaseModel):
    id: int
    text: str
    order: int
    is_example: bool
    question_type: str
    image_url: Optional[str] = None
    options: List["AnswerOptionDetail"] = []
    class Config: from_attributes = True

class TestPreviewResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    duration_minutes: int
    require_all_answers: bool
    memorization_duration_seconds: Optional[int] = None
    stimulus_text: Optional[str] = None
    stimulus_image_url: Optional[str] = None
    example_question: Optional[Question] = None
    class Config: from_attributes = True

class VerificationResult(BaseModel):
    name: str
    test_number: str
    package_name: str
    test_date: datetime
    conclusion: Optional[str] = None

    sim_type: Optional[str] = None
    sim_status: Optional[str] = None
    test_location: Optional[str] = None
    class Config: from_attributes = True

# ===================================================================
# SKEMA UNTUK ALUR ADMIN
# ===================================================================

class Token(BaseModel):
    access_token: str
    token_type: str

class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminProfile(BaseModel):
    id: int
    email: str
    is_active: bool
    role: str # <-- TAMBAHKAN INI
    parent_id: Optional[int] = None # <-- TAMBAHKAN INI
    full_name: Optional[str] = None
    sipp_number: Optional[str] = None
    city: Optional[str] = None
    signature_image_url: Optional[str] = None

    gerai_id: Optional[int] = None
    
    class Config:
        from_attributes = True

class AdminProfileUpdate(BaseModel):
    email: Optional[str] = None; full_name: Optional[str] = None
    sipp_number: Optional[str] = None; city: Optional[str] = None
    signature_image_url: Optional[str] = None

# --- Manajemen Template Psikogram ---
class PsychogramTemplateCreate(BaseModel):
    name: str

# --- Manajemen Paket Tes ---
class TestPackageCreate(BaseModel):
    name: str; access_code: str
    is_active: bool = True
    psychogram_template_id: Optional[int] = None
    gerai_id: Optional[int] = None
    
class TestPackageUpdate(TestPackageCreate):
    pass

class TestPackageListResponse(BaseModel):
    total_count: int
    packages: List[TestPackage]

class TestOrderUpdate(BaseModel):
    test_ids: List[int]

# --- Manajemen Master Tes ---
class TestCreate(BaseModel):
    name: str
    description: Optional[str] = None
    duration_minutes: int
    is_active: bool = True
    require_all_answers: bool = False
    memorization_duration_seconds: Optional[int] = None
    stimulus_text: Optional[str] = None
    stimulus_image_url: Optional[str] = None

class TestUpdate(BaseModel):
    name: Optional[str] = None; description: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    require_all_answers: Optional[bool] = None
    memorization_duration_seconds: Optional[int] = None
    stimulus_text: Optional[str] = None; stimulus_image_url: Optional[str] = None

class MasterTestListResponse(BaseModel):
    total_count: int; tests: List[Test]

# --- Manajemen Aspek & Sub-Aspek ---
class AspectCreate(BaseModel):
    name: str; order: int = 0
    
class SubAspectCreate(BaseModel):
    name: str; order: int = 0
    aspect_id: int; minimum_category: str = 'B'

class SubAspectUpdate(SubAspectCreate):
    pass

class SubAspectUpdateManual(BaseModel):
    name: str
    category: str

class AspectUpdateManual(BaseModel):
    name: str
    sub_aspects: List[SubAspectUpdateManual]

class ReportUpdateRequest(BaseModel):
    overall_score: str
    aspects: List[AspectUpdateManual]

class ReportFullUpdateRequest(BaseModel):
    target_position: Optional[str] = None
    iq_score: Optional[int] = None
    iq_category: Optional[str] = None
    iq_narrative: Optional[str] = None
    personality_type: Optional[str] = None
    personality_narrative: Optional[str] = None
    strengths_list: Optional[str] = None
    weaknesses_list: Optional[str] = None
    overall_score: Optional[str] = None
    conclusion: Optional[str] = None
    development_suggestions: Optional[str] = None
    interpretation_summary: Optional[str] = None


# --- Manajemen Pertanyaan ---
class AnswerOptionCreate(BaseModel):
    text: str; score: int = 0
    category: Optional[str] = None
    is_correct: bool = False
    image_url: Optional[str] = None

class AnswerOptionUpdate(AnswerOptionCreate):
    id: Optional[int] = None

class QuestionCreate(BaseModel):
    text: str; order: int; question_type: str
    is_example: bool = False; image_url: Optional[str] = None
    options: List[AnswerOptionCreate] = []

class QuestionUpdate(QuestionCreate):
    options: List[AnswerOptionUpdate] = []

# --- Manajemen Interpretasi ---
class InterpretationRuleBase(BaseModel):
    sub_aspect_id: int; min_score: int; max_score: int
    interpretation_text: str; category: Optional[str] = None

class InterpretationRuleCreate(InterpretationRuleBase):
    pass

class InterpretationRule(InterpretationRuleBase):
    id: int
    class Config: from_attributes = True

# --- Laporan & Hasil Peserta ---
class ParticipantResult(BaseModel):
    id: int; name: str; test_number: Optional[str] = None
    created_at: datetime; package_name: str
    birth_date: Optional[date] = None; job: Optional[str] = None
    address: Optional[str] = None; registration_number: Optional[str] = None
    # --- TAMBAHKAN INI ---
    sim_type: Optional[str] = None
    sim_status: Optional[str] = None
    test_location: Optional[str] = None
    # ---------------------
    overall_status: str  # Status gabungan (Selesai, Sedang Mengerjakan)
    conclusion: Optional[str] = None # Lulus / Tidak Lulus
    setu_status: Optional[str] = None # Status pengiriman ke SETU

    class Config:
        from_attributes = True
        
class ParticipantDetail(ParticipantResult):
    sessions: List[TestStatus] = []


class ParticipantListResponse(BaseModel):
    total_count: int; participants: List[ParticipantResult]


class TestResult(BaseModel):
    id: int
    participant_id: int
    test_package_id: int
    target_position: Optional[str] = None
    iq_score: Optional[int] = None
    iq_category: Optional[str] = None
    iq_narrative: Optional[str] = None
    competency_scores: Optional[str] = None
    career_interests: Optional[str] = None
    personality_type: Optional[str] = None
    personality_narrative: Optional[str] = None
    strengths_list: Optional[str] = None
    weaknesses_list: Optional[str] = None
    overall_score: Optional[str] = None
    conclusion: Optional[str] = None
    development_suggestions: Optional[str] = None
    interpretation_summary: Optional[str] = None
    generated_at: datetime

    class Config:
        from_attributes = True


# Tambahkan ini di paling bawah schemas.py
class PsychologistNotesUpdate(BaseModel):
    notes: str

class TestResultUpdate(BaseModel):
    target_position: Optional[str] = None
    iq_score: Optional[int] = None
    iq_category: Optional[str] = None
    iq_narrative: Optional[str] = None
    personality_type: Optional[str] = None
    personality_narrative: Optional[str] = None
    strengths_list: Optional[str] = None
    weaknesses_list: Optional[str] = None
    overall_score: Optional[str] = None
    conclusion: Optional[str] = None
    development_suggestions: Optional[str] = None
    interpretation_summary: Optional[str] = None


class AdminUserCreate(BaseModel):
    email: str
    password: str
    role: str = 'admin' # Defaultnya adalah 'admin' biasa
    full_name: Optional[str] = None
    parent_id: Optional[int] = None

    gerai_id: Optional[int] = None

class SubAspectReportDetail(BaseModel):
    name: str
    category: str

class AspectReportDetail(BaseModel):
    name: str
    sub_aspects: List[SubAspectReportDetail]

class ParticipantReportResponse(BaseModel):
    # Status Laporan
    report_status: str # 'ready' atau 'pending'
    
    # Informasi Laporan
    package_name: str
    test_date: datetime
    generated_at: Optional[datetime] = None
    conclusion: Optional[str] = None
    psychologist_notes: Optional[str] = None
    
    # Detail Peserta
    participant_name: str
    participant_test_number: str
    participant_birth_date: Optional[date] = None
    participant_job: Optional[str] = None

    sim_type: Optional[str] = None
    sim_status: Optional[str] = None
    test_location: Optional[str] = None    

    participant_address: Optional[str] = None
    
    # Detail Psikogram (jika laporan sudah siap)
    report_details: Optional[List[AspectReportDetail]] = None
    
    # Informasi Penanggung Jawab (Psikolog)
    psychologist_name: Optional[str] = None
    psychologist_sipp: Optional[str] = None
    psychologist_city: Optional[str] = None
    psychologist_signature_url: Optional[str] = None

# Di dalam backend/schemas.py

class ReportTypeUpdateRequest(BaseModel):
    result_type: str

# backend/schemas.py

# Buat skema ini untuk membuat master sub-aspek
class SubAspectCreateMaster(BaseModel):
    name: str
    minimum_category: str = 'B'


class TestAssociationCreate(BaseModel):
    sub_aspect_id: int
    test_id: int

# Skema untuk menampilkan asosiasi yang sudah ada
# Ini akan menyertakan objek SubAspect dan Test yang lengkap
class TestAssociation(BaseModel):
    template_id: int
    sub_aspect_id: int
    test_id: int
    sub_aspect: SubAspect # Menggunakan skema SubAspect yang sudah ada
    test: Test         # Menggunakan skema Test yang sudah ada

    class Config:
        from_attributes = True

# Ini akan menyelesaikan referensi "TestPackage" di dalam SessionCreateResponse
SessionCreateResponse.model_rebuild() 

# Ini akan menyelesaikan referensi "AnswerOptionDetail" di dalam Question
Question.model_rebuild()


# --- SKEMA NORMA & SKORING ---
class NormDataCreate(BaseModel):
    raw_score_min: int
    raw_score_max: int
    standard_score: int
    category: Optional[str] = None

class NormDataUpdate(NormDataCreate):
    pass

class NormData(NormDataCreate):
    id: int
    norm_table_id: int
    class Config: from_attributes = True

class NormTableCreate(BaseModel):
    name: str
    description: Optional[str] = None
    data: List[NormDataCreate] = []

class NormTableUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class NormTable(NormTableCreate):
    id: int
    created_at: datetime
    data: List[NormData] = []
    class Config: from_attributes = True

class ScoringMappingCreate(BaseModel):
    psychogram_template_id: int
    sub_aspect_id: Optional[int] = None
    target_type: str = 'sub_aspect'
    formula_expression: str
    norm_table_id: Optional[int] = None

class ScoringMappingUpdate(BaseModel):
    formula_expression: Optional[str] = None
    norm_table_id: Optional[int] = None

class ScoringMapping(ScoringMappingCreate):
    id: int
    created_at: datetime
    class Config: from_attributes = True


