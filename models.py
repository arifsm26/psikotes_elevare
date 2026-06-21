# backend/models.py (VERSI DIPERBAIKI)

from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, DateTime, Table, Text, Date, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# --- DEFINISI TABEL PENGHUBUNG DI PALING ATAS ---
template_tests_association = Table(
    'template_tests', Base.metadata,
    Column('psychogram_template_id', Integer, ForeignKey('psychogram_templates.id'), primary_key=True),
    Column('test_id', Integer, ForeignKey('tests.id'), primary_key=True)
)

class TemplateSubAspectTest(Base):
    __tablename__ = 'template_subaspect_tests'
    template_id = Column(Integer, ForeignKey('psychogram_templates.id', ondelete='CASCADE'), primary_key=True)
    sub_aspect_id = Column(Integer, ForeignKey('sub_aspects.id', ondelete='CASCADE'), primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.id', ondelete='CASCADE'), primary_key=True)

    # Definisikan relasi kembali ke induknya
    template = relationship("PsychogramTemplate", back_populates="test_associations")
    sub_aspect = relationship("SubAspect", back_populates="template_associations")
    test = relationship("Test", back_populates="template_associations")


# --- ASSOCIATION OBJECT untuk Package <-> Test (karena butuh kolom 'order') ---
class PackageTestAssociation(Base):
    __tablename__ = 'package_tests'
    test_package_id = Column(Integer, ForeignKey('test_packages.id'), primary_key=True)
    test_id = Column(Integer, ForeignKey('tests.id'), primary_key=True)
    test_order = Column(Integer, default=0, nullable=False)
    
    # Relasi dari object ini kembali ke induknya
    test = relationship("Test", back_populates="packages_association")
    package = relationship("TestPackage", back_populates="tests_association")

# --- DEFINISI MODEL UTAMA ---


# --- PERBARUI PsychogramTemplate ---
class PsychogramTemplate(Base):
    __tablename__ = "psychogram_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    passing_rule = Column(String(50), nullable=False, server_default='NO_C')

    aspects = relationship(
        "Aspect", 
        back_populates="template", 
        cascade="all, delete-orphan",
        order_by="Aspect.order"
    )
    
    # Relasi ke object asosiasi
    test_associations = relationship("TemplateSubAspectTest", back_populates="template", cascade="all, delete-orphan")
    
    # Hapus relasi lama yang tidak terpakai
    # tests = relationship("Test", secondary=template_tests_association, ...)


class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    scoring_module = Column(String(50), nullable=True, default='default', server_default='default')
    duration_minutes = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, default=True, server_default='1', nullable=False)
    require_all_answers = Column(Boolean, default=False, server_default='0', nullable=False)
    memorization_duration_seconds = Column(Integer, nullable=True)
    stimulus_text = Column(Text, nullable=True)
    stimulus_image_url = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # --- RELASI DUA ARAH ---
    packages_association = relationship("PackageTestAssociation", back_populates="test")
    template_associations = relationship("TemplateSubAspectTest", back_populates="test")

class TestPackage(Base):
    __tablename__ = "test_packages"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    access_code = Column(String(50), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    gerai_id = Column(Integer, ForeignKey("gerai.id"), nullable=True)
    gerai = relationship("Gerai", back_populates="packages")
    psychogram_template_id = Column(Integer, ForeignKey("psychogram_templates.id"), nullable=True)
    
    psychogram_template = relationship("PsychogramTemplate")

    owner_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True) # Dibuat nullable untuk data lama
    owner = relationship("AdminUser", back_populates="owned_packages")
 # --- RELASI UTAMA KE TEST MELALUI ASSOCIATION OBJECT ---
    tests_association = relationship(
        "PackageTestAssociation",
        order_by="PackageTestAssociation.test_order",
        back_populates="package",
        cascade="all, delete-orphan"
    )

    # Properti 'tests' ini hanya untuk kemudahan membaca, TIDAK didefinisikan sebagai relationship
    @property
    def tests(self):
        return [assoc.test for assoc in self.tests_association]
        
    participants = relationship("Participant", back_populates="package")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"))
    text = Column(Text, nullable=False)
    order = Column(Integer, nullable=False)
    is_example = Column(Boolean, default=False, server_default='0', nullable=False)
    image_url = Column(String(255), nullable=True)
    question_type = Column(String(50), nullable=False, server_default='multiple_choice')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    test = relationship("Test")
    options = relationship("AnswerOption", back_populates="question", cascade="all, delete-orphan")

