import asyncio
from typing import Dict, Any

from src.graph.state import PipelineState
from src.agents.maharera import MahareraAgent
from src.agents.zaubacorp import ZaubacorpAgent
from src.agents.ninety_nine_acres import NinetyNineAcresAgent
from src.agents.housing import HousingAgent
from src.utils.logger import get_logger
from src.config import INTER_AGENT_DELAY_SECONDS
from pydantic import BaseModel

log = get_logger("pipeline")


async def maharera_agent_node(state: PipelineState) -> Dict[str, Any]:
    log.info(f"Running MahaRERA Agent for {state['rera_number']}...")

    agent = MahareraAgent(rera_number=state["rera_number"])
    
    max_retries = 3
    result = None
    status = "failed"
    
    for attempt in range(max_retries):
        try:
            log.info(f"MahaRERA extraction attempt {attempt + 1}/{max_retries}")
            result = await agent.run()
            
            if result.get("data") and not result["data"].get("error"):
                status = "success"
                break
            else:
                err_msg = result.get("data", {}).get("error", "Unknown error")
                log.warning(f"MahaRERA attempt {attempt + 1} failed: {err_msg}")
                await asyncio.sleep(5)
        except Exception as e:
            log.error(f"MahaRERA Agent crashed on attempt {attempt + 1}: {e}")
            result = {"source": "maharera", "data": {"error": str(e)}}
            await asyncio.sleep(5)
            
    if status == "failed":
        log.warning("MahaRERA portal failed completely. Using DuckDuckGo fallback to find Project/Promoter names...")
        try:
            from src.utils.llm import groq_generate_with_retry
            from curl_cffi import requests
            from bs4 import BeautifulSoup
            from pydantic import BaseModel
            import json
            
            class FallbackData(BaseModel):
                project_name: str
                promoter_name: str
                
            resp = requests.get(f"https://html.duckduckgo.com/html/?q={state['rera_number']}+maharera", impersonate="chrome")
            soup = BeautifulSoup(resp.content, "html.parser")
            snippets = " ".join([a.text for a in soup.find_all("a", class_="result__snippet")])
            
            prompt = f"Extract the Real Estate Project Name and Promoter/Developer Name for RERA Number {state['rera_number']} from these search snippets: {snippets}"
            res = await groq_generate_with_retry(contents=prompt, response_schema=FallbackData)
            
            if res:
                fb_data = json.loads(res.text)
                log.info(f"Fallback extracted: {fb_data}")
                result = {
                    "source": "maharera",
                    "data": {
                        "project_name": fb_data.get("project_name", state["rera_number"]),
                        "promoter_name": fb_data.get("promoter_name", state["rera_number"]),
                        "error": "Portal down. Data from fallback search.",
                    }
                }
        except Exception as e:
            log.error(f"Fallback also failed: {e}")

    return {
        "partial_briefs": [result],
        "agent_statuses": {"maharera": status},
    }


async def downstream_agents_node(state: PipelineState) -> Dict[str, Any]:
    log.info("Running downstream agents sequentially...")

    zaubacorp_agent = ZaubacorpAgent(rera_number=state["rera_number"])
    acres_agent = NinetyNineAcresAgent(rera_number=state["rera_number"])
    housing_agent = HousingAgent(rera_number=state["rera_number"])

    # ── Dynamic context: strictly bounded by MahaRERA or Fallback ────────
    context = {
        "promoter_name": state.get("fallback_developer", ""),
        "project_name": state.get("fallback_project", ""),
        "location": state.get("fallback_location", ""),
    }
    
    # If MahaRERA ran, override with its exact data
    for partial in state.get("partial_briefs", []):
        if partial.get("source") == "maharera" and not partial.get("data", {}).get("error"):
            data = partial.get("data", {})
            if data.get("promoter_name"):
                context["promoter_name"] = data["promoter_name"]
            if data.get("project_name"):
                context["project_name"] = data["project_name"]
            if data.get("location"):
                context["location"] = data["location"]
            break

    log.info(f"Downstream bounded context: {context}")

    # ── Run sequentially with delays to protect Free Tier limits ───
    z_res = await zaubacorp_agent.run(context_data=context)
    await asyncio.sleep(INTER_AGENT_DELAY_SECONDS)

    a_res = await acres_agent.run(context_data=context)
    await asyncio.sleep(INTER_AGENT_DELAY_SECONDS)

    h_res = await housing_agent.run(context_data=context)

    results = [z_res, a_res, h_res]
    names = ["zaubacorp", "99acres", "housing"]

    partial_briefs = []
    agent_statuses = {}

    for i, name in enumerate(names):
        res = results[i]
        if isinstance(res, Exception):
            log.error(f"{name} Agent failed: {res}")
            partial_briefs.append({"source": name, "data": {"error": str(res)}})
            agent_statuses[name] = "failed"
        else:
            partial_briefs.append(res)
            agent_statuses[name] = "success"

    return {
        "partial_briefs": partial_briefs,
        "agent_statuses": agent_statuses,
    }


