"""
tests/test_rules.py — Unit Tests for Validation Rules

WHY TESTS EXIST IN A REAL PROJECT:
When you change a rule, tests catch regressions immediately.
When a new payer requirement comes in, you write a test first, then the rule.
This is called Test-Driven Development (TDD).
A project without tests is not production-grade.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from claims_validator.rules import (
    validate_billing_npi,
    validate_rendering_npi,
    validate_diagnosis_codes,
    validate_service_dates,
    validate_procedure_codes,
    validate_billed_amount,
    validate_subscriber_id,
    validate_place_of_service,
)
from claims_validator.models import ErrorSeverity


# ─────────────────────────────────────────────
# NPI TESTS
# ─────────────────────────────────────────────

class TestBillingNPI:

    def test_valid_npi_passes(self):
        claim = {"billing_npi": "1234567893"}
        errors = validate_billing_npi(claim)
        assert len(errors) == 0

    def test_missing_npi_returns_critical_error(self):
        claim = {"billing_npi": ""}
        errors = validate_billing_npi(claim)
        assert len(errors) == 1
        assert errors[0].error_code == "NPI_001"
        assert errors[0].severity == ErrorSeverity.CRITICAL

    def test_npi_wrong_length_returns_error(self):
        claim = {"billing_npi": "123456789"}  # 9 digits
        errors = validate_billing_npi(claim)
        assert any(e.error_code == "NPI_003" for e in errors)

    def test_npi_with_letters_returns_error(self):
        claim = {"billing_npi": "123456789A"}
        errors = validate_billing_npi(claim)
        assert any(e.error_code == "NPI_002" for e in errors)

    def test_missing_npi_key_returns_error(self):
        claim = {}
        errors = validate_billing_npi(claim)
        assert len(errors) == 1
        assert errors[0].error_code == "NPI_001"


# ─────────────────────────────────────────────
# DIAGNOSIS CODE TESTS
# ─────────────────────────────────────────────

class TestDiagnosisCodes:

    def test_valid_icd10_passes(self):
        claim = {"primary_diagnosis_code": "M54.5", "diagnosis_pointer": "1"}
        errors = validate_diagnosis_codes(claim)
        assert len(errors) == 0

    def test_missing_diagnosis_returns_critical(self):
        claim = {"primary_diagnosis_code": "", "diagnosis_pointer": "1"}
        errors = validate_diagnosis_codes(claim)
        assert any(e.error_code == "DX_001" for e in errors)
        assert any(e.severity == ErrorSeverity.CRITICAL for e in errors)

    def test_invalid_format_returns_error(self):
        claim = {"primary_diagnosis_code": "12345", "diagnosis_pointer": "1"}
        errors = validate_diagnosis_codes(claim)
        assert any(e.error_code == "DX_002" for e in errors)

    def test_missing_pointer_returns_error(self):
        claim = {"primary_diagnosis_code": "Z23", "diagnosis_pointer": ""}
        errors = validate_diagnosis_codes(claim)
        assert any(e.error_code == "DX_003" for e in errors)


# ─────────────────────────────────────────────
# DATE TESTS
# ─────────────────────────────────────────────

class TestServiceDates:
    from datetime import datetime, timedelta

    def test_valid_date_passes(self):
        from datetime import datetime, timedelta
        dos = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        claim = {"date_of_service": dos}
        errors = validate_service_dates(claim)
        assert len(errors) == 0

    def test_future_date_returns_critical(self):
        from datetime import datetime, timedelta
        dos = (datetime.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        claim = {"date_of_service": dos}
        errors = validate_service_dates(claim)
        assert any(e.error_code == "DATE_003" for e in errors)

    def test_missing_date_returns_critical(self):
        claim = {"date_of_service": ""}
        errors = validate_service_dates(claim)
        assert any(e.error_code == "DATE_001" for e in errors)

    def test_old_claim_returns_warning(self):
        from datetime import datetime, timedelta
        dos = (datetime.today() - timedelta(days=400)).strftime("%Y-%m-%d")
        claim = {"date_of_service": dos}
        errors = validate_service_dates(claim)
        assert any(e.error_code == "DATE_004" for e in errors)
        assert any(e.severity == ErrorSeverity.WARNING for e in errors)


# ─────────────────────────────────────────────
# PROCEDURE CODE TESTS
# ─────────────────────────────────────────────

class TestProcedureCodes:

    def test_valid_cpt_passes(self):
        claim = {"procedure_code": "99213"}
        errors = validate_procedure_codes(claim)
        assert len(errors) == 0

    def test_valid_hcpcs_passes(self):
        claim = {"procedure_code": "G0438"}
        errors = validate_procedure_codes(claim)
        assert len(errors) == 0

    def test_invalid_code_returns_error(self):
        claim = {"procedure_code": "XXXXX"}
        errors = validate_procedure_codes(claim)
        assert any(e.error_code == "PROC_002" for e in errors)

    def test_missing_code_returns_critical(self):
        claim = {"procedure_code": ""}
        errors = validate_procedure_codes(claim)
        assert any(e.error_code == "PROC_001" for e in errors)


# ─────────────────────────────────────────────
# BILLED AMOUNT TESTS
# ─────────────────────────────────────────────

class TestBilledAmount:

    def test_valid_amount_passes(self):
        claim = {"billed_amount": 250.00}
        errors = validate_billed_amount(claim)
        assert len(errors) == 0

    def test_zero_amount_returns_critical(self):
        claim = {"billed_amount": 0}
        errors = validate_billed_amount(claim)
        assert any(e.error_code == "AMT_002" for e in errors)

    def test_negative_amount_returns_critical(self):
        claim = {"billed_amount": -100}
        errors = validate_billed_amount(claim)
        assert any(e.error_code == "AMT_002" for e in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
