#!/usr/bin/env python
"""
Benchmark: Simple Calculator Application.

Seeds HLRs for a calculator application.

Usage:
    source .venv/bin/activate
    python scripts/04_benchmark_calculator.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from backend.db import init_db, get_session, get_or_create
from backend.db.models import Component, HighLevelRequirement, Language

CALCULATOR_HLRS = [
    "The calculator application provides a GUI with a numeric display and buttons "
    "for digits 0-9, operators (+, -, *, /), clear, and equals. Display shows current "
    "input and result.",

    "The calculator performs addition, subtraction, multiplication, and division with "
    "proper input validation. Division by zero raises an error. Invalid expressions "
    "are rejected. Results are returned immediately.",
]


def main():
    init_db()

    with get_session() as session:
        existing = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.description.like("%calculator%")
        ).count()
        if existing >= len(CALCULATOR_HLRS):
            print(f"Already seeded: {existing} calculator HLRs")
            return

        lang, _ = get_or_create(session, Language, name="Python",
                                  defaults={"version": "3.11"})
        comp, created = get_or_create(
            session, Component, name="Calculator",
            defaults={"namespace": "calculator",
                      "description": "Simple calculator application",
                      "language": lang},
        )
        if created:
            print(f"Created component: {comp.name}")

        for desc in CALCULATOR_HLRS:
            hlr = HighLevelRequirement(description=desc, component=comp)
            session.add(hlr)
            print(f"Added HLR: {desc[:80]}...")

        count = session.query(HighLevelRequirement).filter(
            HighLevelRequirement.component == comp
        ).count()
        print(f"\nBenchmark seeded: {count} HLRs for component '{comp.name}'")


if __name__ == "__main__":
    main()
