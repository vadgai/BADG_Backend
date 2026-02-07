# Backend/Followup_Generation/followup.py
import os
import json
import ast
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

    def _is_similar(q1: str, q2: str) -> bool:
        if not q1 or not q2:
            return False
        q1_norm = " ".join(q1.lower().split())
        q2_norm = " ".join(q2.lower().split())
        if q1_norm == q2_norm:
            return True
        w1 = set(q1_norm.split())
        w2 = set(q2_norm.split())
        if not w1 or not w2:
            return False
        common = w1 & w2
        similarity = len(common) / max(len(w1), len(w2))
        return similarity > 0.75

    def _pick_first_unique(candidates, asked_list):
        for item in candidates:
            q = item.get("Question", "")
            if not q:
                continue
            if not any(_is_similar(q, asked) for asked in asked_list):
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

    def _deterministic_fallback(asked_list: list) -> Dict:
        """
        Clinical fallback MCQ when Gemini model is unavailable or all API keys fail.
        Uses symptom-based clinical reasoning to generate targeted questions.
        NEVER returns generic questions like "how long" or "any other symptoms".
        """
        logger.warning("Using clinical fallback MCQ for follow-up question.")
        s = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
        s_low = s.lower()
        asked_list = asked_list or []
        
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
            picked = _pick_first_unique(candidates, asked_list)
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
                picked = _pick_first_unique(candidates, asked_list)
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
                picked = _pick_first_unique(candidates, asked_list)
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
                picked = _pick_first_unique(candidates, asked_list)
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
                picked = _pick_first_unique(candidates, asked_list)
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
            picked = _pick_first_unique(candidates, asked_list)
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
            picked = _pick_first_unique(candidates, asked_list)
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
            picked = _pick_first_unique(candidates, asked_list)
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
        picked = _pick_first_unique(vague_candidates, asked_list)
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
        picked = _pick_first_unique(candidates, asked_list)
        if picked:
            return picked

        # As a last resort, return a safe non-repeating generic
        last_resort = {
            "Question": "Are you feeling any new or worsening symptoms right now?",
            "A": "Yes, new or worsening symptoms",
            "B": "No, symptoms are stable",
            "C": "Symptoms are improving",
            "D": "I'm not sure",
        }
        if any(_is_similar(last_resort["Question"], asked) for asked in asked_list):
            return "Ready for diagnosis"
        return last_resort

    # Count questions asked so far - app.py stores as {"bot": "Q"} or {"user": "A"}
    question_count = 0
    if chat_history and isinstance(chat_history, list):
        for msg in chat_history:
            if isinstance(msg, dict) and (msg.get("bot") or msg.get("Question")):
                question_count += 1
    
    # If we've asked too many questions, proceed to diagnosis
    # Limit to at most 10 follow-up questions to keep the flow concise.
    if question_count >= 10:
        logger.info("Maximum questions reached (%d), proceeding to diagnosis", question_count)
        return "Ready for diagnosis"
    
    # If Gemini model isn't available via the centralized manager, use deterministic fallback
    model_ok, _ = get_gemini_model()
    if not model_ok:
        logger.warning("Gemini model unavailable for follow-up; using deterministic fallback question.")
        return _deterministic_fallback(asked_questions_list)

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
    
    # Add BMI if weight and height available
    bmi_info = ""
    # Only compute BMI when BOTH weight and height are present and valid.
    # Do not infer or assume BMI if either value is missing.
    if weight is not None and height is not None:
        try:
            bmi = float(weight) / ((float(height) / 100) ** 2)
            if bmi > 0:
                bmi_category = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
                bmi_info = f"\n- BMI: {bmi:.1f} ({bmi_category})"
        except Exception:
            bmi_info = ""
    
    # Add lifestyle factors
    lifestyle_info = ""
    if occupation:
        lifestyle_info += f"\n- Occupation: {occupation}"
    if physical_activity:
        lifestyle_info += f"\n- Physical Activity: {physical_activity}"
    if diet_type:
        lifestyle_info += f"\n- Diet Type: {diet_type}"
    
    # Add location context
    location_info = ""
    if location and isinstance(location, dict):
        loc_parts = []
        if location.get("city"):
            loc_parts.append(location["city"])
        if location.get("state"):
            loc_parts.append(location["state"])
        if location.get("country"):
            loc_parts.append(location["country"])
        if loc_parts:
            location_info = f"\n- Location: {', '.join(loc_parts)} (consider regional diseases and environmental factors)"

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
                        is_duplicate = False
                        for asked_q in asked_questions_list:
                            # Simple similarity check: if 80% of words match, consider it duplicate
                            bot_words = set(bot_text_normalized.lower().split())
                            asked_words = set(asked_q.lower().split())
                            if len(bot_words) > 0 and len(asked_words) > 0:
                                common_words = bot_words & asked_words
                                similarity = len(common_words) / max(len(bot_words), len(asked_words))
                                if similarity > 0.75:  # 75% similarity threshold
                                    is_duplicate = True
                                    logger.warning(f"Detected duplicate question (similarity={similarity:.2f}): {bot_text_normalized[:50]}...")
                                    break
                        
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
            
            conversation_context = "\n\n".join(q_and_a) if q_and_a else "No previous questions asked - this is the initial assessment"
        else:
            conversation_context = "No previous questions asked - this is the initial assessment"
    else:
        conversation_context = "No previous questions asked - this is the initial assessment"
    
    logger.info(f"Found {len(asked_questions_list)} unique questions asked so far")

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

    chat_history_text = conversation_context
    chat_history_text += (
        f"\n\nLast Question: {last_bot_question or 'None'}"
        f"\nLast Answer: {last_user_answer or 'None'}"
        f"\nAll Answers:\n{all_answers_str}"
    )

    base_prompt = f"""You are a top medical diagnosis expert. Your primary goal is to efficiently gather just enough information from the patient to form a likely diagnosis or differential diagnoses. Avoid unnecessary or repetitive questions.

Patient: {age}-year-old {gender.lower()} with initial symptoms: {symptoms_str}
Conversation history:
{chat_history_text}

Have you gathered sufficient essential and differentiating information to reasonably proceed towards a diagnosis?

- If YES: reply ONLY with the exact string: Ready for diagnosis
- If NO (you still need one more critical piece of info): ask ONE follow-up question as an MCQ.
  * MCQ must be relevant to the most recent turn and be differentiating medically.
  * Use four options A, B, C, D; option D must be "None of these".
  * Use plain, easy-to-understand language.

Return format MUST be exactly JSON only (no explanation, no markdown), e.g.:
{{"Question":"...","A":"...","B":"...","C":"...","D":"None of these"}}"""

    raw_text = ""
    parsed = None
    retry_prompt_suffix = "\n\nThe previous response could not be parsed. PLEASE RETURN ONLY the JSON object in this exact format:\n{\"Question\":\"...\",\"A\":\"...\",\"B\":\"...\",\"C\":\"...\",\"D\":\"None of these\"}\nDo not include any other text or formatting."

    def _call_gemini(prompt_text: str):
        return generate_content_with_fallback(
            prompt=prompt_text,
            max_retries=None,  # Try all configured keys (up to 15)
            temperature=0.3,
            max_output_tokens=1000,
        )

    try:
        # First attempt: ask model via centralized Gemini API manager (multi-key with fallback)
        success, raw_text, error = _call_gemini(base_prompt)
        if not success or not raw_text:
            logger.error("Gemini follow-up generation failed: %s", error)
            if _is_api_key_failure(error):
                return _api_failure_response()
            return _deterministic_fallback(asked_questions_list)

        raw_text = (raw_text or "").strip()
        logger.info("Model response received (len=%d) for session prompt.", len(raw_text))

        # Quick normalized check for Ready for diagnosis
        if raw_text.strip().strip('"').strip("'").lower() == "ready for diagnosis":
            logger.info("Model returned Ready for diagnosis string.")
            return "Ready for diagnosis"

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
                return _deterministic_fallback(asked_questions_list)

        # Must be a dict – if not, fall back to a safe deterministic MCQ
        if not isinstance(parsed, dict):
            logger.error("Parsed output is not a dict. Parsed repr: %r", parsed)
            return _deterministic_fallback(asked_questions_list)

        parsed = _normalize_mcq_keys(parsed)
        if not _validate_mcq_structure(parsed):
            logger.error("MCQ structure invalid or missing keys after normalization: %s", parsed.keys())
            # If structure invalid, return fallback rather than None
            # Retry once with stricter instructions
            success, raw_text, error = _call_gemini(base_prompt + retry_prompt_suffix)
            if success and raw_text:
                parsed_retry = extract_json_from_text((raw_text or "").strip())
                if isinstance(parsed_retry, dict):
                    parsed_retry = _normalize_mcq_keys(parsed_retry)
                    if _validate_mcq_structure(parsed_retry):
                        parsed = parsed_retry
                    else:
                        return _deterministic_fallback(asked_questions_list)
                else:
                    return _deterministic_fallback(asked_questions_list)
            else:
                if _is_api_key_failure(error):
                    return _api_failure_response()
                return _deterministic_fallback(asked_questions_list)

        # Sanitize question/options for clarity and length
        parsed = _sanitize_mcq(parsed)

        # Check if this question is a duplicate of previously asked questions
        if parsed.get("Question"):
            question_text = " ".join(parsed["Question"].split())  # Normalize whitespace
            for asked_q in asked_questions_list:
                # Check similarity
                q_words = set(question_text.lower().split())
                asked_words = set(asked_q.lower().split())
                if len(q_words) > 0 and len(asked_words) > 0:
                    common_words = q_words & asked_words
                    similarity = len(common_words) / max(len(q_words), len(asked_words))
                    if similarity > 0.75:  # 75% similarity = duplicate
                        logger.warning(f"Generated question is duplicate (similarity={similarity:.2f}). Retrying with stricter prompt.")
                        success, raw_text, error = _call_gemini(base_prompt + retry_prompt_suffix)
                        if success and raw_text:
                            parsed_retry = extract_json_from_text((raw_text or "").strip())
                            if isinstance(parsed_retry, dict):
                                parsed_retry = _normalize_mcq_keys(parsed_retry)
                                parsed_retry = _sanitize_mcq(parsed_retry)
                                q_retry = parsed_retry.get("Question", "")
                                if q_retry and not any(_is_similar(q_retry, asked) for asked in asked_questions_list):
                                    parsed = parsed_retry
                                    break
                        if _is_api_key_failure(error):
                            return _api_failure_response()
                        return _deterministic_fallback(asked_questions_list)

        # Keep the model's Option D as-is (context-aware), don't override it
        # Only set default if D is missing
        if "D" not in parsed or not parsed["D"]:
            parsed["D"] = "None of these"

        return parsed

    except Exception as e:
        logger.exception("Unhandled exception in get_followup_for_diagnosis: %s", e)
        # Return a safe fallback
        return {
            "Question": "Are you experiencing any breathing difficulties?",
            "A": "Yes, mild",
            "B": "Yes, severe",
            "C": "No",
            "D": "None of these",
        }
