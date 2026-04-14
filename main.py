# =============================================================================
# Copyright (c) 2025 Lisa Patel | github.com/lp07
# Original portfolio project. Unauthorized commercial use prohibited.
# Attribution required for any use, modification, or distribution.
# =============================================================================
"""
main.py — Healthcare Claims DQ Platform Entry Point

HOW TO RUN:
    python main.py                          # Validate sample data
    python main.py --input your_claims.csv  # Validate your own file
    python main.py --generate               # Generate fresh sample data first

WHAT THIS DOES:
1. Loads claims from CSV
2. Runs validation engine (base rules + payer-specific rules)
3. Generates full report, error breakdown, and summary
4. Prints summary to console
5. Saves detailed reports to data/sample_output/
"""

import argparse
import logging
import os
import sys
import pandas as pd

from claims_validator.engine import ClaimsValidationEngine
from claims_validator.reporter import ValidationReporter

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Healthcare Claims DQ Platform — EDI 837 Validation Engine"
    )
    parser.add_argument(
        "--input",
        default="data/sample_claims.csv",
        help="Path to claims CSV file (default: data/sample_claims.csv)"
    )
    parser.add_argument(
        "--output-dir",
        default="data/sample_output",
        help="Directory for output reports (default: data/sample_output)"
    )
    parser.add_argument(
        "--payer-configs",
        default="payer_configs",
        help="Directory containing payer JSON config files"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate fresh synthetic sample data before validating"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Optionally generate fresh sample data
    if args.generate or not os.path.exists(args.input):
        logger.info("Generating synthetic sample claims data...")
        from data.generate_sample_data import generate_claims
        df = generate_claims(1200)
        os.makedirs("data", exist_ok=True)
        df.to_csv(args.input, index=False)
        logger.info(f"Sample data saved to {args.input}")

    # Load claims
    try:
        claims_df = pd.read_csv(args.input)
        logger.info(f"Loaded {len(claims_df)} claims from {args.input}")
    except FileNotFoundError:
        logger.error(f"Input file not found: {args.input}")
        logger.error("Run with --generate flag to create sample data first.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load claims file: {e}")
        sys.exit(1)

    # Initialize engine and reporter
    engine = ClaimsValidationEngine(payer_config_dir=args.payer_configs)
    reporter = ValidationReporter(output_dir=args.output_dir)

    # Run validation
    results = engine.validate_batch(claims_df)

    # Generate reports
    full_report_path = reporter.generate_full_report(results)
    error_breakdown_path = reporter.generate_error_breakdown(results)
    summary = reporter.generate_summary(results)

    print(f"
Reports saved to: {args.output_dir}/")
    print(f"  Full report:     {os.path.basename(full_report_path)}")
    if error_breakdown_path:
        print(f"  Error breakdown: {os.path.basename(error_breakdown_path)}")


if __name__ == "__main__":
    main()
