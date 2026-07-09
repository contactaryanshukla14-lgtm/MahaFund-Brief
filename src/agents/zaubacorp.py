import os
import json

import httpx
from bs4 import BeautifulSoup
from typing import Dict, Any
from curl_cffi import requests as curl_requests
from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.schema.enums import SourceName
from src.utils.llm import groq_generate_with_retry
from src.utils.logger import get_logger
from src.config import DEFAULT_USER_AGENT, NETWORK_TIMEOUT_SECONDS

log = get_logger("zaubacorp")


class ZaubacorpData(BaseModel):
    authorized_capital: str = Field(description="The authorized capital of the company")
    paid_up_capital: str = Field(description="The paid up capital of the company")
    business_activity: str = Field(description="The business activity or NIC code description")
    directors: list[str] = Field(description="List of names of the directors")


class ZaubacorpAgent(BaseAgent):
    """Agent that uses DuckDuckGo to find the Zaubacorp profile and curl_cffi+Gemini to extract details."""

    async def run(self, context_data: Dict[str, Any] = None) -> Dict[str, Any]:
        log.info("Starting ZaubacorpAgent...")
        promoter_name = (context_data or {}).get("promoter_name", "Poonam Group")

        # ── Step 1: DuckDuckGo search ──────────────────────────────────
        log.info(f"Searching DuckDuckGo for: site:zaubacorp.com {promoter_name}")
        search_url = "https://html.duckduckgo.com/html/"
        target_company = None
        
        try:
            res = curl_requests.post(search_url, data={"q": f"site:zaubacorp.com {promoter_name}"}, impersonate="chrome120", timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for a in soup.select("a.result__url"):
                    href = a.get("href", "")
                    text = a.text.strip()
                    if "zaubacorp.com/company/" in href or "zaubacorp.com/company/" in text:
                        real_url = f"https://{text}" if "zaubacorp.com" in text else href
                        if not real_url.startswith("http"):
                            real_url = "https://" + real_url
                        target_company = {"text": text, "href": real_url}
                        break
        except Exception as e:
            log.warning(f"DuckDuckGo search failed for Zaubacorp: {e}")

        if not target_company:
            log.warning("No company links found in DuckDuckGo results.")
            return {
                "source": SourceName.ZAUBACORP.value,
                "data": {"error": f"Could not find Zaubacorp profile for {promoter_name}"},
            }

        log.info(f"Selecting company URL: {target_company['href']}")
        extracted_data = {}

        # ── Step 2: Fetch page via curl_cffi ───────────────────────────
        log.info(f"Fetching {target_company['href']} using curl_cffi...")
        try:
            proxy_url = os.getenv("PROXY_URL")
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url and proxy_url != "auto" else None

            resp = curl_requests.get(
                target_company["href"],
                impersonate="chrome120",
                proxies=proxies,
                timeout=NETWORK_TIMEOUT_SECONDS,
            )

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)

            # ── Step 3: Groq extraction with retry ───────────────────
            log.info("Extracting structured data with Groq...")
            prompt = (
                "Extract the following information about the company from "
                "the provided Zaubacorp page text:\n"
                "1. Authorized Capital\n2. Paid Up Capital\n"
                "3. Business activity / NIC code description\n"
                "4. List of Director names\n\n"
                f"Text:\n{page_text[:15000]}"
            )

            response = await groq_generate_with_retry(
                contents=prompt,
                response_schema=ZaubacorpData,
            )

            if response:
                extracted_data = json.loads(response.text)
                extracted_data["company_searched"] = promoter_name
                extracted_data["url"] = target_company["href"]
            else:
                log.error("Groq extraction returned None after retries.")

        except Exception as e:
            log.error(f"Zaubacorp extraction failed: {e}")
            extracted_data = {"error": str(e)}

        return {
            "source": SourceName.ZAUBACORP.value,
            "data": extracted_data,
        }
