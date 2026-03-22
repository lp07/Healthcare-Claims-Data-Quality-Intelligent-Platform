# Healthcare Claims Data Quality Intelligence Platform

A production-grade EDI 837 claim validation engine that enforces field-level rules, payer-specific adjudication requirements, and revenue integrity checks across multi-payer healthcare claim submissions.

Built from direct experience with real-world RCM operations — specifically the failure patterns that cause the most preventable revenue loss: NPI errors, diagnosis pointer mismatches, timely filing violations, and payer-specific field gaps.

---

## The Problem This Solves

Healthcare billing teams lose significant revenue to **preventable technical denials** — claims rejected by payers not because care wasn't medically necessary, but because a field was wrong, missing, or didn't match payer-specific formatting rules.

The standard workflow at most practices:
1. Submit claim to payer portal
2. Claim gets rejected (sometimes days later)
3. Billing team manually reviews rejection reason
4. Resubmit — now delayed by days or weeks

This platform moves validation **upstream** — before submission. Every claim runs through a rule engine that catches critical errors at the point of ingestion, not after denial.

---

## Architecture
```
┌─────────────────────┐
│   Input Claims CSV   │  ← EDI 837 field-mapped records
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Validation Engine   │  ← Base rules + payer-specific config
│  (engine.py)         │
│                      │
│  ┌───────────────┐   │
│  │  Base Rules   │   │  ← 8 universal EDI 837 field validators
│  └───────────────┘   │
│  ┌───────────────┐   │
│  │ Payer Config  │   │  ← Per-payer JSON rules (BCBS/Aetna/Cigna/Humana/Medicare)
│  └───────────────┘   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  ValidationResult    │  ← VALID / FLAGGED / REJECTED + error list
│  per claim           │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│     Reporter         │  ← 3 output formats
│                      │
│  • Full report CSV   │  ← one row per claim
│  • Error breakdown   │  ← one row per error
│  • Summary JSON      │  ← KPIs and revenue at risk
└─────────────────────┘
```

---

## Validation Rules

### Base EDI 837 Rules (Universal — all payers)

| Rule | EDI Segment | Error Code | Severity |
|------|-------------|------------|----------|
| Billing NPI present and valid (Luhn check) | NM1\*85 | NPI_001–004 | CRITICAL |
| Rendering NPI present and valid | NM1\*82 | NPI_005–006 | CRITICAL |
| Primary diagnosis code ICD-10 format | HI | DX_001–002 | CRITICAL |
| Diagnosis pointer references valid position | SV1 | DX_003–004 | CRITICAL/WARNING |
| Date of service not future, within timely filing | DTP\*472 | DATE_001–004 | CRITICAL/WARNING |
| Procedure code valid CPT or HCPCS format | SV1 | PROC_001–002 | CRITICAL |
| Billed amount greater than zero | CLM | AMT_001–002 | CRITICAL |
| Subscriber/Member ID present | NM1\*IL | SUB_001 | CRITICAL |
| Place of service valid CMS code | CLM | POS_001–002 | CRITICAL/WARNING |

### Payer-Specific Rules (from JSON config)

| Payer | Timely Filing | Additional Requirements |
|-------|--------------|------------------------|
| BCBS | 365 days | Taxonomy code required |
| Aetna | 180 days | Subscriber ID: 9 numeric digits |
| Cigna | 90 days | Prior auth number, Subscriber ID: U + 8 digits |
| Humana | 365 days | Taxonomy code, Subscriber ID: H + 8 digits + letter |
| Medicare | 365 days | Taxonomy code (NUCC), CLIA for lab claims |

---

## Sample Run Results

Validated against 1,200 synthetic claims across 5 payers:
```
============================================================
  CLAIMS VALIDATION SUMMARY
============================================================
  Total Claims:       1,200
  Valid:              668   (55.7%)
  Flagged:            55    (4.6%)
  Rejected:           477   (39.8%)
  Pass Rate:          55.67%
  Total Billed:       $2,707,848.63
  Revenue at Risk:    $1,164,308.52
  Risk %:             43.0%

  TOP ERROR CODES:
    PAYER_TF_001:  259  Timely filing limit exceeded
    NPI_002:        66  NPI contains non-numeric characters
    DX_004:         48  Invalid diagnosis pointer
    NPI_003:        48  NPI wrong length
    NPI_006:        42  Rendering NPI invalid
    DX_002:         41  ICD-10 format violation
    PROC_002:       27  Invalid CPT/HCPCS code
    AMT_002:        26  Zero billed amount
    PAYER_SUB_001:  21  Subscriber ID format mismatch
    DATE_003:       19  Future date of service
============================================================
```

