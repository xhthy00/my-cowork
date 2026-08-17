"""Supervisor + Workers StateGraph — re-exports workforce graph."""

from app.graphs.workforce import (  # noqa: F401
    compile_supervisor_graph,
    compile_workforce_graph,
)
