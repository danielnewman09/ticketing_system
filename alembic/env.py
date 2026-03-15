from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so they register with Base.metadata
import db.models  # noqa: F401
from db.base import Base

target_metadata = Base.metadata

# Tables to exclude from autogenerate (codebase DB tables, Django leftovers)
EXCLUDE_TABLES = {
    # Codebase DB tables (managed externally)
    "compounds", "members", "parameters", "symbol_refs",
    "files", "namespaces", "includes", "metadata",
    # Django system tables
    "auth_group", "auth_group_permissions", "auth_permission",
    "auth_user", "auth_user_groups", "auth_user_user_permissions",
    "django_admin_log", "django_content_type", "django_migrations",
    "django_session", "sqlite_sequence",
}


def include_object(object, name, type_, reflected, compare_to):
    """Filter out codebase and Django system tables."""
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
