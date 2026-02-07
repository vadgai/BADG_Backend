"""
Disease Info API Route
Provides patient-friendly, structured disease information using Gemini.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.gemini_api_manager import generate_content_with_fallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["disease-info"])


class DiseaseInfoRequest(BaseModel):
    disease_name: str
    language: Optional[str] = "en"


def _load_prompt_template() -> str:
    """
    Load the disease-info prompt template from documents/prompt.txt.
    Falls back to an embedded template if the file is missing.
    """
    try:
        backend_dir = Path(__file__).resolve().parent.parent
        root_dir = backend_dir.parent
        prompt_path = root_dir / "documents" / "prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("Failed to load prompt template from documents/prompt.txt: %s", exc)

    # Minimal fallback
    return (
        "You are a medical expert. Provide comprehensive, accurate information about the disease: {disease_name}\n\n"
        "Please provide information in {language} language covering:\n"
        "1. What is this disease? (Brief description)\n"
        "2. What causes it? (Etiology)\n"
        "3. Common symptoms and signs\n"
        "4. How is it diagnosed?\n"
        "5. Treatment options (medical and lifestyle)\n"
        "6. Prevention methods\n"
        "7. Home remedies (if applicable)\n"
        "8. When to see a doctor (red flags)\n\n"
        "Format your response in clear, easy-to-understand language for patients.\n"
        "Use bullet points and sections for readability.\n"
        "Be accurate but avoid unnecessary medical jargon."
    )


@router.post("/disease-info")
async def disease_info(payload: DiseaseInfoRequest):
    """
    Generate structured disease information for a given disease name.
    Returns a markdown-like template string in `information`.
    """
    disease_name = (payload.disease_name or "").strip()
    if not disease_name:
        raise HTTPException(status_code=400, detail="disease_name is required")

    prompt_template = _load_prompt_template()
    prompt = prompt_template.format(
        disease_name=disease_name,
        language=payload.language or "en"
    )

    try:
        success, text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,  # try all keys
            temperature=0.3,
            max_output_tokens=2000,
        )
        if not success or not text:
            logger.error("Disease info generation failed: %s", error)
            raise HTTPException(status_code=503, detail="AI service unavailable. Please try again.")

        return {
            "disease_name": disease_name,
            "language": payload.language or "en",
            "information": text.strip(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error generating disease info: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate disease information.")
