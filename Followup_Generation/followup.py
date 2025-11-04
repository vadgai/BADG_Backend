# Backend/Followup_Generation/followup.py
import os
import json
import ast
import logging
import asyncio
from typing import Optional, Union, Dict
from dotenv import load_dotenv
import google.generativeai as genai

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Load env
load_dotenv()
# Try both common environment variable names
google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# Use gemini-2.0-flash (latest and fastest)
# Alternative: gemini-pro or gemini-1.5-flash
MODEL_NAME = "gemini-2.0-flash"  

# configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model initialization (non-fatal if missing; functions will check model_available)
model_available = False
model = None

# 🔍 DEBUGGING: Log API key status
if not google_api_key:
    logger.error("="*80)
    logger.error("❌ GEMINI API KEY NOT FOUND!")
    logger.error("   Checked: GOOGLE_API_KEY and GEMINI_API_KEY")
    logger.error("   Please set in Backend/.env file:")
    logger.error("   GEMINI_API_KEY=your_actual_key_here")
    logger.error("="*80)
else:
    logger.info("="*80)
    logger.info("✅ Gemini API key loaded successfully")
    logger.info(f"   Key prefix: {google_api_key[:10]}..." if len(google_api_key) > 10 else "   Key too short!")
    logger.info("="*80)

