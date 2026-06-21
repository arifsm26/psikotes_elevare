from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def upgrade_subaspects():
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE sub_aspects ADD COLUMN description TEXT DEFAULT NULL;"))
        db.execute(text("ALTER TABLE sub_aspects ADD COLUMN low_score_description TEXT DEFAULT NULL;"))
        db.execute(text("ALTER TABLE sub_aspects ADD COLUMN high_score_description TEXT DEFAULT NULL;"))
        db.commit()
        print("✅ SUKSES: 3 Kolom deskripsi berhasil ditambahkan ke tabel sub_aspects!")
    except Exception as e:
        print(f"❌ GAGAL (Atau mungkin sudah pernah ditambahkan): {e}")
    finally:
        db.close()

if __name__ == "__main__":
    upgrade_subaspects()
