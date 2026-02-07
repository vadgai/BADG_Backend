"""
Diagnosis Rule Engine with Disease Registry
Provides rule-based and AI-enhanced medical diagnosis capabilities.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global disease registry
DISEASE_REGISTRY: Dict[str, Dict[str, Any]] = {}

# Global disease profiles (processed for faster lookup)
DISEASE_PROFILES: List[Dict[str, Any]] = []


def load_diseases_from_folder(folder_path: Optional[str] = None) -> int:
    """
    Load all disease definitions from JSON files in the diseases folder.
    
    Args:
        folder_path: Optional path to diseases folder. Defaults to backend/diseases/
    
    Returns:
        Number of diseases loaded
    """
    global DISEASE_REGISTRY
    
    if folder_path is None:
        # Get the directory where this file is located
        current_dir = Path(__file__).parent
        folder_path = current_dir / "diseases"
    else:
        folder_path = Path(folder_path)
    
    if not folder_path.exists():
        logger.warning(f"Diseases folder not found: {folder_path}")
        return 0
    
    DISEASE_REGISTRY = {}
    loaded_count = 0
    
    # Load all JSON files matching the pattern D###_*.json
    for json_file in sorted(folder_path.glob("D*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                disease_data = json.load(f)
                
            # Validate required fields
            if not isinstance(disease_data, dict):
                logger.warning(f"Invalid format in {json_file.name}: expected dict")
                continue
            
            disease_id = disease_data.get("id") or json_file.stem
            disease_name = disease_data.get("name", "Unknown Disease")
            
            if disease_id in DISEASE_REGISTRY:
                logger.warning(f"Duplicate disease ID {disease_id} in {json_file.name}")
            
            DISEASE_REGISTRY[disease_id] = disease_data
            loaded_count += 1
            logger.debug(f"Loaded disease: {disease_id} - {disease_name}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON in {json_file.name}: {e}")
        except Exception as e:
            logger.error(f"Error loading {json_file.name}: {e}")
    
    logger.info(f"✅ Loaded {loaded_count} disease(s) from {folder_path}")
    return loaded_count


def build_disease_profiles() -> List[Dict[str, Any]]:
    """
    Build optimized disease profiles from the registry for faster matching.
    
    Returns:
        List of disease profiles with normalized symptom lists and metadata
    """
    global DISEASE_REGISTRY, DISEASE_PROFILES
    
    profiles = []
    
    for disease_id, disease_data in DISEASE_REGISTRY.items():
        profile = {
            "id": disease_id,
            "name": disease_data.get("name", "Unknown"),
            "organ_system": disease_data.get("organ_system", "General"),
            "symptoms": {
                "required": [s.lower().strip() for s in disease_data.get("symptoms", {}).get("required", [])],
                "common": [s.lower().strip() for s in disease_data.get("symptoms", {}).get("common", [])],
                "rare": [s.lower().strip() for s in disease_data.get("symptoms", {}).get("rare", [])]
            },
            "risk_factors": {
                "age_range": disease_data.get("risk_factors", {}).get("age_range", []),
                "gender": disease_data.get("risk_factors", {}).get("gender", []),
                "bmi_range": disease_data.get("risk_factors", {}).get("bmi_range", []),
                "other": disease_data.get("risk_factors", {}).get("other", [])
            },
            "urgency_indicators": [s.lower().strip() for s in disease_data.get("urgency_indicators", [])],
            "prevalence": disease_data.get("prevalence", "common"),  # common, uncommon, rare
            "diagnostic_criteria": disease_data.get("diagnostic_criteria", []),
            "raw_data": disease_data  # Keep original for reference
        }
        profiles.append(profile)
    
    DISEASE_PROFILES = profiles
    logger.info(f"✅ Built {len(profiles)} disease profile(s)")
    return profiles


def score_disease_match(
    disease_profile: Dict[str, Any],
    patient_symptoms: List[str],
    age: Optional[int] = None,
    gender: Optional[str] = None,
    weight: Optional[float] = None,
    height: Optional[float] = None,
    chat_history: Optional[str] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Score how well a disease profile matches a patient case.
    
    Args:
        disease_profile: Disease profile from build_disease_profiles()
        patient_symptoms: List of patient symptoms (normalized to lowercase)
        age: Patient age
        gender: Patient gender
        weight: Patient weight in kg
        height: Patient height in cm
        chat_history: Additional clinical history
    
    Returns:
        Tuple of (score: float, details: dict)
    """
    score = 0.0
    details = {
        "symptom_matches": {"required": 0, "common": 0, "rare": 0},
        "risk_factor_matches": 0,
        "urgency_match": False,
        "match_reasons": []
    }
    
    # Normalize patient symptoms
    patient_symptoms_lower = [s.lower().strip() for s in patient_symptoms]
    
    # Score symptom matches
    required_symptoms = disease_profile["symptoms"]["required"]
    common_symptoms = disease_profile["symptoms"]["common"]
    rare_symptoms = disease_profile["symptoms"]["rare"]
    
    # Check required symptoms (high weight)
    required_matches = sum(1 for s in required_symptoms if any(s in ps or ps in s for ps in patient_symptoms_lower))
    details["symptom_matches"]["required"] = required_matches
    if required_symptoms:
        required_ratio = required_matches / len(required_symptoms)
        score += required_ratio * 0.5  # Required symptoms are critical
    
    # Check common symptoms (medium weight)
    common_matches = sum(1 for s in common_symptoms if any(s in ps or ps in s for ps in patient_symptoms_lower))
    details["symptom_matches"]["common"] = common_matches
    if common_symptoms:
        common_ratio = common_matches / len(common_symptoms)
        score += common_ratio * 0.3
    
    # Check rare symptoms (low weight)
    rare_matches = sum(1 for s in rare_symptoms if any(s in ps or ps in s for ps in patient_symptoms_lower))
    details["symptom_matches"]["rare"] = rare_matches
    if rare_symptoms:
        rare_ratio = rare_matches / len(rare_symptoms)
        score += rare_ratio * 0.1
    
    # Score risk factors
    risk_factors = disease_profile["risk_factors"]
    risk_score = 0.0
    
    # Age matching
    if age is not None and risk_factors.get("age_range"):
        age_ranges = risk_factors["age_range"]
        for age_range in age_ranges:
            if isinstance(age_range, dict):
                min_age = age_range.get("min", 0)
                max_age = age_range.get("max", 150)
                if min_age <= age <= max_age:
                    risk_score += 0.15
                    details["match_reasons"].append(f"Age {age} matches risk range")
                    break
            elif isinstance(age_range, list) and len(age_range) == 2:
                if age_range[0] <= age <= age_range[1]:
                    risk_score += 0.15
                    details["match_reasons"].append(f"Age {age} matches risk range")
                    break
    
    # Gender matching
    if gender and risk_factors.get("gender"):
        gender_lower = gender.lower()
        if gender_lower in [g.lower() for g in risk_factors["gender"]]:
            risk_score += 0.1
            details["match_reasons"].append(f"Gender {gender} matches risk profile")
    
    # BMI matching disabled
    
    score += risk_score
    details["risk_factor_matches"] = risk_score
    
    # Check urgency indicators
    if disease_profile.get("urgency_indicators"):
        urgency_matches = sum(1 for ind in disease_profile["urgency_indicators"] 
                             if any(ind in ps or ps in ind for ps in patient_symptoms_lower))
        if urgency_matches > 0:
            details["urgency_match"] = True
            score += 0.1
    
    # Adjust for prevalence (common diseases get slight boost)
    if disease_profile.get("prevalence") == "common":
        score *= 1.1
    elif disease_profile.get("prevalence") == "rare":
        score *= 0.9
    
    # Normalize score to 0-1 range
    score = min(1.0, max(0.0, score))
    
    return score, details