class AnswerOption(Base):
    __tablename__ = "answer_options"
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    text = Column(String(255), nullable=False)
    score = Column(Integer, default=0)
    category = Column(String(50), nullable=True) # Tambahan untuk DISC (D/I/S/C/*)
    is_correct = Column(Boolean, default=False, server_default='0', nullable=False)
    image_url = Column(String(255), nullable=True)
    question = relationship("Question", back_populates="options")

# --- MODEL DATA PESERTA & HASIL ---
class Participant(Base):
    __tablename__ = "participants"
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    test_number = Column(String(50), nullable=False)
    birth_date = Column(Date, nullable=True)
    registration_number = Column(String(50), nullable=True)
    job = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    sim_type = Column(String(50), nullable=True)
    sim_status = Column(String(50), nullable=True) # Baru atau Perpanjangan
    test_location = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    test_package_id = Column(Integer, ForeignKey("test_packages.id"))
    package = relationship("TestPackage", back_populates="participants")
    sessions = relationship("TestSession", back_populates="participant", cascade="all, delete-orphan")
    results = relationship("TestResult", back_populates="participant")
    __table_args__ = (UniqueConstraint('test_number', 'test_package_id', name='_test_number_package_uc'),)

class TestSession(Base):
    __tablename__ = "test_sessions"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default='not_started')
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    score = Column(Integer, nullable=True)
    participant_id = Column(Integer, ForeignKey("participants.id"))
    test_id = Column(Integer, ForeignKey("tests.id"))
    participant = relationship("Participant", back_populates="sessions")
    test = relationship("Test")

class ParticipantAnswer(Base):
    __tablename__ = "participant_answers"
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("participants.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    selected_option_id = Column(Integer, ForeignKey("answer_options.id"), nullable=True)
    answer_text = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)
    participant = relationship("Participant")
    question = relationship("Question")
    selected_option = relationship("AnswerOption")


class TestResult(Base):
    __tablename__ = "test_results"
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("participants.id"))
    test_package_id = Column(Integer, ForeignKey("test_packages.id"))
    
    # Kolom yang baru saja ditambah via SQL:
    target_position = Column(String(255), nullable=True)
    iq_score = Column(Integer, nullable=True)
    iq_category = Column(String(100), nullable=True)
    iq_narrative = Column(Text, nullable=True)
    competency_scores = Column(Text, nullable=True) 
    career_interests = Column(Text, nullable=True)
    personality_type = Column(String(50), nullable=True)
    personality_narrative = Column(Text, nullable=True)
    strengths_list = Column(Text, nullable=True)
    weaknesses_list = Column(Text, nullable=True)
    overall_score = Column(String(50), nullable=True) # Nilai % atau Kesimpulan
    conclusion = Column(String(100), nullable=True) # e.g. Disarankan
    development_suggestions = Column(Text, nullable=True)
    
    interpretation_summary = Column(Text, nullable=True) # JSON Psikogram R-T
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    psychologist_notes = Column(Text, nullable=True)
    
    result_type = Column(String(50), nullable=True, default='automatic') # 'automatic' atau 'manual'
    setu_status = Column(String(50), nullable=True) # 'Terkirim', 'Gagal', dll.

    participant = relationship("Participant")
    test_package = relationship("TestPackage")



class InterpretationRule(Base):
    __tablename__ = "interpretation_rules"
    id = Column(Integer, primary_key=True, index=True)
#    test_id = Column(Integer, ForeignKey("tests.id"))
    min_score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)
    sub_aspect_id = Column(Integer, ForeignKey("sub_aspects.id")) # <-- GANTI DENGAN INI
    interpretation_text = Column(Text, nullable=False)
    category = Column(String(10), nullable=True)
#    test = relationship("Test")


class Gerai(Base):
    __tablename__ = "gerai"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    address = Column(Text, nullable=True)

    # Relasi balik ke admin dan paket
    admins = relationship("AdminUser", back_populates="gerai")
    packages = relationship("TestPackage", back_populates="gerai")

# --- MODEL NORMA & SKORING ---
class NormTable(Base):
    __tablename__ = "norm_tables"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    data = relationship("NormData", back_populates="norm_table", cascade="all, delete-orphan")

