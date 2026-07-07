from typing import Annotated, TypedDict, List, Dict, Any
from pydantic import BaseModel
import operator

class PipelineState(TypedDict):
    rera_number: str
    fallback_project: str
    fallback_developer: str
    fallback_location: str
    
    # We will accumulate PartialBriefs here
    partial_briefs: Annotated[List[Dict[str, Any]], operator.add]
    
    # Store errors or statuses from agents
    agent_statuses: Dict[str, str]
    
    # The final merged and synthesized brief
    final_brief: Dict[str, Any]
    
    # Path to the generated docx
    docx_path: str