def analyze_case(
    age: int,
    gender: str,
    symptoms: List[str],
    chat_history: str = "",
    weight: Optional[float] = None,
    height: Optional[float] = None
) -> Dict[str, Any]:
    """
    Analyze a patient case using the disease registry and return top diagnoses.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: List of symptoms
        chat_history: Clinical history from Q&A
        weight: Patient weight in kg (optional)
        height: Patient height in cm (optional)
    
    Returns:
        Dictionary with conditions and follow-up questions in the expected format
    """
    global DISEASE_PROFILES
    
    if not DISEASE_PROFILES:
        logger.warning("No disease profiles loaded. Call build_disease_profiles() first.")
        return {
            "conditions": [],
            "follow_up_questions": [
                "How long have you had these symptoms?",
                "Have you taken any medication?",
                "Any other symptoms you've noticed?"
            ]
        }
    
    # Score all diseases
    scored_diseases = []
    for profile in DISEASE_PROFILES:
        score, details = score_disease_match(
            profile,
            symptoms,
            age=age,
            gender=gender,
            weight=weight,
            height=height,
            chat_history=chat_history
        )
        
        if score > 0:  # Only include diseases with some match
            scored_diseases.append({
                "profile": profile,
                "score": score,
                "details": details
            })
    
    # Sort by score (highest first)
    scored_diseases.sort(key=lambda x: x["score"], reverse=True)
    
    # Get top 3
    top_diseases = scored_diseases[:3]
    
    # Build response in expected format
    conditions = []
    for disease_data in top_diseases:
        profile = disease_data["profile"]
        score = disease_data["score"]
        details = disease_data["details"]
        
        # Determine probability level
        if score >= 0.7:
            probability = "High"
        elif score >= 0.5:
            probability = "Moderate"
        else:
            probability = "Low"
        
        # Determine urgency
        urgency = "Monitor"
        if details.get("urgency_match"):
            urgency = "Emergency"
        elif score >= 0.6:
            urgency = "Routine"
        
        # Build reasoning
        reasoning_parts = []
        if details["symptom_matches"]["required"] > 0:
            reasoning_parts.append(f"Matches {details['symptom_matches']['required']} required symptom(s)")
        if details["symptom_matches"]["common"] > 0:
            reasoning_parts.append(f"Matches {details['symptom_matches']['common']} common symptom(s)")
        if details["risk_factor_matches"] > 0:
            reasoning_parts.append("Patient demographics match risk profile")
        
        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Possible differential based on symptom pattern."
        
        conditions.append({
            "name": profile["name"],
            "probability": probability,
            "reasoning": reasoning,
            "urgency": urgency
        })
    
    # Generate follow-up questions
    follow_up_questions = build_followup_questions(top_diseases, symptoms, chat_history)
    
    return {
        "conditions": conditions,
        "follow_up_questions": follow_up_questions
    }


