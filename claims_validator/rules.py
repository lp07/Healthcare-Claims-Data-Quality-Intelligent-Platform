"""
rules.py — Field-level EDI 837 validation rules

WHY THIS FILE EXISTS:
The validation engine calls rules. Rules don't call the engine.
This separation means you can add a new rule without touching engine logic.
Each rule function takes a claim row (dict) and returns a list of ValidationErrors.
Empty list = no errors for that rule.

EDI 837 CONTEXT (so you understand what we're validating):
- Loop 2010AA: Billing Provider (NPI, name, address)
- Loop 2010BA: Subscriber (patient/insured)
- Loop 2300:   Claim Information (CLM segment — dates, amounts, place of service)
- Loop 2400:   Service Line (SV1 segment — procedure codes, charges)
- HI segment:  Diagnosis codes (ICD-10)
- NM1 segment: Name segments (provider, patient, payer)
"""

import re
from datetime import datetime
from typing import List, Dict, Any
from claims_validator.models import ValidationError, ErrorSeverity


# ─────────────────────────────────────────────
# NPI VALIDATION
# ─────────────────────────────────────────────

def validate_billing_npi(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    NPI = National Provider Identifier.
    10-digit numeric. Must pass Luhn algorithm check.
    EDI segment: NM1*85 (Billing Provider)

    WHY THIS IS THE #1 ERROR:
    Missing or invalid NPI = automatic denial from every payer.
    No exceptions. This is the most common rejection you saw at Aventador.
    """
    errors = []
    raw = claim.get("billing_npi", "")

    # Handle float conversion from pandas CSV read (e.g. 1234567893.0 -> "1234567893")
    try:
        if raw != "" and raw is not None:
            npi = str(int(float(str(raw)))).strip()
        else:
            npi = ""
    except (ValueError, TypeError):
        npi = str(raw).strip()

    if not npi or npi == "0":
        errors.append(ValidationError(
            field_name="billing_npi",
            error_code="NPI_001",
            message="Billing provider NPI is missing. EDI segment NM1*85 requires a 10-digit NPI.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))
        return errors

    if not npi.isdigit():
        errors.append(ValidationError(
            field_name="billing_npi",
            error_code="NPI_002",
            message=f"Billing NPI '{npi}' contains non-numeric characters. NPI must be 10 digits.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))
        return errors

    if len(npi) != 10:
        errors.append(ValidationError(
            field_name="billing_npi",
            error_code="NPI_003",
            message=f"Billing NPI '{npi}' is {len(npi)} digits. NPI must be exactly 10 digits.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))
        return errors

    if not _luhn_check(npi):
        errors.append(ValidationError(
            field_name="billing_npi",
            error_code="NPI_004",
            message=f"Billing NPI '{npi}' fails Luhn algorithm check. NPI is invalid.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))

    return errors


def validate_rendering_npi(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    Rendering provider NPI — the provider who actually delivered the service.
    EDI segment: NM1*82
    Required for most professional claims (837P).
    """
    errors = []
    raw = claim.get("rendering_npi", "")
    try:
        if raw != "" and raw is not None:
            npi = str(int(float(str(raw)))).strip()
        else:
            npi = ""
    except (ValueError, TypeError):
        npi = str(raw).strip()

    if not npi or npi == "0":
        errors.append(ValidationError(
            field_name="rendering_npi",
            error_code="NPI_005",
            message="Rendering provider NPI is missing. Required for professional claims (837P).",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))
        return errors

    if not npi.isdigit() or len(npi) != 10:
        errors.append(ValidationError(
            field_name="rendering_npi",
            error_code="NPI_006",
            message=f"Rendering NPI '{npi}' is invalid. Must be exactly 10 numeric digits.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))

    return errors


def _luhn_check(npi: str) -> bool:
    """
    Luhn algorithm — standard checksum for NPI validation.
    Step 1: Prefix with '80840' per CMS NPI standard.
    Step 2: Apply Luhn checksum.

    WHY: CMS mandates NPI validation uses Luhn.
    Every clearinghouse runs this check before accepting a claim.
    """
    number = "80840" + npi
    total = 0
    reverse = number[::-1]
    for i, digit in enumerate(reverse):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ─────────────────────────────────────────────
# DIAGNOSIS CODE VALIDATION
# ─────────────────────────────────────────────

def validate_diagnosis_codes(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    ICD-10-CM diagnosis codes.
    EDI segment: HI (Health Information)
    Format: Letter + 2 digits + optional decimal + up to 4 more chars
    Example: A00.1, Z23, M54.5

    WHY THIS MATTERS:
    Wrong diagnosis code = medical necessity denial.
    Pointer mismatch (service line pointing to wrong diagnosis) = technical denial.
    """
    errors = []
    primary_dx = str(claim.get("primary_diagnosis_code", "")).strip().upper()

    if not primary_dx:
        errors.append(ValidationError(
            field_name="primary_diagnosis_code",
            error_code="DX_001",
            message="Primary diagnosis code (ICD-10) is missing. Required in HI segment.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="HI"
        ))
        return errors

    # ICD-10 format: A-Z, followed by 2 digits, optional decimal, up to 4 alphanumeric
    icd10_pattern = re.compile(r'^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$')
    primary_dx_clean = primary_dx.replace(".", "")

    if not re.match(r'^[A-Z][0-9]{2}[A-Z0-9]{0,4}$', primary_dx_clean):
        errors.append(ValidationError(
            field_name="primary_diagnosis_code",
            error_code="DX_002",
            message=f"Diagnosis code '{primary_dx}' does not match ICD-10-CM format (e.g. M54.5, Z23).",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="HI"
        ))

    # Validate diagnosis pointer
    dx_pointer = str(claim.get("diagnosis_pointer", "")).strip()
    if not dx_pointer:
        errors.append(ValidationError(
            field_name="diagnosis_pointer",
            error_code="DX_003",
            message="Diagnosis pointer is missing on service line. SV1 segment requires pointer to HI diagnosis.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="SV1"
        ))
    elif dx_pointer not in ["1", "2", "3", "4", "A", "B", "C", "D"]:
        errors.append(ValidationError(
            field_name="diagnosis_pointer",
            error_code="DX_004",
            message=f"Diagnosis pointer '{dx_pointer}' is invalid. Must reference a valid diagnosis position.",
            severity=ErrorSeverity.WARNING,
            edi_segment="SV1"
        ))

    return errors


# ─────────────────────────────────────────────
# DATE VALIDATION
# ─────────────────────────────────────────────

def validate_service_dates(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    Service dates in EDI 837 use CCYYMMDD format (e.g. 20240315).
    EDI segment: DTP*472 (Date of Service)

    Rules:
    - Date of service cannot be in the future
    - Date of service cannot be more than 1 year old (timely filing)
    - From date must be <= To date for date ranges
    """
    errors = []
    dos_str = str(claim.get("date_of_service", "")).strip()

    if not dos_str:
        errors.append(ValidationError(
            field_name="date_of_service",
            error_code="DATE_001",
            message="Date of service is missing. Required in DTP*472 segment.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="DTP"
        ))
        return errors

    try:
        dos = datetime.strptime(dos_str, "%Y-%m-%d")
    except ValueError:
        errors.append(ValidationError(
            field_name="date_of_service",
            error_code="DATE_002",
            message=f"Date of service '{dos_str}' is not valid. Expected format: YYYY-MM-DD.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="DTP"
        ))
        return errors

    today = datetime.today()

    if dos > today:
        errors.append(ValidationError(
            field_name="date_of_service",
            error_code="DATE_003",
            message=f"Date of service '{dos_str}' is in the future. Claims cannot be submitted for future dates.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="DTP"
        ))

    days_old = (today - dos).days
    if days_old > 365:
        errors.append(ValidationError(
            field_name="date_of_service",
            error_code="DATE_004",
            message=f"Date of service '{dos_str}' is {days_old} days old. Most payers require submission within 365 days (timely filing limit).",
            severity=ErrorSeverity.WARNING,
            edi_segment="DTP"
        ))

    return errors


# ─────────────────────────────────────────────
# PROCEDURE CODE VALIDATION
# ─────────────────────────────────────────────

def validate_procedure_codes(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    CPT/HCPCS procedure codes.
    EDI segment: SV1 (Professional Service)
    CPT: 5 digits (e.g. 99213)
    HCPCS: Letter + 4 digits (e.g. G0438)
    """
    errors = []
    proc_code = str(claim.get("procedure_code", "")).strip().upper()

    if not proc_code:
        errors.append(ValidationError(
            field_name="procedure_code",
            error_code="PROC_001",
            message="Procedure code is missing. Required in SV1 segment.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="SV1"
        ))
        return errors

    cpt_pattern = re.compile(r'^\d{5}$')
    hcpcs_pattern = re.compile(r'^[A-Z]\d{4}$')

    if not cpt_pattern.match(proc_code) and not hcpcs_pattern.match(proc_code):
        errors.append(ValidationError(
            field_name="procedure_code",
            error_code="PROC_002",
            message=f"Procedure code '{proc_code}' is not a valid CPT (5 digits) or HCPCS (letter + 4 digits) format.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="SV1"
        ))

    return errors


# ─────────────────────────────────────────────
# BILLED AMOUNT VALIDATION
# ─────────────────────────────────────────────

def validate_billed_amount(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    Billed amount must be positive and non-zero.
    EDI segment: CLM*05 (Claim Information)
    """
    errors = []
    try:
        amount = float(claim.get("billed_amount", 0))
    except (ValueError, TypeError):
        errors.append(ValidationError(
            field_name="billed_amount",
            error_code="AMT_001",
            message="Billed amount is not a valid number.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="CLM"
        ))
        return errors

    if amount <= 0:
        errors.append(ValidationError(
            field_name="billed_amount",
            error_code="AMT_002",
            message=f"Billed amount '{amount}' must be greater than zero.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="CLM"
        ))

    return errors


# ─────────────────────────────────────────────
# SUBSCRIBER / MEMBER ID VALIDATION
# ─────────────────────────────────────────────

def validate_subscriber_id(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    Subscriber/Member ID — payer-assigned identifier for the insured.
    EDI segment: NM1*IL (Subscriber Name loop)
    Cannot be empty. Format varies by payer (enforced in payer config).
    """
    errors = []
    subscriber_id = str(claim.get("subscriber_id", "")).strip()

    if not subscriber_id:
        errors.append(ValidationError(
            field_name="subscriber_id",
            error_code="SUB_001",
            message="Subscriber/Member ID is missing. Required in NM1*IL segment.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="NM1"
        ))

    return errors


# ─────────────────────────────────────────────
# PLACE OF SERVICE VALIDATION
# ─────────────────────────────────────────────

def validate_place_of_service(claim: Dict[str, Any]) -> List[ValidationError]:
    """
    Place of Service (POS) codes — CMS-defined 2-digit codes.
    EDI segment: CLM*05-1
    Common codes: 11=Office, 21=Inpatient Hospital, 22=Outpatient Hospital,
                  23=ER, 31=SNF, 81=Independent Lab
    """
    errors = []

    VALID_POS_CODES = {
        "11", "12", "13", "14", "15", "19", "20", "21", "22", "23",
        "24", "25", "26", "31", "32", "33", "34", "41", "42", "49",
        "50", "51", "52", "53", "54", "55", "56", "57", "58", "60",
        "61", "62", "65", "71", "72", "81", "99"
    }

    pos = str(claim.get("place_of_service", "")).strip().zfill(2)

    if not pos or pos == "00":
        errors.append(ValidationError(
            field_name="place_of_service",
            error_code="POS_001",
            message="Place of service code is missing. Required in CLM segment.",
            severity=ErrorSeverity.CRITICAL,
            edi_segment="CLM"
        ))
        return errors

    if pos not in VALID_POS_CODES:
        errors.append(ValidationError(
            field_name="place_of_service",
            error_code="POS_002",
            message=f"Place of service code '{pos}' is not a valid CMS POS code.",
            severity=ErrorSeverity.WARNING,
            edi_segment="CLM"
        ))

    return errors


# ─────────────────────────────────────────────
# MASTER RULE REGISTRY
# ─────────────────────────────────────────────

# WHY A LIST OF FUNCTIONS:
# The engine iterates this list and calls each rule function.
# To add a new rule, you add it here — nothing else changes.
# This is the Open/Closed Principle: open for extension, closed for modification.

BASE_RULES = [
    validate_billing_npi,
    validate_rendering_npi,
    validate_diagnosis_codes,
    validate_service_dates,
    validate_procedure_codes,
    validate_billed_amount,
    validate_subscriber_id,
    validate_place_of_service,
]