if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        logger.info("🔧 Configuring Gemini API...")
        
        try:
            # If get_model is available in your GenAI SDK version, this probes model existence.
            genai.get_model(MODEL_NAME)
            logger.info(f"✅ Model '{MODEL_NAME}' is available")
        except Exception as e:
            # ignore - not all SDK installs expose get_model
            logger.warning(f"⚠️ Could not verify model availability (this is usually OK): {e}")
            
        try:
            model = genai.GenerativeModel(MODEL_NAME)
            model_available = True
            logger.info("="*80)
            logger.info(f"✅ SUCCESSFULLY CONNECTED TO MODEL: {MODEL_NAME}")
            logger.info("   Gemini AI is ready for follow-up question generation")
            logger.info("="*80)
        except Exception as e:
            logger.error("="*80)
            logger.error(f"❌ Failed to instantiate GenerativeModel: {e}")
            logger.error("   Will use fallback questions instead")
            logger.error("="*80)
    except Exception as e:
        logger.error("="*80)
        logger.error(f"❌ Error accessing model {MODEL_NAME}: {e}")
        logger.error("   Please check your API key and model name.")
        logger.error("="*80)

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

    # Count questions asked so far - count both "Question:" and "bot" messages
    question_count = 0
    if chat_history:
        # Count bot messages that contain questions
        for msg in chat_history:
            if isinstance(msg, dict) and msg.get("type") == "bot":
                if "Question:" in msg.get("content", "") or "?" in msg.get("content", ""):
                    question_count += 1
    
    # If we've asked too many questions, proceed to diagnosis
    if question_count >= 10:  # Reduced to 10 for faster diagnosis
        logger.info("Maximum questions reached (%d), proceeding to diagnosis", question_count)
        return "Ready for diagnosis"

    # If model not available, log and use deterministic fallback
    if not model_available or model is None:
        logger.warning("Model not available — using deterministic fallback MCQ.")
        # Simple fallback based on symptom keywords (keeps UX moving)
        s = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
        s_low = s.lower()
        if "fever" in s_low:
            return {
                "Question": "Do you have a cough along with the fever?",
                "A": "Dry cough",
                "B": "Productive / with phlegm",
                "C": "No cough",
                "D": "None of these",
            }
        if any(k in s_low for k in ["pain", "ache", "hurt"]):
            return {
                "Question": "Is the pain localized to one area or generalized?",
                "A": "Localized (one area)",
                "B": "Generalized (whole body)",
                "C": "Intermittent / comes and goes",
                "D": "None of these",
            }
        # generic fallback
        return {
            "Question": "Has this symptom started suddenly or gradually?",
            "A": "Sudden onset",
            "B": "Gradual onset",
            "C": "Intermittent",
            "D": "None of these",
        }

    # Build plain symptoms string
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    
    # Build enhanced patient profile for context
    patient_context = f"{age}-year-old {gender.lower()}"
    
    # Add BMI if weight and height available
    bmi_info = ""
    if weight and height:
        try:
            bmi = weight / ((height / 100) ** 2)
            bmi_category = "Underweight" if bmi < 18.5 else "Normal" if bmi < 25 else "Overweight" if bmi < 30 else "Obese"
            bmi_info = f"\n- BMI: {bmi:.1f} ({bmi_category})"
        except:
            pass
    
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

    base_prompt = f"""
You are an expert medical diagnostician conducting a targeted clinical interview. Your goal is to efficiently narrow down the differential diagnosis by asking the MOST relevant questions based on symptom patterns and patient context.

Patient Profile:
- Age & Gender: {patient_context}{bmi_info}{lifestyle_info}{location_info}

Initial Symptoms: {symptoms_str}

Conversation History (Previous Q&A):
{chat_history}

CURRENT QUESTION COUNT: {question_count}/10

CLINICAL REASONING FRAMEWORK:
1. ANALYZE all symptoms and previous answers together as a pattern
2. Identify which disease differentials are most likely based on the complete clinical picture
3. Ask questions that will DIFFERENTIATE between the top 2-3 competing diagnoses
4. Prioritize questions about: severity, duration, progression, associated symptoms, risk factors, red flags
5. Consider patient demographics (age, gender, BMI, lifestyle, occupation, location) when assessing disease probability

DECISION RULES:
- If you have asked {question_count} questions and gathered sufficient information to distinguish between likely conditions → reply: Ready for diagnosis
- If critical differentiating information is still missing AND {question_count} < 10 → ask ONE highly targeted follow-up question
- DO NOT ask repetitive or redundant questions already answered in chat history
- DO NOT ask general questions - each question must help narrow the differential diagnosis
- Focus on RED FLAGS, SEVERITY indicators, and PATHOGNOMONIC features

FOLLOW-UP QUESTION STRATEGY:
✓ Ask about: temporal patterns (onset, duration, progression), quality/character of symptoms, aggravating/relieving factors, associated symptoms specific to top differential diagnoses
✓ Consider: anatomical location, radiation, timing, triggers, impact on daily function
✓ Explore: relevant past medical history, family history, medication use, recent exposures
✗ Avoid: vague questions, questions already answered, unnecessary demographic questions

MCQ FORMAT (if asking a question):
- Frame question to target the most discriminating clinical feature
- Options A, B, C must represent distinct clinical scenarios that point to different diagnoses
- Option D must always be "None of these"
- Use clear, patient-friendly language without medical jargon

Return format MUST be JSON only (no markdown, no explanation):
{{"Question":"...","A":"...","B":"...","C":"...","D":"None of these"}}

OR if ready: Ready for diagnosis
"""

    raw_text = ""
    parsed = None

    try:
        # First attempt: ask model
        try:
            response = model.generate_content(base_prompt)
            raw_text = (getattr(response, "text", "") or "").strip()
            logger.info("Model response received (len=%d) for session prompt.", len(raw_text))
            logger.debug("Raw model response repr: %r", response)
        except Exception as e:
            logger.exception("Model.generate_content raised an exception: %s", e)
            # Fall back to deterministic MCQ to keep flow alive
            logger.warning("Using deterministic fallback because model raised an exception.")
            return {
                "Question": "Are you experiencing any of these: cough, breathlessness, or chest pain?",
                "A": "Cough",
                "B": "Shortness of breath",
                "C": "Chest pain",
                "D": "None of these",
            }

        # Quick normalized check for Ready for diagnosis
        if raw_text.strip().strip('"').strip("'").lower() == "ready for diagnosis":
            logger.info("Model returned Ready for diagnosis string.")
            return "Ready for diagnosis"

        # Clean and extract JSON
        cleaned = _strip_code_fences(raw_text)
        logger.debug("Cleaned model text (first 300 chars): %s", cleaned[:300])
        json_sub = _extract_first_json_object(cleaned)

        if json_sub:
            try:
                parsed = _safe_parse_json_like(json_sub)
            except Exception as e:
                logger.warning("JSON substring parse failed: %s", e)
                parsed = None
        else:
            try:
                parsed = _safe_parse_json_like(cleaned)
            except Exception:
                parsed = None

        # Retry loop if parse failed
        attempts = 0
        while parsed is None and attempts < max_retries:
            attempts += 1
            logger.info("Parsing failed — asking model to reformat strictly as JSON (retry %d).", attempts)
            reformat_prompt = (
                "The previous response could not be parsed. PLEASE RETURN ONLY the JSON object in this exact format:\n"
                '{"Question":"...","A":"...","B":"...","C":"...","D":"None of these"}\n'
                "Do not include any other text or formatting."
            )
            try:
                response = model.generate_content(cleaned + "\n\n" + reformat_prompt)
                raw_text = (getattr(response, "text", "") or "").strip()
                logger.info("Retry model response received (len=%d)", len(raw_text))
                cleaned = _strip_code_fences(raw_text)
                json_sub = _extract_first_json_object(cleaned)
                if json_sub:
                    parsed = _safe_parse_json_like(json_sub)
                else:
                    parsed = _safe_parse_json_like(cleaned)
            except Exception as e:
                logger.warning("Retry attempt failed: %s", e)
                parsed = None

        if parsed is None:
            # Log the raw_text for debugging and return fallback (do not crash)
            logger.error("Could not parse model output after retries. Raw response:\n%s", raw_text[:4000])
            # deterministic fallback (so UI does not get stuck)
            logger.warning("Returning deterministic fallback MCQ to avoid blocking the client.")
            return {
                "Question": "Is this problem getting worse, staying the same, or improving?",
                "A": "Getting worse",
                "B": "Staying the same",
                "C": "Improving",
                "D": "None of these",
            }

        # Must be a dict
        if not isinstance(parsed, dict):
            logger.error("Parsed output is not a dict. Parsed repr: %r", parsed)
            return None

        parsed = _normalize_mcq_keys(parsed)
        if not _validate_mcq_structure(parsed):
            logger.error("MCQ structure invalid or missing keys after normalization: %s", parsed.keys())
            # If structure invalid, return fallback rather than None
            return {
                "Question": "Please select the option that best describes your current condition.",
                "A": "Mild symptoms",
                "B": "Moderate symptoms",
                "C": "Severe symptoms",
                "D": "None of these",
            }

        # Ensure option D equals "None of these"
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