async def merge_node(state: PipelineState) -> Dict[str, Any]:
    log.info("Merging partial briefs...")
    final_brief_data = {}

    for partial in state.get("partial_briefs", []):
        source = partial.get("source")
        data = partial.get("data", {})

        if source == "maharera" and not data.get("error"):
            final_brief_data["promoter_name"] = data.get("promoter_name")
            final_brief_data["project_name"] = data.get("project_name")
            final_brief_data["project_type"] = data.get("project_type")
            final_brief_data["plot_area"] = data.get("plot_area")
            final_brief_data["construction_status_rera"] = data.get("construction_status")
            final_brief_data["proposed_completion_date"] = data.get("proposed_completion_date")
            final_brief_data["cost_breakdown"] = data.get("cost_breakdown")
            final_brief_data["projected_revenue"] = data.get("projected_revenue")
            final_brief_data["facility_loan_amount"] = data.get("facility_loan_amount")
            final_brief_data["documents"] = data.get("documents", [])

        elif source == "zaubacorp" and not data.get("error"):
            final_brief_data["group_name"] = data.get("company_searched")
            final_brief_data["group_net_worth"] = data.get("paid_up_capital")
            final_brief_data["directors"] = data.get("directors", [])
            final_brief_data["other_business_lines"] = [data.get("business_activity")]

        elif source == "99acres" and not data.get("error"):
            final_brief_data["project_status"] = data.get("project_status")
            final_brief_data["possession_date"] = data.get("possession_date")
            final_brief_data["configurations_99acres"] = data.get("configurations", [])
            final_brief_data["location_advantages_99acres"] = data.get("location_advantages", [])
            final_brief_data["site_images_99acres"] = data.get("site_images", [])

        elif source == "housing.com" and not data.get("error"):
            final_brief_data["project_status_housing"] = data.get("project_status")
            final_brief_data["configurations_housing"] = data.get("configurations", [])
            final_brief_data["location_advantages_housing"] = data.get("location_advantages", [])
            final_brief_data["site_images_housing"] = data.get("site_images", [])

    # Aggregate images
    img_set = []
    for img in final_brief_data.get("site_images_99acres", []) + final_brief_data.get("site_images_housing", []):
        if img and img not in img_set:
            img_set.append(img)
    final_brief_data["site_images"] = img_set[:3] # Keep top 3 overall

    # Cross-source conflict detection
    conflicts = []
    status_99acres = final_brief_data.get("project_status")
    status_housing = final_brief_data.get("project_status_housing")
    if status_99acres and status_housing and status_99acres.lower() != status_housing.lower():
        conflicts.append({
            "field": "Project Status",
            "values": {"99acres": status_99acres, "housing.com": status_housing},
        })
    final_brief_data["conflicts"] = conflicts

    return {"final_brief": final_brief_data}


async def synthesize_node(state: PipelineState) -> Dict[str, Any]:
    log.info("Synthesizing executive summary...")
    final_brief = state.get("final_brief", {})

    from src.utils.llm import groq_generate_with_retry
    import json

    prompt = (
        "You are a Senior Real Estate Analyst. Write a 2-paragraph executive summary for this project. "
        "It should read like a professional credit memo introduction.\n\n"
        f"Data:\n{json.dumps(final_brief, indent=2)}\n\n"
        "Return ONLY the plain text summary, no markdown, no prefixes."
    )

    class SummaryData(BaseModel):
        summary: str

    res = await groq_generate_with_retry(contents=prompt, response_schema=SummaryData)
    
    if res:
        try:
            summary_data = json.loads(res.text)
            final_brief["executive_summary"] = summary_data.get("summary", "Executive summary generation failed.")
        except:
            final_brief["executive_summary"] = res.text
    else:
        final_brief["executive_summary"] = "Executive summary generation failed."

    return {"final_brief": final_brief}


async def eligibility_node(state: PipelineState) -> Dict[str, Any]:
    log.info("Calculating Funding Eligibility Score...")
    final_brief = state.get("final_brief", {})

    from src.utils.llm import groq_generate_with_retry
    import json
    from pydantic import Field

    class EligibilityAssessment(BaseModel):
        score: int = Field(description="Score from 1 to 10")
        recommendation: str = Field(description="One of: 'Eligible', 'Conditional', 'Not Eligible'")
        strengths: list[str] = Field(description="List of strong points")
        risks: list[str] = Field(description="List of risk factors")
        conditions: list[str] = Field(description="List of conditions for approval")
        narrative: str = Field(description="2-3 paragraph analyst summary justifying the score")

    # Flag if RERA was missing
    rera_context = ""
    if not state.get("rera_number"):
        rera_context = "WARNING: No RERA number was provided. This project's registration is unverified. This is a major risk factor."

    prompt = f"""You are a Junior Credit Analyst evaluating a real estate project for funding eligibility.
Evaluate the following project data and generate a score (1-10) and recommendation (Eligible: 8-10, Conditional: 5-7, Not Eligible: 1-4).
{rera_context}

Project Data:
{json.dumps(final_brief, indent=2)}
"""

    res = await groq_generate_with_retry(contents=prompt, response_schema=EligibilityAssessment)
    
    if res:
        try:
            eligibility_data = json.loads(res.text)
            final_brief["eligibility"] = eligibility_data
        except Exception as e:
            log.error(f"Failed to parse eligibility data: {e}")
            final_brief["eligibility"] = None
    else:
        final_brief["eligibility"] = None

    return {"final_brief": final_brief}


async def generate_docx_node(state: PipelineState) -> Dict[str, Any]:
    log.info("Generating DOCX...")
    from src.output.docx_generator import generate_docx

    final_brief = state.get("final_brief", {})

    import os
    import time
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    rera_num = state.get("rera_number", "UNKNOWN")
    timestamp = int(time.time())
    output_path = os.path.join(output_dir, f"Brief_{rera_num}_{timestamp}.docx")
    template_path = "src/output/template.docx"

    generate_docx(final_brief, template_path, output_path)

    return {"docx_path": output_path}
