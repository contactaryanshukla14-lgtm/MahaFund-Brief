import os
import json
import base64
import uuid
import asyncio
from typing import Dict, Any

from playwright.async_api import async_playwright
from pydantic import BaseModel, Field
from google.genai import types
import fitz  # PyMuPDF
import httpx
from bs4 import BeautifulSoup
from io import BytesIO

from src.agents.base import BaseAgent
from src.schema.enums import SourceName
from src.utils.llm import get_gemini_client, gemini_generate_with_retry, groq_generate_with_retry
from src.utils.logger import get_logger
from src.config import (
    GEMINI_MODEL, DEFAULT_USER_AGENT, DEBUG_BROWSER,
    CAPTCHA_WAIT_TIMEOUT_MS, CAPTCHA_MAX_ATTEMPTS, PAGE_LOAD_WAIT_MS,
)

log = get_logger("maharera")


class MahareraData(BaseModel):
    project_name: str = Field(description="Name of the project")
    promoter_name: str = Field(description="Name of the promoter / developer group", default="")
    project_type: str = Field(description="Project Type (e.g., Others, Commercial, Residential)")
    location: str = Field(description="City or specific location of the project", default="")
    plot_area: str = Field(description="Total Land Area of Approved Layout (Sq. Mts.) or Plot area")
    proposed_completion_date: str = Field(description="Proposed Completion Date (Original)")
    construction_status: str = Field(description="Status of construction (e.g., Active)")
    cost_breakdown: str = Field(description="Extract any financial numbers related to costs, expenses, land cost, construction cost, amounts deposited or amounts withdrawn found in the attached PDFs. If none are found, state 'Not found'.")
    projected_revenue: str = Field(description="Extract any financial numbers related to revenue, sales, funds collected, or amount received found in the attached PDFs. If none are found, state 'Not found'.")
    facility_loan_amount: str = Field(description="Extract the Facility/Loan Amount, encumbrance details, or secured amount if any. If none found, state 'Not found'.")