def build_followup_questions(
    top_diseases: List[Dict[str, Any]],
    symptoms: List[str],
    chat_history: str
) -> List[str]:
    """
    Build relevant follow-up questions based on top disease matches.
    
    Args:
        top_diseases: List of top-scoring disease matches
        symptoms: Current symptoms
        chat_history: Existing clinical history
    
    Returns:
        List of follow-up questions
    """
    questions = []
    
    # Generic questions if no specific matches
    if not top_diseases:
        return [
            "How long have you had these symptoms?",
            "Have you taken any medication?",
            "Any other symptoms you've noticed?"
        ]
    
    # Build questions based on top disease
    top_disease = top_diseases[0]
    profile = top_disease["profile"]
    
    # Check for missing required symptoms
    required_symptoms = profile["symptoms"]["required"]
    patient_symptoms_lower = [s.lower().strip() for s in symptoms]
    
    missing_required = []
    for req_symptom in required_symptoms:
        if not any(req_symptom in ps or ps in req_symptom for ps in patient_symptoms_lower):
            missing_required.append(req_symptom)
    
    if missing_required:
        questions.append(f"Have you experienced {missing_required[0]}?")
    
    # Add temporal questions
    if "How long" not in chat_history and "duration" not in chat_history.lower():
        questions.append("How long have you been experiencing these symptoms?")
    
    # Add severity questions
    if not any(word in chat_history.lower() for word in ["severe", "mild", "moderate", "pain level"]):
        questions.append("On a scale of 1-10, how would you rate the severity of your symptoms?")
    
    # Add context-specific questions based on organ system
    organ_system = profile.get("organ_system", "").lower()
    if "gastrointestinal" in organ_system or "hepatobiliary" in organ_system:
        if not any(word in chat_history.lower() for word in ["appetite", "eating", "diet"]):
            questions.append("Have you noticed any changes in your appetite or eating habits?")
    elif "respiratory" in organ_system:
        if not any(word in chat_history.lower() for word in ["cough", "breathing", "shortness"]):
            questions.append("Have you experienced any difficulty breathing or coughing?")
    elif "cardiovascular" in organ_system:
        if not any(word in chat_history.lower() for word in ["chest", "heart", "palpitation"]):
            questions.append("Have you experienced any chest discomfort or heart-related symptoms?")
    
    # Ensure we have at least 3 questions
    while len(questions) < 3:
        questions.append("Any other symptoms or concerns you'd like to mention?")
    
    return questions[:3]  # Return top 3


