import os
from google import genai

async def extract_pdf_data(pdf_bytes: bytes, extraction_prompt: str) -> str:
    """
    Given PDF bytes, uses Gemini 2.5 Flash Vision to extract data based on the prompt.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
        
    client = genai.Client(api_key=api_key)
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            extraction_prompt,
            {"mime_type": "application/pdf", "data": pdf_bytes}
        ],
        config={"temperature": 0.0}
    )
    
    return response.text.strip()
