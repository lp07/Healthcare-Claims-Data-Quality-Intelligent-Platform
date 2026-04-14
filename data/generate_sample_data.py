# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
generate_sample_data.py — Synthetic Claims Data Generator

Generates realistic 837 claim records for testing.
All data is synthetic — no real patient or provider information.
Intentionally injects common errors to demonstrate the validation engine.
"""

import pandas as pd
import random
from datetime import datetime, timedelta

# Verified valid NPIs — all pass CMS Luhn algorithm
VALID_NPIS = [
    "1234567893", "1679576722", "1982645297",
    "1003000126", "1144224569", "1932102084",
    "1528060639", "1891794814", "1269671339",
    "1734770807", "1846447971", "1192200818",
    "1912645326", "1094276916", "1289265203",
    "1231738505", "1540301995", "1456791494",
    "1092362080", "1966335584"
]

def generate_valid_npi():
    return random.choice(VALID_NPIS)


def generate_claims(n=1200):
    random.seed(42)

    payers = ["BCBS", "AETNA", "CIGNA", "HUMANA", "MEDICARE"]
    procedure_codes = ["99213", "99214", "99232", "93000", "71046",
                       "80053", "85025", "36415", "99283", "G0438"]
    diagnosis_codes = ["M54.5", "Z23", "I10", "E11.9", "J06.9",
                       "R05", "K21.0", "F32.1", "M79.3", "Z00.00"]
    pos_codes = ["11", "22", "21", "23", "81"]

    records = []

    for i in range(n):
        payer = random.choice(payers)
        billed = round(random.uniform(150, 4500), 2)
        dos = datetime.today() - timedelta(days=random.randint(1, 300))

        claim = {
            "claim_id": f"CLM{str(i+1).zfill(6)}",
            "patient_id": f"PAT{str(random.randint(10000, 99999))}",
            "payer": payer,
            "billing_npi": generate_valid_npi(),
            "rendering_npi": generate_valid_npi(),
            "subscriber_id": _generate_subscriber_id(payer),
            "primary_diagnosis_code": random.choice(diagnosis_codes),
            "diagnosis_pointer": random.choice(["1", "2", "A", "B"]),
            "procedure_code": random.choice(procedure_codes),
            "date_of_service": dos.strftime("%Y-%m-%d"),
            "billed_amount": billed,
            "place_of_service": random.choice(pos_codes),
            "taxonomy_code": "207Q00000X" if random.random() > 0.2 else "",
            "group_number": f"GRP{random.randint(100000, 999999)}",
            "authorization_number": f"AUTH{random.randint(100000, 999999)}" if random.random() > 0.3 else "",
            "referral_number": f"REF{random.randint(10000, 99999)}" if random.random() > 0.4 else "",
            "clia_number": f"CLIA{random.randint(10000, 99999)}" if random.random() > 0.6 else "",
        }

        # Inject realistic errors — ~30% error rate, NPI most common
        error_roll = random.random()

        if error_roll < 0.05:
            claim["billing_npi"] = ""                          # Missing NPI
        elif error_roll < 0.09:
            claim["billing_npi"] = "123456789"                 # 9 digits — invalid length
        elif error_roll < 0.13:
            claim["rendering_npi"] = ""                        # Missing rendering NPI
        elif error_roll < 0.16:
            claim["primary_diagnosis_code"] = random.choice(["999", "ABCDE", "12345"])
        elif error_roll < 0.19:
            claim["diagnosis_pointer"] = ""
        elif error_roll < 0.21:
            claim["date_of_service"] = (datetime.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        elif error_roll < 0.23:
            claim["date_of_service"] = (datetime.today() - timedelta(days=400)).strftime("%Y-%m-%d")
        elif error_roll < 0.25:
            claim["procedure_code"] = "XXXXX"
        elif error_roll < 0.27:
            claim["billed_amount"] = 0.0
        elif error_roll < 0.29:
            claim["subscriber_id"] = ""

        records.append(claim)

    return pd.DataFrame(records)


def _generate_subscriber_id(payer: str) -> str:
    if payer == "BCBS":
        letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
        digits = "".join(random.choices("0123456789", k=9))
        return letters + digits
    elif payer == "AETNA":
        return "".join(random.choices("0123456789", k=9))
    elif payer == "CIGNA":
        return "U" + "".join(random.choices("0123456789", k=8))
    elif payer == "HUMANA":
        letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        return "H" + "".join(random.choices("0123456789", k=8)) + letter
    elif payer == "MEDICARE":
        return "1A2B3C4D5E6"
    return "SUB" + "".join(random.choices("0123456789", k=8))


if __name__ == "__main__":
    df = generate_claims(1200)
    df.to_csv("data/sample_claims.csv", index=False)
    print(f"Generated {len(df)} synthetic claims → data/sample_claims.csv")
    print(f"Payer distribution:
{df['payer'].value_counts()}")
