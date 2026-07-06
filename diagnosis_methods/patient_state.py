"""
Patient State Management for Method 2 (Hybrid State-Based Diagnosis)

This module manages the structured patient state JSON that replaces
full chat history in the hybrid diagnosis approach.
"""

import json
import logging
"""
Patient State Management for Method 2 (Hybrid State-Based Diagnosis)

This module manages the structured patient state JSON that replaces
full chat history in the hybrid diagnosis approach.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def _calculate_bmi(weight: Optional[float], height: Optional[float], gender: str) -> Dict[str, Any]:
    """
    Calculate BMI with fallbacks to Indian population averages if data is missing.
    Male: 170cm, 70kg | Female: 156cm, 60kg
    """
    # Fallbacks based on Indian population averages (ICMR/NIN)
    default_h = 170.0 if gender.lower() == "male" else 156.0
    default_w = 70.0 if gender.lower() == "male" else 60.0

    h = float(height) if height and float(height) > 0 else default_h
    w = float(weight) if weight and float(weight) > 0 else default_w

    # Handle height in meters (e.g. 1.7) vs cm (e.g. 170)
    if 0.5 <= h <= 2.5:
        h *= 100.0
    
    bmi = w / ((h / 100) ** 2)
    
    category = "Normal"
    if bmi < 18.5:
        category = "Underweight"
    elif bmi >= 30:
        category = "Obese"
    elif bmi >= 25:
        category = "Overweight"
    
    return {
        "value": round(bmi, 1),
        "category": category,
        "height_cm": round(h, 1),
        "weight_kg": round(w, 1),
        "is_estimated": not (weight and height)
    }


def initialize_patient_state(
    age: int, 
    gender: str, 
    symptoms: List[str],
    weight: Optional[float] = None,
    height: Optional[float] = None
) -> Dict[str, Any]:
    """
    Initialize a new patient state JSON structure.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: Initial symptoms list
        weight: Patient weight in kg
        height: Patient height in cm or meters
        
    Returns:
        Initialized patient state dictionary
    """
    return {
        "demographics": {
            "age": age,
            "gender": gender.lower(),
            "weight": weight,
            "height": height,
            "bmi": _calculate_bmi(weight, height, gender)
        },
        "chief_complaint": ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms),
        "identified_symptoms": symptoms if isinstance(symptoms, list) else [str(symptoms)],
        "negatives": [],  # Symptoms/conditions ruled out
        "suspected_conditions": [],  # List of {name, probability} (deprecated, use differential_diagnosis)
        "differential_diagnosis": [],  # List of {name, confidence, reasoning} - Top 3 suspects ranked by likelihood
        "differentiator_symptom": "",  # The symptom that differentiates Suspect #1 from Suspect #2
        "running_summary": "",  # Pre-calculated summary for fast report generation
        "red_flags": [],  # Critical danger signs extracted during follow-up
        "symptom_state": {
            "current_symptoms": symptoms if isinstance(symptoms, list) else [str(symptoms)],
            "modifiers": [],
            "modifier_map": {
                "duration": "",
                "onset": "",
                "location": "",
                "quality": "",
                "severity": "",
                "aggravating_factors": [],
                "relieving_factors": [],
                "associated_symptoms": [],
            },
            "red_flags": [],
            "questions_asked": [],
        },
        "diagnostic_trace": [],
        "diagnostic_counters": {
            "repeated_question_prevention_hits": 0,
            "generic_question_rejection_hits": 0,
            "deterministic_fallback_frequency": 0,
            "out_of_pool_llm_suggestion_rejections": 0,
        },
        "confidence_score": 0.0,
        "turn_count": 0,
        "created_at": datetime.utcnow().isoformat(),
        "last_updated": datetime.utcnow().isoformat()
    }


def update_patient_state(
    state: Dict[str, Any],
    question: str,
    answer: str,
    ai_analysis: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Update patient state after a Q&A turn.
    
    Args:
        state: Current patient state
        question: The question that was asked
        answer: The patient's answer
        ai_analysis: Optional AI analysis of the answer (extracted symptoms, conditions, etc.)
        
    Returns:
        Updated patient state
    """
    # Increment turn count
    state["turn_count"] = state.get("turn_count", 0) + 1
    state["last_updated"] = datetime.utcnow().isoformat()
    
    # Track conversation history for LLM context
    history = state.setdefault("chat_history", [])
    if question or answer:
        history.append({"bot": question, "user": answer})
    
    # If AI analysis is provided, use it to update state
    if ai_analysis:
        from symptom_extractor_v5 import humanize_internal_token

        # Update identified symptoms
        if "identified_symptoms" in ai_analysis:
            new_symptoms = ai_analysis["identified_symptoms"]
            existing = set(state.get("identified_symptoms", []))
            for symptom in new_symptoms:
                symptom = humanize_internal_token(symptom)
                if symptom and symptom not in existing:
                    state["identified_symptoms"].append(symptom)
                    existing.add(symptom)

        # Update negatives (ruled out symptoms/conditions)
        if "negatives" in ai_analysis:
            new_negatives = ai_analysis["negatives"]
            existing_negatives = set(state.get("negatives", []))
            for negative in new_negatives:
                negative = humanize_internal_token(negative)
                if negative and negative not in existing_negatives:
                    state["negatives"].append(negative)
                    existing_negatives.add(negative)
        
        # Update suspected conditions (deprecated, kept for compatibility)
        if "suspected_conditions" in ai_analysis:
            # Merge with existing conditions, updating probabilities
            existing_conditions = {c["name"]: c for c in state.get("suspected_conditions", [])}
            
            for condition in ai_analysis["suspected_conditions"]:
                name = condition.get("name")
                if name:
                    if name in existing_conditions:
                        # Update existing condition probability if new one is higher
                        existing_prob = existing_conditions[name].get("probability", "Low")
                        new_prob = condition.get("probability", "Low")
                        prob_order = {"Low": 0, "Medium": 1, "High": 2}
                        if prob_order.get(new_prob, 0) > prob_order.get(existing_prob, 0):
                            existing_conditions[name]["probability"] = new_prob
                    else:
                        # Add new condition
                        existing_conditions[name] = {
                            "name": name,
                            "probability": condition.get("probability", "Low")
                        }
            
            state["suspected_conditions"] = list(existing_conditions.values())
        
        # Update differential diagnosis (new method - pure LLM reasoning)
        if "differential_diagnosis" in ai_analysis:
            # Replace with new differential diagnosis (Top 3 suspects from LLM)
            differential = ai_analysis["differential_diagnosis"]
            if isinstance(differential, list) and len(differential) > 0:
                # Ensure we have exactly Top 3
                state["differential_diagnosis"] = differential[:3]
                logger.debug(f"Updated differential diagnosis with {len(differential[:3])} suspects")
        
        # Update differentiator symptom
        if "differentiator_symptom" in ai_analysis:
            differentiator = ai_analysis.get("differentiator_symptom", "")
            if differentiator:
                state["differentiator_symptom"] = differentiator
                logger.debug(f"Updated differentiator symptom: {differentiator[:50]}...")
        
        # Update running summary for fast report generation
        if "running_summary" in ai_analysis:
            summary = ai_analysis.get("running_summary", "")
            if summary:
                state["running_summary"] = summary

        if "modifier_map" in ai_analysis and isinstance(ai_analysis.get("modifier_map"), dict):
            symptom_state_local = state.get("symptom_state") if isinstance(state.get("symptom_state"), dict) else {}
            existing_map = symptom_state_local.get("modifier_map") if isinstance(symptom_state_local.get("modifier_map"), dict) else {}
            merged_map = dict(existing_map)
            for key, value in ai_analysis.get("modifier_map", {}).items():
                if isinstance(value, list):
                    prev = merged_map.get(key, [])
                    if not isinstance(prev, list):
                        prev = []
                    merged_map[key] = list(dict.fromkeys([*prev, *value]))
                elif str(value).strip():
                    merged_map[key] = value
            symptom_state_local["modifier_map"] = merged_map
            state["symptom_state"] = symptom_state_local
        
        # Update confidence score
        if "confidence_score" in ai_analysis:
            state["confidence_score"] = ai_analysis.get("confidence_score", state.get("confidence_score", 0.0))

    # Keep structured symptom_state synchronized for token-efficient prompting.
    symptom_state = state.get("symptom_state")
    if not isinstance(symptom_state, dict):
        symptom_state = {
            "current_symptoms": [],
            "modifiers": [],
            "modifier_map": {
                "duration": "",
                "onset": "",
                "location": "",
                "quality": "",
                "severity": "",
                "aggravating_factors": [],
                "relieving_factors": [],
                "associated_symptoms": [],
            },
            "red_flags": [],
            "questions_asked": [],
        }
    symptom_state["current_symptoms"] = list(state.get("identified_symptoms", []))
    symptom_state["red_flags"] = list(state.get("red_flags", []))
    symptom_state.setdefault("modifiers", [])
    symptom_state.setdefault(
        "modifier_map",
        {
            "duration": "",
            "onset": "",
            "location": "",
            "quality": "",
            "severity": "",
            "aggravating_factors": [],
            "relieving_factors": [],
            "associated_symptoms": [],
        },
    )
    symptom_state.setdefault("questions_asked", [])
    state["symptom_state"] = symptom_state
    state.setdefault("diagnostic_trace", [])
    state.setdefault(
        "diagnostic_counters",
        {
            "repeated_question_prevention_hits": 0,
            "generic_question_rejection_hits": 0,
            "deterministic_fallback_frequency": 0,
            "out_of_pool_llm_suggestion_rejections": 0,
        },
    )
    
    return state


