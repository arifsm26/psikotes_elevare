# backend/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- 1. TAMBAHKAN IMPORT INI ---
from fastapi.middleware.cors import CORSMiddleware
# -----------------------------

from admin_router import router as admin_router
from participant_router import router as participant_router

app = FastAPI(
    title="Psikotes API",
    description="API untuk platform psikotes online.",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

from database import engine
from sqlalchemy import text

@app.on_event("startup")
def run_migrations():
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE participant_answers ADD COLUMN score INT NULL;"))
            print("Successfully added 'score' column to participant_answers.")
    except Exception as e:
        # Ignore if column already exists
        print("Column 'score' may already exist or another error occurred:", str(e))


# --- 2. TAMBAHKAN BLOK KONFIGURASI CORS DI SINI ---
# Definisikan origin yang diizinkan
origins = [
    "http://localhost",
    "http://localhost:8080", # Izinkan server development Vue
    "http://148.230.97.203", # Izinkan dari IP server itu sendiri (jika frontend juga di sana)
    # Tambahkan domain produksi Anda di sini nanti, misal: "https://www.psikotesonline.id"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Izinkan semua metode (GET, POST, dll.)
    allow_headers=["*"], # Izinkan semua header
)
# ----------------------------------------------------


# Mount static files (ini sudah ada)
app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(admin_router, prefix="/api")
app.include_router(participant_router, prefix="/api")