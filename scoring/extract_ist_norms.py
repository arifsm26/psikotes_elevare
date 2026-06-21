import pandas as pd
import json
import os

file_path = '/Users/arifsm/Documents/Projects/psikotes_elevare/Rekap Psikogram skoring_YPIA_2025  (2).xlsx'
output_dir = '/Users/arifsm/Documents/Projects/psikotes_elevare/backend/scoring/norms'

def extract_norms():
    try:
        print("Reading Excel file...")
        df = pd.read_excel(file_path, sheet_name='Norma IST')
        
        # 1. RW to SW
        rw_to_sw = {}
        for index, row in df.iterrows():
            group_rs = str(row.iloc[3]).strip()
            if len(group_rs) >= 2 and group_rs[0] in 'ABCDEFGH':
                group = group_rs[0]
                try:
                    rs = str(int(row.iloc[4]))
                    if group not in rw_to_sw:
                        rw_to_sw[group] = {}
                    rw_to_sw[group][rs] = {
                        'SE': float(row.iloc[5]) if pd.notna(row.iloc[5]) else 0,
                        'WA': float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0,
                        'AN': float(row.iloc[7]) if pd.notna(row.iloc[7]) else 0,
                        'GE': float(row.iloc[8]) if pd.notna(row.iloc[8]) else 0,
                        'ME': float(row.iloc[9]) if pd.notna(row.iloc[9]) else 0,
                        'RA': float(row.iloc[10]) if pd.notna(row.iloc[10]) else 0,
                        'ZR': float(row.iloc[11]) if pd.notna(row.iloc[11]) else 0,
                        'FA': float(row.iloc[12]) if pd.notna(row.iloc[12]) else 0,
                        'WU': float(row.iloc[13]) if pd.notna(row.iloc[13]) else 0,
                    }
                except ValueError:
                    pass

        with open(os.path.join(output_dir, 'ist_rw_to_sw.json'), 'w') as f:
            json.dump(rw_to_sw, f, indent=4)
        print(f"Extracted RW to SW: {len(rw_to_sw)} groups")

        # 2. GEST_ws to SS
        gest_to_ss = {'A':{}, 'B':{}, 'C':{}, 'D':{}, 'E':{}, 'F':{}, 'G':{}, 'H':{}}
        group_col_mapping = {'A': 17, 'B': 19, 'C': 21, 'D': 23, 'E': 25, 'F': 27, 'G': 29, 'H': 31}
        
        for index, row in df.iterrows():
            gest_val = row.iloc[15]
            try:
                gest_ws = str(int(gest_val))
                for g, col_idx in group_col_mapping.items():
                    ss_val = row.iloc[col_idx]
                    if pd.notna(ss_val):
                        gest_to_ss[g][gest_ws] = float(ss_val)
            except ValueError:
                pass

        with open(os.path.join(output_dir, 'ist_gest_to_ss.json'), 'w') as f:
            json.dump(gest_to_ss, f, indent=4)
        print(f"Extracted GEST to SS for 8 groups")

        # 3. SS to IQ
        ss_to_iq = {}
        for index, row in df.iterrows():
            try:
                ss = str(int(row.iloc[33]))
                iq = float(row.iloc[34])
                persentil = float(row.iloc[35]) if pd.notna(row.iloc[35]) else 0
                ss_to_iq[ss] = {'IQ': int(iq), 'PERSENTIL': int(persentil)}
            except ValueError:
                pass
        
        with open(os.path.join(output_dir, 'ist_ss_to_iq.json'), 'w') as f:
            json.dump(ss_to_iq, f, indent=4)
        print(f"Extracted SS to IQ: {len(ss_to_iq)} records")

    except Exception as e:
        print(f"Error extracting norms: {e}")

if __name__ == "__main__":
    extract_norms()
