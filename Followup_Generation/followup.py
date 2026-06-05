# Backend/Followup_Generation/followup.py
import os
import json
import ast
import math
import logging
from typing import Optional, Union, Dict
from dotenv import load_dotenv

from utils.gemini_api_manager import (
    generate_content_with_fallback,
    get_gemini_model,
    extract_json_from_text,
)

# Load env (multi-key manager also loads .env as needed)
load_dotenv()

# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini model via centralized API manager (non-fatal if missing)
model_available, model = get_gemini_model()
if model_available and model is not None:
    logger.info("=" * 80)
    logger.info("✅ Gemini model available for follow-up question generation (via API manager)")
    logger.info("=" * 80)
else:
    logger.warning("=" * 80)
    logger.warning("⚠️ Gemini model not available; follow-up will use deterministic fallback questions when needed.")
    logger.warning("   Ensure GEMINI_API_KEY_1 (or GOOGLE_API_KEY / GEMINI_API_KEY) is set in Backend/.env or environment.")
    logger.warning("=" * 80)

# ------------------ helper functions for parsing and normalizing model output ------------------ #
def _strip_code_fences(text: str) -> str:
    """
    Remove common code-fence wrappers like ```json ... ``` or ``` ... ```
    and remove surrounding single/double quotes.
    """
    t = (text or "").strip()
    # remove triple backticks (with optional "json")
    if t.startswith("```"):
        idx = t.find("\n")
        if idx != -1:
            t = t[idx + 1 :].rstrip()
            if t.endswith("```"):
                t = t[: -3].strip()
    # remove single-line fences like `...`
    if t.startswith("`") and t.endswith("`"):
        t = t[1:-1].strip()
    # strip surrounding quotes if they enclose entire text
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    return t


def _extract_first_json_object(text: str) -> Optional[str]:
    """
    Find the first balanced JSON object in text by scanning for the first '{'
    and matching braces. Returns substring (including braces) or None.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _safe_parse_json_like(s: str):
    """
    Try json.loads, otherwise fall back to ast.literal_eval (safe),
    returning a Python object on success or raise the original exception.
    """
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(s)
        except Exception:
            raise


def _normalize_mcq_keys(d: Dict) -> Dict:
    """
    Normalize keys to expected canonical keys:
    'Question', 'A', 'B', 'C', 'D' (case-insensitive).
    """
    mapping = {}
    for key, val in d.items():
        k = key.strip().lower()
        if k.startswith("question"):
            mapping["Question"] = val
        elif k == "a":
            mapping["A"] = val
        elif k == "b":
            mapping["B"] = val
        elif k == "c":
            mapping["C"] = val
        elif k == "d":
            mapping["D"] = val
        else:
            mapping[key] = val
    return mapping


def _convert_structured_to_mcq(data: Dict) -> Optional[Dict]:
    """
    Convert structured follow_up_questions format to legacy MCQ format.
    """
    if not isinstance(data, dict):
        return None
    questions = data.get("follow_up_questions")
    if not isinstance(questions, list) or not questions:
        return None
    first_q = questions[0] if isinstance(questions[0], dict) else None
    if not first_q:
        return None
    options = first_q.get("options") or {}
    mcq = {
        "Question": first_q.get("question", ""),
        "A": options.get("A", "Option A"),
        "B": options.get("B", "Option B"),
        "C": options.get("C", "Option C"),
        "D": options.get("D", "None of these"),
    }
    if "clinical_focus" in first_q:
        mcq["clinical_purpose"] = first_q.get("clinical_focus", "")
    if "reasoning_trace" in data:
        mcq["reasoning_trace"] = data.get("reasoning_trace")
    if "top_hypothesis" in data:
        mcq["top_hypothesis"] = data.get("top_hypothesis")
    if "confidence_score" in data:
        mcq["confidence_score"] = data.get("confidence_score")
    return mcq


def _sanitize_text(text: str, max_len: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    # Try to cut at first sentence boundary if overly long
    for sep in (". ", "? ", "! "):
        idx = cleaned.find(sep)
        if 0 < idx < max_len:
            return cleaned[: idx + 1].strip()
    return cleaned[:max_len].rstrip()


def _sanitize_mcq(d: Dict) -> Dict:
    """
    Enforce short, clear language and concise options.
    """
    out = dict(d)
    if "Question" in out:
        # Strip numeric prefixes like "1. " or "1) "
        q = out.get("Question", "")
        if isinstance(q, str):
            q = q.strip()
            q = __import__("re").sub(r"^\d+[\.\)\-\:\s]+\s*", "", q)
        out["Question"] = _sanitize_text(q, 140)
    for key in ("A", "B", "C", "D"):
        if key in out:
            out[key] = _sanitize_text(out[key], 80)
    return out


def _validate_mcq_structure(d: Dict) -> bool:
    """
    Ensure the MCQ contains at least Question + options A/B/C/D.
    """
    required = {"Question", "A", "B", "C", "D"}
    return required.issubset(set(d.keys()))


def _coerce_numeric(value: Optional[Union[int, float, str]]) -> Optional[float]:
    """
    Safely coerce user-supplied numeric inputs.
    Returns None for missing/invalid/unclear values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"", "na", "n/a", "none", "null", "unknown", "-"}:
            return None
        # Keep only basic numeric characters to tolerate values like "170 cm".
        cleaned = "".join(ch for ch in raw if ch in "0123456789.+-")
        if cleaned in {"", ".", "+", "-", "+.", "-."}:
            return None
        try:
            parsed = float(cleaned)
        except Exception:
            return None
    else:
        try:
            parsed = float(value)
        except Exception:
            return None

    if not math.isfinite(parsed):
        return None
    return parsed


def _normalize_height_cm(height_value: Optional[Union[int, float, str]]) -> Optional[float]:
    """
    Normalize height to centimeters.
    Accepts cm directly, meters, or inches. Returns None when unclear/invalid.
    """
    value = _coerce_numeric(height_value)
    if value is None or value <= 0:
        return None

    # meters -> centimeters
    if 0.5 <= value <= 2.5:
        value = value * 100.0
    # inches -> centimeters
    elif 36 <= value <= 96:
        value = value * 2.54

    # Conservative adult-safe range to avoid bad BMI from noisy inputs.
    if not (90 <= value <= 250):
        return None
    return value


def _calculate_bmi_signal(weight: Optional[Union[int, float, str]], height: Optional[Union[int, float, str]]) -> Dict:
    """
    Calculate BMI safely and return a structured signal.
    """
    weight_kg = _coerce_numeric(weight)
    height_cm = _normalize_height_cm(height)

    if weight_kg is None or weight_kg <= 0 or height_cm is None:
        return {
            "available": False,
            "bmi": None,
            "category": "Unknown",
            "text": "Not available",
        }

    if not (20 <= weight_kg <= 400):
        return {
            "available": False,
            "bmi": None,
            "category": "Unknown",
            "text": "Not available",
        }

    bmi = weight_kg / ((height_cm / 100.0) ** 2)
    if not math.isfinite(bmi) or bmi <= 0 or bmi > 80:
        return {
            "available": False,
            "bmi": None,
            "category": "Unknown",
            "text": "Not available",
        }

    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"

    bmi_rounded = round(bmi, 1)
    return {
        "available": True,
        "bmi": bmi_rounded,
        "category": category,
        "text": f"{bmi_rounded:.1f} ({category})",
    }


