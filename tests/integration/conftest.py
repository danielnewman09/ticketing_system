"""Pytest configuration for integration tests.

Requires that ``nicegui_app.py`` is running at http://localhost:8081
before tests execute.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a running application",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--no-snapshot",
        action="store_true",
        default=False,
        help="Skip snapshot generation in integration tests",
    )
