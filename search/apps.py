from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _load_sqlite_vec(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        import sqlite_vec
        conn = connection.connection
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)


class SearchConfig(AppConfig):
    name = 'search'

    def ready(self):
        connection_created.connect(_load_sqlite_vec)
        import search.signals  # noqa: F401
