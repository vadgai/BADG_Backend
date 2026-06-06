"""WebSocket follow-up handler (extracted from app.py)."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from followup.constants import MAX_FOLLOWUP_QUESTIONS, MIN_FOLLOWUP_QUESTIONS
from followup.feature_tracking import record_sent_question
from followup.fallbacks.turn_templates import build_turn_indexed_question
from followup.orchestrator import get_next_followup_question, update_state_with_answer
from followup.selection import select_question_candidate
from followup.session_helpers import (
    ensure_states,
    map_client_answer,
    mcq_options,
    record_question_trace,
    sync_structured_state,
    update_last_trace_after_answer,
)

logger = logging.getLogger("uvicorn.error")


async def handle_followup_websocket(
    websocket: WebSocket,
    session_id: str,
    session_store: Dict[str, dict],
    executor: ThreadPoolExecutor,
) -> None:
    logger.info("=" * 80)
    logger.info("WEBSOCKET CONNECTION session_id=%s client=%s", session_id, websocket.client)
    logger.info("=" * 80)

    try:
        await websocket.accept()
        logger.info("WebSocket accepted for session %s", session_id)

        if session_id not in session_store:
            await websocket.send_json({"error": "Invalid session_id"})
            await websocket.close(code=1008, reason="Invalid session_id")
            return

        session = session_store[session_id]
        age = session.get("age")
        gender = session.get("gender")
        symptoms = session.get("symptoms") or []

        async def run_blocking(func, *args, **kwargs):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

        patient_state, symptom_state = ensure_states(session, age, gender, symptoms)
        sync_structured_state(session, patient_state, symptom_state)
        session.setdefault("question_count", 0)

        if session.get("question_count", 0) >= MAX_FOLLOWUP_QUESTIONS:
            await websocket.send_json({
                "message": "Maximum questions reached, generating diagnosis",
                "status": "ready_for_diagnosis",
            })
            await websocket.close(code=1000, reason="Max questions reached")
            return

        async def send_question(raw_response, question_count: int) -> bool:
            selected = select_question_candidate(
                raw_response, patient_state, symptom_state, question_count
            )

            if isinstance(selected, str) and "ready for diagnosis" in selected.lower():
                if question_count >= MIN_FOLLOWUP_QUESTIONS:
                    await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Diagnosis ready")
                    return False
                selected = build_turn_indexed_question(
                    patient_state,
                    symptom_state,
                    question_count,
                    symptom_state.get("questions_asked", []),
                    allow_suffix_fallback=True,
                )

            if not (isinstance(selected, dict) and selected.get("Question")):
                if question_count >= MIN_FOLLOWUP_QUESTIONS:
                    await websocket.send_json({"message": "Diagnosis is ready", "status": "ready_for_diagnosis"})
                    await websocket.close(code=1000, reason="Diagnosis ready")
                    return False
                selected = build_turn_indexed_question(
                    patient_state,
                    symptom_state,
                    question_count,
                    symptom_state.get("questions_asked", []),
                    allow_suffix_fallback=True,
                )

            if not (isinstance(selected, dict) and selected.get("Question")):
                await websocket.send_json({"error": "Unable to generate a clinically valid follow-up question."})
                await websocket.close(code=1011, reason="Question generation failure")
                return False

            session["question_count"] = question_count
            session["last_options"] = selected
            session["last_question_data"] = selected
            session["last_question_text"] = selected.get("Question")
            record_sent_question(symptom_state, selected)
            trace_turn = record_question_trace(patient_state, selected, question_count)
            sync_structured_state(session, patient_state, symptom_state)

            payload = {
                "question": selected["Question"],
                "options": mcq_options(selected),
                "status": "waiting_for_answer",
                "allow_other": bool(selected.get("allow_other", True)),
            }
            for meta_key in (
                "priority", "clinical_intent", "differentiates_between",
                "feature_id", "question_source",
            ):
                if meta_key in selected:
                    payload[meta_key] = selected.get(meta_key)
            if isinstance(trace_turn, dict):
                payload["diagnostic_trace_turn"] = trace_turn

            await websocket.send_json(payload)
            return True

        if session.get("question_count", 0) == 0:
            try:
                raw_response = await run_blocking(get_next_followup_question, patient_state, 1)
            except Exception as exc:
                logger.warning("Initial generation failed session=%s: %s", session_id, exc)
                from followup.fallbacks.contextual import build_contextual_fallback
                raw_response = build_contextual_fallback(patient_state, symptom_state)

            if isinstance(raw_response, dict) and raw_response.get("error") == "api_key_failure":
                await websocket.send_json({"error": raw_response.get("message", "Service temporarily unavailable.")})
                await websocket.close(code=1011, reason="API key failure")
                return

            continued = await send_question(raw_response, 1)
            if not continued:
                return
        else:
            last_q = session.get("last_options")
            if isinstance(last_q, dict) and last_q.get("Question"):
                await websocket.send_json({
                    "question": last_q["Question"],
                    "options": mcq_options(last_q),
                    "status": "waiting_for_answer",
                    "allow_other": bool(last_q.get("allow_other", True)),
                    "feature_id": last_q.get("feature_id"),
                    "question_source": last_q.get("question_source"),
                })

        while True:
            try:
                client_msg = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("Session %s disconnected by client.", session_id)
                break
            except Exception as exc:
                logger.exception("Receive error session=%s: %s", session_id, exc)
                await websocket.send_json({"error": "Error receiving message"})
                await websocket.close(code=1011, reason="Receive error")
                break

            try:
                msg_data = json.loads(client_msg)
                if isinstance(msg_data, dict) and msg_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
            except json.JSONDecodeError:
                pass

            user_answer = map_client_answer(client_msg, session.get("last_options", {}))
            last_question_text = session.get("last_question_text", "")

            try:
                patient_state, update_meta = await run_blocking(
                    update_state_with_answer,
                    patient_state,
                    last_question_text or "",
                    user_answer,
                )
                if isinstance(update_meta, dict):
                    signals = update_meta.get("signals") or {}
                    if isinstance(signals, dict):
                        update_last_trace_after_answer(patient_state, signals)
                sync_structured_state(session, patient_state, symptom_state)
            except Exception as exc:
                logger.warning("update_state_with_answer failed session=%s: %s", session_id, exc)

            current_count = session.get("question_count", 0)
            if current_count >= MAX_FOLLOWUP_QUESTIONS:
                await websocket.send_json({
                    "message": "Maximum questions reached, generating diagnosis",
                    "status": "ready_for_diagnosis",
                })
                await websocket.close(code=1000, reason="Max questions reached")
                break

            try:
                next_raw = await run_blocking(get_next_followup_question, patient_state, 1)
            except Exception as exc:
                logger.exception("get_next_followup_question error session=%s: %s", session_id, exc)
                await websocket.send_json({"error": "Failed to process answer (server error)."})
                await websocket.close(code=1011, reason="Internal processing error")
                break

            if isinstance(next_raw, dict) and next_raw.get("error") == "api_key_failure":
                await websocket.send_json({"error": next_raw.get("message", "Service temporarily unavailable.")})
                await websocket.close(code=1011, reason="API key failure")
                break

            continued = await send_question(next_raw, current_count + 1)
            if not continued:
                break

    except WebSocketDisconnect:
        logger.info("Session %s disconnected (outer).", session_id)
    except Exception as exc:
        logger.exception("Unhandled websocket error session=%s: %s", session_id, exc)
        try:
            await websocket.send_json({"error": "Internal server error during followup"})
            await websocket.close(code=1011, reason="Unhandled server error")
        except Exception:
            pass
    finally:
        logger.info("Connection closed for session %s", session_id)
