"""Unit tests for the Neo4j connection migration.

Verifies that:
- backend_migrated.connection uses codegraph for driver management
- backend.db.neo4j.connection re-exports from backend_migrated
- services.dependencies re-exports from backend_migrated
- No deprecated neomodel config API (config.DATABASE_URL) is used
- frontend_migrated/data/project.py has no backend.db imports
"""

import ast


# ---------------------------------------------------------------------------
# backend_migrated/connection.py
# ---------------------------------------------------------------------------


class TestBackendMigratedConnection:
    """Structural tests for backend_migrated/connection.py."""

    @classmethod
    def _source(cls) -> str:
        with open("backend_migrated/connection.py") as f:
            return f.read()

    def test_imports_codegraph_connection(self):
        """Must import driver helpers from codegraph.connection."""
        src = self._source()
        assert "from codegraph.connection import" in src, (
            "backend_migrated/connection.py must import from codegraph.connection"
        )
        assert "_ensure_driver" in src
        assert "get_session" in src
        assert "verify_connectivity" in src

    def test_imports_codegraph_config(self):
        """Must import NEO4J env vars from codegraph.config."""
        src = self._source()
        assert "from codegraph.config import" in src

    def test_neo4j_session_manager_delegates_to_codegraph(self):
        """Neo4jSessionManager.session() must call get_session from codegraph."""
        src = self._source()
        # The session() method should call get_session()
        assert "return get_session()" in src

    def test_neo4j_session_manager_verify_delegates(self):
        """Neo4jSessionManager.verify_connectivity() must call codegraph."""
        src = self._source()
        assert "return verify_connectivity()" in src

    def test_has_init_get_close_neo4j(self):
        """Must provide init_neo4j, get_neo4j, close_neo4j lifecycle functions."""
        src = self._source()
        assert "def init_neo4j" in src
        assert "def get_neo4j" in src
        assert "def close_neo4j" in src

    def test_has_ensure_connection(self):
        """Must provide ensure_connection helper."""
        src = self._source()
        assert "def ensure_connection" in src

    def test_no_deprecated_config_api(self):
        """Must NOT use deprecated config.DATABASE_URL or config.ALLOW_RELOAD."""
        src = self._source()
        assert "config.DATABASE_URL" not in src, (
            "Should not use deprecated config.DATABASE_URL"
        )
        assert "config.ALLOW_RELOAD" not in src, (
            "Should not use deprecated config.ALLOW_RELOAD"
        )

    def test_no_backend_db_imports(self):
        """Must NOT import from backend.db (avoids old SQLAlchemy dependency)."""
        src = self._source()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("backend.db"):
                    if "backend_migrated" not in node.module:
                        assert False, (
                            f"Should not import from backend.db: from {node.module}"
                        )


# ---------------------------------------------------------------------------
# backend/db/neo4j/connection.py — backward-compat shim
# ---------------------------------------------------------------------------


class TestBackendDbNeo4jConnection:
    """Verify the backward-compat shim re-exports from backend_migrated."""

    @classmethod
    def _source(cls) -> str:
        with open("backend/db/neo4j/connection.py") as f:
            return f.read()

    def test_re_exports_neo4j_session_manager(self):
        """Must re-export Neo4jSessionManager from backend_migrated."""
        src = self._source()
        assert "from backend_migrated.connection import" in src
        assert "Neo4jSessionManager" in src

    def test_re_exports_neo4j_env_vars(self):
        """Must re-export NEO4J_URI/USER/PASSWORD from codegraph.config."""
        src = self._source()
        assert "from codegraph.config import" in src
        assert "NEO4J_URI" in src
        assert "NEO4J_USER" in src
        assert "NEO4J_PASSWORD" in src

    def test_no_deprecated_config_api(self):
        """Must NOT set config.DATABASE_URL or config.ALLOW_RELOAD directly."""
        src = self._source()
        assert "config.DATABASE_URL =" not in src, (
            "Should not set config.DATABASE_URL directly"
        )
        assert "config.ALLOW_RELOAD" not in src, (
            "Should not use config.ALLOW_RELOAD"
        )

    def test_is_thin_shim(self):
        """Should be a thin re-export module, no class definitions."""
        src = self._source()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ClassDef):
                assert False, (
                    f"Shim should not define classes, found: {node.name}"
                )


