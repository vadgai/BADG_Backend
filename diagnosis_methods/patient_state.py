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


def initialize_patient_state(age: int, gender: str, symptoms: List[str]) -> Dict[str, Any]:
    """
    Initialize a new patient state JSON structure.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: Initial symptoms list
        
    Returns:
        Initialized patient state dictionary
    """
    return {
        "demographics": {
            "age": age,
            "gender": gender.lower()
        },
        "chief_complaint": ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms),
        "identified_symptoms": symptoms if isinstance(symptoms, list) else [str(symptoms)],
        "negatives": [],  # Symptoms/conditions ruled out
        "suspected_conditions": [],  # List of {name, probability} (deprecated, use differential_diagnosis)
        "differential_diagnosis": [],  # List of {name, confidence, reasoning} - Top 3 suspects ranked by likelihood
        "differentiator_symptom": "",  # The symptom that differentiates Suspect #1 from Suspect #2
        "running_summary": "",  # Pre-calculated summary for fast report generation
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
    
    # If AI analysis is provided, use it to update state
    if ai_analysis:
        # Update identified symptoms
        if "identified_symptoms" in ai_analysis:
            new_symptoms = ai_analysis["identified_symptoms"]
            existing = set(state.get("identified_symptoms", []))
            for symptom in new_symptoms:
                if symptom not in existing:
                    state["identified_symptoms"].append(symptom)
        
        # Update negatives (ruled out symptoms/conditions)
        if "negatives" in ai_analysis:
            new_negatives = ai_analysis["negatives"]
            existing_negatives = set(state.get("negatives", []))
            for negative in new_negatives:
                if negative not in existing_negatives:
                    state["negatives"].append(negative)
        
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
        
        # Update confidence score
        if "confidence_score" in ai_analysis:
            state["confidence_score"] = ai_analysis.get("confidence_score", state.get("confidence_score", 0.0))
    
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
    lines.append(f"Chief Complaint: {state.get('chief_complaint', 'N/A')}")
    lines.append("")
    lines.append("Identified Symptoms:")
    for symptom in state.get("identified_symptoms", []):
        lines.append(f"  - {symptom}")
    
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


