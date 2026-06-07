"""Page definitions — stubs.

Importing this module registers all NiceGUI routes. Each page function
raises NotImplementedError until reimplemented against the migrated data layer.
"""

from frontend_migrated.pages.project import project_page
from frontend_migrated.pages.requirements import requirements_page
from frontend_migrated.pages.hlr_detail import hlr_detail_page
from frontend_migrated.pages.llr_detail import llr_detail_page
from frontend_migrated.pages.components import components_page
from frontend_migrated.pages.ontology import ontology_page
from frontend_migrated.pages.ontology_graph import ontology_graph_page
from frontend_migrated.pages.node_detail import node_detail_page
from frontend_migrated.pages.component_detail import component_detail_page
from frontend_migrated.pages.dependency_review import dependency_review_page

__all__ = [
    "project_page",
    "requirements_page",
    "hlr_detail_page",
    "llr_detail_page",
    "components_page",
    "component_detail_page",
    "dependency_review_page",
    "ontology_page",
    "ontology_graph_page",
    "node_detail_page",
]