---

## Project Structure
```
healthcare-claims-dq-platform/
│
├── claims_validator/
│   ├── __init__.py       # Package exports
│   ├── models.py         # ValidationResult, ValidationError, ClaimStatus
│   ├── rules.py          # 8 base EDI 837 validation rule functions
│   ├── engine.py         # Orchestration — batch processing + payer config loader
│   └── reporter.py       # CSV/JSON output generation
│
├── payer_configs/
│   ├── bcbs.json         # BCBS-specific rules
│   ├── aetna.json        # Aetna-specific rules
│   ├── cigna.json        # Cigna-specific rules
│   ├── humana.json       # Humana-specific rules
│   ├── medicare.json     # Medicare-specific rules
│   └── default.json      # Fallback for unknown payers
│
├── data/
│   ├── generate_sample_data.py   # Synthetic 837 data generator
│   └── sample_output/            # Validation reports land here
│
├── tests/
│   └── test_rules.py     # 20 unit tests across all rule functions
│
├── main.py               # CLI entry point
└── requirements.txt
```

---

## Tech Stack and Why

| Technology | Why Used |
|------------|----------|
| **Python** | Industry standard for healthcare data pipelines |
| **Pandas** | Vectorized processing of bulk claim batches |
| **Dataclasses** | Clean, typed data models without boilerplate |
| **Enums** | Type-safe status and severity values |
| **JSON configs** | Payer rules updatable without code changes |
| **Python logging** | Audit trail for every validation run |
| **pytest** | Unit test coverage on all rule functions |

---

## Design Decisions

**Why separate payer configs from rule logic:**
Payer requirements change constantly. BCBS updates its NPI format, Cigna changes its timely filing window, a new payer contract comes in. With JSON configs, rule updates require zero Python changes — the engine picks them up automatically at runtime.

**Why dataclasses for models:**
Every claim produces a ValidationResult carrying its claim ID, status, errors, and revenue impact. Dataclasses give us typed, immutable-friendly structures with auto-generated __init__ and __repr__ — no boilerplate, no inconsistency.

**Why the Luhn algorithm for NPI validation:**
CMS mandates NPI validation uses the Luhn checksum algorithm. The 10th digit of every NPI is a check digit calculated from the first 9. Every payer clearinghouse runs this check. Our engine runs the same check — claims with invalid NPIs never leave the validation layer.

**Why Open/Closed Principle for rules:**
The BASE_RULES list in rules.py is the extension point. Adding a new validation rule means adding one function and registering it in that list. The engine, reporter, and models don't change. This is how you build systems that scale without breaking.

---

## How to Run
```bash
# Clone and set up
git clone https://github.com/lp07/healthcare-claims-dq-platform.git
cd healthcare-claims-dq-platform
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate synthetic data and validate
python main.py --generate

# Validate an existing claims file
python main.py --input path/to/your/claims.csv

# Run tests
python -m pytest tests/test_rules.py -v
```

---

## Output Files

After each run, three files are written to `data/sample_output/`:

**`claims_validation_report_[timestamp].csv`** — Full claim-level results. Columns: claim_id, payer, status, billed_amount, error_count, error_codes, revenue_at_risk.

**`error_breakdown_[timestamp].csv`** — Per-error detail for every flagged/rejected claim.

**`summary_[timestamp].json`** — Aggregate KPIs: total claims, pass rate, total billed, revenue at risk, top error codes.

---

## Extending the Platform

**Add a new payer:**
Create `payer_configs/newpayer.json` with timely filing days, subscriber ID pattern, and required fields. No Python changes needed.

**Add a new validation rule:**
1. Write a function in `rules.py` that takes a claim dict and returns a list of `ValidationError` objects
2. Add the function to `BASE_RULES` list at the bottom of `rules.py`
3. Write a test in `tests/test_rules.py`

**Connect to a real data source:**
Replace the CSV load in `main.py` with a SQL query, API call, or S3 read. The engine accepts any pandas DataFrame.

---

## Domain Context

Built on direct experience processing claims across BCBS, Aetna, Cigna, Humana, and Medicare. The error patterns in this platform reflect real denial root causes observed in production RCM operations — particularly the NPI validation failures and payer-specific timely filing violations that account for the majority of preventable technical denials.

---

*All data in this repository is synthetically generated. No real patient, provider, or payer data is used.*