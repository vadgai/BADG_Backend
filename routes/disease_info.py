"""
Disease Info API Route
Provides patient-friendly, structured disease information using Gemini.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

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


def _title_from_key(key: str) -> str:
    return re.sub(r"\b\w", lambda match: match.group(0).upper(), key.replace("_", " "))


def _format_section_value(value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    lines: list[str] = []

    if value is None:
        return lines
    if isinstance(value, str):
        text = value.strip()
        if text:
            lines.append(f"{prefix}{text}")
        return lines
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                lines.append(f"{prefix}- {item.strip()}")
            else:
                lines.extend(_format_section_value(item, indent))
        return lines
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if isinstance(child_value, (str, list)) or (
                isinstance(child_value, dict) and child_value
            ):
                if isinstance(child_value, str):
                    lines.append(f"{prefix}- **{_title_from_key(child_key)}:** {child_value.strip()}")
                elif isinstance(child_value, list):
                    lines.append(f"{prefix}- **{_title_from_key(child_key)}:**")
                    lines.extend(_format_section_value(child_value, indent + 1))
                else:
                    lines.append(f"{prefix}- **{_title_from_key(child_key)}:**")
                    lines.extend(_format_section_value(child_value, indent + 1))
        return lines

    lines.append(f"{prefix}{str(value)}")
    return lines


def _json_to_markdown(data: dict[str, Any], disease_name: str) -> str:
    name = (
        data.get("disease")
        or data.get("disease_name")
        or data.get("name")
        or disease_name
    )
    lines = [f"## What is {name}?"]

    description = data.get("description") or data.get("summary")
    sections = data.get("sections")
    if not description and isinstance(sections, dict):
        for key, value in sections.items():
            if re.match(r"^what[\s_]?is", key, re.IGNORECASE) or key.startswith("what_is"):
                if isinstance(value, str):
                    description = value
                break
    if not description and isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("heading") or "").strip()
            content = section.get("content") or section.get("text")
            if re.search(r"what\s+is", title, re.IGNORECASE) and isinstance(content, str):
                description = content
                break

    lines.append(description.strip() if isinstance(description, str) else "")
    lines.append("")

    section_map = [
        ("Causes & Transmission", ["causes", "etiology", "cause", "transmission", "causes_and_transmission"]),
        ("Risk Factors", ["risk_factors", "risks"]),
        ("Common Symptoms", ["symptoms", "common_symptoms"]),
        ("How It Is Diagnosed", ["diagnosis", "how_it_is_diagnosed", "diagnostic"]),
        ("Treatment Options", ["treatment", "treatment_options", "medications", "meds"]),
        ("Prevention", ["prevention", "preventive_measures"]),
        ("Home Remedies", ["home_remedies"]),
        ("Recommended (Do)", ["recommended", "recommendations", "do"]),
        ("Avoid (Don't)", ["avoid", "dont", "do_not"]),
        ("When to See a Doctor", ["when_to_see_a_doctor", "red_flags", "warning_signs"]),
    ]

    rendered_keys: set[str] = set()
    for title, keys in section_map:
        for key in keys:
            if key in data and data[key] not in (None, "", [], {}):
                lines.append(f"## {title}")
                lines.extend(_format_section_value(data[key]))
                lines.append("")
                rendered_keys.add(key)
                break

    if isinstance(sections, dict):
        for key, value in sections.items():
            if key in rendered_keys:
                continue
            if re.match(r"^what[\s_]?is", key, re.IGNORECASE) or key.startswith("what_is"):
                continue
            lines.append(f"## {_title_from_key(key)}")
            lines.extend(_format_section_value(value))
            lines.append("")
    elif isinstance(sections, list):
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("heading") or f"Section {idx + 1}").strip()
            if re.search(r"what\s+is", title, re.IGNORECASE):
                continue
            data_value = section.get("content") or section.get("points") or section.get("items")
            if data_value in (None, "", [], {}):
                continue
            lines.append(f"## {title}")
            lines.extend(_format_section_value(data_value))
            lines.append("")

    lines.append(
        "> **Note:** This is general information for educational purposes. "
        "Always consult a qualified healthcare professional for personalized medical advice."
    )
    return "\n".join(line for line in lines if line is not None)


def _normalize_information(text: str, disease_name: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    if not cleaned.startswith("{"):
        return cleaned

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return text.strip()

    if isinstance(data, dict):
        if "medical_summary" in data and isinstance(data["medical_summary"], dict):
            data = data["medical_summary"]
        return _json_to_markdown(data, disease_name)

    return text.strip()


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

        information = _normalize_information(text, disease_name)

        return {
            "disease_name": disease_name,
            "language": payload.language or "en",
            "information": information,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error generating disease info: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate disease information.")
