EXTERNAL_MODELS = {
    "codebasefile",
    "namespace",
    "compound",
    "member",
    "parameter",
    "symbolref",
    "include",
    "metadata",
}


def _is_external(model):
    return (
        model._meta.app_label == "codebase"
        and model._meta.model_name in EXTERNAL_MODELS
    )


class CodebaseDatabaseRouter:
    """Route external codebase models to the 'codebase' DB.

    Django-managed ontology models (OntologyNode, OntologyTriple) stay in
    the default database.
    """

    def db_for_read(self, model, **hints):
        if _is_external(model):
            return "codebase"
        return None

    def db_for_write(self, model, **hints):
        if _is_external(model):
            return "codebase"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if _is_external(type(obj1)) and _is_external(type(obj2)):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == "codebase":
            return False
        if app_label == "codebase" and model_name in EXTERNAL_MODELS:
            return False
        return None
