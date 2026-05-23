#!/usr/bin/env python
"""Benchmark: Simple Calculator Application.

Seeds HLRs for a calculator application in Neo4j.

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
from backend.db.models import Component, Language
from backend.db.neo4j.connection import Neo4jConnection
from backend.db.neo4j.repositories.requirement import RequirementRepository
from services.dependencies import get_neo4j, init_neo4j, close_neo4j

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
    init_neo4j()

    neo4j_conn = Neo4jConnection()
    neo4j_conn.ensure_constraints()
    neo4j_conn.ensure_requirement_constraints()

    with get_session() as session:
        lang, _ = get_or_create(session, Language, name="Python", defaults={"version": "3.11"})
        comp, created = get_or_create(
            session,
            Component,
            name="Calculator",
            defaults={
                "namespace": "calculator",
                "description": "Simple calculator application",
                "language": lang,
            },
        )
        if created:
            print(f"Created component: {comp.name}")

    with get_neo4j().session() as ns:
        repo = RequirementRepository(ns)

        existing = len(repo.list_hlrs(component_id=None))
        if existing >= len(CALCULATOR_HLRS):
            print(f"Already seeded: {existing} HLRs")
            close_neo4j()
            return

        for desc in CALCULATOR_HLRS:
            hlr = repo.create_hlr(description=desc)
            print(f"Added HLR {hlr.id}: {desc[:80]}...")

        count = len(repo.list_hlrs())
        print(f"\nBenchmark seeded: {count} HLRs")

    close_neo4j()


if __name__ == "__main__":
    main()