# ------------------ the follow-up MCQ generator (synchronous) ------------------ #
def get_followup_for_diagnosis(
    age: int,
    gender: str,
    symptoms: Union[str, list],
    chat_history: str,
    max_retries: int = 1,
    weight: float = None,
    height: float = None,
    occupation: str = None,
    location: dict = None,
    physical_activity: str = None,
    diet_type: str = None,
    raw_symptoms: Optional[Union[str, list]] = None,
) -> Union[Dict, str, None]:
    """
    Generates a follow-up MCQ (as dict) or returns "Ready for diagnosis".
    Enhanced with comprehensive patient data for better context-aware questions.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: List or string of symptoms
        chat_history: Previous conversation history
        max_retries: Number of retries for AI generation
        weight: Patient weight in kg (optional)
        height: Patient height in cm (optional)
        occupation: Patient occupation (optional)
        location: Dict with country, state, city (optional)
        physical_activity: Activity level (optional)
        diet_type: Diet type (optional)
    
    Returns:
      - dict: parsed MCQ with keys "Question","A","B","C","D"
      - str: "Ready for diagnosis"
      - None: on error/unrecoverable

    NOTE: synchronous function (run in executor by WebSocket handler).
    """

    def _normalize_tokens(text: str) -> list:
        if not text:
            return []
        import re
        stopwords = {
            "do", "you", "have", "any", "are", "is", "the", "a", "an", "of", "to", "and", "or", "in",
            "on", "with", "for", "your", "currently", "been", "feel", "feeling", "from", "at", "by",
            "does", "did", "can", "could", "would", "will", "should", "please", "patient", "symptoms",
            "symptom", "about", "like", "that", "this", "these", "those", "now", "today"
        }
        cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        raw_tokens = [t for t in cleaned.split() if t and t not in stopwords]
        # Normalize common clinical synonyms to reduce re-phrased repeats
        synonym_map = {
            "abdomen": "stomach",
            "abdominal": "stomach",
            "belly": "stomach",
            "gastric": "stomach",
            "tummy": "stomach",
            "ache": "pain",
            "hurt": "pain",
            "hurting": "pain",
            "sore": "pain",
            "onset": "start",
            "begin": "start",
            "began": "start",
            "started": "start",
            "starting": "start",
            "duration": "timing",
            "timing": "timing",
            "located": "location",
            "location": "location",
            "where": "location",
        }
        raw_tokens = [synonym_map.get(t, t) for t in raw_tokens]
        def _stem(tok: str) -> str:
            for suffix in ("ing", "ed", "es", "s"):
                if tok.endswith(suffix) and len(tok) > (len(suffix) + 2):
                    return tok[: -len(suffix)]
            return tok
        return [_stem(t) for t in raw_tokens]

    def _topic_from_text(text: str) -> str:
        t = (text or "").lower()
        topic_map = {
            "respiratory": ("cough", "phlegm", "sputum", "breath", "chest", "wheeze"),
            "gastrointestinal": ("nausea", "vomit", "diarrhea", "stool", "abdominal", "stomach"),
            "neurological": ("headache", "dizzy", "weakness", "numb", "speech", "neck", "light"),
            "urinary": ("urine", "urination", "dysuria", "frequency", "hematuria"),
            "pain_characterization": ("pain", "radiate", "throbbing", "pressure", "severity"),
            "timeline": ("when", "start", "began", "duration", "how long", "progress"),
            "red_flag": ("loss of consciousness", "severe difficulty", "crushing chest pain", "one-sided"),
        }
        for topic, markers in topic_map.items():
            if any(marker in t for marker in markers):
                return topic
        return "general"

    def _infer_primary_system(symptoms_text: str, patient_words_text: str, answers_text: str) -> str:
        combined = " ".join(
            [
                str(symptoms_text or "").lower(),
                str(patient_words_text or "").lower(),
                str(answers_text or "").lower(),
            ]
        )
        system_markers = {
            "gastrointestinal": ("stomach", "abdominal", "abdomen", "nausea", "vomit", "diarrhea", "stool", "bloating"),
            "respiratory": ("cough", "phlegm", "sputum", "breath", "wheeze", "chest congestion", "sore throat"),
            "neurological": ("headache", "dizzy", "vertigo", "numb", "weak", "speech", "confusion", "seizure"),
            "cardiac": ("chest pain", "pressure", "palpitation", "radiate to arm", "tightness", "heart"),
            "renal": ("urine", "urination", "dysuria", "flank", "back pain with fever", "hematuria", "swelling"),
        }
        best_system = "general"
        best_score = 0
        for system, markers in system_markers.items():
            score = 0
            for marker in markers:
                if marker in combined:
                    score += 1
            if score > best_score:
                best_score = score
                best_system = system
        return best_system

    def _tree_node_for_question(question_count_local: int, primary_system: str) -> str:
        # If system is already clear from form/history, skip broad system screening.
        if question_count_local == 0:
            return "severity" if primary_system != "general" else "system"
        if question_count_local == 1:
            return "time_course"
        if question_count_local == 2:
            return "localization"
        if question_count_local == 3:
            return "syndrome_match"
        return "risk_red_flag"

    def _completed_nodes_text(question_count_local: int, primary_system: str) -> str:
        ordered = ["system", "severity", "time_course", "localization", "syndrome_match", "risk_red_flag"]
        current = _tree_node_for_question(question_count_local, primary_system)
        if current not in ordered:
            return "None"
        idx = ordered.index(current)
        completed = ordered[:idx]
        return ", ".join(completed) if completed else "None"

    def _infer_branch_hint(primary_system: str, last_answer_text: str, all_answers_text: str, symptoms_text: str) -> str:
        combined = " ".join(
            [
                str(last_answer_text or "").lower(),
                str(all_answers_text or "").lower(),
                str(symptoms_text or "").lower(),
            ]
        )
        if primary_system == "gastrointestinal":
            if any(k in combined for k in ["cannot keep fluids", "small sips", "dehydration"]):
                return "acute_gastroenteritis_with_dehydration"
            if any(k in combined for k in ["upper", "burning", "after meals", "acid"]):
                return "acid_peptic_pattern"
            if any(k in combined for k in ["right lower", "appendix"]):
                return "appendiceal_pattern"
            if any(k in combined for k in ["loose stool", "diarrhea", "bloody stool"]):
                return "infectious_colitis_pattern"
            return "undifferentiated_gastrointestinal"
        if primary_system == "respiratory":
            if "dry cough" in combined:
                return "viral_upper_respiratory_pattern"
            if any(k in combined for k in ["phlegm", "sputum", "yellow", "green"]):
                return "bacterial_lower_respiratory_pattern"
            if any(k in combined for k in ["wheeze", "tightness"]):
                return "bronchospastic_pattern"
            return "undifferentiated_respiratory"
        if primary_system == "neurological":
            if any(k in combined for k in ["sudden weakness", "speech", "one side"]):
                return "focal_neurological_pattern"
            if any(k in combined for k in ["light sensitivity", "throbbing", "migraine"]):
                return "migraine_meningeal_pattern"
            if any(k in combined for k in ["spinning", "vertigo", "balance"]):
                return "vestibular_pattern"
            return "undifferentiated_neurological"
        if primary_system == "cardiac":
            if any(k in combined for k in ["exertion", "pressure"]):
                return "ischemic_exertional_pattern"
            if any(k in combined for k in ["rest pain", "sweating", "nausea"]):
                return "acute_coronary_pattern"
            if any(k in combined for k in ["deep breath", "pleuritic"]):
                return "pleuritic_noncardiac_pattern"
            return "undifferentiated_cardiac"
        if primary_system == "renal":
            if any(k in combined for k in ["burning urination", "frequent urination", "dysuria"]):
                return "lower_urinary_pattern"
            if any(k in combined for k in ["flank", "back pain", "fever"]):
                return "upper_urinary_pattern"
            if any(k in combined for k in ["blood", "dark urine", "swelling"]):
                return "renal_inflammatory_pattern"
            return "undifferentiated_renal"
        return "undifferentiated_general"

    def _infer_negatives_from_answer(answer_text: Optional[str]) -> str:
        if not answer_text:
            return "None reported"
        text = str(answer_text).strip()
        lowered = text.lower()
        if "none of these" in lowered or lowered in {"none", "no", "nope", "nah"}:
            return "None of the listed options from the last question"
        if any(token in lowered for token in [" no ", " not ", "denies", "denied"]):
            return text
        return "None reported"

    def _default_differential_list(symptoms_text: str, primary_system: str) -> list:
        st = (symptoms_text or "").lower()
        if any(k in st for k in ["headache", "migraine"]):
            return ["Migraine", "Tension headache"]
        if any(k in st for k in ["chest pain", "pressure", "tightness"]):
            return ["Acute coronary syndrome", "GERD"]
        if any(k in st for k in ["shortness of breath", "breath", "wheeze"]):
            return ["Pneumonia", "Asthma"]
        if primary_system == "gastrointestinal":
            return ["Gastroenteritis", "Appendicitis"]
        if primary_system == "respiratory":
            return ["Viral URI", "Pneumonia"]
        if primary_system == "neurological":
            return ["Migraine", "Meningitis"]
        if primary_system == "cardiac":
            return ["Acute coronary syndrome", "Musculoskeletal chest pain"]
        if primary_system == "renal":
            return ["UTI", "Pyelonephritis"]
        return ["Viral infection", "Anxiety/stress"]

    def _is_similar(q1: str, q2: str) -> bool:
        if not q1 or not q2:
            return False
        q1_norm = " ".join(q1.lower().split())
        q2_norm = " ".join(q2.lower().split())
        if q1_norm == q2_norm:
            return True
        t1 = _normalize_tokens(q1)
        t2 = _normalize_tokens(q2)
        if not t1 or not t2:
            return False
        s1 = set(t1)
        s2 = set(t2)
        overlap = len(s1 & s2) / max(len(s1), len(s2))
        if overlap >= 0.7:
            return True
        b1 = set(zip(t1, t1[1:]))
        b2 = set(zip(t2, t2[1:]))
        if b1 and b2:
            bigram_overlap = len(b1 & b2) / max(len(b1), len(b2))
            if bigram_overlap >= 0.6:
                return True
        return False

    def _pick_first_unique(candidates, asked_list, asked_topics):
        for item in candidates:
            q = item.get("Question", "")
            if not q:
                continue
            topic = _topic_from_text(q)
            # Prefer unseen topics to keep each question high-value.
            if topic in asked_topics and topic != "red_flag":
                continue
            if not any(_is_similar(q, asked) for asked in asked_list):
                return item
        # Fallback pass: allow seen topics if still non-duplicate.
        for item in candidates:
            q = item.get("Question", "")
            if q and not any(_is_similar(q, asked) for asked in asked_list):
                return item
        return None

    API_FAILURE_MESSAGE = "Service temporarily unavailable due to high request volume. Please try again later."

    def _is_api_key_failure(error_text: str) -> bool:
        if not error_text:
            return False
        lowered = error_text.lower()
        return (
            "api key" in lowered
            or "unauthorized" in lowered
            or "forbidden" in lowered
            or "quota" in lowered
            or "rate limit" in lowered
            or "all api keys" in lowered
            or "401" in lowered
            or "403" in lowered
        )

    def _api_failure_response() -> Dict:
        return {"error": "api_key_failure", "message": API_FAILURE_MESSAGE}

    def _is_ready_signal_text(text: str) -> bool:
        t = (text or "").strip().strip('"').strip("'").lower()
        if not t:
            return False
        return "ready for diagnosis" in t

    def _is_ready_signal_dict(data: Dict) -> bool:
        if not isinstance(data, dict):
            return False
        if data.get("ready_for_diagnosis") is True:
            return True
        for k, v in data.items():
            k_norm = str(k).strip().lower()
            if "ready for diagnosis" in k_norm:
                if isinstance(v, bool):
                    return v
                return True
        q_val = data.get("Question") or data.get("question")
        if isinstance(q_val, str) and "ready for diagnosis" in q_val.strip().lower():
            return True
        return False

    def _deterministic_fallback(
        asked_list: list,
        question_count_local: int = 0,
        primary_system: str = "general",
        tree_node: str = "system",
        branch_hint: str = "undifferentiated_general",
    ) -> Dict:
        """
        Clinical fallback MCQ when Gemini model is unavailable or all API keys fail.
        Uses symptom-based clinical reasoning to generate targeted questions.
        NEVER returns generic questions like "how long" or "any other symptoms".
        """
        logger.warning("Using clinical fallback MCQ for follow-up question.")
        s = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
        s_low = s.lower()
        asked_list = asked_list or []
        asked_topics = set(_topic_from_text(q) for q in asked_list if q)
        # Stop after minimum clinical depth in fallback mode.
        if question_count_local >= 7:
            return "Ready for diagnosis"

        # Tree-first fallback: one decision-node question at a time.
        tree_candidates = []
        if tree_node == "system":
            tree_candidates = [
                {
                    "Question": "Which body area is bothering you the most right now?",
                    "A": "Chest or breathing",
                    "B": "Stomach or bowel",
                    "C": "Head, nerves, or balance",
                    "D": "None of these",
                }
            ]
        elif tree_node == "severity":
            if primary_system == "respiratory":
                tree_candidates = [
                    {
                        "Question": "How is your breathing right now?",
                        "A": "Breathless even at rest",
                        "B": "Breathless only with activity",
                        "C": "No breathing trouble",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "gastrointestinal":
                tree_candidates = [
                    {
                        "Question": "Are you able to drink and keep fluids down?",
                        "A": "No, I cannot keep fluids down",
                        "B": "Only small sips",
                        "C": "Yes, I can drink normally",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "neurological":
                tree_candidates = [
                    {
                        "Question": "Any severe warning signs right now?",
                        "A": "Confusion or very drowsy",
                        "B": "Sudden weakness or speech trouble",
                        "C": "No severe warning signs",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "cardiac":
                tree_candidates = [
                    {
                        "Question": "How severe is your chest discomfort now?",
                        "A": "Severe and persistent",
                        "B": "Moderate, comes and goes",
                        "C": "Mild discomfort only",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "renal":
                tree_candidates = [
                    {
                        "Question": "Are you passing much less urine than usual?",
                        "A": "Yes, much less",
                        "B": "Slightly less",
                        "C": "No change",
                        "D": "None of these",
                    }
                ]
            else:
                tree_candidates = [
                    {
                        "Question": "Which associated pattern is most prominent with your main symptom?",
                        "A": "A localized focal feature in one body region",
                        "B": "An infective pattern with fever/chills",
                        "C": "An episodic trigger-linked pattern",
                        "D": "None of these",
                    }
                ]
        elif tree_node == "time_course":
            tree_candidates = [
                {
                    "Question": "How long has this current problem been going on?",
                    "A": "Less than 24 hours",
                    "B": "1 to 7 days",
                    "C": "More than 1 week or recurring",
                    "D": "None of these",
                }
            ]
        elif tree_node == "localization":
            if primary_system == "gastrointestinal":
                tree_candidates = [
                    {
                        "Question": "Where exactly is the stomach/abdominal discomfort?",
                        "A": "Upper middle or left side",
                        "B": "Right lower side",
                        "C": "Diffuse/all over",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "respiratory":
                tree_candidates = [
                    {
                        "Question": "Where do you feel symptoms most?",
                        "A": "Chest tightness",
                        "B": "Throat/nose area",
                        "C": "Mainly cough without chest pain",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "neurological":
                tree_candidates = [
                    {
                        "Question": "Where is the main neurological symptom?",
                        "A": "One side of body/face",
                        "B": "Whole head or both sides",
                        "C": "Mainly balance/dizziness",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "cardiac":
                tree_candidates = [
                    {
                        "Question": "Where is the chest pain/discomfort centered?",
                        "A": "Center chest pressure",
                        "B": "Left chest radiating to arm/jaw",
                        "C": "Sharp pain with breathing/movement",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "renal":
                tree_candidates = [
                    {
                        "Question": "Where is the pain/discomfort located most?",
                        "A": "Flank/back on one side",
                        "B": "Lower abdomen/pelvis",
                        "C": "Generalized swelling/discomfort",
                        "D": "None of these",
                    }
                ]
        elif tree_node == "syndrome_match":
            if primary_system == "gastrointestinal":
                if "dehydration" in branch_hint:
                    tree_candidates = [
                        {
                            "Question": "Along with vomiting, do you also have frequent watery stools?",
                            "A": "Yes, frequent watery stools",
                            "B": "No, mainly vomiting",
                            "C": "Both are mild",
                            "D": "None of these",
                        }
                    ]
                elif "acid_peptic" in branch_hint:
                    tree_candidates = [
                        {
                            "Question": "Is the upper stomach pain linked to meals or acidity?",
                            "A": "Worse after meals or spicy food",
                            "B": "Better after food/antacid",
                            "C": "No meal relation",
                            "D": "None of these",
                        }
                    ]
                elif "appendiceal" in branch_hint:
                    tree_candidates = [
                        {
                            "Question": "Did pain move from around the navel to the right lower side?",
                            "A": "Yes, pain shifted to right lower side",
                            "B": "No, pain stayed in one place",
                            "C": "Pain is diffuse",
                            "D": "None of these",
                        }
                    ]
                else:
                    tree_candidates = [
                        {
                            "Question": "Which pattern best matches your digestive symptoms?",
                            "A": "Vomiting with dehydration",
                            "B": "Abdominal pain with loose stools",
                            "C": "Burning upper stomach pain after meals",
                            "D": "None of these",
                        }
                    ]
            elif primary_system == "respiratory":
                tree_candidates = [
                    {
                        "Question": "Which breathing pattern fits best?",
                        "A": "Dry cough with fever",
                        "B": "Cough with phlegm and fever",
                        "C": "Wheeze/chest tightness episodes",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "neurological":
                tree_candidates = [
                    {
                        "Question": "Which neurological pattern fits best?",
                        "A": "Severe headache with light sensitivity",
                        "B": "Sudden focal weakness or numbness",
                        "C": "Spinning dizziness without weakness",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "cardiac":
                tree_candidates = [
                    {
                        "Question": "Which chest symptom pattern fits best?",
                        "A": "Pressure with exertion",
                        "B": "Pain at rest with sweating/nausea",
                        "C": "Sharp pain worse on deep breath",
                        "D": "None of these",
                    }
                ]
            elif primary_system == "renal":
                tree_candidates = [
                    {
                        "Question": "Which urine-related pattern fits best?",
                        "A": "Burning/frequent urination",
                        "B": "Flank pain with fever/chills",
                        "C": "Dark or blood-tinged urine",
                        "D": "None of these",
                    }
                ]
        elif tree_node == "risk_red_flag":
            if primary_system == "gastrointestinal":
                tree_candidates = [
                    {
                        "Question": "Any danger sign like blood in stool/vomit or fainting?",
                        "A": "Yes, blood in stool or vomit",
                        "B": "Yes, fainting or severe weakness",
                        "C": "No danger sign",
                        "D": "None of these",
                    }
                ]
            else:
                tree_candidates = [
                    {
                        "Question": "Any high-risk exposure or danger sign right now?",
                        "A": "Recent travel/sick contact/new food-water risk",
                        "B": "Serious warning sign (blood, fainting, severe breathlessness)",
                        "C": "No clear exposure or danger sign",
                        "D": "None of these",
                    }
                ]

        picked_tree = _pick_first_unique(tree_candidates, asked_list, asked_topics)
        if picked_tree:
            return picked_tree
        # If we already covered this node and no unique question remains,
        # stop instead of drifting into broad off-path questions.
        if tree_candidates and tree_node in {"localization", "syndrome_match", "risk_red_flag"}:
            return "Ready for diagnosis"
        
        # Pattern 1: Fever - screen for respiratory, GI, or systemic infection
        if "fever" in s_low or "temperature" in s_low:
            candidates = [
                {
                    "Question": "Do you have a cough, shortness of breath, or chest discomfort?",
                    "A": "Yes, dry cough",
                    "B": "Yes, cough with phlegm",
                    "C": "Yes, shortness of breath or chest discomfort",
                    "D": "No respiratory symptoms",
                },
                {
                    "Question": "Are you experiencing nausea, vomiting, or diarrhea?",
                    "A": "Yes, nausea and vomiting",
                    "B": "Yes, diarrhea (watery or bloody)",
                    "C": "Both vomiting and diarrhea",
                    "D": "No digestive issues",
                },
                {
                    "Question": "Do you have a severe headache, stiff neck, or sensitivity to light?",
                    "A": "Yes, severe headache with stiff neck",
                    "B": "Yes, severe headache with light sensitivity",
                    "C": "Yes, feeling confused or very drowsy",
                    "D": "No severe neurological symptoms",
                },
                {
                    "Question": "Do you have a sore throat, runny nose, or body aches?",
                    "A": "Yes, sore throat",
                    "B": "Yes, runny nose or sneezing",
                    "C": "Yes, body aches",
                    "D": "No, none of these",
                },
            ]
            picked = _pick_first_unique(candidates, asked_list, asked_topics)
            if picked:
                return picked
        
        # Pattern 2: Pain - characterize location, severity, and type
        if any(k in s_low for k in ["pain", "ache", "hurt"]):
            if "chest" in s_low or "heart" in s_low:
                candidates = [{
                    "Question": "Does the chest pain radiate to your left arm, jaw, or back?",
                    "A": "Yes, to left arm or jaw",
                    "B": "Yes, to back or between shoulder blades",
                    "C": "Pain stays in chest only",
                    "D": "No radiation at all",
                }]
                picked = _pick_first_unique(candidates, asked_list, asked_topics)
                if picked:
                    return picked
            elif "head" in s_low:
                candidates = [{
                    "Question": "Is the headache throbbing/pulsating or constant pressure?",
                    "A": "Throbbing on one side (pulsating)",
                    "B": "Constant pressure on both sides (band-like)",
                    "C": "Sharp, sudden, worst headache ever",
                    "D": "Other type of headache",
                }]
                picked = _pick_first_unique(candidates, asked_list, asked_topics)
                if picked:
                    return picked
            elif "abdom" in s_low or "stomach" in s_low:
                candidates = [{
                    "Question": "Where exactly is the abdominal pain located?",
                    "A": "Right lower abdomen (near appendix area)",
                    "B": "Upper center or left (stomach area)",
                    "C": "All over abdomen, cramping",
                    "D": "Different location",
                }]
                picked = _pick_first_unique(candidates, asked_list, asked_topics)
                if picked:
                    return picked
            else:
                candidates = [{
                    "Question": "On a scale of 1-10, how severe is your pain currently?",
                    "A": "Severe (8-10) - cannot function normally",
                    "B": "Moderate (5-7) - uncomfortable but manageable",
                    "C": "Mild (1-4) - barely bothersome",
                    "D": "Pain level varies",
                }]
                picked = _pick_first_unique(candidates, asked_list, asked_topics)
                if picked:
                    return picked
        
        # Pattern 3: Respiratory symptoms
        if any(k in s_low for k in ["cough", "breath", "respiratory", "wheez"]):
            candidates = [{
                "Question": "What are you coughing up, if anything?",
                "A": "Blood or blood-tinged sputum",
                "B": "Yellow or green thick phlegm",
                "C": "Clear or white mucus",
                "D": "Nothing - dry cough",
            }]
            picked = _pick_first_unique(candidates, asked_list, asked_topics)
            if picked:
                return picked
        
        # Pattern 4: Neurological symptoms
        if any(k in s_low for k in ["dizz", "vertigo", "faint", "numb", "weak"]):
            candidates = [{
                "Question": "Do you have sudden weakness, numbness, or difficulty speaking?",
                "A": "Yes, one-sided weakness or numbness (face/arm/leg)",
                "B": "Yes, difficulty speaking clearly or understanding words",
                "C": "Yes, severe dizziness or loss of balance",
                "D": "No sudden neurological changes",
            }]
            picked = _pick_first_unique(candidates, asked_list, asked_topics)
            if picked:
                return picked
        
        # Pattern 5: GI symptoms
        if any(k in s_low for k in ["nausea", "vomit", "diarrhea", "constip"]):
            candidates = [{
                "Question": "Is there any blood in your vomit or stool?",
                "A": "Yes, bright red blood in vomit or stool",
                "B": "Yes, dark/black tarry stool",
                "C": "Yes, coffee-ground appearance in vomit",
                "D": "No blood seen",
            }]
            picked = _pick_first_unique(candidates, asked_list, asked_topics)
            if picked:
                return picked
        
        # Pattern 6: Minimal/vague symptoms - general system screening first
        # Avoid red-flag questions unless symptoms mention breathing/chest or neuro red flags.
        vague_candidates = [
            {
                "Question": "Do you have cough, sore throat, or runny nose?",
                "A": "Yes, cough",
                "B": "Yes, sore throat",
                "C": "Yes, runny nose",
                "D": "No, none of these",
            },
            {
                "Question": "Are you having stomach problems like nausea, vomiting, or diarrhea?",
                "A": "Yes, nausea or vomiting",
                "B": "Yes, diarrhea",
                "C": "Yes, both",
                "D": "No stomach problems",
            },
        ]
        picked = _pick_first_unique(vague_candidates, asked_list, asked_topics)
        if picked:
            return picked

        # Only ask red-flag questions if symptoms suggest it
        red_flag_needed = any(k in s_low for k in ["breath", "chest", "faint", "collapse", "unconscious", "vision"])
        candidates = []
        if red_flag_needed:
            candidates = [
                {
                    "Question": "Are you experiencing severe difficulty breathing or chest pain?",
                    "A": "Yes, severe difficulty breathing (can't speak full sentences)",
                    "B": "Yes, severe crushing chest pain",
                    "C": "Yes, both breathing difficulty and chest pain",
                    "D": "No severe breathing or chest pain",
                },
                {
                    "Question": "Have you noticed sudden vision changes, severe dizziness, or loss of consciousness?",
                    "A": "Yes, sudden vision loss or double vision",
                    "B": "Yes, severe room-spinning dizziness",
                    "C": "Yes, passed out or nearly passed out",
                    "D": "No sudden neurological changes",
                },
            ]
        picked = _pick_first_unique(candidates, asked_list, asked_topics)
        if picked:
            return picked

        # As a last resort, ask a symptom-linked differentiator (never generic filler).
        if primary_system == "respiratory":
            last_resort_candidates = [{
                "Question": "Which respiratory association is present with your main complaint now?",
                "A": "Pleuritic chest pain with productive cough",
                "B": "Dry cough with upper-airway symptoms",
                "C": "Breathlessness without major cough",
                "D": "None of these",
            }]
        elif primary_system == "gastrointestinal":
            last_resort_candidates = [{
                "Question": "Which abdominal association best matches your current pattern?",
                "A": "Localized right-lower pain with movement tenderness",
                "B": "Diffuse cramps with frequent loose stools",
                "C": "Upper-abdominal burning related to meals",
                "D": "None of these",
            }]
        elif primary_system == "neurological":
            last_resort_candidates = [{
                "Question": "Which neurological association is currently present?",
                "A": "Neck stiffness or altered awareness",
                "B": "Unilateral throbbing headache with light sensitivity",
                "C": "Positional vertigo without focal weakness",
                "D": "None of these",
            }]
        else:
            focus = ""
            if isinstance(symptoms, list):
                for item in symptoms:
                    text = str(item).strip()
                    if text:
                        focus = text
                        break
            focus = focus or "main symptom"
            last_resort_candidates = [{
                "Question": f"For your {focus}, which associated clinical pattern is present now?",
                "A": "Localized focal pattern",
                "B": "Systemic infectious pattern",
                "C": "Trigger-linked episodic pattern",
                "D": "None of these",
            }]

        picked = _pick_first_unique(last_resort_candidates, asked_list, asked_topics)
        if picked:
            return picked
        return "Ready for diagnosis"

    # Count questions asked so far - app.py stores as {"bot": "Q"} or {"user": "A"}
    question_count = 0
    if chat_history and isinstance(chat_history, list):
        for msg in chat_history:
            if isinstance(msg, dict) and (msg.get("bot") or msg.get("Question")):
                question_count += 1
    
    # If we've asked too many questions, proceed to diagnosis
    # Limit to at most 8 follow-up questions to keep the flow concise.
    if question_count >= 10:
        logger.info("Maximum questions reached (%d), proceeding to diagnosis", question_count)
        return "Ready for diagnosis"
    
    # Build plain symptoms string — connect patient symptoms to prompt
    if isinstance(symptoms, list):
        symptoms_str = ", ".join(str(s).strip() for s in symptoms if s) or "No symptoms provided"
    elif symptoms:
        symptoms_str = str(symptoms).strip()
    else:
        symptoms_str = "No symptoms provided"

    raw_symptoms_str = ""
    if raw_symptoms:
        if isinstance(raw_symptoms, list):
            raw_symptoms_str = "\n".join(str(s).strip() for s in raw_symptoms if s)
        else:
            raw_symptoms_str = str(raw_symptoms).strip()
    if not raw_symptoms_str:
        raw_symptoms_str = "None"
    
    # Build enhanced patient profile for context
    patient_context = f"{age}-year-old {gender.lower()}"
    
    # BMI signal from patient form (safe parsing; never breaks flow on invalid input)
    bmi_signal = _calculate_bmi_signal(weight, height)
    additional_context = bmi_signal["text"]
    bmi_category = bmi_signal["category"]
    bmi_value_display = (
        f"{bmi_signal['bmi']:.1f}" if bmi_signal.get("available") and bmi_signal.get("bmi") is not None else "Not available"
    )

    # Build conversation context from chat_history
    conversation_context = ""
    asked_questions_list = []
    # Log chat history for debugging
    logger.info(f"Processing chat_history: type={type(chat_history)}, length={len(chat_history) if chat_history else 0}")
    if chat_history and len(chat_history) > 0:
        logger.info(f"First chat_history item: {chat_history[0] if len(chat_history) > 0 else 'N/A'}")
    
    if chat_history:
        # Handle both list and string formats
        if isinstance(chat_history, str):
            # Legacy format: convert to list if needed
            try:
                import json as json_lib
                chat_history = json_lib.loads(chat_history)
            except:
                chat_history = []
        
        if isinstance(chat_history, list):
            q_and_a = []
            for i, msg in enumerate(chat_history):
                if isinstance(msg, dict):
                    # Try both "bot" and "Question" keys (different formats)
                    bot_text = msg.get("bot") or msg.get("Question")
                    if bot_text:
                        # Clean up the question text (remove extra whitespace, normalize)
                        bot_text_normalized = " ".join(bot_text.split())
                        
                        # Check if this question is too similar to already asked ones
                        is_duplicate = any(_is_similar(bot_text_normalized, asked_q) for asked_q in asked_questions_list)
                        if is_duplicate:
                            logger.warning("Detected duplicate question: %s...", bot_text_normalized[:50])
                        
                        if not is_duplicate:
                            asked_questions_list.append(bot_text_normalized)
                        
                        # Get the next user message if it exists
                        user_ans = None
                        if i + 1 < len(chat_history):
                            next_msg = chat_history[i + 1]
                            if isinstance(next_msg, dict):
                                user_ans = next_msg.get("user")
                        
                        if user_ans:
                            q_and_a.append(f"Q{len(q_and_a) + 1}: {bot_text_normalized}\nA{len(q_and_a) + 1}: {user_ans}")
                        else:
                            q_and_a.append(f"Q{len(q_and_a) + 1}: {bot_text_normalized}\n(No answer yet)")
            
            if len(q_and_a) > 6:
                q_and_a = q_and_a[-6:]
            conversation_context = "\n\n".join(q_and_a) if q_and_a else "No previous questions asked - this is the initial assessment"
        else:
            conversation_context = "No previous questions asked - this is the initial assessment"
    else:
        conversation_context = "No previous questions asked - this is the initial assessment"
    
    logger.info(f"Found {len(asked_questions_list)} unique questions asked so far")
    asked_topics_set = set(_topic_from_text(q) for q in asked_questions_list if q)

    # Extract most recent exchange + all prior answers for stronger context
    last_user_answer = None
    last_bot_question = None
    all_user_answers = []
    if isinstance(chat_history, list):
        for msg in chat_history:
            if isinstance(msg, dict) and msg.get("user"):
                all_user_answers.append(str(msg.get("user")).strip())
        for msg in reversed(chat_history):
            if isinstance(msg, dict) and msg.get("user"):
                last_user_answer = str(msg.get("user")).strip()
                break
        for msg in reversed(chat_history):
            if isinstance(msg, dict) and (msg.get("bot") or msg.get("Question")):
                last_bot_question = str(msg.get("bot") or msg.get("Question")).strip()
                break

    all_answers_str = "\n".join([f"- {a}" for a in all_user_answers]) if all_user_answers else "None"
    answers_blob = " ".join(all_user_answers) if all_user_answers else ""
    primary_system = _infer_primary_system(symptoms_str, raw_symptoms_str, answers_blob)
    current_tree_node = _tree_node_for_question(question_count, primary_system)
    completed_tree_nodes = _completed_nodes_text(question_count, primary_system)
    branch_hint = _infer_branch_hint(primary_system, last_user_answer or "", answers_blob, symptoms_str)
    # Let BMI subtly shape branch priority without overriding symptom evidence.
    if bmi_category == "Obese":
        branch_hint = f"{branch_hint}; bmi_obesity_risk"
    elif bmi_category == "Underweight":
        branch_hint = f"{branch_hint}; bmi_underweight_risk"

    asked_questions_str = "\n".join([f"- {q}" for q in asked_questions_list]) if asked_questions_list else "None"

    chat_history_text = conversation_context
    chat_history_text += (
        f"\n\nLast Question: {last_bot_question or 'None'}"
        f"\nLast Answer: {last_user_answer or 'None'}"
        f"\nAll Answers:\n{all_answers_str}"
    )

    symptoms_positives = symptoms_str or "None reported"
    symptoms_negatives = _infer_negatives_from_answer(last_user_answer)
    current_differential_list = ", ".join(_default_differential_list(symptoms_str, primary_system))
    next_question_id = question_count + 1

    # If Gemini model isn't available via the centralized manager, use deterministic fallback
    model_ok, _ = get_gemini_model()
    if not model_ok:
        logger.warning("Gemini model unavailable for follow-up; using deterministic fallback question.")
        return _deterministic_fallback(
            asked_questions_list,
            question_count_local=question_count,
            primary_system=primary_system,
            tree_node=current_tree_node,
            branch_hint=branch_hint,
        )

    base_prompt = f"""ACT: Senior Clinical Consultant (Symptom-Driven Mode).
GOAL: Generate ONE targeted MCQ to differentiate the top 2 hypotheses.

CONTEXT:
- Patient: {age}yo {gender}
- BMI: {bmi_value_display} ({bmi_category})
- Confirmed Symptoms (+): {symptoms_positives}
- Ruled Out (-): {symptoms_negatives}
- Current Top Hypotheses: {current_differential_list}
- Current Clinical Branch: {primary_system} / node={current_tree_node} / hint={branch_hint}
- Questions Already Asked: {question_count}
- Previously Asked Questions:
{asked_questions_str}

STRICT RULES:
1. INTERNAL ANALYSIS: Infer TOP 2 competing diseases from (+), (-), branch context, and demographics.
2. DIFFERENTIATION: Ask ONE question about a feature that separates Suspect #1 from Suspect #2.
3. NON-REPETITION: Do not ask a question already present in Previously Asked Questions.
4. RED FLAGS: Prioritize safety-critical differentiation whenever alarm features are possible.
5. FORBIDDEN: Never output generic filler questions or placeholder/template wording.
6. If evidence is sparse, ask the most clinically relevant differentiator anchored to known symptoms, not a generic progression/severity check.
7. TERMINATE: If question_count >= 10 OR (question_count >= 7 and diagnosis is sufficiently certain), return:
{{"ready_for_diagnosis": true}}

OUTPUT JSON ONLY:
{{
  "Question": "Is pain localized to the right lower abdomen and worsened by movement?",
  "A": "Yes, right-lower pain worsens while walking/coughing",
  "B": "No, pain is diffuse with loose stools or vomiting",
  "C": "No, pain is mainly upper-abdominal burning after meals",
  "D": "None of these",
  "priority": "red-flag|high|medium",
  "clinical_intent": "What this question differentiates",
  "differentiates_between": ["Appendicitis", "Gastroenteritis"]
}}"""

    raw_text = ""
    parsed = None
    retry_prompt_suffix = (
        "\nReturn ONLY valid JSON in one of these exact structures:\n"
        "{\"ready_for_diagnosis\": true}\n"
        "OR\n"
        "{"
        "\"Question\":\"Is abdominal pain localized to the right lower side and worsened by movement?\","
        "\"A\":\"Yes, right-lower localized pain worsens with walking/coughing\","
        "\"B\":\"No, pain is diffuse with loose stools or vomiting\","
        "\"C\":\"No, pain is mainly upper-abdominal burning after meals\","
        "\"D\":\"None of these\","
        "\"priority\":\"red-flag|high|medium\","
        "\"clinical_intent\":\"What this question differentiates\","
        "\"differentiates_between\":[\"Appendicitis\",\"Gastroenteritis\"]"
        "}"
    )

    def _call_gemini(prompt_text: str):
        return generate_content_with_fallback(
            prompt=prompt_text,
            max_retries=None,  # Try all configured keys (up to 15)
            temperature=0.3,
            max_output_tokens=320,
        )

    try:
        # First attempt: ask model via centralized Gemini API manager (multi-key with fallback)
        success, raw_text, error = _call_gemini(base_prompt)
        if not success or not raw_text:
            logger.error("Gemini follow-up generation failed: %s", error)
            if _is_api_key_failure(error):
                return _api_failure_response()
            return _deterministic_fallback(
                asked_questions_list,
                question_count_local=question_count,
                primary_system=primary_system,
                tree_node=current_tree_node,
                branch_hint=branch_hint,
            )

        raw_text = (raw_text or "").strip()
        logger.info("Model response received (len=%d) for session prompt.", len(raw_text))

        # Quick normalized check for ready signal
        if _is_ready_signal_text(raw_text):
            if question_count >= 7:
                logger.info("Model returned Ready for diagnosis string.")
                return "Ready for diagnosis"
            logger.info("Model requested early diagnosis at question_count=%d; continuing to minimum depth.", question_count)
            return _deterministic_fallback(
                asked_questions_list,
                question_count_local=question_count,
                primary_system=primary_system,
                tree_node=current_tree_node,
                branch_hint=branch_hint,
            )

        # Robust JSON extraction using centralized helper
        parsed = extract_json_from_text(raw_text)

        if parsed is None:
            # Best-effort secondary parsing using local helpers (for edge cases)
            cleaned = _strip_code_fences(raw_text)
            logger.debug("Cleaned model text (first 300 chars): %s", cleaned[:300])
            json_sub = _extract_first_json_object(cleaned)

            if json_sub:
                try:
                    parsed = _safe_parse_json_like(json_sub)
                except Exception as exc:
                    logger.warning("JSON substring parse failed: %s", exc)
                    parsed = None
            else:
                try:
                    parsed = _safe_parse_json_like(cleaned)
                except Exception:
                    parsed = None

        if parsed is None:
            # Retry once with stricter instructions before fallback
            logger.warning("Could not parse model output as JSON, retrying with stricter prompt.")
            success, raw_text, error = _call_gemini(base_prompt + retry_prompt_suffix)
            if success and raw_text:
                parsed = extract_json_from_text((raw_text or "").strip())
            if parsed is None:
                logger.error(
                    "Could not parse model output as JSON after retry. Raw response (first 4000 chars):\n%s",
                    (raw_text or "")[:4000],
                )
                if _is_api_key_failure(error):
                    return _api_failure_response()
                return _deterministic_fallback(
                    asked_questions_list,
                    question_count_local=question_count,
                    primary_system=primary_system,
                    tree_node=current_tree_node,
                    branch_hint=branch_hint,
                )

        # Must be a dict – if not, fall back to a safe deterministic MCQ
        if not isinstance(parsed, dict):
            logger.error("Parsed output is not a dict. Parsed repr: %r", parsed)
            return _deterministic_fallback(
                asked_questions_list,
                question_count_local=question_count,
                primary_system=primary_system,
                tree_node=current_tree_node,
                branch_hint=branch_hint,
            )

        # Handle alternate ready formats from model JSON
        if _is_ready_signal_dict(parsed):
            if question_count >= 7:
                logger.info("Model indicated ready_for_diagnosis in JSON payload.")
                return "Ready for diagnosis"
            logger.info("Model indicated early ready_for_diagnosis at question_count=%d; continuing.", question_count)
            return _deterministic_fallback(
                asked_questions_list,
                question_count_local=question_count,
                primary_system=primary_system,
                tree_node=current_tree_node,
                branch_hint=branch_hint,
            )

        if isinstance(parsed, dict) and "follow_up_questions" in parsed and not _validate_mcq_structure(parsed):
            converted = _convert_structured_to_mcq(parsed)
            if converted:
                parsed = converted

        parsed = _normalize_mcq_keys(parsed)
        if not _validate_mcq_structure(parsed):
            if _is_ready_signal_dict(parsed):
                if question_count >= 7:
                    logger.info("Model indicated ready_for_diagnosis in non-MCQ JSON payload.")
                    return "Ready for diagnosis"
                logger.info("Model indicated early ready in non-MCQ JSON at question_count=%d; continuing.", question_count)
                return _deterministic_fallback(
                    asked_questions_list,
                    question_count_local=question_count,
                    primary_system=primary_system,
                    tree_node=current_tree_node,
                    branch_hint=branch_hint,
                )
            logger.error("MCQ structure invalid or missing keys after normalization: %s", parsed.keys())
            # If structure invalid, return fallback rather than None
            # Retry once with stricter instructions
            success, raw_text, error = _call_gemini(base_prompt + retry_prompt_suffix)
            if success and raw_text:
                parsed_retry = extract_json_from_text((raw_text or "").strip())
                if isinstance(parsed_retry, dict):
                    if _is_ready_signal_dict(parsed_retry):
                        if question_count >= 7:
                            logger.info("Retry payload indicated ready_for_diagnosis.")
                            return "Ready for diagnosis"
                        logger.info("Retry payload indicated early ready at question_count=%d; continuing.", question_count)
                        return _deterministic_fallback(
                            asked_questions_list,
                            question_count_local=question_count,
                            primary_system=primary_system,
                            tree_node=current_tree_node,
                            branch_hint=branch_hint,
                        )
                    if "follow_up_questions" in parsed_retry and not _validate_mcq_structure(parsed_retry):
                        converted_retry = _convert_structured_to_mcq(parsed_retry)
                        if converted_retry:
                            parsed_retry = converted_retry
                    parsed_retry = _normalize_mcq_keys(parsed_retry)
                    if _validate_mcq_structure(parsed_retry):
                        parsed = parsed_retry
                    else:
                        return _deterministic_fallback(
                            asked_questions_list,
                            question_count_local=question_count,
                            primary_system=primary_system,
                            tree_node=current_tree_node,
                            branch_hint=branch_hint,
                        )
                else:
                    return _deterministic_fallback(
                        asked_questions_list,
                        question_count_local=question_count,
                        primary_system=primary_system,
                        tree_node=current_tree_node,
                        branch_hint=branch_hint,
                    )
            else:
                if _is_api_key_failure(error):
                    return _api_failure_response()
                return _deterministic_fallback(
                    asked_questions_list,
                    question_count_local=question_count,
                    primary_system=primary_system,
                    tree_node=current_tree_node,
                    branch_hint=branch_hint,
                )

        # Sanitize question/options for clarity and length
        parsed = _sanitize_mcq(parsed)

        # Check if this question is a duplicate of previously asked questions
        if parsed.get("Question"):
            question_text = " ".join(parsed["Question"].split())  # Normalize whitespace
            question_topic = _topic_from_text(question_text)
            is_repetitive_topic = question_topic in asked_topics_set and question_topic != "red_flag"
            is_repetitive_text = any(_is_similar(question_text, asked) for asked in asked_questions_list)
            if is_repetitive_topic or is_repetitive_text:
                logger.warning("Generated question is duplicate. Retrying with stricter prompt.")
                success, raw_text, error = _call_gemini(base_prompt + retry_prompt_suffix)
                if success and raw_text:
                    parsed_retry = extract_json_from_text((raw_text or "").strip())
                    if isinstance(parsed_retry, dict):
                        if _is_ready_signal_dict(parsed_retry):
                            if question_count >= 7:
                                logger.info("Duplicate-check retry indicated ready_for_diagnosis.")
                                return "Ready for diagnosis"
                            logger.info("Duplicate-check retry indicated early ready at question_count=%d; continuing.", question_count)
                            return _deterministic_fallback(
                                asked_questions_list,
                                question_count_local=question_count,
                                primary_system=primary_system,
                                tree_node=current_tree_node,
                                branch_hint=branch_hint,
                            )
                        if "follow_up_questions" in parsed_retry and not _validate_mcq_structure(parsed_retry):
                            converted_retry = _convert_structured_to_mcq(parsed_retry)
                            if converted_retry:
                                parsed_retry = converted_retry
                        parsed_retry = _normalize_mcq_keys(parsed_retry)
                        parsed_retry = _sanitize_mcq(parsed_retry)
                        q_retry = parsed_retry.get("Question", "")
                        retry_topic = _topic_from_text(q_retry)
                        retry_topic_seen = retry_topic in asked_topics_set and retry_topic != "red_flag"
                        retry_text_seen = any(_is_similar(q_retry, asked) for asked in asked_questions_list)
                        if q_retry and not retry_topic_seen and not retry_text_seen:
                            parsed = parsed_retry
                        else:
                            if _is_api_key_failure(error):
                                return _api_failure_response()
                            return _deterministic_fallback(
                                asked_questions_list,
                                question_count_local=question_count,
                                primary_system=primary_system,
                                tree_node=current_tree_node,
                                branch_hint=branch_hint,
                            )
                    else:
                        if _is_api_key_failure(error):
                            return _api_failure_response()
                        return _deterministic_fallback(
                            asked_questions_list,
                            question_count_local=question_count,
                            primary_system=primary_system,
                            tree_node=current_tree_node,
                            branch_hint=branch_hint,
                        )
                else:
                    if _is_api_key_failure(error):
                        return _api_failure_response()
                    return _deterministic_fallback(
                        asked_questions_list,
                        question_count_local=question_count,
                        primary_system=primary_system,
                        tree_node=current_tree_node,
                        branch_hint=branch_hint,
                    )

        # Keep the model's Option D as-is (context-aware), don't override it
        # Only set default if D is missing
        if "D" not in parsed or not parsed["D"]:
            parsed["D"] = "None of these"

        return parsed

    except Exception as e:
        logger.exception("Unhandled exception in get_followup_for_diagnosis: %s", e)
        # Return a symptom-linked deterministic fallback instead of generic template text.
        return _deterministic_fallback(
            asked_questions_list if "asked_questions_list" in locals() else [],
            question_count_local=question_count if "question_count" in locals() else 0,
            primary_system=primary_system if "primary_system" in locals() else "general",
            tree_node=current_tree_node if "current_tree_node" in locals() else "system",
            branch_hint=branch_hint if "branch_hint" in locals() else "undifferentiated_general",
        )
