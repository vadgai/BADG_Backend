#!/usr/bin/env python3
"""Diagnose follow-up quality over the live WebSocket flow.

Prints each question's `question_source` (llm / deterministic / turn_indexed)
so we can see whether the v5 LLM reasoning is actually driving questions.
"""

import asyncio
import json

import requests
import websockets

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


async def run_session(symptoms_text):
    patient = {
        "name": "Flow Test",
        "age": 30,
        "gender": "Male",
        "symptoms": symptoms_text,
    }
    r = requests.post(f"{BASE}/symptom", json=patient, timeout=30)
    r.raise_for_status()
    session_id = r.json()["session_id"]
    print(f"Session: {session_id} | symptoms: {symptoms_text}")

    answers = ["A", "B", "A", "C", "B", "A"]
    sources = []

    async with websockets.connect(f"{WS_BASE}/followup/{session_id}", max_size=None) as ws:
        turn = 0
        ans_idx = 0
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
            except asyncio.TimeoutError:
                print("  [timeout waiting for server]")
                break

            data = json.loads(raw)
            status = data.get("status")
            if data.get("type") == "pong":
                continue
            if "error" in data:
                print(f"  [server error] {data['error']}")
                break
            if status == "ready_for_diagnosis" or "ready" in str(data.get("message", "")).lower():
                print(f"  -> {data.get('message', 'ready')}")
                break
            if "question" not in data:
                continue

            turn += 1
            src = data.get("question_source", "unknown")
            sources.append(src)
            print(f"  Q{turn} [source={src}]: {data['question']}")

            if ans_idx >= len(answers):
                break
            await ws.send(answers[ans_idx])
            ans_idx += 1

    return sources


async def main():
    print("=" * 70)
    print("WEBSOCKET FOLLOW-UP SOURCE DIAGNOSTIC")
    print("=" * 70)
    for symptoms in ["fever, cough", "abdominal pain, nausea"]:
        print()
        sources = await run_session(symptoms)
        llm = sum(1 for s in sources if s == "llm")
        det = len(sources) - llm
        print(f"  SUMMARY: {llm} LLM / {det} deterministic of {len(sources)} questions")


if __name__ == "__main__":
    asyncio.run(main())
