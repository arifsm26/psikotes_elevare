import os
import json
from datetime import date
from typing import List, Dict, Any
from .base import BaseScorer
from models import Participant

# Memuat data JSON sekali saat modul di-import untuk performa maksimal
NORMS_DIR = os.path.join(os.path.dirname(__file__), 'norms')

try:
    with open(os.path.join(NORMS_DIR, 'ist_rw_to_sw.json'), 'r') as f:
        IST_RW_TO_SW = json.load(f)
    with open(os.path.join(NORMS_DIR, 'ist_gest_to_ss.json'), 'r') as f:
        IST_GEST_TO_SS = json.load(f)
    with open(os.path.join(NORMS_DIR, 'ist_ss_to_iq.json'), 'r') as f:
        IST_SS_TO_IQ = json.load(f)
except Exception as e:
    print(f"ERROR loading IST norms: {e}")
    IST_RW_TO_SW, IST_GEST_TO_SS, IST_SS_TO_IQ = {}, {}, {}

class ISTScorer(BaseScorer):
    """
    Modul skoring khusus untuk Intelligenz Struktur Test (IST).
    Menghitung RW (Raw Score), mengkonversi ke SW (Standardized Score) berdasarkan norma usia,
    lalu menjumlahkan SW untuk mendapatkan skor IQ.
    """
    
    @staticmethod
    def _calculate_age(birth_date: date) -> int:
        if not birth_date:
            return 25 # Default usia rata-rata pekerja (Group A)
        today = date.today()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    @staticmethod
    def _get_group(age: int) -> str:
        if age <= 20: return 'C'
        if 21 <= age <= 25: return 'A'
        if 26 <= age <= 30: return 'B'
        if 31 <= age <= 35: return 'D'
        if 36 <= age <= 40: return 'E'
        if 41 <= age <= 45: return 'F'
        if 46 <= age <= 50: return 'G'
        return 'H'

    @staticmethod
    def _get_subtest(order: int) -> str:
        if 1 <= order <= 20: return 'SE'
        if 21 <= order <= 40: return 'WA'
        if 41 <= order <= 60: return 'AN'
        if 61 <= order <= 76: return 'GE'
        if 77 <= order <= 96: return 'RA'
        if 97 <= order <= 116: return 'ZR'
        if 117 <= order <= 136: return 'FA'
        if 137 <= order <= 156: return 'WU'
        if 157 <= order <= 176: return 'ME'
        return None

    @staticmethod
    def _get_iq_category(iq: int) -> str:
        if iq >= 130: return "Sangat Superior"
        if iq >= 120: return "Superior"
        if iq >= 110: return "Diatas Rata-rata"
        if iq >= 90: return "Rata-rata"
        if iq >= 80: return "Dibawah Rata-rata"
        if iq >= 70: return "Borderline"
        return "Cacat Mental"

    @classmethod
    def calculate_score(cls, participant_answers: List[Any], test_package_id: int, participant_id: int, db_session) -> Dict[str, Any]:
        # 1. Ambil usia peserta & tentukan Group
        participant = db_session.query(Participant).filter(Participant.id == participant_id).first()
        age = cls._calculate_age(participant.birth_date if participant else None)
        group = cls._get_group(age)

        # 2. Hitung Raw Score (RW) per subtes
        rw_scores = {'SE': 0, 'WA': 0, 'AN': 0, 'GE': 0, 'ME': 0, 'RA': 0, 'ZR': 0, 'FA': 0, 'WU': 0}
        total_correct = 0

        # Kumpulkan jawaban berdasarkan question_id
        answers_by_q = {}
        for ans in participant_answers:
            if not ans.question: continue
            qid = ans.question.id
            if qid not in answers_by_q:
                answers_by_q[qid] = {'question': ans.question, 'selected_options': []}
            if ans.selected_option:
                answers_by_q[qid]['selected_options'].append(ans.selected_option)

        for qid, qdata in answers_by_q.items():
            question = qdata['question']
            selected_opts = qdata['selected_options']
            subtest = cls._get_subtest(question.order)
            
            if not subtest:
                continue

            if question.question_type == 'multiple_answer':
                correct_options_count = sum(1 for opt in question.options if opt.score > 0)
                selected_correct = sum(1 for opt in selected_opts if opt.score > 0)
                selected_wrong = sum(1 for opt in selected_opts if opt.score <= 0)
                
                # Syarat mendapat nilai 1: pilih semua opsi yang benar, dan tidak ada yang salah
                if correct_options_count > 0 and selected_correct == correct_options_count and selected_wrong == 0:
                    rw_scores[subtest] += 1
                    total_correct += 1
            else:
                # Untuk soal biasa (multiple_choice, dll)
                if selected_opts and (selected_opts[0].score > 0 or selected_opts[0].is_correct):
                    rw_scores[subtest] += 1
                    total_correct += 1

        # 3. Konversi RW ke SW
        sw_scores = {}
        gest_ws = 0
        group_rw_to_sw = IST_RW_TO_SW.get(group, {})
        
        for subtest, rw in rw_scores.items():
            rw_str = str(rw)
            if rw_str in group_rw_to_sw:
                sw_val = group_rw_to_sw[rw_str].get(subtest, 0)
                sw_scores[subtest] = sw_val
                gest_ws += sw_val
            else:
                sw_scores[subtest] = 0

        gest_ws_int = int(gest_ws)

        # 4. Konversi GEST_ws ke SS
        ss_val = 0
        group_gest_to_ss = IST_GEST_TO_SS.get(group, {})
        gest_str = str(gest_ws_int)
        
        if gest_str in group_gest_to_ss:
            ss_val = int(group_gest_to_ss[gest_str])
        else:
            # Fallback jika tidak ada exact match (cari yang terdekat)
            available_gests = [int(k) for k in group_gest_to_ss.keys()]
            if available_gests:
                nearest_gest = min(available_gests, key=lambda x: abs(x - gest_ws_int))
                ss_val = int(group_gest_to_ss[str(nearest_gest)])

        # 5. Konversi SS ke IQ
        iq_val = 100
        ss_str = str(ss_val)
        if ss_str in IST_SS_TO_IQ:
            iq_val = IST_SS_TO_IQ[ss_str].get('IQ', 100)
        else:
            # Fallback
            available_ss = [int(k) for k in IST_SS_TO_IQ.keys()]
            if available_ss:
                nearest_ss = min(available_ss, key=lambda x: abs(x - ss_val))
                iq_val = IST_SS_TO_IQ[str(nearest_ss)].get('IQ', 100)

        # 6. Hasil Akhir
        return {
            "total_correct": total_correct,
            "iq_score": iq_val,
            "iq_category": cls._get_iq_category(iq_val),
            "overall_score": str(iq_val),
            "details": {
                "group": group,
                "age": age,
                "raw_scores": rw_scores,
                "standard_scores": sw_scores,
                "gest_ws": gest_ws,
                "ss": ss_val
            }
        }
