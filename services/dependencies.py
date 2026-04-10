"""Neo4j connection provider - works in both app context and standalone scripts."""

from nicegui import app


def get_neo4j():
    """Get Neo4j connection from app context.
    
    Falls back to environment variables if app.neo4j is not available
    (e.g., when running in standalone scripts).
    """
    # Try app context first (NiceGUI running)
    if hasattr(app, 'neo4j') and app.neo4j is not None:
        return app.neo4j
    
    # Fallback: create driver from environment variables (standalone scripts)
    import os
    from neo4j import GraphDatabase
    
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "msd-local-dev")
    
    # Cache the driver in app for subsequent calls
    driver = GraphDatabase.driver(uri, auth=(user, password))
    if hasattr(app, 'neo4j'):
        app.neo4j = driver
    return driver
