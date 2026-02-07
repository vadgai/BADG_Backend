"""
Diagnosis Methods: Method 1 (Chat History) and Method 2 (State-Based)

This module contains the two diagnosis approaches:
- Method 1: Uses full chat history (original approach, disabled by default)
- Method 2: Uses structured patient state (new hybrid approach, default)
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

from Followup_Generation.followup import get_followup_for_diagnosis, get_followup_for_diagnosis_hindi, _convert_to_new_format, _validate_mcq_structure, _normalize_mcq_keys
from diagnosis_methods.patient_state import (
    initialize_patient_state,
    update_patient_state,
    state_to_prompt_string
)
from diagnosis_methods.state_followup import (
    get_followup_from_state,
    analyze_answer_for_state
)
from diagnosis_methods.entropy_tracker import EntropyTracker

logger = logging.getLogger(__name__)


def _validate_question_response(response: Dict) -> bool:
    """
    Validate that a question response has the required structure.
    
    Args:
        response: Dictionary with question data
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(response, dict):
        return False
    
    # Check for required keys (case-insensitive)
    has_question = "Question" in response or "question" in response
    has_options = any(key in response for key in ["A", "B", "C", "D", "options", "Options"])
    
    return has_question and has_options


async def run_diagnosis_method_1(
    websocket: WebSocket,
    session_id: str,
    session: Dict,
    age: int,
    gender: str,
    symptoms: List[str],
    chat_history: List[Dict],
    selected_language: str,
    executor,
    run_generator
) -> None:
    """
    Method 1: Original chat history-based diagnosis approach.
    
    This method uses the full chat history to generate follow-up questions.
    Kept as backup but disabled by default.
    
    Args:
        websocket: WebSocket connection
        session_id: Session identifier
        session: Session data dictionary
        age: Patient age
        gender: Patient gender
        symptoms: Initial symptoms list
        chat_history: Full chat history (list of bot/user messages)
        selected_language: Language code (en, hi, etc.)
        executor: Thread pool executor
        run_generator: Async function to run blocking generators
    """
    logger.info(f"🔵 Method 1 (Chat History) - Session {session_id}")
    
    # Generate initial followup question
    existing_question_count = session.get("question_count", 0)
    
    if existing_question_count == 0:
        try:
            if selected_language == "hi":
                raw_response = await run_generator(
                    get_followup_for_diagnosis_hindi,
                    age, gender, symptoms, chat_history, 1
                )
            else:
                raw_response = await run_generator(
                    get_followup_for_diagnosis,
                    age, gender, symptoms, chat_history, 1
                )
            
            if isinstance(raw_response, str) and raw_response.strip().strip('"').strip("'").lower() == "ready for diagnosis":
                await websocket.send_json({
                    "message": "Sufficient information gathered. Generating diagnosis...",
                    "status": "ready_for_diagnosis"
                })
                await websocket.close(code=1000, reason="Ready for diagnosis")
                return
            
            if isinstance(raw_response, dict) and ("Question" in raw_response or "question" in raw_response):
                normalized = _convert_to_new_format(
                    raw_response,
                    language=selected_language,
                    next_question_number=session.get("question_count", 0) + 1
                )
                
                session["question_count"] = session.get("question_count", 0) + 1
                session["last_options"] = normalized
                chat_history.append({"bot": normalized["question"]})
                
                options_list = normalized.get("options", [])
                if not options_list:
                    options_list = ["Yes", "No", "Not sure", "None of these"]
                
                frontend_options = [
                    {"key": chr(65 + i), "value": opt}
                    for i, opt in enumerate(options_list[:5])
                ]
                
                await websocket.send_json({
                    "question": normalized["question"],
                    "options": frontend_options,
                    "status": "waiting_for_answer"
                })
        except Exception as e:
            logger.exception(f"Error in Method 1 initial question: {e}")
            await websocket.send_json({"error": "Failed to generate initial question"})
            await websocket.close(code=1011, reason="Initial question error")
            return
    
    # Conversation loop (original while True loop)
    while True:
        try:
            client_msg = await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(f"Session {session_id} disconnected by client.")
            break
        except Exception as e:
            logger.exception(f"Error receiving message for session {session_id}: {e}")
            await websocket.send_json({"error": "Error receiving message"})
            await websocket.close(code=1011, reason="Receive error")
            break
        
        logger.info(f"Received message for session {session_id}: {client_msg}")
        
        # Ignore heartbeat/ping messages
        try:
            msg_data = json.loads(client_msg)
            if isinstance(msg_data, dict) and msg_data.get("type") == "ping":
                logger.debug(f"Heartbeat ping received from session {session_id} - ignoring")
                await websocket.send_json({"type": "pong"})
                continue
        except json.JSONDecodeError:
            pass
        
        client_msg_clean = client_msg.strip().upper()
        
        # Map A/B/C/D to option text
        last_response = session.get("last_options", {})
        mapped_answer = None
        
        if "options" in last_response and isinstance(last_response["options"], list):
            options_list = last_response["options"]
            if client_msg_clean in ("A", "B", "C", "D", "E"):
                index = ord(client_msg_clean) - 65
                if 0 <= index < len(options_list):
                    mapped_answer = options_list[index]
            else:
                for opt in options_list:
                    if isinstance(opt, str) and client_msg_clean in opt.upper():
                        mapped_answer = opt
                        break
        else:
            if client_msg_clean in ("A", "B", "C", "D"):
                mapped_answer = last_response.get(client_msg_clean)
            else:
                for key, value in last_response.items():
                    if isinstance(value, str) and client_msg_clean in value.upper():
                        mapped_answer = value
                        break
        
        if mapped_answer:
            user_answer = mapped_answer
        else:
            logger.warning(f"Unmapped response from client for session {session_id}: {client_msg_clean}")
            user_answer = client_msg_clean
        
        # Add user answer to chat history
        chat_history.append({"user": user_answer})
        session["chat_history"] = chat_history
        
        updated_chat_history = session.get("chat_history", [])
        
        # Safety check: Detect repetitive questions
        if len(updated_chat_history) >= 6:
            last_bot_questions = [msg.get("bot", "") for msg in updated_chat_history[-6:] if isinstance(msg, dict) and "bot" in msg]
            if len(last_bot_questions) >= 3:
                if len(set(last_bot_questions[-3:])) == 1:
                    logger.warning(f"Session {session_id}: Detected 3 identical questions, forcing diagnosis")
                    await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Repetitive questions detected")
                    break
        
        # Generate next question
        try:
            if selected_language == "hi":
                next_raw = await run_generator(
                    get_followup_for_diagnosis_hindi,
                    age, gender, symptoms, updated_chat_history, 1
                )
            else:
                next_raw = await run_generator(
                    get_followup_for_diagnosis,
                    age, gender, symptoms, updated_chat_history, 1
                )
        except Exception as e:
            logger.exception(f"get_followup_for_diagnosis error for session {session_id}: {e}")
            await websocket.send_json({"error": "Failed to process answer (server error)."})
            await websocket.close(code=1011, reason="Internal processing error")
            break
        
        # Handle response
        if isinstance(next_raw, str) and next_raw.strip().strip('"').strip("'").lower() == "ready for diagnosis":
            logger.info(f"Session {session_id}: AI determined ready for diagnosis")
            await websocket.send_json({"message": "Sufficient information gathered. Generating diagnosis...", "status": "ready_for_diagnosis"})
            await websocket.close(code=1000, reason="Ready for diagnosis")
            break
        elif isinstance(next_raw, dict) and ("Question" in next_raw or "question" in next_raw):
            normalized = _convert_to_new_format(
                next_raw,
                language=selected_language,
                next_question_number=session.get("question_count", 0) + 1
            )
            
            current_question_count = session.get("question_count", 0)
            if current_question_count >= 12:
                logger.info(f"Session {session_id}: Reached maximum questions, forcing diagnosis")
                await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Max questions reached")
                break
            
            session["question_count"] = current_question_count + 1
            updated_chat_history.append({"bot": normalized["question"]})
            session["chat_history"] = updated_chat_history
            session["last_options"] = normalized
            
            options_list = normalized.get("options", [])
            if not options_list:
                options_list = ["Yes", "No", "Not sure", "None of these"]
            
            frontend_options = [
                {"key": chr(65 + i), "value": opt}
                for i, opt in enumerate(options_list[:5])
            ]
            
            await websocket.send_json({
                "question": normalized["question"],
                "options": frontend_options,
                "status": "waiting_for_answer"
            })
        else:
            logger.error(f"Unexpected format from generator for session {session_id}")
            await websocket.send_json({"error": "Unexpected response format"})
            await websocket.close(code=1011, reason="Unexpected format")
            break


