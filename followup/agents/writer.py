"""
Agent 3 — MCQ Writer (LLM).

Builds the follow-up generation prompt with full asked-question context.
"""

from typing import Dict, List

from followup.constants import (
    FOLLOWUP_DIMENSIONS,
    MAX_FOLLOWUP_QUESTIONS,
    MIN_FOLLOWUP_QUESTIONS,
)


def build_followup_writer_prompt(patient_state: Dict, strategy_hint: str = "") -> str:
    """Build LLM prompt for next follow-up MCQ."""


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

    # Compact repetition control: send remaining unasked dimensions, not prior text.
    feature_ids = symptom_state.get("feature_ids_asked") or []
    covered = {str(f).strip().lower() for f in feature_ids if str(f).strip()}
    covered_text = ", ".join(sorted(covered)) or "none"
    remaining = [d for d in FOLLOWUP_DIMENSIONS if d not in covered]
    remaining_text = ", ".join(remaining) or "any unasked clinical dimension"

    # Prefer a short information-gain-ranked dimension list over the full
    # catalogue — the model picks from targeted, differential-splitting axes
    # instead of inventing generic screening questions.
    try:
        from followup.information_gain import rank_candidate_findings
        eig_ranked = rank_candidate_findings(patient_state, top_k=6, limit=5)
        eig_findings = (eig_ranked or {}).get("findings") or []
        if eig_findings:
            remaining_text = ", ".join(
                f"{f['dimension']} (e.g. {f['term']})" for f in eig_findings[:5]
            ) + " — ranked by information gain; prefer the first that fits"
    except Exception:
        pass

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

    return f"""Clinical diagnostician. Ask the SINGLE highest-yield MCQ to separate the top differentials, like an experienced doctor. JSON only.

PATIENT {age}/{gender}{bmi_text} | Chief: {chief_complaint}
+Confirmed: {positives_text}
-Ruled out: {negatives_text}
Red flags: {red_flags_text}
Turn {turn_count + 1}/{MAX_FOLLOWUP_QUESTIONS}{summary_text}{differentiator_text}{strategy_line}
Differential: {diff_text}

- feature_id = ONE unused dimension from: {remaining_text}
- Already covered, never re-ask: {covered_text}
- Probe EXACTLY ONE dimension: A-D are mutually-exclusive ANSWERS to that single question (levels/variants), NOT a list of different symptoms — never bundle multiple topics. E = "Not sure / None of these".
- Split Suspect #1 vs #2. Prefer still-missing high-yield axes first (duration/onset, red-flag, severity). Use age/sex for demographic-specific dimensions. Stay in the most likely body system unless a red flag forces otherwise. 5-10 words.
- Plain language for a patient with no medical background: everyday words only, never clinical/technical terms (say "trouble breathing" not "dyspnea", "throwing up" not "emesis", "coughing up blood" not "hemoptysis"). Question: 5-10 words. Each option A-D: a short, concrete phrase, 2-6 words.

EARLY STOP: only if turn >= {MAX_FOLLOWUP_QUESTIONS}, OR (turn >= {MIN_FOLLOWUP_QUESTIONS} AND top suspect is High-confidence with key differentiators answered) → return {{"ready_for_diagnosis": true}}. NEVER stop before turn {MIN_FOLLOWUP_QUESTIONS}.

Return JSON only:
{{"Question":"...","A":"...","B":"...","C":"...","D":"...","E":"Not sure / None of these","feature_id":"<one_unused_dimension>"}}
"""