def build_json_prompt(
    age: int,
    gender: str,
    symptoms: List[str],
    chat_history: str = "",
    weight: Optional[float] = None,
    height: Optional[float] = None,
    disease_context: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Build a JSON-formatted prompt for LLM enhancement of rule-based analysis.
    
    Args:
        age: Patient age
        gender: Patient gender
        symptoms: List of symptoms
        chat_history: Clinical history
        weight: Patient weight (optional)
        height: Patient height (optional)
        disease_context: Optional list of top disease matches from rule engine
    
    Returns:
        Formatted prompt string
    """
    formatted_symptoms = ", ".join(symptoms)
    
    # BMI calculation disabled
    bmi_text = ""
    
    # Add disease context if available
    disease_context_text = ""
    if disease_context:
        disease_context_text = "\n\n    RULE-BASED ANALYSIS CONTEXT:\n"
        disease_context_text += "    The following conditions were identified by rule-based matching:\n"
        for idx, disease in enumerate(disease_context[:3], 1):
            disease_context_text += f"    {idx}. {disease.get('name', 'Unknown')} (Match Score: {disease.get('score', 0):.2f})\n"
        disease_context_text += "\n    Use this context to refine and enhance your clinical reasoning."
    
    prompt = f"""
    You are an expert clinical diagnostician performing differential diagnosis analysis. Your task is to synthesize ALL available patient data into a coherent clinical picture and rank the most likely conditions.
    
    Patient Profile:
    - Age: {age} years (consider age-related disease susceptibility, physiological changes, and epidemiology)
    - Gender: {gender} (consider gender-specific conditions and hormonal factors)
    {bmi_text}
    
    Reported Symptoms: {formatted_symptoms}
    
    Detailed Clinical History (Q&A Responses):
    {chat_history}
    {disease_context_text}
    
    CLINICAL REASONING APPROACH:
    1. **Pattern Recognition**: Analyze symptom constellation - which symptoms cluster together in known disease patterns?
    2. **Temporal Analysis**: Consider onset (acute vs gradual), duration, progression, timing patterns
    3. **Severity Assessment**: Evaluate symptom intensity and functional impact
    4. **Risk Stratification**: Factor in age and gender
    5. **Differential Diagnosis**: Distinguish between competing diagnoses using discriminating clinical features
    6. **Likelihood Ranking**: Assign probability based on symptom match, prevalence, and patient-specific risk factors
    
    PROBABILITY ASSIGNMENT RULES:
    - **High**: ≥70% symptom match + strong supporting evidence from history + consistent with patient demographics
    - **Moderate**: 50-70% symptom match + some supporting evidence + plausible for patient profile
    - **Low**: <50% symptom match OR missing key features BUT still possible differential
    
    URGENCY CLASSIFICATION:
    - **Emergency**: Life-threatening symptoms, severe organ dysfunction, requires immediate medical attention
    - **Routine**: Stable symptoms, schedule appointment within 24-48 hours
    - **Monitor**: Mild symptoms, self-limiting conditions, observe and seek care if worsening
    
    TASK: Identify the TOP 3 most likely medical conditions based on comprehensive analysis of ALL available data.
    
    For each condition provide:
    1. **Name**: Specific disease/condition (use medical terminology but clear)
    2. **Probability**: High / Moderate / Low (based on clinical reasoning above)
    3. **Reasoning**: 2-3 sentences explaining WHY this diagnosis fits (cite specific symptoms, risk factors, clinical features)
    4. **Urgency**: Emergency / Routine / Monitor
    
    Also suggest 2-3 relevant follow-up questions that would help confirm or rule out the top diagnoses.
    
    RESPOND STRICTLY IN JSON FORMAT (no markdown, no extra text):
    {{
      "conditions": [
        {{"name": "...", "probability": "High/Moderate/Low", "reasoning": "Clinical reasoning with specific symptom references", "urgency": "Emergency/Routine/Monitor"}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}},
        {{"name": "...", "probability": "...", "reasoning": "...", "urgency": "..."}}
      ],
      "follow_up_questions": ["...", "...", "..."]
    }}
    """
    
    return prompt

