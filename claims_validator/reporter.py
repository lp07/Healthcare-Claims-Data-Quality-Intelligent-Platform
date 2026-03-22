"""
reporter.py — Validation Report Generator

WHY THIS FILE EXISTS:
The engine produces ValidationResult objects.
This module turns those results into actionable output:
- A detailed CSV of every claim and its errors
- A summary report with revenue at risk metrics
- An error breakdown by error code

WHY SEPARATE FROM ENGINE:
The engine's job is to validate. The reporter's job is to present.
If you want to add a new output format (Excel, JSON, email),
you add it here without touching the engine.
"""

import os
import logging
from typing import List
from datetime import datetime
import pandas as pd

from claims_validator.models import ValidationResult, ClaimStatus

logger = logging.getLogger(__name__)


class ValidationReporter:
    """
    Generates validation reports from a list of ValidationResult objects.
    """

    def __init__(self, output_dir: str = "data/sample_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_full_report(self, results: List[ValidationResult]) -> str:
        """
        Generate a detailed CSV report — one row per claim.
        Returns the output file path.
        """
        rows = [r.to_dict() for r in results]
        df = pd.DataFrame(rows)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"claims_validation_report_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)

        df.to_csv(filepath, index=False)
        logger.info(f"Full validation report saved: {filepath}")
        return filepath

    def generate_summary(self, results: List[ValidationResult]) -> dict:
        """
        Generate a summary of the validation run.

        This is what you'd show a billing manager:
        - How many claims processed
        - How many passed / failed
        - Total revenue at risk
        - Top error codes driving denials
        """
        total = len(results)
        valid = [r for r in results if r.status == ClaimStatus.VALID]
        flagged = [r for r in results if r.status == ClaimStatus.FLAGGED]
        rejected = [r for r in results if r.status == ClaimStatus.REJECTED]

        total_billed = sum(r.billed_amount for r in results)
        total_at_risk = sum(r.revenue_at_risk for r in results)

        # Error code frequency
        error_counts = {}
        for result in results:
            for error in result.errors:
                code = error.error_code
                error_counts[code] = error_counts.get(code, 0) + 1

        top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        summary = {
            "run_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_claims": total,
            "valid_claims": len(valid),
            "flagged_claims": len(flagged),
            "rejected_claims": len(rejected),
            "pass_rate_pct": round(len(valid) / total * 100, 2) if total > 0 else 0,
            "total_billed_amount": round(total_billed, 2),
            "total_revenue_at_risk": round(total_at_risk, 2),
            "revenue_at_risk_pct": round(total_at_risk / total_billed * 100, 2) if total_billed > 0 else 0,
            "top_error_codes": top_errors,
        }

        self._print_summary(summary)
        self._save_summary(summary)
        return summary

    def generate_error_breakdown(self, results: List[ValidationResult]) -> str:
        """
        Generate a per-payer, per-error-code breakdown CSV.
        Useful for identifying which payers have the most issues.
        """
        rows = []
        for result in results:
            for error in result.errors:
                rows.append({
                    "claim_id": result.claim_id,
                    "payer": result.payer,
                    "status": result.status.value,
                    "billed_amount": result.billed_amount,
                    "error_code": error.error_code,
                    "field_name": error.field_name,
                    "severity": error.severity.value,
                    "edi_segment": error.edi_segment,
                    "message": error.message,
                })

        if not rows:
            logger.info("No errors found in this batch.")
            return ""

        df = pd.DataFrame(rows)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"error_breakdown_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Error breakdown report saved: {filepath}")
        return filepath

    def _print_summary(self, summary: dict):
        """Print summary to console — useful when running from terminal."""
        print("\n" + "="*60)
        print("  CLAIMS VALIDATION SUMMARY")
        print("="*60)
        print(f"  Run Time:           {summary['run_timestamp']}")
        print(f"  Total Claims:       {summary['total_claims']}")
        print(f"  Valid:              {summary['valid_claims']}")
        print(f"  Flagged:            {summary['flagged_claims']}")
        print(f"  Rejected:           {summary['rejected_claims']}")
        print(f"  Pass Rate:          {summary['pass_rate_pct']}%")
        print(f"  Total Billed:       ${summary['total_billed_amount']:,.2f}")
        print(f"  Revenue at Risk:    ${summary['total_revenue_at_risk']:,.2f}")
        print(f"  Risk %:             {summary['revenue_at_risk_pct']}%")
        print("\n  TOP ERROR CODES:")
        for code, count in summary['top_error_codes']:
            print(f"    {code}: {count} occurrences")
        print("="*60 + "\n")

    def _save_summary(self, summary: dict):
        """Save summary as JSON."""
        import json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"summary_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Summary saved: {filepath}")
