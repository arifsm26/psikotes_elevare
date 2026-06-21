from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def upgrade_category_length():
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE norm_data MODIFY COLUMN category VARCHAR(50);"))
        db.commit()
        print("✅ SUKSES: Kapasitas teks kategori berhasil diperbesar menjadi 50 karakter!")
    except Exception as e:
        print(f"❌ GAGAL: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_category_length()
