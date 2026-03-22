"""
models.py — Data models for the Claims DQ Platform

WHY THIS FILE EXISTS:
Every claim that goes through validation produces a result.
That result needs to carry: which claim, what status, what errors, what's the revenue impact.
We define that structure here — once — so every other module uses the same shape.
This is called a data model. It prevents inconsistency across the codebase.
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum


class ClaimStatus(Enum):
    """
    WHY ENUM:
    Status can only be one of these exact values.
    Using strings like "valid" or "VALID" leads to bugs.
    Enums enforce consistency — you can't accidentally type "Valide".
    """
    VALID = "VALID"
    FLAGGED = "FLAGGED"
    REJECTED = "REJECTED"


class ErrorSeverity(Enum):
    """
    Not all errors are equal.
    CRITICAL = claim cannot be submitted, will be denied
    WARNING  = claim may have issues, needs review
    INFO     = informational, does not block submission
    """
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ValidationError:
    """
    A single validation error on a claim.

    WHY DATACLASS:
    Dataclasses auto-generate __init__, __repr__, __eq__.
    We get a clean object without boilerplate code.

    Fields:
    - field_name:    Which EDI field failed (e.g. "billing_npi", "diagnosis_code")
    - error_code:    Internal code for this error type (e.g. "NPI_001")
    - message:       Human-readable description of what's wrong
    - severity:      CRITICAL / WARNING / INFO
    - edi_segment:   Which EDI segment this maps to (e.g. "NM1", "CLM", "HI")
    """
    field_name: str
    error_code: str
    message: str
    severity: ErrorSeverity
    edi_segment: str


@dataclass
class ValidationResult:
    """
    The complete validation result for one claim.

    Fields:
    - claim_id:         Unique claim identifier
    - patient_id:       Patient identifier
    - payer:            Which payer this claim is for
    - billed_amount:    Dollar amount billed
    - status:           VALID / FLAGGED / REJECTED
    - errors:           List of ValidationError objects
    - revenue_at_risk:  Dollar amount at risk if claim is denied
    """
    claim_id: str
    patient_id: str
    payer: str
    billed_amount: float
    status: ClaimStatus = ClaimStatus.VALID
    errors: List[ValidationError] = field(default_factory=list)

    @property
    def revenue_at_risk(self) -> float:
        """
        WHY PROPERTY:
        Revenue at risk is derived — not stored.
        If claim is VALID, risk = 0.
        If FLAGGED or REJECTED, the full billed amount is at risk.
        We compute it on the fly rather than storing a potentially stale value.
        """
        if self.status == ClaimStatus.VALID:
            return 0.0
        return self.billed_amount

    @property
    def critical_errors(self) -> List[ValidationError]:
        """Returns only CRITICAL severity errors."""
        return [e for e in self.errors if e.severity == ErrorSeverity.CRITICAL]

    @property
    def has_critical_errors(self) -> bool:
        return len(self.critical_errors) > 0

    def add_error(self, error: ValidationError):
        """
        Add an error and automatically update claim status.
        CRITICAL error → REJECTED
        WARNING error → FLAGGED (unless already REJECTED)
        """
        self.errors.append(error)
        if error.severity == ErrorSeverity.CRITICAL:
            self.status = ClaimStatus.REJECTED
        elif error.severity == ErrorSeverity.WARNING and self.status != ClaimStatus.REJECTED:
            self.status = ClaimStatus.FLAGGED

    def to_dict(self) -> dict:
        """Serialize to dictionary for CSV/JSON output."""
        return {
            "claim_id": self.claim_id,
            "patient_id": self.patient_id,
            "payer": self.payer,
            "billed_amount": self.billed_amount,
            "status": self.status.value,
            "error_count": len(self.errors),
            "critical_error_count": len(self.critical_errors),
            "error_codes": "|".join([e.error_code for e in self.errors]),
            "error_messages": " | ".join([e.message for e in self.errors]),
            "revenue_at_risk": self.revenue_at_risk,
        }