# ------------------ FastAPI WebSocket endpoint and router ------------------ #

router = APIRouter()
_sessions: Dict[str, Dict] = {}


async def _run_sync_in_executor(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


@router.websocket("/followup/{session_id}")
async def followup_ws(session_id: str, websocket: WebSocket):
    """
    WebSocket endpoint for follow-up question flow.

    Client should send an init JSON:
    {"type":"init","age":..,"gender":"..","symptoms":"..","chat_history":".."}

    Server returns either:
     - {"question":"...","options":["A text","B text","C text","None of these"]}
     - {"ready": true, "message":"Ready for diagnosis"}
     - {"error":"Unable to generate initial question.","detail":"..."} (then closes)
    """
    # Accept and log client info
    client_addr = None
    try:
        client_addr = getattr(websocket, "client", None)
        client_addr = client_addr.host if client_addr else "unknown"
    except Exception:
        client_addr = "unknown"

    await websocket.accept()
    logger.info("WebSocket connected for session %s from %s", session_id, client_addr)

    session = _sessions.setdefault(
        session_id, {"age": None, "gender": None, "symptoms": None, "chat_history": "", "answers": [], "last_options": {}}
    )

    try:
        # receive init payload (with timeout)
        try:
            init_text = await asyncio.wait_for(websocket.receive_text(), timeout=20.0)
        except asyncio.TimeoutError:
            err_msg = "No initialization data received from client."
            logger.error("Session %s: %s", session_id, err_msg)
            await websocket.send_text(json.dumps({"error": err_msg, "detail": "Client did not send init payload within 20s"}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1000)
            return

        try:
            init_payload = json.loads(init_text)
        except Exception as e:
            err_msg = "Invalid init payload JSON."
            detail = str(e)
            logger.exception("Session %s: invalid init payload: %s", session_id, detail)
            await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1002)
            return

        if init_payload.get("type") != "init":
            err_msg = "First message must be init payload."
            logger.error("Session %s: %s Received: %s", session_id, err_msg, init_payload)
            await websocket.send_text(json.dumps({"error": err_msg, "detail": "Expected type == 'init'"}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1002)
            return

        # validate/assign fields
        try:
            age = int(init_payload.get("age"))
            gender = str(init_payload.get("gender") or "unknown")
            symptoms = init_payload.get("symptoms") or ""
            chat_history = str(init_payload.get("chat_history") or "")
        except Exception as e:
            err_msg = "Init payload missing required fields or invalid types."
            detail = str(e)
            logger.exception("Session %s: invalid init fields: %s", session_id, detail)
            await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1002)
            return

        session.update({"age": age, "gender": gender, "symptoms": symptoms, "chat_history": chat_history, "answers": []})

        # generate initial question (run synchronous generator in executor)
        try:
            logger.info("Followup websocket: generating initial question for session %s", session_id)
            result = await _run_sync_in_executor(get_followup_for_diagnosis, age, gender, symptoms, chat_history)
        except Exception as e:
            err_msg = "Unable to generate initial question."
            detail = str(e)
            logger.exception("Followup websocket initial question failed for %s: %s", session_id, detail)
            try:
                await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
                await asyncio.sleep(0.1)
            except Exception:
                logger.exception("Failed to send followup error message to client for %s", session_id)
            try:
                await websocket.close(code=1011, reason=json.dumps({"error": err_msg, "detail": detail}))
            except Exception:
                try:
                    await websocket.close()
                except Exception:
                    pass
            return

        # interpret result
        if result is None:
            err_msg = "Unable to generate initial question."
            detail = "Model returned no usable output."
            logger.error("Session %s: %s Raw result: %s", session_id, err_msg, repr(result))
            try:
                await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
                await asyncio.sleep(0.1)
            except Exception:
                logger.exception("Failed to send followup error message to client for %s", session_id)
            try:
                await websocket.close(code=1011, reason=json.dumps({"error": err_msg, "detail": detail}))
            except Exception:
                try:
                    await websocket.close()
                except Exception:
                    pass
            return

        if isinstance(result, str) and result.lower().strip() == "ready for diagnosis":
            await websocket.send_text(json.dumps({"ready": True, "message": "Ready for diagnosis"}))
            logger.info("Session %s: model returned Ready for diagnosis.", session_id)
        elif isinstance(result, dict):
            q_text = result.get("Question") or result.get("question") or ""
            options = []
            for k in ("A", "B", "C", "D"):
                v = result.get(k) or result.get(k.lower())
                if v is not None:
                    options.append(v)
            if not options and result.get("options"):
                options = list(result.get("options"))
            # ensure option D is "None of these"
            if len(options) >= 4:
                options[3] = "None of these"
            else:
                while len(options) < 3:
                    options.append("Other")
                options.append("None of these")

            # store last options mapping (A/B/C/D mapped to full text)
            session["last_options"] = {"A": options[0], "B": options[1], "C": options[2], "D": options[3]}

            await websocket.send_text(json.dumps({"question": q_text, "options": options}))
            logger.info("Session %s: sent initial question -> %s", session_id, q_text)
        else:
            err_msg = "Unexpected model output type."
            detail = f"model returned: {repr(result)}"
            logger.error("Session %s: %s", session_id, detail)
            await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1011, reason=json.dumps({"error": err_msg, "detail": detail}))
            return

        # main loop: handle client answers
        while True:
            try:
                msg_text = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected by client for session %s", session_id)
                break
            except Exception as e:
                logger.exception("Error receiving from websocket for %s: %s", session_id, str(e))
                break

            try:
                msg = json.loads(msg_text)
            except Exception as e:
                logger.exception("Session %s: failed to parse incoming JSON: %s", session_id, str(e))
                await websocket.send_text(json.dumps({"error": "Invalid JSON", "detail": str(e)}))
                continue

            msg_type = msg.get("type")
            if msg_type == "answer":
                answer = msg.get("answer")
                session["answers"].append(answer)
                session["chat_history"] = (session.get("chat_history") or "") + f"\nQ: {msg.get('question','?')}\nA: {answer}"

                # generate next follow-up synchronously via executor
                try:
                    result = await _run_sync_in_executor(
                        get_followup_for_diagnosis,
                        session["age"],
                        session["gender"],
                        session["symptoms"],
                        session.get("chat_history", ""),
                    )
                except Exception as e:
                    err_msg = "Unable to generate follow-up question."
                    detail = str(e)
                    logger.exception("Followup generation failed for %s: %s", session_id, detail)
                    try:
                        await websocket.send_text(json.dumps({"error": err_msg, "detail": detail}))
                        await asyncio.sleep(0.1)
                    except Exception:
                        logger.exception("Failed to send followup error message to client for %s", session_id)
                    try:
                        await websocket.close(code=1011, reason=json.dumps({"error": err_msg, "detail": detail}))
                    except Exception:
                        try:
                            await websocket.close()
                        except Exception:
                            pass
                    return

                if result is None:
                    await websocket.send_text(json.dumps({"error": "Model returned no output on follow-up.", "detail": ""}))
                    continue

                if isinstance(result, str) and result.lower().strip() == "ready for diagnosis":
                    await websocket.send_text(json.dumps({"ready": True, "message": "Ready for diagnosis"}))
                    logger.info("Session %s: model indicates ready for diagnosis.", session_id)
                    continue

                if isinstance(result, dict):
                    q_text = result.get("Question") or result.get("question") or ""
                    options = []
                    for k in ("A", "B", "C", "D"):
                        v = result.get(k) or result.get(k.lower())
                        if v is not None:
                            options.append(v)
                    if not options and result.get("options"):
                        options = list(result.get("options"))
                    if len(options) >= 4:
                        options[3] = "None of these"
                    else:
                        while len(options) < 3:
                            options.append("Other")
                        options.append("None of these")
                    session["last_options"] = {"A": options[0], "B": options[1], "C": options[2], "D": options[3]}
                    await websocket.send_text(json.dumps({"question": q_text, "options": options}))
                    continue

                await websocket.send_text(json.dumps({"error": "Unexpected model output type", "detail": repr(result)}))

            elif msg_type == "close":
                logger.info("Session %s: client requested close.", session_id)
                await websocket.close()
                break
            else:
                await websocket.send_text(json.dumps({"error": "Unknown message type", "detail": f"Received: {msg_type}"}))

    except Exception as e:
        logger.exception("Unhandled exception in followup_ws for %s: %s", session_id, str(e))
        try:
            await websocket.send_text(json.dumps({"error": "Server error", "detail": str(e)}))
            await asyncio.sleep(0.05)
            await websocket.close(code=1011, reason=json.dumps({"error": "Server error", "detail": str(e)}))
        except Exception:
            try:
                await websocket.close()
            except Exception:
                pass
    finally:
        try:
            _sessions.pop(session_id, None)
            logger.info("Session %s cleaned up from store.", session_id)
        except Exception:
            pass
