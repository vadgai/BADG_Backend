"""
Agent 3 — MCQ Writer (LLM).

Builds the follow-up generation prompt with full asked-question context.
"""

from typing import Dict, List

from followup.validators.repetition import extract_asked_questions


def build_followup_writer_prompt(patient_state: Dict, strategy_hint: str = "") -> str:
    """Build LLM prompt for next follow-up MCQ."""
    from diagnosis_methods.state_followup import _format_chat_history

    symptom_state = (
        patient_state.get("symptom_state")
        if isinstance(patient_state.get("symptom_state"), dict)
        else {}
    )
    demographics = (
        patient_state.get("demographics")
        if isinstance(patient_state.get("demographics"), dict)
        else {}
    )
    turn_count = int(patient_state.get("turn_count", 0) or 0)

    age = demographics.get("age", "Unknown")
    gender = demographics.get("gender", "Unknown")
    positives = (
        symptom_state.get("current_symptoms")
        if isinstance(symptom_state.get("current_symptoms"), list)
        else patient_state.get("identified_symptoms", [])
    )
    negatives = patient_state.get("negatives") if isinstance(patient_state.get("negatives"), list) else []
    red_flags = (
        symptom_state.get("red_flags")
        if isinstance(symptom_state.get("red_flags"), list)
        else patient_state.get("red_flags", [])
    )

    positives_text = ", ".join(str(s).strip() for s in positives if str(s).strip()) or "None"
    negatives_text = ", ".join(str(s).strip() for s in negatives if str(s).strip()) or "None"
    red_flags_text = ", ".join(str(s).strip() for s in red_flags if str(s).strip()) or "None"
    full_history_text = _format_chat_history(patient_state)

    asked_all = extract_asked_questions(patient_state)
    previously_asked_titles = "\n".join(f"- {q}" for q in asked_all) or "None"

    feature_ids = symptom_state.get("feature_ids_asked") or []
    features_text = ", ".join(str(f) for f in feature_ids) or "None"

    chief_complaint = str(patient_state.get("chief_complaint", "")).strip() or positives_text

    bmi_data = demographics.get("bmi", {})
    bmi_text = ""
    if bmi_data:
        bmi_text = f" | BMI: {bmi_data.get('value')} ({bmi_data.get('category')})"

    differential = (
        patient_state.get("differential_diagnosis")
        if isinstance(patient_state.get("differential_diagnosis"), list)
        else []
    )
    diff_text = "Not yet established."
    if differential:
        diff_lines = []
        for idx, item in enumerate(differential[:3], 1):
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                confidence = str(item.get("confidence", "")).strip()
                reasoning = str(item.get("reasoning", "")).strip()
                if name:
                    diff_lines.append(f"  #{idx}: {name} ({confidence}) — {reasoning[:80]}")
        if diff_lines:
            diff_text = "\n".join(diff_lines)

    differentiator = str(patient_state.get("differentiator_symptom", "")).strip()
    differentiator_text = f"\n- Key differentiator to confirm: {differentiator}" if differentiator else ""

    running_summary = str(patient_state.get("running_summary", "")).strip()
    summary_text = f"\n- Clinical summary so far: {running_summary[:200]}" if running_summary else ""

    strategy_line = f"\n- Strategist hint: {strategy_hint}" if strategy_hint else ""

    return f"""Clinical diagnostician. Ask the SINGLE highest-yield next question to separate the top differential diagnoses.

PATIENT: {age}/{gender}{bmi_text} | Chief: {chief_complaint}
+Confirmed: {positives_text}
-Ruled out: {negatives_text}
Red flags: {red_flags_text}
Turn {turn_count + 1}/12{summary_text}{differentiator_text}{strategy_line}

DIFFERENTIAL (current top suspects):
{diff_text}

ALREADY ASKED — never repeat or paraphrase (text or clinical dimension):
{previously_asked_titles}

CLINICAL DIMENSIONS ALREADY COVERED (do not re-ask):
{features_text}

CONVERSATION:
{full_history_text}

SELECT NEXT QUESTION:
1. Target the one feature that best splits Suspect #1 vs #2. Priority: pathognomonic > red-flag > severity > timing/onset > location.
2. Must add NEW info not in confirmed/ruled-out lists and not overlapping asked questions or feature dimensions.
3. Stay within the most likely body system unless a red flag forces otherwise.
4. 5-10 plain-English words. A-D clinically distinct; E = "Not sure / None of these".

EARLY STOP: if turn >= 12, OR top suspect is High-confidence with key differentiators answered → return {{"ready_for_diagnosis": true}}

Return STRICT JSON only:
{{"Question":"...","A":"...","B":"...","C":"...","D":"...","E":"Not sure / None of these","feature_id":"snake_case_dimension"}}
"""