def state_to_prompt_string(state: Dict[str, Any]) -> str:
    """
    Convert patient state to a formatted string for AI prompts.
    
    Args:
        state: Patient state dictionary
        
    Returns:
        Formatted string representation
    """
    lines = []
    lines.append("PATIENT STATE:")
    lines.append(f"Age: {state['demographics']['age']} years")
    lines.append(f"Gender: {state['demographics']['gender']}")
    
    bmi_data = state['demographics'].get('bmi', {})
    if bmi_data:
        lines.append(f"BMI: {bmi_data.get('value')} ({bmi_data.get('category')})")
        if bmi_data.get('is_estimated'):
            lines.append("  (Note: BMI estimated using Indian population averages)")
            
    lines.append(f"Chief Complaint: {state.get('chief_complaint', 'N/A')}")

    lines.append("")
    lines.append("Identified Symptoms:")
    for symptom in state.get("identified_symptoms", []):
        lines.append(f"  - {symptom}")

    symptom_state = state.get("symptom_state") if isinstance(state.get("symptom_state"), dict) else {}
    modifier_map = symptom_state.get("modifier_map") if isinstance(symptom_state.get("modifier_map"), dict) else {}
    if modifier_map:
        lines.append("")
        lines.append("Modifier Map:")
        for key, value in modifier_map.items():
            if isinstance(value, list):
                if value:
                    lines.append(f"  - {key}: {', '.join(str(v) for v in value)}")
            elif str(value).strip():
                lines.append(f"  - {key}: {value}")
    
    if state.get("negatives"):
        lines.append("")
        lines.append("Ruled Out (Negatives):")
        for negative in state.get("negatives", []):
            lines.append(f"  - {negative}")
    
    if state.get("suspected_conditions"):
        lines.append("")
        lines.append("Suspected Conditions (Legacy):")
        for condition in state.get("suspected_conditions", []):
            prob = condition.get("probability", "Unknown")
            lines.append(f"  - {condition.get('name', 'Unknown')} (Probability: {prob})")
    
    if state.get("differential_diagnosis"):
        lines.append("")
        lines.append("Differential Diagnosis (Top 3 Suspects):")
        for idx, condition in enumerate(state.get("differential_diagnosis", []), 1):
            name = condition.get("name", "Unknown")
            confidence = condition.get("confidence", "Unknown")
            reasoning = condition.get("reasoning", "")
            lines.append(f"  Suspect #{idx}: {name} (Confidence: {confidence})")
            if reasoning:
                lines.append(f"     Reasoning: {reasoning[:150]}...")
    
    if state.get("differentiator_symptom"):
        lines.append("")
        lines.append(f"Differentiator Symptom: {state.get('differentiator_symptom')}")
        lines.append("  (The symptom that differentiates Suspect #1 from Suspect #2)")
    
    if state.get("running_summary"):
        lines.append("")
        lines.append("Running Summary (for fast report generation):")
        lines.append(f"  {state.get('running_summary')[:200]}...")
    
    lines.append("")
    lines.append(f"Confidence Score: {state.get('confidence_score', 0.0):.2f}")
    lines.append(f"Turn Count: {state.get('turn_count', 0)}")
    
    return "\n".join(lines)


def state_to_json_string(state: Dict[str, Any]) -> str:
    """
    Convert patient state to JSON string for storage/transmission.
    
    Args:
        state: Patient state dictionary
        
    Returns:
        JSON string
    """
    return json.dumps(state, indent=2, ensure_ascii=False)