async def run_diagnosis_method_2(
    websocket: WebSocket,
    session_id: str,
    session: Dict,
    age: int,
    gender: str,
    symptoms: List[str],
    selected_language: str,
    executor,
    run_generator
) -> None:
    """
    Method 2: Hybrid State-Based diagnosis approach.
    
    This method uses structured patient state instead of full chat history.
    State is updated after each Q&A turn with extracted information.
    
    Args:
        websocket: WebSocket connection
        session_id: Session identifier
        session: Session data dictionary
        age: Patient age
        gender: Patient gender
        symptoms: Initial symptoms list
        selected_language: Language code (en, hi, etc.)
        executor: Thread pool executor
        run_generator: Async function to run blocking generators
    """
    logger.info(f"🟢 Method 2 (Pure LLM Sequential Diagnostic Reasoning) - Session {session_id}")
    
    # Initialize or retrieve patient state
    if "patient_state" not in session:
        session["patient_state"] = initialize_patient_state(age, gender, symptoms)
        logger.info(f"Initialized patient state for session {session_id}")
    else:
        logger.info(f"Using existing patient state for session {session_id}")
    
    patient_state = session["patient_state"]
    
    # Initialize Entropy Tracker (now works with differential diagnosis instead of disease scores)
    if "entropy_tracker" not in session:
        session["entropy_tracker"] = EntropyTracker()
    entropy_tracker = session["entropy_tracker"]
    
    # Get initial differential diagnosis from state (if exists)
    initial_differential = patient_state.get("differential_diagnosis", [])
    if initial_differential:
        logger.info(f"Initial differential diagnosis: {[d.get('name') for d in initial_differential[:3]]}")
        # Record initial differential for entropy tracking
        entropy_tracker.record_differential(initial_differential)
    
    # Generate initial followup question
    existing_question_count = session.get("question_count", 0)
    
    if existing_question_count == 0:
        # Generate initial question with retry logic
        max_retries_initial = 3
        retry_delay_initial = 1.0
        raw_response = None
        last_error_initial = None
        
        for attempt in range(max_retries_initial):
            try:
                raw_response = await run_generator(
                    get_followup_from_state,
                    patient_state,
                    None,  # top_diseases (deprecated - kept for compatibility)
                    None,  # disease_engine (deprecated - kept for compatibility)
                    entropy_tracker,  # Pass for entropy tracking
                    1  # max_retries (internal to get_followup_from_state)
                )
                
                # FIX: Check if response is None (not an exception but function returned None)
                if raw_response is None:
                    if attempt < max_retries_initial - 1:
                        wait_time = retry_delay_initial * (attempt + 1)
                        logger.warning(f"get_followup_from_state returned None for session {session_id} (attempt {attempt+1}/{max_retries_initial}). Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue  # Retry
                    else:
                        # Last attempt failed
                        logger.error(f"get_followup_from_state returned None after {max_retries_initial} attempts for session {session_id}")
                        break  # Exit loop to handle None below
                
                # Success - break out of retry loop
                break
            except Exception as e:
                last_error_initial = e
                error_type = type(e).__name__
                error_msg = str(e)
                
                if attempt < max_retries_initial - 1:
                    wait_time = retry_delay_initial * (attempt + 1)
                    logger.warning(f"Initial question generation exception for session {session_id} (attempt {attempt+1}/{max_retries_initial}): {error_type}: {error_msg}. Retrying in {wait_time}s...")
                    try:
                        await asyncio.sleep(wait_time)
                    except Exception as sleep_error:
                        logger.warning(f"Error during retry delay: {sleep_error}")
                else:
                    logger.exception(f"Initial question generation failed after {max_retries_initial} attempts for session {session_id}: {error_type}: {error_msg}")
                    error_message = f"Unable to generate initial question after {max_retries_initial} attempts. Error: {error_type}"
                    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        error_message = "Request timed out while generating initial question. The system may be experiencing high load. Please refresh and try again."
                    elif "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                        error_message = "Service is temporarily unavailable due to high demand. Please try again in a moment."
                    
                    await websocket.send_json({
                        "error": error_message,
                        "error_type": error_type,
                        "retry_count": max_retries_initial
                    })
                    await websocket.close(code=1011, reason=f"Initial question failed after {max_retries_initial} retries")
                    return
        
        # FIX: Handle None response after all retries (both exception and None returns)
        # DO NOT close connection immediately - let frontend handle error and retry
        if raw_response is None:
            error_msg = f"get_followup_from_state returned None after {max_retries_initial} attempts for session {session_id}"
            if last_error_initial:
                error_msg += f". Last exception: {type(last_error_initial).__name__}: {str(last_error_initial)}"
            logger.error(error_msg)
            
            # Check if it's an API/network issue and provide helpful error message
            if last_error_initial and ("timeout" in str(last_error_initial).lower() or "timed out" in str(last_error_initial).lower()):
                error_message = "Request timed out while generating initial question. The system tried all available API keys but timed out. Please refresh and try again."
            elif last_error_initial and ("quota" in str(last_error_initial).lower() or "rate limit" in str(last_error_initial).lower() or "429" in str(last_error_initial)):
                error_message = "Service is temporarily unavailable due to high demand. All API keys are experiencing high load. Please try again in a moment."
            elif last_error_initial and ("api key" in str(last_error_initial).lower() or "401" in str(last_error_initial) or "403" in str(last_error_initial)):
                error_message = "API configuration issue detected. All API keys may be invalid or unauthorized. Please contact support."
            else:
                error_message = "Failed to generate initial question after trying all available API keys. Please refresh and try again."
            
            # Send error but KEEP connection open - frontend can handle retry
            await websocket.send_json({
                "error": error_message,
                "error_detail": str(last_error_initial) if last_error_initial else "All API keys failed or returned None",
                "retry_count": max_retries_initial,
                "error_type": "api_failure",
                "can_retry": True
            })
            
            # Log but don't close - let frontend decide when to close
            logger.warning(f"Connection kept open despite initial question failure for session {session_id}. Frontend should handle retry or close.")
            # DO NOT close here - this allows frontend to retry or show error UI
            # Connection will close naturally when frontend closes it or when normal flow completes
            return
        
        # Process successful response
        if isinstance(raw_response, str) and raw_response.strip().strip('"').strip("'").lower() == "ready for diagnosis":
            await websocket.send_json({
                "message": "Sufficient information gathered. Generating diagnosis...",
                "status": "ready_for_diagnosis"
            })
            await websocket.close(code=1000, reason="Ready for diagnosis")
            return
        
        if isinstance(raw_response, dict) and ("Question" in raw_response or "question" in raw_response):
            normalized = _convert_to_new_format(
                raw_response,
                language=selected_language,
                next_question_number=session.get("question_count", 0) + 1
            )
            
            session["question_count"] = session.get("question_count", 0) + 1
            session["last_options"] = normalized
            session["last_question"] = normalized["question"]
            
            # Also update chat_history for compatibility with report generation
            if "chat_history" not in session:
                session["chat_history"] = []
            session["chat_history"].append({"bot": normalized["question"]})
            
            options_list = normalized.get("options", [])
            if not options_list:
                options_list = ["Yes", "No", "Not sure", "None of these"]
            
            frontend_options = [
                {"key": chr(65 + i), "value": opt}
                for i, opt in enumerate(options_list[:5])
            ]
            
            await websocket.send_json({
                "question": normalized["question"],
                "options": frontend_options,
                "status": "waiting_for_answer"
            })
        else:
            # Unexpected format
            logger.error(f"Unexpected response format for initial question, session {session_id}: {type(raw_response)}")
            await websocket.send_json({"error": "Unexpected response format. Please refresh and try again."})
            await websocket.close(code=1011, reason="Invalid response format")
            return
    
    # Conversation loop (state-based)
    while True:
        try:
            client_msg = await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info(f"Session {session_id} disconnected by client.")
            break
        except Exception as e:
            logger.exception(f"Error receiving message for session {session_id}: {e}")
            await websocket.send_json({"error": "Error receiving message"})
            await websocket.close(code=1011, reason="Receive error")
            break
        
        logger.info(f"Received message for session {session_id}: {client_msg}")
        
        # Ignore heartbeat/ping messages
        try:
            msg_data = json.loads(client_msg)
            if isinstance(msg_data, dict) and msg_data.get("type") == "ping":
                logger.debug(f"Heartbeat ping received from session {session_id} - ignoring")
                await websocket.send_json({"type": "pong"})
                continue
        except json.JSONDecodeError:
            pass
        
        client_msg_clean = client_msg.strip().upper()
        
        # Map A/B/C/D to option text
        last_response = session.get("last_options", {})
        mapped_answer = None
        
        if "options" in last_response and isinstance(last_response["options"], list):
            options_list = last_response["options"]
            if client_msg_clean in ("A", "B", "C", "D", "E"):
                index = ord(client_msg_clean) - 65
                if 0 <= index < len(options_list):
                    mapped_answer = options_list[index]
            else:
                for opt in options_list:
                    if isinstance(opt, str) and client_msg_clean in opt.upper():
                        mapped_answer = opt
                        break
        else:
            if client_msg_clean in ("A", "B", "C", "D"):
                mapped_answer = last_response.get(client_msg_clean)
            else:
                for key, value in last_response.items():
                    if isinstance(value, str) and client_msg_clean in value.upper():
                        mapped_answer = value
                        break
        
        if mapped_answer:
            user_answer = mapped_answer
        else:
            logger.warning(f"Unmapped response from client for session {session_id}: {client_msg_clean}")
            user_answer = client_msg_clean
        
        # Get the question that was asked
        last_question = session.get("last_question", "")
        
        # Analyze answer and update patient state
        try:
            ai_analysis = await run_generator(
                analyze_answer_for_state,
                last_question,
                user_answer,
                patient_state
            )
            
            # Update patient state with analysis
            patient_state = update_patient_state(
                patient_state,
                last_question,
                user_answer,
                ai_analysis
            )
            session["patient_state"] = patient_state
            
            # Also update chat_history for compatibility with report generation
            if "chat_history" not in session:
                session["chat_history"] = []
            session["chat_history"].append({"user": user_answer})
            
            logger.info(f"Updated patient state for session {session_id}. Turn count: {patient_state.get('turn_count', 0)}")
        except Exception as e:
            logger.warning(f"Failed to analyze answer for state update: {e}")
            # Continue without state update if analysis fails
        
        # Action B: Get updated differential diagnosis from patient state
        current_differential = patient_state.get("differential_diagnosis", [])
        if current_differential:
            logger.info(f"Current differential diagnosis. Top 3: {[d.get('name') for d in current_differential[:3]]}")
            # Record differential for entropy tracking
            entropy_tracker.record_differential(current_differential, last_question)
        
        # Action C: Safety Check - Check for emergency conditions in differential diagnosis
        emergency_keywords = ["heart attack", "myocardial infarction", "sepsis", "stroke", "meningitis", 
                            "pulmonary embolism", "cardiac arrest", "anaphylaxis"]
        emergency_detected = False
        if current_differential:
            for condition in current_differential[:5]:
                name_lower = condition.get("name", "").lower()
                if any(keyword in name_lower for keyword in emergency_keywords):
                    emergency_detected = True
                    logger.warning(f"🚨 EMERGENCY DETECTED in differential: {condition.get('name')}")
                    break
        
        # Check stopping rules using Entropy Tracker (now works with differential diagnosis)
        turn_count = patient_state.get("turn_count", 0)
        
        # Synchronize question_count with turn_count for consistency
        if session.get("question_count", 0) != turn_count:
            session["question_count"] = turn_count
            logger.debug(f"Synced question_count to turn_count: {turn_count}")
        
        # PROFESSIONAL CLINICAL TURN CONSTRAINTS: Minimum 7 (general) / 8 (emergency), Maximum 12
        # Determine minimum based on emergency status
        min_required_turns = 8 if emergency_detected else 7
        
        if turn_count < min_required_turns:
            logger.info(f"Session {session_id}: Turn count {turn_count} < {min_required_turns} ({'emergency' if emergency_detected else 'general'}), continuing (minimum requirement)")
            # Force continue - don't check stopping rules yet
            should_stop = False
        # Enforce maximum 12 questions
        elif turn_count >= 12:
            logger.info(f"Session {session_id}: Turn count {turn_count} >= 12, stopping (maximum reached)")
            should_stop = True
            stop_reason = "exhaustion"
        else:
            # Check smart stop logic (only if min_required_turns <= turn_count < 12)
            # Note: entropy_tracker expects 7-12 range, which aligns with our min_required_turns
            should_stop, stop_reason = entropy_tracker.check_stopping_rules(
                current_differential,  # Pass differential diagnosis instead of top_diseases
                turn_count,
                emergency_detected
            )
        
        if should_stop:
            # Store stopping reason in session for report generation
            session["stopping_reason"] = stop_reason
            session["entropy_tracker"] = entropy_tracker  # Save tracker state
            session["emergency_detected"] = emergency_detected  # Store emergency flag
            
            if stop_reason == "emergency_detected":
                logger.warning(f"Session {session_id}: EMERGENCY DETECTED - Generating emergency report (after {turn_count} questions)")
                await websocket.send_json({
                    "message": "Emergency condition detected. Generating urgent diagnosis...",
                    "status": "ready_for_diagnosis",
                    "emergency": True
                })
            elif stop_reason == "confidence":
                logger.info(f"Session {session_id}: Stopping due to high confidence (after {turn_count} questions)")
                await websocket.send_json({
                    "message": "Sufficient information gathered. Generating diagnosis...",
                    "status": "ready_for_diagnosis"
                })
            elif stop_reason == "uselessness":
                logger.info(f"Session {session_id}: Stopping due to low information gain (after {turn_count} questions)")
                await websocket.send_json({
                    "message": "Reached optimal information level. Generating diagnosis...",
                    "status": "ready_for_diagnosis"
                })
            elif stop_reason == "exhaustion":
                logger.info(f"Session {session_id}: Stopping due to question limit (12 questions)")
                await websocket.send_json({
                    "message": "Maximum questions reached. Generating diagnosis...",
                    "status": "ready_for_diagnosis"
                })
            
            await websocket.close(code=1000, reason=f"Stopped: {stop_reason}")
            break
        
        # Generate next question from updated state (pure LLM reasoning) with retry logic
        max_retries = 3
        retry_delay = 1.0  # seconds
        next_raw = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                next_raw = await run_generator(
                    get_followup_from_state,
                    patient_state,
                    None,  # top_diseases (deprecated - kept for compatibility)
                    None,  # disease_engine (deprecated - kept for compatibility)
                    entropy_tracker,  # Pass for entropy tracking
                    1  # max_retries (internal to get_followup_from_state)
                )
                # Success - break out of retry loop
                break
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_msg = str(e)
                
                if attempt < max_retries - 1:
                    # Not last attempt - retry with delay
                    wait_time = retry_delay * (attempt + 1)  # Exponential backoff: 1s, 2s, 3s
                    logger.warning(f"get_followup_from_state error for session {session_id} (attempt {attempt+1}/{max_retries}): {error_type}: {error_msg}. Retrying in {wait_time}s...")
                    # Use asyncio.sleep for retry delay
                    try:
                        await asyncio.sleep(wait_time)
                    except Exception as sleep_error:
                        logger.warning(f"Error during retry delay: {sleep_error}")
                else:
                    # Last attempt failed - log and send error
                    logger.exception(f"get_followup_from_state failed after {max_retries} attempts for session {session_id}: {error_type}: {error_msg}")
                    # Send detailed error message to client
                    error_message = f"Unable to generate question after {max_retries} attempts. Error: {error_type}"
                    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        error_message = "Request timed out while generating question. The system may be experiencing high load. Please try again."
                    elif "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                        error_message = "Service is temporarily unavailable due to high demand. Please try again in a moment."
                    elif "api" in error_msg.lower() or "key" in error_msg.lower():
                        error_message = "Service configuration issue detected. Please contact support if this persists."
                    
                    await websocket.send_json({
                        "error": error_message,
                        "error_type": error_type,
                        "retry_count": max_retries
                    })
                    await websocket.close(code=1011, reason=f"Generation failed after {max_retries} retries")
                    break
        
        # Handle response
        current_question_count = session.get("question_count", 0)
        
        # Handle None or invalid responses
        if next_raw is None:
            logger.error(f"get_followup_from_state returned None for session {session_id}")
            await websocket.send_json({"error": "Failed to generate question. Please try again."})
            await websocket.close(code=1011, reason="Generation failed")
            break
        
        # Synchronize question_count with turn_count for consistency
        turn_count = patient_state.get("turn_count", 0)
        if current_question_count != turn_count:
            current_question_count = turn_count
            session["question_count"] = turn_count
        
        # Determine minimum based on emergency status
        min_required_turns = 8 if emergency_detected else 7
        
        # PROFESSIONAL CLINICAL TURN CONSTRAINTS: Enforce minimum 7 (general) / 8 (emergency), maximum 12
        if isinstance(next_raw, str) and next_raw.strip().strip('"').strip("'").lower() == "ready for diagnosis":
            # Check if we've met minimum requirement
            if current_question_count < min_required_turns:
                logger.info(f"Session {session_id}: AI wants to stop at {current_question_count} questions, but minimum is {min_required_turns} ({'emergency' if emergency_detected else 'general'}) - forcing continuation")
                # Force generation of another question
                # The LLM will be instructed to continue in the next iteration
                # For now, generate a generic follow-up question
                normalized = {
                    "question": "Can you provide more details about your symptoms?",
                    "options": ["Yes, I can provide more details", "I've told you everything", "I'm not sure", "None of these"]
                }
            else:
                logger.info(f"Session {session_id}: AI determined ready for diagnosis (after {current_question_count} questions)")
                await websocket.send_json({"message": "Sufficient information gathered. Generating diagnosis...", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Ready for diagnosis")
                break
        elif isinstance(next_raw, dict) and ("Question" in next_raw or "question" in next_raw):
            # Validate JSON structure
            if not _validate_question_response(next_raw):
                logger.error(f"Invalid question response format for session {session_id}: {next_raw}")
                await websocket.send_json({"error": "Invalid question format. Please try again."})
                await websocket.close(code=1011, reason="Invalid response format")
                break
            
            normalized = _convert_to_new_format(
                next_raw,
                language=selected_language,
                next_question_number=current_question_count + 1
            )
            
            # Validate normalized format
            if not normalized or not normalized.get("question") or not normalized.get("options"):
                logger.error(f"Failed to normalize question response for session {session_id}")
                await websocket.send_json({"error": "Failed to process question. Please try again."})
                await websocket.close(code=1011, reason="Normalization failed")
                break
            
            # Enforce maximum 12 questions
            if current_question_count >= 12:
                session["stopping_reason"] = "exhaustion"
                logger.info(f"Session {session_id}: Reached maximum questions (12), forcing diagnosis")
                await websocket.send_json({"message": "Maximum questions reached, generating diagnosis", "status": "ready_for_diagnosis"})
                await websocket.close(code=1000, reason="Max questions reached")
                break
            
            # Increment both question_count and sync with turn_count
            new_count = current_question_count + 1
            session["question_count"] = new_count
            # Note: turn_count will be incremented in update_patient_state when answer is received
            # Keep them aligned by ensuring turn_count is at least question_count - 1
            if patient_state.get("turn_count", 0) < current_question_count:
                patient_state["turn_count"] = current_question_count
            
            session["last_options"] = normalized
            session["last_question"] = normalized["question"]
            
            # Update chat_history for compatibility
            if "chat_history" not in session:
                session["chat_history"] = []
            session["chat_history"].append({"bot": normalized["question"]})
            
            options_list = normalized.get("options", [])
            if not options_list or len(options_list) < 2:
                logger.warning(f"Insufficient options in response for session {session_id}, using defaults")
                options_list = ["Yes", "No", "Not sure", "None of these"]
            
            # Ensure options are valid strings
            options_list = [str(opt).strip() for opt in options_list if opt and str(opt).strip()][:5]
            
            if len(options_list) < 2:
                logger.error(f"Invalid options list for session {session_id}")
                await websocket.send_json({"error": "Invalid question options. Please try again."})
                await websocket.close(code=1011, reason="Invalid options")
                break
            
            frontend_options = [
                {"key": chr(65 + i), "value": opt}
                for i, opt in enumerate(options_list[:5])
            ]
            
            # Validate WebSocket response before sending
            response_payload = {
                "question": str(normalized["question"]).strip(),
                "options": frontend_options,
                "status": "waiting_for_answer"
            }
            
            # Ensure response is valid JSON (json is already imported at module level)
            try:
                json.dumps(response_payload)  # Validate it's serializable
                await websocket.send_json(response_payload)
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize WebSocket response for session {session_id}: {e}")
                await websocket.send_json({"error": "Failed to format response. Please try again."})
                await websocket.close(code=1011, reason="Serialization failed")
                break
        else:
            logger.error(f"Unexpected format from generator for session {session_id}")
            await websocket.send_json({"error": "Unexpected response format"})
            await websocket.close(code=1011, reason="Unexpected format")
            break