# ---------------------------------------------------------------------------
# services/dependencies.py — thin re-export
# ---------------------------------------------------------------------------


class TestServicesDependencies:
    """Verify services/dependencies re-exports from backend_migrated."""

    @classmethod
    def _source(cls) -> str:
        with open("services/dependencies.py") as f:
            return f.read()

    def test_re_exports_from_backend_migrated(self):
        """Must re-export from backend_migrated.connection."""
        src = self._source()
        assert "from backend_migrated.connection import" in src

    def test_exports_init_get_close(self):
        """Must re-export init_neo4j, get_neo4j, close_neo4j."""
        src = self._source()
        assert "init_neo4j" in src
        assert "get_neo4j" in src
        assert "close_neo4j" in src

    def test_no_deprecated_config_api(self):
        """Must NOT use deprecated config.DATABASE_URL."""
        src = self._source()
        assert "config.DATABASE_URL" not in src


# ---------------------------------------------------------------------------
# frontend_migrated/data/project.py — no backend.db imports
# ---------------------------------------------------------------------------


class TestFrontendMigratedProject:
    """Verify frontend_migrated/data/project.py uses codegraph, not backend.db."""

    @classmethod
    def _source(cls) -> str:
        with open("frontend_migrated/data/project.py") as f:
            return f.read()

    def test_no_backend_db_imports(self):
        """Must NOT import from backend.db."""
        src = self._source()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("backend.db"):
                    assert False, (
                        f"Should not import from backend.db: from {node.module}"
                    )

    def test_uses_codegraph_config(self):
        """Must import from codegraph.config for connection setup."""
        src = self._source()
        assert "codegraph.config" in src or "codegraph.connection" in src, (
            "Should use codegraph for database connection setup"
        )

    def test_uses_codegraph_ensure_driver(self):
        """Must use codegraph.connection._ensure_driver for driver init."""
        src = self._source()
        assert "_ensure_driver" in src


# ---------------------------------------------------------------------------
# nicegui_app_migrated.py
# ---------------------------------------------------------------------------


class TestNiceguiAppMigrated:
    """Verify nicegui_app_migrated.py uses backend_migrated.connection."""

    @classmethod
    def _source(cls) -> str:
        with open("nicegui_app_migrated.py") as f:
            return f.read()

    def test_imports_from_backend_migrated(self):
        """Must import Neo4jSessionManager from backend_migrated."""
        src = self._source()
        assert "from backend_migrated.connection import Neo4jSessionManager" in src

    def test_sets_app_neo4j(self):
        """Must set app.neo4j = Neo4jSessionManager()."""
        src = self._source()
        assert "app.neo4j = Neo4jSessionManager()" in src

    def test_closes_on_shutdown(self):
        """Must close neo4j on app shutdown."""
        src = self._source()
        assert "app.neo4j.close()" in src

    def test_no_backend_db_imports(self):
        """Must NOT import from backend.db."""
        src = self._source()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("backend.db"):
                    assert False, (
                        f"Should not import from backend.db: from {node.module}"
                    )


# ---------------------------------------------------------------------------
# nicegui_app.py (old)
# ---------------------------------------------------------------------------


class TestNiceguiAppOld:
    """Verify old nicegui_app.py uses backend_migrated.connection."""

    @classmethod
    def _source(cls) -> str:
        with open("nicegui_app.py") as f:
            return f.read()

    def test_imports_from_backend_migrated(self):
        """Must import Neo4jSessionManager from backend_migrated."""
        src = self._source()
        assert "from backend_migrated.connection import Neo4jSessionManager" in src

    def test_no_deprecated_import(self):
        """Must NOT import from backend.db.neo4j.connection."""
        src = self._source()
        assert "from backend.db.neo4j.connection import" not in src


# ---------------------------------------------------------------------------
# backend_migrated/__init__.py
# ---------------------------------------------------------------------------


class TestBackendMigratedInit:
    """Verify backend_migrated package exports connection symbols."""

    @classmethod
    def _source(cls) -> str:
        with open("backend_migrated/__init__.py") as f:
            return f.read()

    def test_exports_connection_symbols(self):
        """Must export connection lifecycle functions."""
        src = self._source()
        assert "ensure_connection" in src
        assert "init_neo4j" in src
        assert "get_neo4j" in src
        assert "close_neo4j" in src
        assert "Neo4jSessionManager" in src