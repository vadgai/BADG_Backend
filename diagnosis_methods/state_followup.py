"""
State-Based Followup Generation for Method 2 - Pure LLM Sequential Diagnostic Reasoning

This module implements "Sequential Differential Diagnosis" using pure LLM reasoning:
- Step A: Evidence Analysis
- Step B: Differential Mapping (3-5 conditions)
- Step C: Gap Identification
- Step D: Next-Best-Question (NBQ)
"""

import json
import logging
from typing import Optional, Union, Dict, List
from dotenv import load_dotenv
load_dotenv()

from utils.gemini_api_manager import generate_content_with_fallback, extract_json_from_text
from diagnosis_methods.patient_state import state_to_prompt_string

logger = logging.getLogger(__name__)


def get_followup_from_state(
    patient_state: Dict,
    top_diseases: Optional[List[Dict]] = None,  # Kept for compatibility, but not used
    disease_engine=None,  # Kept for compatibility, but not used
    entropy_tracker=None,  # Kept for compatibility, but not used
    max_retries: int = 1,
) -> Union[Dict, str, None]:
    """
    Generate a follow-up MCQ question using Pure LLM Sequential Differential Diagnosis.
    
    This function follows the "Senior Diagnostic Consultant" approach:
    1. Evidence Analysis: Analyze all previous patient responses
    2. Differential Mapping: Generate ranked list of 3-5 most likely conditions
    3. Gap Identification: Identify critical information to differentiate top 2 conditions
    4. Next-Best-Question (NBQ): Generate single most relevant follow-up question
    
    Args:
        patient_state: Structured patient state dictionary
        top_diseases: (Deprecated - kept for compatibility)
        disease_engine: (Deprecated - kept for compatibility)
        entropy_tracker: (Deprecated - kept for compatibility)
        max_retries: Maximum retry attempts for parsing
        
    Returns:
        - dict: parsed MCQ with keys "Question","A","B","C","D"
        - str: "Ready for diagnosis"
        - None: on error/unrecoverable
    """
    from utils.gemini_api_manager import get_gemini_model
    model_available, model = get_gemini_model()
    
    if not model_available or model is None:
        logger.error("Model is not available. Cannot generate content.")
        return None
    
    # Convert state to formatted string
    state_str = state_to_prompt_string(patient_state)
    
    # Get previous differential diagnosis from state (if exists)
    previous_differential = patient_state.get("differential_diagnosis", [])
    differential_str = ""
    if previous_differential:
        differential_str = "\n\nPREVIOUS DIFFERENTIAL DIAGNOSIS:\n"
        for idx, condition in enumerate(previous_differential[:5], 1):
            name = condition.get("name", "Unknown")
            confidence = condition.get("confidence", "Unknown")
            reasoning = condition.get("reasoning", "")
            differential_str += f"{idx}. {name} (Confidence: {confidence})\n"
            if reasoning:
                differential_str += f"   Reasoning: {reasoning[:100]}...\n"
    
    turn_count = patient_state.get('turn_count', 0)
    
    # Check for emergency red flags in identified symptoms
    emergency_detected = False
    emergency_keywords = [
        "chest pain", "severe chest pain", "difficulty breathing", "severe difficulty breathing",
        "loss of consciousness", "stroke", "severe headache", "severe abdominal pain",
        "severe bleeding", "cardiac", "heart attack", "myocardial infarction"
    ]
    identified_symptoms = patient_state.get("identified_symptoms", [])
    for symptom in identified_symptoms:
        symptom_lower = str(symptom).lower()
        if any(keyword in symptom_lower for keyword in emergency_keywords):
            emergency_detected = True
            break
    
    # Get last patient answer for clarification check
    last_answer = ""
    chat_history = patient_state.get("chat_history", [])
    if chat_history and len(chat_history) > 0:
        last_msg = chat_history[-1]
        if isinstance(last_msg, dict) and "user" in last_msg:
            last_answer = last_msg.get("user", "")
    
    # Extract age, gender, symptoms from patient_state for the prompt
    demographics = patient_state.get("demographics", {})
    age = demographics.get("age", "Unknown")
    gender = demographics.get("gender", "Unknown")
    identified_symptoms = patient_state.get("identified_symptoms", [])
    symptoms = ", ".join(identified_symptoms) if identified_symptoms else patient_state.get("chief_complaint", "Unknown")
    
    # Format chat_history as string
    chat_history_str = ""
    if chat_history and isinstance(chat_history, list):
        formatted_messages = []
        for msg in chat_history:
            if isinstance(msg, dict):
                if "bot" in msg:
                    formatted_messages.append(f"AI: {msg['bot']}")
                elif "user" in msg:
                    formatted_messages.append(f"Patient: {msg['user']}")
        chat_history_str = "\n".join(formatted_messages) if formatted_messages else "No previous conversation."
    else:
        chat_history_str = "No previous conversation."
    
    # Build prompt for Professional B2B Clinical Co-Pilot Engine
    # Enforce strict 7-12 turn range (8 for emergencies)
    emergency_min_turns = 8
    general_min_turns = 7
    
    if emergency_detected:
        if turn_count < emergency_min_turns:
            # Emergency: Must complete 8 questions for Clinical Triage Packet
            stop_logic = f"CONTINUE: Emergency suspected. Complete minimum {emergency_min_turns} questions for Clinical Triage Packet. Current: {turn_count}/{emergency_min_turns}"
        elif turn_count >= 12:
            stop_logic = "STOP NOW: Turn count reached 12. Reply ONLY 'Ready for diagnosis'."
        else:
            # Emergency: 8-12 range, can stop if clear
            stop_logic = f"STOP if: Top DDx probability plateau reached (no significant information gain) AND turn_count ({turn_count}) is {emergency_min_turns}-12\nCONTINUE if: More triage data needed AND turn_count < 12"
    else:
        if turn_count < general_min_turns:
            # General: Must complete 7 questions minimum
            stop_logic = f"CONTINUE: Complete minimum {general_min_turns} questions. Current: {turn_count}/{general_min_turns}"
        elif turn_count >= 12:
            stop_logic = "STOP NOW: Turn count reached 12. Reply ONLY 'Ready for diagnosis'."
        else:
            # General: 7-12 range - check for plateau
            stop_logic = f"STOP if ANY condition met:\n   - Top DDx probability plateau (no significant information gain) AND turn_count ({turn_count}) is {general_min_turns}-12\n   - Turn count reaches 12\nCONTINUE if: More information needed AND turn_count < 12 AND information gain > 5%"
    
    # Emergency handling: Clinical Triage Packet requirements
    emergency_note = ""
    triage_packet_requirements = ""
    if emergency_detected:
        if turn_count < emergency_min_turns:
            triage_packet_requirements = f"""
CRITICAL: Gather Clinical Triage Packet (minimum {emergency_min_turns} questions):
- Onset: When did symptoms start? Acute vs gradual?
- PQRST Pain Assessment: Provocation/Palliation, Quality, Region/Radiation, Severity (0-10), Timing
- Relevant PMH: Past medical history, medications, allergies
- Associated Negatives: What symptoms are absent (helps rule out differentials)
- Vital Signs Context: Any reported fever, BP, HR changes?
Current Progress: {turn_count}/{emergency_min_turns}"""
            emergency_note = f"\n🚨 HIGH-ACUITY CASE DETECTED: {triage_packet_requirements}"
        else:
            emergency_note = f"\n🚨 HIGH-ACUITY CASE: Clinical Triage Packet complete ({emergency_min_turns} questions). May stop if diagnosis clear."
    
    # Professional clinical terminology guide
    clinical_terminology_note = """
USE CLINICAL TERMINOLOGY (Professional B2B Mode):
- "dyspnea" not "shortness of breath"
- "syncope" not "fainting"
- "tachycardia" not "fast heart rate"
- "hemoptysis" not "coughing up blood"
- "melena" not "black stool"
- Use precise medical terms appropriate for clinician-to-clinician communication"""
    
    base_prompt = f"""
ACT: Senior Clinical Consultant - Professional Diagnostic Co-Pilot (B2B Mode).
ROLE: You are a clinical decision support tool for Doctors and Nurses. No patient-facing language.
CASE: {age}yo {gender} presenting with: {symptoms}.

CURRENT TURN: {turn_count} (Range: {general_min_turns if not emergency_detected else emergency_min_turns}-12 questions)
{emergency_note}

CONTEXT (Medical History):
{chat_history_str}

SEQUENTIAL CLINICAL REASONING (MANDATORY):
1. UPDATE DIFFERENTIAL DIAGNOSIS (DDx) LEADERBOARD: Rank top 3-5 suspected conditions based on:
   - Symptom pattern match (pathophysiology alignment)
   - Demographics (age, gender)
   - Clinical history evidence
   - Negative findings (what's ruled out)
   
2. CALCULATE INFORMATION GAIN: Identify the 'Differentiator Symptom' that provides maximum information gain to separate:
   - Suspect #1 (top DDx) from Suspect #2 (second most likely)
   This symptom/feature should strongly support one while ruling out the other.

3. GENERATE CLINICALLY PRECISE FOLLOW-UP QUESTION:
   - Focus EXCLUSIVELY on the Differentiator Symptom
   - Use professional medical terminology (see guide below)
   - Be specific and clinically meaningful
   - Probe for quantitative data when relevant (duration, severity scales, frequencies)

{clinical_terminology_note}

TERMINATION LOGIC:
{stop_logic}

OUTPUT FORMAT:
- If STOPPING: Reply ONLY the exact string: "Ready for diagnosis"
- If CONTINUING: Return JSON ONLY (no markdown, no explanations):
{{"Question":"Clinically precise question focused on Differentiator Symptom","A":"Option 1","B":"Option 2","C":"Option 3","D":"None of these"}}

REMEMBER: This is B2B clinical decision support. Be direct, technical, and evidence-focused. No patient counseling language.
"""

    # Check if API keys are available before attempting
    from utils.gemini_api_manager import _load_api_keys
    available_keys = _load_api_keys()
    if not available_keys or len(available_keys) == 0:
        logger.error("get_followup_from_state: NO API KEYS AVAILABLE! Cannot generate question.")
        logger.error("   Please set at least one API key: GEMINI_API_KEY_1 through GEMINI_API_KEY_15")
        logger.error("   Or legacy: GOOGLE_API_KEY or GEMINI_API_KEY")
        # Return None - this will be handled by caller
        return None
    
    logger.info(f"get_followup_from_state: Attempting generation with {len(available_keys)} available API key(s)")
    
    # Try ALL available API keys (up to 15) when one fails - ensure maximum reliability
    # max_retries=None will use all available keys automatically
    success, raw_text, error = generate_content_with_fallback(
        prompt=base_prompt,
        max_retries=None,  # Use all available keys (up to 15) - ensures maximum fallback reliability
        temperature=0.3,
        max_output_tokens=1000  # SPEED FIX: Reduced from 2000 to 1000 (questions are short)
    )
    
    if not success:
        error_details = error or "Unknown error"
        logger.error("="*80)
        logger.error(f"get_followup_from_state: API call failed after trying {len(available_keys)} available API key(s)")
        logger.error(f"   Error details: {error_details}")
        logger.error("="*80)
        
        # Check for specific error types to provide better error context
        error_lower = error_details.lower() if error_details else ""
        if "timeout" in error_lower or "timed out" in error_lower:
            logger.error(f"   → ERROR TYPE: Timeout - All {len(available_keys)} API keys timed out or request exceeded 30s timeout")
        elif "quota" in error_lower or "rate limit" in error_lower or "429" in error_details:
            logger.error(f"   → ERROR TYPE: Quota/Rate limit - All {len(available_keys)} API keys exhausted quotas or hit rate limits")
        elif "api key" in error_lower or "401" in error_details or "403" in error_details or "invalid" in error_lower:
            logger.error(f"   → ERROR TYPE: API key authentication - All {len(available_keys)} API keys may be invalid, expired, or unauthorized")
            logger.error(f"   → ACTION REQUIRED: Check API keys in .env file or environment variables")
        elif "no working" in error_lower or "exhausted" in error_lower:
            logger.error(f"   → ERROR TYPE: All keys failed - All {len(available_keys)} API keys were tried but none succeeded")
        else:
            logger.error(f"   → ERROR TYPE: General API error - {error_details}")
        logger.error("="*80)
        
        # Return None to let caller handle retry logic
        # The error is logged above for debugging
        return None
    
    if not raw_text:
        logger.error("get_followup_from_state: Generated content is empty")
        return None
    
    raw_text = raw_text.strip()
    
    # Normalize the special Ready reply
    if raw_text.strip().strip('"').strip("'").lower() == "ready for diagnosis":
        return "Ready for diagnosis"
    
    # FIX: Use robust JSON extraction like followup.py (handles markdown, extra text, etc.)
    from Followup_Generation.followup import _strip_code_fences, _extract_first_json_object, _safe_parse_json_like
    
    # Clean and extract JSON using same methods as followup.py
    cleaned = _strip_code_fences(raw_text)
    json_sub = _extract_first_json_object(cleaned)
    
    parsed = None
    parsing_error = None
    
    if json_sub:
        try:
            parsed = _safe_parse_json_like(json_sub)
        except Exception as e:
            parsing_error = e
            error_msg = str(e)
            logger.warning(f"get_followup_from_state: Failed to parse extracted JSON: {error_msg}")
    else:
        # If no JSON substring found, try parsing whole cleaned text
        try:
            parsed = _safe_parse_json_like(cleaned)
        except Exception as e:
            parsing_error = e
            error_msg = str(e)
            logger.warning(f"get_followup_from_state: Failed to parse cleaned text: {error_msg}")
    
    # Fallback: try extract_json_from_text if above methods failed
    if parsed is None:
        try:
            parsed_json = extract_json_from_text(raw_text)
            if parsed_json and isinstance(parsed_json, dict):
                parsed = parsed_json
        except Exception as e:
            logger.warning(f"get_followup_from_state: extract_json_from_text also failed: {e}")
    
    # If JSON parsing failed due to truncation/unterminated string, retry with reformat prompt
    if parsed is None and parsing_error:
        error_msg = str(parsing_error)
        if "unterminated" in error_msg.lower() or "truncated" in error_msg.lower() or "expecting" in error_msg.lower():
            logger.warning("="*80)
            logger.warning("⚠️ JSON parsing failed due to truncated/unterminated response")
            logger.warning(f"   Error: {error_msg}")
            logger.warning("   Retrying with reformat prompt to get complete JSON...")
            logger.warning("="*80)
            
            # Retry with a reformat prompt asking for complete JSON
            reformat_prompt = (
                "Your previous response had truncated JSON. Please return ONLY complete, valid JSON:\n"
                '{"Question":"Complete question text here","A":"Option A","B":"Option B","C":"Option C","D":"None of these"}\n\n'
                "IMPORTANT: Ensure the JSON is complete and all string values are properly closed."
            )
            
            retry_success, retry_text, retry_error = generate_content_with_fallback(
                prompt=raw_text[:500] + "\n\n" + reformat_prompt,  # Use first 500 chars + reformat prompt
                max_retries=None,  # Try all available keys (up to 15) if first fails
                temperature=0.3,
                max_output_tokens=1000
            )
            
            if retry_success and retry_text:
                logger.info("   ✅ Retry successful, attempting to parse reformatted response...")
                # Try parsing the retry response
                retry_cleaned = _strip_code_fences(retry_text)
                retry_json_sub = _extract_first_json_object(retry_cleaned)
                
                if retry_json_sub:
                    try:
                        parsed = _safe_parse_json_like(retry_json_sub)
                        logger.info("   ✅ Successfully parsed reformatted JSON")
                    except Exception as retry_e:
                        logger.warning(f"   ⚠️ Retry response still failed to parse: {retry_e}")
                else:
                    try:
                        parsed = _safe_parse_json_like(retry_cleaned)
                        logger.info("   ✅ Successfully parsed reformatted text")
                    except Exception as retry_e:
                        logger.warning(f"   ⚠️ Retry response still failed to parse: {retry_e}")
            else:
                logger.warning(f"   ⚠️ Retry API call failed: {retry_error}")
    
    if parsed and isinstance(parsed, dict):
        # Normalize keys
        from Followup_Generation.followup import _normalize_mcq_keys, _validate_mcq_structure
        normalized = _normalize_mcq_keys(parsed)
        
        # Validate structure before returning
        if _validate_mcq_structure(normalized):
            # Ensure option D equals "None of these"
            normalized["D"] = "None of these"
            logger.info(f"get_followup_from_state: Successfully generated question: {normalized.get('Question', 'N/A')[:50]}...")
            return normalized
        else:
            logger.error(f"get_followup_from_state: MCQ structure validation failed. Keys: {normalized.keys()}")
            logger.debug(f"get_followup_from_state: Parsed dict preview: {str(normalized)[:200]}...")
    else:
        # Log detailed error for debugging
        logger.error(f"get_followup_from_state: JSON parsing failed. Response length: {len(raw_text) if raw_text else 0}")
        logger.error(f"get_followup_from_state: Raw response preview (first 500 chars): {raw_text[:500] if raw_text else 'None'}...")
        logger.error(f"get_followup_from_state: Parsed result type: {type(parsed)}")
    
    # FIX: Return None only after all parsing attempts fail - let caller handle retry
    return None


