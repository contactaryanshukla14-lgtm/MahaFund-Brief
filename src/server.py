import os
import json
import base64
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
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
        "pdf_path": ""
    }
    
    log.info(f"API request received for RERA: {request.rera_number} / Project: {request.project}")
    
    async def generate_stream():
        task = asyncio.create_task(graph.ainvoke(initial_state))
        
        while not task.done():
            yield json.dumps({"status": "processing"}) + "\n"
            await asyncio.sleep(15)
            
        try:
            final_state = task.result()
            pdf_path = final_state.get("pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                yield json.dumps({"status": "error", "detail": "Pipeline failed to generate PDF file."}) + "\n"
                return
                
            filename = os.path.basename(pdf_path)
            with open(pdf_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                
            yield json.dumps({
                "status": "complete", 
                "filename": filename,
                "file_base64": encoded
            }) + "\n"
        except Exception as e:
            log.error(f"Graph execution failed: {e}")
            yield json.dumps({"status": "error", "detail": str(e)}) + "\n"

    return StreamingResponse(generate_stream(), media_type="application/x-ndjson")

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
