"""LangGraph graph definitions for the Digital Workforce Platform.

Exports the three compiled graphs:
  - main_graph: Full task lifecycle (entry -> plan -> execute -> review -> finalize)
  - mechanic_b_graph: Workflow execution analyzer (trace -> score -> propose -> report)
  - sop_runner_graph: SOP-driven dynamic workflow generator
"""

from .main import graph as main_graph
from .mechanic_b import graph as mechanic_b_graph
from .sop_runner import graph as sop_runner_graph

__all__ = ["main_graph", "mechanic_b_graph", "sop_runner_graph"]
