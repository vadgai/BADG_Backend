"""
Report Validation Layer - Ensures all required fields are present and valid.

This module provides comprehensive validation for medical reports to ensure
data integrity and completeness before sending to frontend.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


def validate_report_structure(report: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Comprehensive validation of report structure and fields.
    
    Args:
        report: The report dictionary to validate
        
    Returns:
        Tuple of (is_valid: bool, missing_fields: List[str], validated_report: Dict)
        - is_valid: True if report passes all validation checks
        - missing_fields: List of missing or invalid fields
        - validated_report: Report with any missing critical fields added/fixed
    """
    if not isinstance(report, dict):
        return False, ["Report must be a dictionary"], {}
    
    validated_report = report.copy()
    missing_fields = []
    warnings = []
    
    # ========== TOP-LEVEL REQUIRED FIELDS ==========
    required_top_level = {
        "PatientInfo": dict,
        "Recommendation": str,
        "Urgency": str,
        "ReasonForConsultation": str,
        "MainSymptoms": list,
        "NextDiagnosticSteps": list,  # Required for professional B2B mode
        "TopDiseaseMatches": list,
    }
    
    # ActionableOrders is optional but recommended for B2B mode
    if "ActionableOrders" not in validated_report and "InteractiveCTAs" not in validated_report:
        warnings.append("ActionableOrders or InteractiveCTAs missing (recommended for B2B mode)")
    
    # Validate each required top-level field
    for field, expected_type in required_top_level.items():
        if field not in validated_report:
            missing_fields.append(f"Missing required field: {field}")
            # Add default values for critical fields
            if field == "PatientInfo":
                validated_report[field] = {"Age": "Unknown", "Gender": "Unknown"}
            elif field == "Recommendation":
                validated_report[field] = "Please consult a healthcare professional."
            elif field == "Urgency":
                validated_report[field] = "Moderate"
            elif field == "ReasonForConsultation":
                validated_report[field] = "Patient consultation"
            elif field == "MainSymptoms":
                validated_report[field] = []
            elif field == "NextDiagnosticSteps":
                validated_report[field] = ["Further diagnostic tests may be required based on clinical assessment."]
            elif field == "TopDiseaseMatches":
                validated_report[field] = []
        else:
            # Type validation
            if not isinstance(validated_report[field], expected_type):
                missing_fields.append(f"Invalid type for {field}: expected {expected_type.__name__}, got {type(validated_report[field]).__name__}")
    
    # ========== PATIENTINFO VALIDATION ==========
    if "PatientInfo" in validated_report:
        patient_info = validated_report["PatientInfo"]
        if not isinstance(patient_info, dict):
            patient_info = {}
            validated_report["PatientInfo"] = patient_info
        
        if "Age" not in patient_info:
            patient_info["Age"] = "Unknown"
            warnings.append("PatientInfo.Age missing, set to default")
        if "Gender" not in patient_info:
            patient_info["Gender"] = "Unknown"
            warnings.append("PatientInfo.Gender missing, set to default")
    
    # ========== URGENCY VALIDATION ==========
    if "Urgency" in validated_report:
        valid_urgency = ["Critical", "High", "Moderate", "Routine", "Emergency"]
        urgency = str(validated_report["Urgency"]).strip()
        if urgency not in valid_urgency:
            warnings.append(f"Invalid urgency value: {urgency}, defaulting to 'Moderate'")
            validated_report["Urgency"] = "Moderate"
        else:
            validated_report["Urgency"] = urgency
    
    # ========== MAINSYMPTOMS VALIDATION ==========
    if "MainSymptoms" in validated_report:
        if not isinstance(validated_report["MainSymptoms"], list):
            validated_report["MainSymptoms"] = []
            warnings.append("MainSymptoms must be a list, converted to empty list")
        else:
            # Ensure all symptoms are strings
            validated_report["MainSymptoms"] = [str(s) for s in validated_report["MainSymptoms"] if s]
    
    # ========== NEXTDIAGNOSTICSTEPS VALIDATION ==========
    if "NextDiagnosticSteps" in validated_report:
        if not isinstance(validated_report["NextDiagnosticSteps"], list):
            validated_report["NextDiagnosticSteps"] = ["Further diagnostic tests may be required based on clinical assessment."]
            warnings.append("NextDiagnosticSteps must be a list, converted to default")
        else:
            # Ensure all steps are strings
            validated_report["NextDiagnosticSteps"] = [str(s) for s in validated_report["NextDiagnosticSteps"] if s]
            if len(validated_report["NextDiagnosticSteps"]) == 0:
                validated_report["NextDiagnosticSteps"] = ["Further diagnostic tests may be required based on clinical assessment."]
    
    # ========== TOPDISEASEMATCHES VALIDATION ==========
    if "TopDiseaseMatches" in validated_report:
        disease_matches = validated_report["TopDiseaseMatches"]
        if not isinstance(disease_matches, list):
            missing_fields.append("TopDiseaseMatches must be a list")
            validated_report["TopDiseaseMatches"] = []
        elif len(disease_matches) == 0:
            missing_fields.append("TopDiseaseMatches is empty (must have at least 1 disease)")
            warnings.append("CRITICAL: No diseases in TopDiseaseMatches")
        else:
            # Validate each disease structure
            validated_diseases = []
            for idx, disease in enumerate(disease_matches):
                if not isinstance(disease, dict):
                    warnings.append(f"Disease {idx+1} is not a dictionary, skipping")
                    continue
                
                # Find disease key (Disease1, Disease2, etc.)
                disease_keys = [k for k in disease.keys() if k.startswith("Disease")]
                if not disease_keys:
                    warnings.append(f"Disease {idx+1} missing 'DiseaseN' key, skipping")
                    continue
                
                disease_key = disease_keys[0]
                disease_data = disease[disease_key]
                
                if not isinstance(disease_data, dict):
                    warnings.append(f"Disease {idx+1}.{disease_key} is not a dictionary, skipping")
                    continue
                
                # Validate disease fields
                num = disease_key.replace("Disease", "")
                required_disease_fields = {
                    f"Name{num}": str,
                    f"MatchLevel{num}": str,
                    f"PreHospitalCare{num}": list,
                    f"SymptomsToWatch{num}": list,
                    f"SelfCare{num}": list,
                    f"MedicationSuggestion{num}": list,
                }
                
                # New fields for B2B mode (optional but recommended)
                optional_b2b_fields = {
                    f"ClinicalEvidence{num}": list,
                    f"Contradictions{num}": list,
                }
                
                disease_valid = True
                for field, expected_type in required_disease_fields.items():
                    if field not in disease_data:
                        # Try without number suffix
                        alt_field = field.replace(num, "")
                        if alt_field in disease_data:
                            # Normalize by adding number suffix
                            disease_data[field] = disease_data.pop(alt_field)
                        else:
                            missing_fields.append(f"TopDiseaseMatches[{idx}].{disease_key}.{field} missing")
                            disease_valid = False
                            # Add defaults for critical fields
                            if field.endswith("Name"):
                                disease_data[field] = "Unknown Condition"
                            elif field.endswith("MatchLevel"):
                                disease_data[field] = "Moderate"
                            elif field.endswith(("Care", "Watch", "Suggestion")):
                                disease_data[field] = []
                
                # Validate MatchLevel value
                match_level_key = f"MatchLevel{num}"
                if match_level_key in disease_data:
                    match_level = str(disease_data[match_level_key]).strip()
                    valid_levels = ["High", "Moderate", "Low"]
                    if match_level not in valid_levels:
                        warnings.append(f"Disease {idx+1} has invalid MatchLevel: {match_level}, defaulting to 'Moderate'")
                        disease_data[match_level_key] = "Moderate"
                
                # Validate list fields are actually lists
                for field in [f"PreHospitalCare{num}", f"SymptomsToWatch{num}", f"SelfCare{num}", f"MedicationSuggestion{num}"]:
                    if field in disease_data and not isinstance(disease_data[field], list):
                        disease_data[field] = [str(disease_data[field])] if disease_data[field] else []
                        warnings.append(f"Disease {idx+1}.{field} was not a list, converted")
                
                if disease_valid or idx == 0:  # Always include first disease even if incomplete
                    validated_diseases.append(disease)
            
            validated_report["TopDiseaseMatches"] = validated_diseases
            
            # Ensure at least one disease exists
            if len(validated_diseases) == 0:
                missing_fields.append("No valid diseases found in TopDiseaseMatches after validation")
    
    # ========== ACTIONABLEORDERS VALIDATION (B2B Mode) ==========
    if "ActionableOrders" in validated_report:
        orders = validated_report["ActionableOrders"]
        if not isinstance(orders, dict):
            warnings.append("ActionableOrders must be a dictionary, removing invalid structure")
            validated_report.pop("ActionableOrders")
        else:
            # Validate OrderLabImaging
            if "OrderLabImaging" in orders and isinstance(orders["OrderLabImaging"], dict):
                required_order_fields = ["testName", "testAbbreviation", "buttonText"]
                for field in required_order_fields:
                    if field not in orders["OrderLabImaging"]:
                        orders["OrderLabImaging"][field] = ""
                        warnings.append(f"ActionableOrders.OrderLabImaging.{field} missing")
            
            # Validate SpecialistReferral
            if "SpecialistReferral" in orders and isinstance(orders["SpecialistReferral"], dict):
                required_specialist_fields = ["specialistType", "buttonText"]
                for field in required_specialist_fields:
                    if field not in orders["SpecialistReferral"]:
                        orders["SpecialistReferral"][field] = ""
                        warnings.append(f"ActionableOrders.SpecialistReferral.{field} missing")
    
    # Log warnings
    if warnings:
        for warning in warnings:
            logger.warning(f"⚠️ Report validation warning: {warning}")
    
    # Determine if report is valid (critical fields must be present and valid)
    critical_fields_present = (
        "PatientInfo" in validated_report and isinstance(validated_report["PatientInfo"], dict) and
        "Recommendation" in validated_report and isinstance(validated_report["Recommendation"], str) and
        "Urgency" in validated_report and isinstance(validated_report["Urgency"], str) and
        "MainSymptoms" in validated_report and isinstance(validated_report["MainSymptoms"], list) and
        "NextDiagnosticSteps" in validated_report and isinstance(validated_report["NextDiagnosticSteps"], list) and
        "TopDiseaseMatches" in validated_report and isinstance(validated_report["TopDiseaseMatches"], list)
    )
    
    has_diseases = len(validated_report.get("TopDiseaseMatches", [])) > 0
    
    is_valid = critical_fields_present and has_diseases
    
    if missing_fields:
        logger.warning(f"⚠️ Report validation found {len(missing_fields)} missing/invalid fields: {missing_fields}")
    
    return is_valid, missing_fields, validated_report


def ensure_report_completeness(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure report has all required fields, adding defaults for missing ones.
    This is a non-strict validator that fixes missing fields instead of failing.
    
    Args:
        report: Report dictionary to validate and fix
        
    Returns:
        Validated and completed report dictionary
    """
    is_valid, missing_fields, validated_report = validate_report_structure(report)
    
    # Always return a usable report, even if some fields are defaults
    return validated_report
