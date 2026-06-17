import asyncio
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Question, AnswerOption

# Mapping 24 pertanyaan standar DISC MMI beserta pilihan dan kategorinya
disc_questions = [
    [
        ("Gampangan, Mudah setuju", "S"),
        ("Percaya, Mudah percaya pada orang", "I"),
        ("Petualang, Mengambil resiko", "D"),
        ("Toleran, Menghormati", "C"),
    ],
    [
        ("Lembut suara, Pendiam", "S"),
        ("Optimistik, Visioner", "I"),
        ("Pusat Perhatian, Suka gaul", "*"),
        ("Pendamai, Membawa Harmoni", "C"),
    ],
    [
        ("Menyemangati orang", "I"),
        ("Berusaha sempurna", "C"),
        ("Bagian dari kelompok", "S"),
        ("Ingin membuat tujuan", "D"),
    ],
    [
        ("Menjadi frustrasi", "D"),
        ("Menyimpan perasaan saya", "S"),
        ("Menceritakan sisi saya", "I"),
        ("Siap beroposisi", "C"),
    ],
    [
        ("Hidup, Suka bicara", "I"),
        ("Gerak cepat, Tekun", "D"),
        ("Usaha menjaga keseimbangan", "S"),
        ("Usaha mengikuti aturan", "C"),
    ],
    [
        ("Kelola waktu secara efisien", "C"),
        ("Sering terburu-buru, Merasa tertekan", "D"),
        ("Masalah sosial itu penting", "I"),
        ("Suka selesaikan apa yang saya mulai", "S"),
    ],
    [
        ("Tolak perubahan mendadak", "S"),
        ("Cenderung janji berlebihan", "I"),
        ("Tarik diri di tengah tekanan", "C"),
        ("Tidak takut bertempur", "D"),
    ],
    [
        ("Penyemangat yang baik", "I"),
        ("Pendengar yang baik", "S"),
        ("Penganalisa yang baik", "C"),
        ("Delegator yang baik", "D"),
    ],
    [
        ("Hasil adalah penting", "D"),
        ("Lakukan dengan benar, Akurasi penting", "C"),
        ("Dibuat menyenangkan", "I"),
        ("Mari kerjakan bersama", "S"),
    ],
    [
        ("Akan berjalan terus tanpa kontrol diri", "D"),
        ("Akan membeli sesuai dorongan hati", "I"),
        ("Akan menunggu, Tanpa tekanan", "S"),
        ("Akan mengusahakan yang kuinginkan", "*"),
    ],
    [
        ("Ramah, Mudah bergabung", "I"),
        ("Unik, Bosan rutinitas", "D"),
        ("Aktif mengubah sesuatu", "D"),
        ("Ingin hal-hal pasti", "C"),
    ],
    [
        ("Tidak mudah dikalahkan", "D"),
        ("Kerjakan sesuai perintah, Ikut pimpinan", "C"),
        ("Mudah terangsang, Riang", "I"),
        ("Ingin segalanya teratur, Rapi", "S"),
    ],
    [
        ("Saya akan pimpin mereka", "D"),
        ("Saya akan ikuti mereka", "S"),
        ("Saya akan pengaruhi mereka", "I"),
        ("Saya akan atur mereka", "C"),
    ],
    [
        ("Kebaikan, Kasih sayang", "S"),
        ("Keadilan, Persamaan", "C"),
        ("Kebebasan, Kemerdekaan", "D"),
        ("Kesenangan, Kebahagiaan", "I"),
    ],
    [
        ("Pendidikan, Kebudayaan", "C"),
        ("Prestasi, Ganjaran", "D"),
        ("Keselamatan, keamanan", "S"),
        ("Sosial, Perkumpulan kelompok", "I"),
    ],
    [
        ("Memimpin, Pendekatan langsung", "D"),
        ("Suka bergaul, Antusias", "I"),
        ("Dapat diramal, Konsisten", "S"),
        ("Waspada, Hati-hati", "C"),
    ],
    [
        ("Pikirkan orang lain dahulu", "S"),
        ("Kompetitif, Suka tantangan", "D"),
        ("Optimis, Positif", "I"),
        ("Pemikir logis, Sistematis", "C"),
    ],
    [
        ("Menyenangkan, Suka berteman", "I"),
        ("Menyenangkan, Teliti", "C"),
        ("Menyenangkan, Lembut", "S"),
        ("Menyenangkan, Berani", "D"),
    ],
    [
        ("Suka tantangan baru", "D"),
        ("Suka hal-hal detail", "C"),
        ("Suka lingkungan stabil", "S"),
        ("Suka bicara depan umum", "I"),
    ],
    [
        ("Menganalisa data", "C"),
        ("Memotivasi orang", "I"),
        ("Mengambil keputusan cepat", "D"),
        ("Mendengarkan keluhan", "S"),
    ],
    [
        ("Takut perubahan", "S"),
        ("Takut ditolak", "I"),
        ("Takut kegagalan", "C"),
        ("Takut kehilangan kendali", "D"),
    ],
    [
        ("Kekuatan saya: Empati", "S"),
        ("Kekuatan saya: Ketegasan", "D"),
        ("Kekuatan saya: Keakuratan", "C"),
        ("Kekuatan saya: Persuasi", "I"),
    ],
    [
        ("Bekerja dengan instruksi jelas", "C"),
        ("Bekerja dengan target menantang", "D"),
        ("Bekerja dengan tim yang ramah", "I"),
        ("Bekerja di lingkungan tenang", "S"),
    ],
    [
        ("Suka kebebasan aturan", "I"),
        ("Suka aturan jelas", "C"),
        ("Suka kecepatan", "D"),
        ("Suka keharmonisan", "S"),
    ],
]

def inject_disc_questions():
    db: Session = SessionLocal()
    try:
        print("Mulai injeksi data soal DISC...")
        
        for i, q_options in enumerate(disc_questions):
            # Create the question
            new_q = Question(
                text=f"Pernyataan Diri (DISC) - {i+1}",
                question_type="disc",
                order=i+1,
                test_id=None # Harusnya di-assign ke test tertentu, tapi untuk master kita biarkan null atau Anda bisa assign di admin
            )
            db.add(new_q)
            db.commit()
            db.refresh(new_q)
            
            # Create options
            for opt_text, opt_cat in q_options:
                new_opt = AnswerOption(
                    question_id=new_q.id,
                    text=opt_text,
                    is_correct=False,
                    score=0.0,
                    category=opt_cat
                )
                db.add(new_opt)
            
            db.commit()
            print(f"Soal DISC {i+1} berhasil diinjeksi.")
            
        print("Injeksi selesai!")
        
    except Exception as e:
        db.rollback()
        print(f"Terjadi kesalahan: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    inject_disc_questions()
