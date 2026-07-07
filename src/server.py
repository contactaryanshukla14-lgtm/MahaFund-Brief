import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from src.graph.pipeline import build_graph
from src.utils.logger import get_logger

log = get_logger("api")

app = FastAPI(
    title="MahaFund Brief API",
    description="API to generate detailed funding eligibility briefs based on MahaRERA and other sources.",
    version="1.0.0"
)

# CORS — allow the frontend to make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize graph once
graph = build_graph()

class BriefRequest(BaseModel):
    rera_number: Optional[str] = None
    project: Optional[str] = None
    developer: Optional[str] = None
    location: Optional[str] = None

@app.post("/generate-brief")
async def generate_brief(request: BriefRequest):
    if not request.rera_number and not request.project:
        raise HTTPException(status_code=400, detail="Must provide either rera_number or project name.")

    initial_state = {
        "rera_number": request.rera_number or "",
        "fallback_project": request.project or "",
        "fallback_developer": request.developer or "",
        "fallback_location": request.location or "",
        "partial_briefs": [],
        "agent_statuses": {},
        "final_brief": {},
        "docx_path": ""
    }
    
    log.info(f"API request received for RERA: {request.rera_number} / Project: {request.project}")
    
    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        log.error(f"Graph execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    docx_path = final_state.get("docx_path")
    if not docx_path or not os.path.exists(docx_path):
        raise HTTPException(status_code=500, detail="Pipeline failed to generate DOCX file.")
        
    filename = os.path.basename(docx_path)
    
    return FileResponse(
        path=docx_path, 
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Serve the frontend
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    # Serve index.html at root
    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
    
    # Serve static assets (CSS, JS)
    app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")
