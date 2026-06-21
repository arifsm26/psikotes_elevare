# backend/scoring/base.py

from typing import List, Dict, Any

class BaseScorer:
    """
    Kelas dasar untuk logika skoring. 
    Setiap tes spesifik (IST, PAPI, dll) harus mewarisi kelas ini
    dan mengimplementasikan fungsi calculate_score.
    """
    
    @classmethod
    def calculate_score(cls, participant_answers: List[Any], test_package_id: int, participant_id: int, db_session) -> Dict[str, Any]:
        """
        Fungsi utama untuk menghitung skor.
        
        Args:
            participant_answers: List dari ParticipantAnswer (jawaban user)
            test_package_id: ID dari TestPackage (untuk akses ke PsychogramTemplate dll)
            participant_id: ID peserta
            db_session: Session SQLAlchemy untuk query ke DB jika butuh ambil norma dll
            
        Returns:
            Dictionary berisi hasil skoring seperti iq_score, score_per_aspect, status, dll.
        """
        # Implementasi default (misal: hanya hitung jumlah benar)
        correct_count = 0
        for ans in participant_answers:
            if ans.selected_option and ans.selected_option.is_correct:
                correct_count += 1
        
        return {
            "total_correct": correct_count,
            "overall_score": str(correct_count),
            "status": "completed"
        }