def analyze_answer_for_state(
    question: str,
    answer: str,
    current_state: Dict
) -> Optional[Dict]:
    """
    Analyze a patient's answer and extract structured information to update state.
    Now includes differential diagnosis generation using pure LLM reasoning.
    
    Args:
        question: The question that was asked
        answer: The patient's answer
        current_state: Current patient state
        
    Returns:
        Dictionary with extracted information (symptoms, negatives, conditions, confidence, differential_diagnosis)
        or None if analysis fails
    """
    from utils.gemini_api_manager import get_gemini_model
    model_available, model = get_gemini_model()
    
    if not model_available or model is None:
        return None
    
    state_str = state_to_prompt_string(current_state)
    
    # Get patient demographics for context
    age = current_state.get("demographics", {}).get("age", "Unknown")
    gender = current_state.get("demographics", {}).get("gender", "Unknown")
    
    prompt = f"""
You are analyzing a patient's answer and updating the diagnostic reasoning.

CURRENT PATIENT STATE:
{state_str}

QUESTION ASKED: {question}
PATIENT ANSWER: {answer}

TASK: Extract structured information and generate a differential diagnosis.

STEP 1: Extract Information
1. Any NEW symptoms mentioned in the answer (add to identified_symptoms)
2. Any symptoms/conditions RULED OUT by the answer (add to negatives)
3. Update confidence_score (0.0 to 1.0) based on how much information we have

STEP 2: Generate Differential Diagnosis (Top 3 Suspects)
Based on ALL available information (including this new answer), generate EXACTLY 3 most likely conditions.
Rank them as: Suspect #1 (most likely), Suspect #2, Suspect #3.

For each condition, provide:
- name: Specific medical condition name
- confidence: "High" (≥70%), "Moderate" (50-70%), or "Low" (<50%)
- reasoning: Brief 1-2 sentence explanation of why this condition fits

STEP 3: Identify Differentiator Symptom
Compare Suspect #1 vs Suspect #2:
- Identify the ONE symptom/feature that would:
  * STRONGLY support Suspect #1 if present
  * STRONGLY support Suspect #2 if absent (or vice versa)
- This is the "Differentiator Symptom" - the critical piece of information needed next

Consider:
- Patient demographics (Age: {age}, Gender: {gender})
- All identified symptoms and their patterns
- Negative findings (what's ruled out)
- India-specific context (tropical diseases, lifestyle factors)

Return ONLY valid JSON in this format:
{{
  "identified_symptoms": ["new symptom 1", "new symptom 2"],
  "negatives": ["ruled out symptom/condition"],
  "confidence_score": 0.75,
  "differential_diagnosis": [
    {{
      "name": "Suspect #1 - Most Likely Condition",
      "confidence": "High|Moderate|Low",
      "reasoning": "Brief explanation of why this fits"
    }},
    {{
      "name": "Suspect #2 - Second Most Likely",
      "confidence": "Moderate",
      "reasoning": "Brief explanation"
    }},
    {{
      "name": "Suspect #3 - Third Most Likely",
      "confidence": "Low",
      "reasoning": "Brief explanation"
    }}
  ],
  "differentiator_symptom": "The one symptom/feature that differentiates Suspect #1 from Suspect #2",
  "running_summary": "Concise clinical summary (2-3 sentences) of key findings, top suspect, and critical differentiator. This will be used for fast report generation."
}}

Generate EXACTLY 3 conditions in the differential diagnosis, ranked by likelihood.
The running_summary should be concise and clinical - it will be used to speed up final report generation.
"""

    success, raw_text, error = generate_content_with_fallback(
        prompt=prompt,
        max_retries=None,  # Try all available API keys (up to 15) if first fails
        temperature=0.2,
        max_output_tokens=2000
    )
    
    if not success or not raw_text:
        logger.warning(f"Failed to analyze answer: {error}")
        return None
    
    # Extract JSON
    parsed_json = extract_json_from_text(raw_text)
    
    if parsed_json and isinstance(parsed_json, dict):
        return parsed_json
    
    return None

