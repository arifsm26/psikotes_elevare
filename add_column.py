from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import DATABASE_URL

# Buat engine dan koneksi langsung
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def upgrade_local_db():
    db = SessionLocal()
    try:
        # Jalankan ALTER TABLE secara langsung menggunakan text()
        db.execute(text("ALTER TABLE tests ADD COLUMN scoring_module VARCHAR(50) DEFAULT 'default';"))
        db.commit()
        print("✅ SUKSES: Kolom 'scoring_module' berhasil ditambahkan ke database lokal Anda!")
    except Exception as e:
        # Jika kolom sudah ada, abaikan errornya
        if "Duplicate column name" in str(e):
            print("✅ SUKSES: Kolom 'scoring_module' sudah ada di database lokal Anda.")
        else:
            print(f"❌ GAGAL: Terjadi kesalahan - {e}")
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_local_db()
