"""WebSocket follow-up handler (extracted from app.py)."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from followup.constants import MAX_FOLLOWUP_QUESTIONS
from followup.feature_tracking import record_sent_question
from followup.fallbacks.turn_templates import build_turn_indexed_question
from followup.orchestrator import get_next_followup_question, update_state_with_answer
from followup.selection import can_stop_early, select_question_candidate
from followup.session_helpers import (
    ensure_states,
    map_client_answer,
    mcq_options,
    record_question_trace,
    sync_structured_state,
    update_last_trace_after_answer,
)
from database.session_persistence import get_or_restore_session, save_session
from symptom_card import apply_symptom_card, generate_symptom_card

logger = logging.getLogger("uvicorn.error")

# The mid-questionnaire symptom card IS question #7 of the 10-question flow:
# MCQs 1-6, symptom card, MCQs 8-10. It triggers once the patient has answered
# question 6 and draws from the current top-4 differential, so its selections
# directly shape questions 8-10.
MIDPOINT_CARD_AFTER_QUESTION = 6


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

        session = await get_or_restore_session(session_id, session_store)
        if session is None:
            await websocket.send_json({"error": "Invalid session_id"})
            await websocket.close(code=1008, reason="Invalid session_id")
            return
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
                if can_stop_early(patient_state, question_count):
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
                if can_stop_early(patient_state, question_count):
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

            # Persist before sending: a reconnect may land on another Cloud Run instance.
            await save_session(session_id, session)

            await websocket.send_json(payload)
            return True

        async def offer_midpoint_card() -> bool:
            """Push the Q7 mid-questionnaire symptom card and block for its reply.

            Built from the current top-4 differential's highest-information-gain
            symptoms (no condition names ever leave the server). Returns False if
            the socket disconnects while waiting, so the caller can bail out.
            """
            card = await run_blocking(generate_symptom_card, patient_state, "midpoint")
            if not (isinstance(card, dict) and (card.get("symptoms") or card.get("clinical_factors"))):
                # Nothing to offer — don't consume question slot #7, keep MCQs flowing.
                session["midpoint_card_shown"] = True
                return True

            await websocket.send_json({
                "type": "symptom_card",
                "stage": "midpoint",
                "question_number": MIDPOINT_CARD_AFTER_QUESTION + 1,
                "card": card,
            })

            while True:
                try:
                    card_msg = await websocket.receive_text()
                except WebSocketDisconnect:
                    logger.info("Session %s disconnected while awaiting midpoint symptom card.", session_id)
                    return False
                except Exception as exc:
                    logger.exception("Receive error awaiting midpoint card session=%s: %s", session_id, exc)
                    return False

                try:
                    card_data = json.loads(card_msg)
                except json.JSONDecodeError:
                    card_data = None

                if isinstance(card_data, dict) and card_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                if isinstance(card_data, dict) and card_data.get("type") == "symptom_card_submit":
                    try:
                        # Mutates patient_state in place and returns the same dict.
                        await run_blocking(
                            apply_symptom_card,
                            patient_state,
                            card_data.get("offered") or [],
                            card_data.get("selected") or [],
                            card_data.get("factors") or {},
                        )
                        merged_symptom_state = patient_state.get("symptom_state")
                        if isinstance(merged_symptom_state, dict):
                            symptom_state.update(merged_symptom_state)
                        sync_structured_state(session, patient_state, symptom_state)
                        await save_session(session_id, session)
                    except Exception as exc:
                        logger.warning("apply_symptom_card (midpoint) failed session=%s: %s", session_id, exc)
                # Any non-ping reply (submit or skip) ends the wait — fail open.
                break

            # The card consumed question slot #7 — the next MCQ is #8.
            session["midpoint_card_shown"] = True
            session["question_count"] = MIDPOINT_CARD_AFTER_QUESTION + 1
            await save_session(session_id, session)
            return True

        async def advance_after_answer(current_count: int) -> bool:
            """After question `current_count` has been answered, offer the
            midpoint card if this was question #6 and it hasn't been shown
            yet, then generate + send the next question. Returns False if the
            connection should stop (closed, disconnected, or errored).

            Shared by the normal per-turn loop AND the reconnect path below —
            a client that disconnects while the midpoint card was pending must
            be re-offered that same card on reconnect, not have the
            already-answered question #6 replayed at it.
            """
            if current_count >= MAX_FOLLOWUP_QUESTIONS:
                await websocket.send_json({
                    "message": "Maximum questions reached, generating diagnosis",
                    "status": "ready_for_diagnosis",
                })
                await websocket.close(code=1000, reason="Max questions reached")
                return False

            if current_count == MIDPOINT_CARD_AFTER_QUESTION and not session.get("midpoint_card_shown"):
                if not await offer_midpoint_card():
                    return False
                # Re-read: if the card was shown it took slot #7, so the next MCQ is #8.
                current_count = session.get("question_count", current_count)

            try:
                next_raw = await run_blocking(get_next_followup_question, patient_state, 1)
            except Exception as exc:
                logger.exception("get_next_followup_question error session=%s: %s", session_id, exc)
                await websocket.send_json({"error": "Failed to process answer (server error)."})
                await websocket.close(code=1011, reason="Internal processing error")
                return False

            if isinstance(next_raw, dict) and next_raw.get("error") == "api_key_failure":
                await websocket.send_json({"error": next_raw.get("message", "Service temporarily unavailable.")})
                await websocket.close(code=1011, reason="API key failure")
                return False

            return await send_question(next_raw, current_count + 1)

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
        elif (
            session.get("question_count", 0) == MIDPOINT_CARD_AFTER_QUESTION
            and not session.get("midpoint_card_shown")
        ):
            # Reconnecting after a disconnect that happened while the midpoint
            # card was pending (its reply was never received, so question_count
            # never advanced past #6). Re-offer the same card instead of
            # resending last_options, which is still question #6 — already
            # answered — and would otherwise be replayed at the patient.
            if not await advance_after_answer(session.get("question_count", 0)):
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
                await save_session(session_id, session)
            except Exception as exc:
                logger.warning("update_state_with_answer failed session=%s: %s", session_id, exc)

            current_count = session.get("question_count", 0)
            if not await advance_after_answer(current_count):
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
