import os
import json

import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from curl_cffi import requests as curl_requests
from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.schema.enums import SourceName
from src.utils.llm import groq_generate_with_retry
from src.utils.logger import get_logger
from src.config import DEFAULT_USER_AGENT, NETWORK_TIMEOUT_SECONDS

log = get_logger("housing")


class UnitMix(BaseModel):
    configuration: str = Field(description="E.g., 2 BHK, 3 BHK")
    carpet_area: str = Field(description="Carpet area")
    price: str = Field(description="Price or price range for this configuration")


class HousingData(BaseModel):
    project_status: str = Field(description="Construction status (e.g., Under Construction, Ready to Move)")
    possession_date: str = Field(description="Expected possession date if available", default="")
    configurations: List[UnitMix] = Field(description="List of available unit configurations with area and price")
    location_advantages: List[str] = Field(description="List of nearby landmarks, connectivity details", default=[])
    site_images: List[str] = Field(description="List of up to 3 high-quality image URLs representing the project", default=[])


class HousingAgent(BaseAgent):
    """Agent that uses DuckDuckGo to find the Housing.com project page and curl_cffi+Gemini to extract details."""

    async def run(self, context_data: Dict[str, Any] = None) -> Dict[str, Any]:
        log.info("Starting HousingAgent...")
        project_name = (context_data or {}).get("project_name", "Poonam Estate Cluster 2")

        # ── Step 1: DuckDuckGo search ──────────────────────────────────
        log.info(f"Searching DuckDuckGo for: site:housing.com {project_name}")
        search_url = "https://html.duckduckgo.com/html/"
        res = curl_requests.post(search_url, data={"q": f"site:housing.com {project_name}"}, impersonate="chrome120")

        target_project = None
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.select("a.result__url"):
                href = a.get("href", "")
                text = a.text.strip()
                if "housing.com/in/" in href or "housing.com/in/" in text:
                    real_url = f"https://{text}" if "housing.com" in text else href
                    if not real_url.startswith("http"):
                        real_url = "https://" + real_url
                    target_project = {"text": text, "href": real_url}
                    break

        if not target_project:
            log.warning("No project links found in DuckDuckGo results.")
            return {
                "source": SourceName.HOUSING_COM.value,
                "data": {"error": f"Could not find Housing.com page for {project_name}"},
            }

        log.info(f"Selecting Housing.com URL: {target_project['href']}")
        extracted_data = {}

        # ── Step 2: Fetch page via curl_cffi ───────────────────────────
        log.info(f"Fetching {target_project['href']} using curl_cffi...")
        try:
            proxy_url = os.getenv("PROXY_URL")
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url and proxy_url != "auto" else None

            resp = curl_requests.get(
                target_project["href"],
                impersonate="chrome120",
                proxies=proxies,
                timeout=NETWORK_TIMEOUT_SECONDS,
            )

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)

            # Extract image URLs
            img_urls = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src and ("jpg" in src.lower() or "png" in src.lower()) and "icon" not in src.lower() and "logo" not in src.lower():
                    if src.startswith("//"): src = "https:" + src
                    elif src.startswith("/"): src = "https://housing.com" + src
                    img_urls.append(src)
            # Take a sample of images so Groq doesn't get overwhelmed
            image_context = "\n".join(list(set(img_urls))[:20])

            # ── Step 3: Groq extraction with retry ───────────────────
            log.info("Extracting structured data from Housing.com with Groq...")
            prompt = (
                "Extract the following information about the real estate project "
                "from the provided Housing.com page text:\n"
                "1. Construction status (Ready to Move, Under Construction, etc.)\n"
                "2. Expected possession date\n"
                "3. Available configurations (BHKs, Area, Price)\n"
                "4. Location advantages / Connectivity\n"
                "5. Select the top 3 most relevant site images (high-quality project photos/elevations) from the Image URLs provided below.\n\n"
                f"Image URLs:\n{image_context}\n\n"
                f"Text:\n{page_text[:15000]}"
            )

            response = await groq_generate_with_retry(
                contents=prompt,
                response_schema=HousingData,
            )

            if response:
                extracted_data = json.loads(response.text)
                extracted_data["project_searched"] = project_name
                extracted_data["url"] = target_project["href"]
            else:
                log.error("Groq extraction returned None after retries.")

        except Exception as e:
            log.error(f"Housing extraction failed: {e}")
            extracted_data = {"error": str(e)}

        return {
            "source": SourceName.HOUSING_COM.value,
            "data": extracted_data,
        }
