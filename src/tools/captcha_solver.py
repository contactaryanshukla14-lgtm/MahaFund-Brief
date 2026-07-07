import os
from google import genai

async def solve_captcha(image_bytes: bytes) -> str:
    """
    Given image bytes of a CAPTCHA, uses Gemini 2.5 Flash Vision to solve it.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
        
    client = genai.Client(api_key=api_key)
    
    prompt = (
        "Read the exact text shown in this CAPTCHA image. "
        "Return ONLY the characters, nothing else. Do not include spaces "
        "unless they are clearly part of the CAPTCHA."
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            prompt,
            {"mime_type": "image/png", "data": image_bytes}
        ],
        config={"temperature": 0.0}
    )
    
    return response.text.strip()
