import argparse
import asyncio
from src.graph.pipeline import build_graph
from src.utils.logger import get_logger

log = get_logger("main")

async def main():
    parser = argparse.ArgumentParser(description="MahaFund Brief Generator")
    parser.add_argument("rera_number", nargs="?", help="MahaRERA Registration Number (e.g., P51700000002)")
    parser.add_argument("--project", help="Project name if RERA is unavailable")
    parser.add_argument("--developer", help="Developer/Promoter name if RERA is unavailable")
    parser.add_argument("--location", help="Project location if RERA is unavailable")
    
    args = parser.parse_args()
    
    if not args.rera_number and not args.project:
        parser.error("You must provide either a RERA number OR a --project name.")

    graph = build_graph()
    
    initial_state = {
        "rera_number": args.rera_number or "",
        "fallback_project": args.project or "",
        "fallback_developer": args.developer or "",
        "fallback_location": args.location or "",
        "partial_briefs": [],
        "agent_statuses": {},
        "final_brief": {},
        "docx_path": ""
    }
    
    log.info(f"Starting pipeline...")
    final_state = await graph.ainvoke(initial_state)
    
    if final_state.get("docx_path"):
        log.info("Pipeline finished successfully!")
        print(f"Generated DOCX: {final_state['docx_path']}")
    else:
        log.error("Pipeline failed or did not generate a DOCX.")

if __name__ == "__main__":
    asyncio.run(main())
