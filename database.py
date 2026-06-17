# backend/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ambil variabel langsung dari lingkungan yang disediakan Docker
# Ubah di database.py
db_user = os.getenv("MYSQL_USER")
db_password = os.getenv("MYSQL_PASSWORD")
db_name = os.getenv("MYSQL_DATABASE")
db_host ="mysql_db"



DATABASE_URL = f"mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}"

# engine = create_engine(DATABASE_URL)
engine = create_engine(
    DATABASE_URL,
#    echo=True,
    pool_size=50,         # Jumlah koneksi minimum di pool
    max_overflow=100,     # Jumlah koneksi tambahan yang bisa dibuat saat sibuk
    pool_timeout=30,      # Waktu (detik) request akan menunggu koneksi sebelum error
    pool_recycle=1800     # Daur ulang koneksi setiap 30 menit
)



SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency untuk digunakan di setiap endpoint API
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
