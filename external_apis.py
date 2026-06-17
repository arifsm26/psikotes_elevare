
# backend/external_apis.py


from typing import Tuple, List, Dict
import json
import httpx
from typing import Optional, Dict, List # Tambahkan List

from config import settings

# Inisialisasi HTTP client
if settings.SETU_API_BASE_URL:
    client = httpx.Client(base_url=settings.SETU_API_BASE_URL, timeout=15.0)
else:
    client = None
    print("SETU_API_BASE_URL tidak ditemukan di .env, client dinonaktifkan.")

_current_token: Optional[str] = None

def get_setu_token() -> Optional[str]:
    """Mengambil token JWT dari API SETU."""
    global _current_token
    if _current_token:
        # Di produksi, Anda akan memeriksa masa berlaku token di sini
        return _current_token

    print("\n--- [SETU API] Mencoba mendapatkan token baru... ---")
    payload = {
        "username": settings.SETU_API_USERNAME,
        "password": settings.SETU_API_PASSWORD,
    }
    print(f"[SETU API] Payload untuk /get_token: {payload}")
    
    try:
        response = client.post("/get_token", json=payload)
        print(f"[SETU API] Respons dari /get_token: Status={response.status_code}, Body={response.text}")
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") is True and data.get("token"):
            _current_token = data["token"]
            print(f"[SETU API] Token berhasil didapatkan: {_current_token[:15]}...")
            return _current_token
        else:
            print(f"[SETU API] GAGAL mendapatkan token dari SETU: {data.get('message')}")
            return None
    except httpx.HTTPStatusError as e:
        print(f"[SETU API] HTTP Error saat mengambil token: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print(f"[SETU API] Error tidak terduga saat mengambil token: {e}")
        return None

def send_data_to_setu(payload_list: List[Dict]) -> Tuple[bool, str]: # 1. Perbaiki tipe return
    """
    Mengirim data psikologi ke API SETU.
    Mengembalikan tuple: (sukses: bool, pesan_status: str)
    """
    global _current_token
    
    print("\n--- [SETU API] Mencoba mengirim data psikologi... ---")
    
    for attempt in range(2): # Coba maksimal 2 kali
        token = get_setu_token()
        if not token:
            msg = "Tidak bisa mengirim data karena gagal mendapatkan token."
            print(f"[SETU API] GAGAL: {msg}")
            return False, msg

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"[SETU API] Percobaan ke-{attempt + 1}. Menggunakan token: {token[:15]}...")
        print(f"[SETU API] Payload untuk /input_data: {json.dumps(payload_list, indent=2)}")

        try:
            response = client.post("/input_data", content=json.dumps(payload_list), headers=headers)
            print(f"[SETU API] Respons dari /input_data: Status={response.status_code}, Body={response.text}")
            
            # Periksa jika respons bukan JSON
            try:
                data = response.json()
            except json.JSONDecodeError:
                message = f"Gagal Parsing (Status: {response.status_code})"
                print(f"[SETU API] {message}")
                return False, message

            # Cek kondisi sukses
            if data.get("status") is True:
                print("[SETU API] SUKSES: Data berhasil dikirim.")
                return True, "Terkirim"
            
            # Cek kondisi token kadaluarsa
            elif "expired token" in data.get("message", "").lower():
                print("[SETU API] Token kadaluarsa. Menghapus token lama dan mencoba lagi...")
                _current_token = None # Hapus token lama
                # 'continue' akan membuat loop lanjut ke percobaan berikutnya
                continue 
            
            # Kondisi gagal lainnya dari API SETU
            else:
                message = data.get("message", "Unknown Error from SETU")
                print(f"[SETU API] GAGAL: {message}")
                return False, f"Gagal: {message}"

        except httpx.RequestError as e: # 2. Tangkap error koneksi
            message = f"Error Koneksi: {e.__class__.__name__}"
            print(f"[SETU API] {message}")
            # Jika ada error koneksi, tidak perlu coba lagi, langsung gagal
            return False, message

    # 3. Baris ini hanya akan tercapai jika kedua percobaan gagal karena token expired
    final_message = "Gagal (Token Error setelah 2x percobaan)"
    print(f"[SETU API] {final_message}")
    return False, final_message