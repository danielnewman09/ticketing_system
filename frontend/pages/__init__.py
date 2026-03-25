"""Page definitions. Import this module to register all routes."""

from frontend.pages.requirements import requirements_page
from frontend.pages.hlr_detail import hlr_detail_page
from frontend.pages.llr_detail import llr_detail_page
from frontend.pages.components import components_page
from frontend.pages.ontology import ontology_page
from frontend.pages.ontology_graph import ontology_graph_page
from frontend.pages.node_detail import node_detail_page
from frontend.pages.component_detail import component_detail_page

__all__ = [
    "requirements_page",
    "hlr_detail_page",
    "llr_detail_page",
    "components_page",
    "component_detail_page",
    "ontology_page",
    "ontology_graph_page",
    "node_detail_page",
]
