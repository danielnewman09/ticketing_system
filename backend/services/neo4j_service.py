"""Standalone Neo4j driver management (not tied to NiceGUI app state)."""

import os
from contextlib import contextmanager
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")

_driver = None


def get_driver():
    """Get or create the Neo4j driver singleton."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def get_neo4j_session(database="neo4j"):
    driver = get_driver()
    session = driver.session(database=database)
    try:
        yield session
    finally:
        session.close()


def verify_connection():
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception as e:
        print(f"Neo4j connection failed: {e}")
        return False