class NormData(Base):
    __tablename__ = "norm_data"
    id = Column(Integer, primary_key=True, index=True)
    norm_table_id = Column(Integer, ForeignKey("norm_tables.id", ondelete="CASCADE"))
    raw_score_min = Column(Integer, nullable=False)
    raw_score_max = Column(Integer, nullable=False)
    standard_score = Column(Integer, nullable=False)
    category = Column(String(50), nullable=True) # A/B/C/R/K/T dll jika langsung dari norma
    
    norm_table = relationship("NormTable", back_populates="data")

class ScoringMapping(Base):
    __tablename__ = "scoring_mappings"
    id = Column(Integer, primary_key=True, index=True)
    psychogram_template_id = Column(Integer, ForeignKey("psychogram_templates.id", ondelete="CASCADE"))
    sub_aspect_id = Column(Integer, ForeignKey("sub_aspects.id", ondelete="CASCADE"), nullable=True) # Null jika untuk IQ atau skor khusus
    target_type = Column(String(50), nullable=False, server_default='sub_aspect') # 'sub_aspect', 'iq', 'overall'
    formula_expression = Column(Text, nullable=False) # e.g., "[TEST_1_RAW] * 2" or "NORM([TEST_1_RAW], 1)" (1 is NormTable ID)
    norm_table_id = Column(Integer, ForeignKey("norm_tables.id", ondelete="SET NULL"), nullable=True) # Opsional tabel norma akhir
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    template = relationship("PsychogramTemplate")
    sub_aspect = relationship("SubAspect")
    norm_table = relationship("NormTable")



# --- MODEL ADMIN ---
class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(50), nullable=False, server_default='admin')

    gerai_id = Column(Integer, ForeignKey("gerai.id"), nullable=True)
    gerai = relationship("Gerai", back_populates="admins")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # --- TAMBAHKAN HIERARKI ---
    parent_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    
    # Relasi untuk melihat siapa saja bawahannya
    children = relationship("AdminUser", back_populates="parent")
    # Relasi untuk melihat siapa atasannya
    parent = relationship("AdminUser", remote_side=[id], back_populates="children")
    
    # --- TAMBAHKAN KOLOM PROFIL INI ---
    full_name = Column(String(100), nullable=True) # Nama lengkap untuk TTD
    sipp_number = Column(String(50), nullable=True)  # Nomor SIPP
    city = Column(String(100), nullable=True)        # Kota
    signature_image_url = Column(String(255), nullable=True) # URL gambar TTD
    owned_packages = relationship("TestPackage", back_populates="owner")


    

    # -----------------------------------


    # backend/models.py

# ... (import dan model lain)

# --- 1. BUAT TABEL ASOSIASI BARU ---
aspect_subaspects_association = Table(
    'aspect_subaspects', Base.metadata,
    Column('aspect_id', Integer, ForeignKey('aspects.id'), primary_key=True),
    Column('sub_aspect_id', Integer, ForeignKey('sub_aspects.id'), primary_key=True)
)


class Aspect(Base):
    __tablename__ = "aspects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    order = Column(Integer, default=0, nullable=False)
    template_id = Column(Integer, ForeignKey("psychogram_templates.id"))
    
    # --- PASTIKAN RELASI 'template' INI ADA DAN BENAR ---
    template = relationship(
        "PsychogramTemplate", 
        back_populates="aspects" # <-- Menunjuk kembali ke 'aspects' di PsychogramTemplate
    )
    # ----------------------------------------------------
    
    sub_aspects = relationship(
        "SubAspect",
        secondary=aspect_subaspects_association,
        back_populates="aspects"
    )
    
    __table_args__ = (UniqueConstraint('name', 'template_id', name='_name_template_uc'),)


class SubAspect(Base):
    __tablename__ = "sub_aspects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    minimum_category = Column(String(10), nullable=False, server_default='B')
    
    aspects = relationship(
        "Aspect",
        secondary=aspect_subaspects_association,
        back_populates="sub_aspects"
    )

    # Relasi balik dari object asosiasi
    template_associations = relationship("TemplateSubAspectTest", back_populates="sub_aspect")
    
    # Hapus relasi lama ke Test
    # tests = relationship("Test", secondary=subaspect_tests_association, ...)
