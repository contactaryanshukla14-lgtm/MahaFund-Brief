from langgraph.graph import StateGraph, END
from src.graph.state import PipelineState
from src.graph.nodes import (
    maharera_agent_node,
    downstream_agents_node,
    merge_node,
    synthesize_node,
    eligibility_node,
    generate_pdf_node
)

def check_maharera_success(state: PipelineState) -> str:
    """Route to downstream agents only if MahaRERA extraction succeeded."""
    status = state.get("agent_statuses", {}).get("maharera")
    if status == "success":
        return "downstream_agents"
    else:
        return "merge"

def build_graph() -> StateGraph:
    workflow = StateGraph(PipelineState)
    
    # Add nodes
    workflow.add_node("maharera_agent", maharera_agent_node)
    workflow.add_node("downstream_agents", downstream_agents_node)
    workflow.add_node("merge", merge_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("eligibility", eligibility_node)
    workflow.add_node("generate_pdf", generate_pdf_node)
    
    def entry_point(state: PipelineState) -> str:
        if not state.get("rera_number"):
            return "downstream_agents" # Skip MahaRERA entirely
        return "maharera_agent"

    workflow.set_conditional_entry_point(
        entry_point,
        {
            "maharera_agent": "maharera_agent",
            "downstream_agents": "downstream_agents"
        }
    )
    
    workflow.add_conditional_edges(
        "maharera_agent",
        check_maharera_success,
        {
            "downstream_agents": "downstream_agents",
            "merge": "merge"
        }
    )
    workflow.add_edge("downstream_agents", "merge")
    workflow.add_edge("merge", "synthesize")
    workflow.add_edge("synthesize", "eligibility")
    workflow.add_edge("eligibility", "generate_pdf")
    workflow.add_edge("generate_pdf", END)
    
    return workflow.compile()