class MahareraAgent(BaseAgent):
    """Agent that performs the exact dual-portal MahaRERA flow with CAPTCHA solving and PDF parsing."""

    async def run(self, context_data: Dict[str, Any] = None) -> Dict[str, Any]:
        log.info(f"Starting MahareraAgent for RERA: {self.rera_number}")

        client = get_gemini_client()
        if not client:
            return {"source": SourceName.MAHARERA.value, "data": {}}
        extracted_data = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=not DEBUG_BROWSER
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=DEFAULT_USER_AGENT,
            )
            page = await context.new_page()

            try:
                # ── Step 1: Navigate to search portal and type RERA number ──
                log.info("Navigating to MahaRERA search portal...")
                await page.goto(
                    "https://maharera.maharashtra.gov.in/projects-search-result",
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(3000)

                log.info("Typing RERA Number...")
                await page.fill("input#edit-project-name", self.rera_number)
                await page.click("input#edit-submit")
                await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)

                # ── Step 2: Find "View Details" link ───────────────────────
                log.info("Finding View Details link...")
                view_details_link = await page.evaluate('''() => {
                    let links = Array.from(document.querySelectorAll('a'));
                    let target = links.find(a => a.innerText.includes("View Details") && a.href.includes("project"));
                    return target ? target.href : null;
                }''')

                if not view_details_link:
                    raise Exception("View Details link not found on search results page.")

                log.info(f"Clicking View Details: {view_details_link}")
                await page.goto(view_details_link, wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)

                # Dismiss any external-site modal
                try:
                    yes_btn = await page.query_selector("button:has-text('Yes')")
                    if yes_btn:
                        await yes_btn.click()
                        await page.wait_for_timeout(3000)
                except Exception:
                    pass

                # ── Step 3: CAPTCHA detection + retry loop ─────────────────
                log.info("Waiting for CAPTCHA to render...")
                try:
                    await page.wait_for_selector(
                        "canvas#captcahCanvas, img#imgCaptcha, img[src*='captcha']",
                        timeout=CAPTCHA_WAIT_TIMEOUT_MS,
                    )
                except Exception:
                    log.warning("Timeout waiting for CAPTCHA, proceeding anyway...")

                captcha_solved = False
                for attempt in range(1, CAPTCHA_MAX_ATTEMPTS + 1):
                    captcha_canvas = await page.query_selector("canvas#captcahCanvas")
                    captcha_img = await page.query_selector("img#imgCaptcha, img[src*='captcha']")

                    if not (captcha_canvas or captcha_img):
                        log.info("No CAPTCHA detected — page is open.")
                        captcha_solved = True
                        break

                    log.info(f"CAPTCHA detected (attempt {attempt}/{CAPTCHA_MAX_ATTEMPTS}). Solving...")

                    # Extract base64 from canvas or image
                    if captcha_canvas:
                        base64_img = await page.evaluate(
                            "document.getElementById('captcahCanvas')"
                            ".toDataURL('image/png').split(',')[1]"
                        )
                    else:
                        base64_img = await page.evaluate("""(img) => {
                            let canvas = document.createElement('canvas');
                            canvas.width = img.width || img.naturalWidth;
                            canvas.height = img.height || img.naturalHeight;
                            let ctx = canvas.getContext('2d');
                            ctx.drawImage(img, 0, 0);
                            return canvas.toDataURL('image/png').split(',')[1];
                        }""", captcha_img)

                    # Ask Gemini Vision to read the CAPTCHA
                    solve_response = await gemini_generate_with_retry(
                        contents=[
                            types.Part.from_bytes(
                                data=base64.b64decode(base64_img),
                                mime_type="image/png",
                            ),
                            "Read the alphanumeric characters in this captcha image. "
                            "Respond ONLY with the characters, no spaces, no other text.",
                        ],
                    )

                    if not solve_response:
                        log.error("Failed to solve CAPTCHA via Gemini.")
                        break

                    captcha_text = solve_response.text.strip().replace(" ", "")
                    log.info(f"CAPTCHA solved: {captcha_text}")

                    # Fill and submit
                    await page.fill(
                        "input[name='CaptchaInputText'], input[type='text']:not([hidden])",
                        captcha_text,
                    )
                    await page.click("button:has-text('Submit'), input[type='submit']")
                    await page.wait_for_timeout(4000)

                    # Check if CAPTCHA is still visible (means wrong answer)
                    still_visible = await page.query_selector("canvas#captcahCanvas")
                    if still_visible:
                        log.warning(f"CAPTCHA attempt {attempt} failed — refreshing...")
                        refresh_btn = await page.query_selector("a:has-text('↻'), .captcha-refresh, a[title='Refresh']")
                        if refresh_btn:
                            await refresh_btn.click()
                            await page.wait_for_timeout(2000)
                    else:
                        captcha_solved = True
                        log.info("CAPTCHA passed! Checking for new tabs...")
                        pages = context.pages
                        if len(pages) > 1:
                            log.info(f"Detected {len(pages)} tabs. Switching to the newest tab...")
                            page = pages[-1]
                        
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(6000)
                        
                        # HTML successfully loaded after captcha
                        break

                # ── Step 4: Extract page HTML ──────────────────────────────
                html_content = await page.content()
                
                # ── Step 5: Download and parse important PDFs via Angular Click Interception ───
                pdf_parts_for_gemini = []
                document_index = []
                
                # We need to find the specific buttons. 
                btn_elements = await page.query_selector_all("a.download, a.Download, a#download, a#downloadFile")
                
                target_btns = []
                for btn in btn_elements:
                    try:
                        parent_text = await btn.evaluate("el => el.parentElement.parentElement.innerText || ''")
                        lower_text = parent_text.lower()
                        
                        # Categorize documents
                        if "form 3" in lower_text or "form 5" in lower_text or "ca " in lower_text or "chartered accountant" in lower_text or "audit" in lower_text:
                            target_btns.append((btn, "Financial Statement / CA Certificate (Form 3/5)", True))
                        elif "registration" in lower_text or "rera certificate" in lower_text:
                            target_btns.append((btn, "RERA Registration Certificate", False))
                        elif "title" in lower_text:
                            target_btns.append((btn, "Legal Title Report", False))
                        elif "layout" in lower_text or "plan approval" in lower_text:
                            target_btns.append((btn, "Layout / Plan Approval", False))
                        elif "form b" in lower_text or "declaration" in lower_text:
                            target_btns.append((btn, "Declaration (Form B)", False))
                        elif "allotment" in lower_text or "agreement" in lower_text:
                            target_btns.append((btn, "Proforma of Allotment / Agreement", False))
                    except Exception:
                        pass
                
                # If we couldn't confidently identify them, take the first 3
                if not target_btns:
                    for i, btn in enumerate(btn_elements[:3]):
                        target_btns.append((btn, f"Project Document {i+1}", False))
                
                # Ensure we only have up to 6 unique targets max
                final_targets = []
                seen_types = set()
                for btn, dtype, is_financial in target_btns:
                    # Allow multiple financial forms if they are different years, but limit total to 6
                    if len(final_targets) < 6 and (dtype not in seen_types or is_financial):
                        final_targets.append((btn, dtype, is_financial))
                        if not is_financial:
                            seen_types.add(dtype)

                cookies = await context.cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                
                for idx, (btn, doc_type, is_financial) in enumerate(final_targets):
                    title = doc_type
                    href = ""
                    log.info(f"Downloading PDF {idx+1}/{len(final_targets)}: {title}")
                    
                    pdf_path = f"temp_{uuid.uuid4().hex}_{idx}.pdf"
                    
                    fut = asyncio.get_event_loop().create_future()
                    def on_download(d):
                        if not fut.done(): fut.set_result(("download", d))
                    def on_popup(p):
                        if not fut.done(): fut.set_result(("popup", p))
                        
                    page.once("download", on_download)
                    context.once("page", on_popup)
                    
                    await btn.evaluate("el => el.click()")
                    
                    try:
                        result_type, obj = await asyncio.wait_for(fut, timeout=15.0)
                        if result_type == "download":
                            await obj.save_as(pdf_path)
                            href = obj.url
                        else:
                            await obj.wait_for_load_state()
                            href = obj.url
                            if href.startswith("blob:"):
                                base64_data = await obj.evaluate(f'''async () => {{
                                    const response = await fetch("{href}");
                                    const blob = await response.blob();
                                    return new Promise((resolve) => {{
                                        const reader = new FileReader();
                                        reader.onloadend = () => resolve(reader.result.split(",")[1]);
                                        reader.readAsDataURL(blob);
                                    }});
                                }}''')
                                with open(pdf_path, "wb") as f:
                                    f.write(base64.b64decode(base64_data))
                            elif href.startswith("http"):
                                resp = httpx.get(href, headers={"Cookie": cookie_str}, timeout=15.0)
                                with open(pdf_path, "wb") as f:
                                    f.write(resp.content)
                            else:
                                raise ValueError(f"Invalid popup URL: {href}")
                            await obj.close()
                    except asyncio.TimeoutError:
                        log.warning(f"Timeout waiting for download/popup for {title}")
                        continue
                    finally:
                        try: page.remove_listener("download", on_download)
                        except: pass
                        try: context.remove_listener("page", on_popup)
                        except: pass
                        
                    if not href:
                        continue

                    # ── PDF Upload and Gemini Integration ──
                    pdf_part = None
                    try:
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()
                            # Prepare for Gemini only if it's a financial doc
                            if is_financial:
                                pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                            
                            # Upload to tmpfiles.org for a shareable URL
                            files = {'file': (f"{title.replace(' ', '_')}_{idx}.pdf", pdf_bytes, 'application/pdf')}
                            upload_resp = httpx.post("https://tmpfiles.org/api/v1/upload", files=files, timeout=30.0)
                            if upload_resp.status_code == 200:
                                upload_data = upload_resp.json()
                                raw_url = upload_data.get("data", {}).get("url", "")
                                href = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/") if raw_url else href
                            else:
                                log.warning(f"Failed to upload {title} to tmpfiles: {upload_resp.text}")
                    except Exception as e:
                        log.error(f"Error handling PDF {title}: {e}")
                    
                    if pdf_part:
                        pdf_parts_for_gemini.append(pdf_part)
                    
                    # Add to index immediately
                    document_index.append({
                        "title": title,
                        "href": href,
                        "document_type": doc_type,
                        "summary": "Financial and Registration details" if is_financial else "Project Registration / General Document"
                    })

                    try:
                        os.remove(pdf_path)
                    except:
                        pass

                log.info("Extracting final structured data with Gemini using PDF vision...")
                
                soup = BeautifulSoup(html_content, "html.parser")
                clean_html_text = soup.get_text(separator=" ", strip=True)
                
                prompt_text = (
                    "Extract the required MahaRERA project information. "
                    "Use the PAGE TEXT for project basics. "
                    "CRITICAL: I have attached the actual Financial PDF documents (CA Certificate / Form 3 / Form 5). "
                    "You MUST read the attached PDFs to extract the precise financial numbers: "
                    "'Total Estimated Cost of the Real Estate Project', 'Cost of Construction', 'Land Cost', and 'Projected Revenue'. "
                    "Look for tables containing these financial figures.\n\n"
                    f"--- PAGE TEXT ---\n{clean_html_text[:25000]}\n"
                )

                schema_dict = MahareraData.model_json_schema()
                prompt_text += f"\nYou MUST return ONLY a valid JSON object adhering exactly to this schema:\n{json.dumps(schema_dict)}"
                
                contents_payload = pdf_parts_for_gemini + [prompt_text]

                response = await gemini_generate_with_retry(
                    contents=contents_payload,
                )

                if response:
                    raw_text = response.text.strip()
                    if raw_text.startswith("```json"):
                        raw_text = raw_text.split("```json")[1]
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("```")[1]
                    if raw_text.endswith("```"):
                        raw_text = raw_text.rsplit("```", 1)[0]
                    raw_text = raw_text.strip()
                    
                    try:
                        extracted_data = json.loads(raw_text)
                        extracted_data["documents"] = document_index # Attach the generated index!
                    except json.JSONDecodeError as e:
                        log.error(f"Failed to parse JSON: {e} | Raw text: {raw_text[:200]}")
                        extracted_data = {"error": "JSON parse error"}
                else:
                    log.error("Groq extraction returned None after retries.")

            except Exception as e:
                log.error(f"MahaRERA flow failed: {e}")
                extracted_data = {"error": str(e)}

            await browser.close()

        return {
            "source": SourceName.MAHARERA.value,
            "data": extracted_data,
        }
