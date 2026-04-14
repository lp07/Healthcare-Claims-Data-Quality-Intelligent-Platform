# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
engine.py — Core Validation Engine

WHY THIS FILE EXISTS:
This is the orchestrator. It takes a batch of claims,
loads the right payer config for each claim,
runs base rules + payer-specific rules,
and returns a list of ValidationResult objects.

The engine knows nothing about individual rules — it just runs them.
The engine knows nothing about reporting — it just produces results.
Clean separation of concerns.
"""

import json
import logging
import os
import time
from typing import List, Dict, Any
import pandas as pd

from claims_validator.models import ValidationResult, ClaimStatus
from claims_validator.rules import BASE_RULES

# ─────────────────────────────────────────────
# LOGGING SETUP
# WHY: Every production pipeline needs an audit trail.
# We log at INFO level for normal flow, ERROR for failures.
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class PayerConfig:
    """
    Loads and holds payer-specific validation rules from JSON config files.

    WHY JSON CONFIG FILES instead of hardcoded rules:
    Payer rules change constantly — BCBS updates its NPI format requirements,
    Medicare changes timely filing limits, Aetna adds new required fields.
    With JSON configs, a business analyst can update rules without touching Python code.
    This is how real RCM systems work.
    """

    def __init__(self, payer_config_dir: str):
        self.payer_config_dir = payer_config_dir
        self._configs: Dict[str, dict] = {}
        self._load_all_configs()

    def _load_all_configs(self):
        """Load all payer JSON configs at startup."""
        if not os.path.exists(self.payer_config_dir):
            logger.warning(f"Payer config directory not found: {self.payer_config_dir}")
            return

        for filename in os.listdir(self.payer_config_dir):
            if filename.endswith(".json"):
                payer_name = filename.replace(".json", "").upper()
                filepath = os.path.join(self.payer_config_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        self._configs[payer_name] = json.load(f)
                    logger.info(f"Loaded payer config: {payer_name}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse payer config {filename}: {e}")

    def get_config(self, payer: str) -> dict:
        """
        Get config for a specific payer.
        Falls back to DEFAULT config if payer not found.
        WHY DEFAULT: New payers without a config file still get validated
        against baseline rules. No silent failures.
        """
        payer_upper = payer.upper().strip()
        if payer_upper in self._configs:
            return self._configs[payer_upper]
        logger.warning(f"No specific config found for payer '{payer}'. Using DEFAULT rules.")
        return self._configs.get("DEFAULT", {})


class ClaimsValidationEngine:
    """
    Main validation engine.

    Usage:
        engine = ClaimsValidationEngine(payer_config_dir="payer_configs/")
        results = engine.validate_batch(claims_df)
    """

    def __init__(self, payer_config_dir: str = "payer_configs"):
        self.payer_config = PayerConfig(payer_config_dir)
        logger.info("ClaimsValidationEngine initialized.")

    def validate_claim(self, claim: Dict[str, Any]) -> ValidationResult:
        """
        Validate a single claim against base rules + payer-specific rules.

        Flow:
        1. Create a ValidationResult for this claim
        2. Run all BASE_RULES (apply to every payer)
        3. Load payer-specific config
        4. Run payer-specific additional checks
        5. Return populated ValidationResult
        """
        result = ValidationResult(
            claim_id=str(claim.get("claim_id", "UNKNOWN")),
            patient_id=str(claim.get("patient_id", "UNKNOWN")),
            payer=str(claim.get("payer", "UNKNOWN")),
            billed_amount=float(claim.get("billed_amount", 0.0)),
        )

        # Step 1: Run all base rules
        for rule_fn in BASE_RULES:
            try:
                errors = rule_fn(claim)
                for error in errors:
                    result.add_error(error)
            except Exception as e:
                logger.error(f"Rule {rule_fn.__name__} failed on claim {result.claim_id}: {e}")

        # Step 2: Run payer-specific checks
        payer_config = self.payer_config.get_config(result.payer)
        self._apply_payer_rules(claim, result, payer_config)

        return result

    def _apply_payer_rules(
        self,
        claim: Dict[str, Any],
        result: ValidationResult,
        config: dict
    ):
        """
        Apply payer-specific validation rules from config.

        WHY SEPARATE FROM BASE RULES:
        Base rules = universal EDI 837 requirements (every payer, no exceptions)
        Payer rules = specific requirements that vary by payer contract

        Example: BCBS requires taxonomy code on every claim.
                 Medicare requires CLIA number for lab claims.
                 These are not universal — they live in payer configs.
        """
        from claims_validator.models import ValidationError, ErrorSeverity

        # Check required fields defined in payer config
        required_fields = config.get("required_fields", [])
        for field_spec in required_fields:
            field_name = field_spec["field"]
            value = str(claim.get(field_name, "")).strip()
            if not value:
                result.add_error(ValidationError(
                    field_name=field_name,
                    error_code=field_spec.get("error_code", "PAYER_001"),
                    message=field_spec.get("message", f"Required field '{field_name}' is missing for {result.payer}."),
                    severity=ErrorSeverity[field_spec.get("severity", "CRITICAL")],
                    edi_segment=field_spec.get("edi_segment", "UNKNOWN")
                ))

        # Check timely filing limit
        timely_filing_days = config.get("timely_filing_days")
        if timely_filing_days:
            from datetime import datetime
            dos_str = str(claim.get("date_of_service", "")).strip()
            try:
                dos = datetime.strptime(dos_str, "%Y-%m-%d")
                days_old = (datetime.today() - dos).days
                if days_old > timely_filing_days:
                    result.add_error(ValidationError(
                        field_name="date_of_service",
                        error_code="PAYER_TF_001",
                        message=(
                            f"{result.payer} timely filing limit is {timely_filing_days} days. "
                            f"This claim is {days_old} days old and will be denied."
                        ),
                        severity=ErrorSeverity.CRITICAL,
                        edi_segment="DTP"
                    ))
            except (ValueError, TypeError):
                pass

        # Check subscriber ID format if payer defines a pattern
        subscriber_pattern = config.get("subscriber_id_pattern")
        if subscriber_pattern:
            import re
            subscriber_id = str(claim.get("subscriber_id", "")).strip()
            if subscriber_id and not re.match(subscriber_pattern, subscriber_id):
                result.add_error(ValidationError(
                    field_name="subscriber_id",
                    error_code="PAYER_SUB_001",
                    message=(
                        f"{result.payer} subscriber ID '{subscriber_id}' does not match "
                        f"expected format. Pattern: {subscriber_pattern}"
                    ),
                    severity=ErrorSeverity.WARNING,
                    edi_segment="NM1"
                ))

    def validate_batch(self, claims_df: pd.DataFrame) -> List[ValidationResult]:
        """
        Validate a full batch of claims.

        WHY PANDAS DATAFRAME INPUT:
        Claims come from CSV files, SQL queries, or API responses — all convert to DataFrame.
        We iterate rows and validate each claim independently.
        This means one bad claim doesn't stop the entire batch.

        Returns a list of ValidationResult objects.
        """
        results = []
        total = len(claims_df)
        start_time = time.time()

        logger.info(f"Starting validation batch: {total} claims")

        for idx, row in claims_df.iterrows():
            claim_dict = row.to_dict()
            result = self.validate_claim(claim_dict)
            results.append(result)

            # Log progress every 100 claims
            if (idx + 1) % 100 == 0:
                logger.info(f"Processed {idx + 1}/{total} claims...")

        elapsed = round(time.time() - start_time, 2)
        valid = sum(1 for r in results if r.status == ClaimStatus.VALID)
        flagged = sum(1 for r in results if r.status == ClaimStatus.FLAGGED)
        rejected = sum(1 for r in results if r.status == ClaimStatus.REJECTED)

        logger.info(
            f"Batch complete in {elapsed}s | "
            f"Total: {total} | Valid: {valid} | "
            f"Flagged: {flagged} | Rejected: {rejected}"
        )

        return results
