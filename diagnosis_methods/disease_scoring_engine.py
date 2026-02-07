"""
Disease Scoring Engine for Method 2

This module loads disease JSON files and calculates scores based on patient symptoms,
exclude symptoms, and age ranges. Returns Top 5 highest-scoring diseases.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class DiseaseScoringEngine:
    """
    Engine that loads disease JSON files and calculates scores based on patient symptoms.
    """
    
    def __init__(self, diseases_folder: Optional[str] = None):
        """
        Initialize the Disease Scoring Engine.
        
        Args:
            diseases_folder: Path to folder containing disease JSON files.
                           Defaults to Backend/diseases relative to this file.
        """
        if diseases_folder is None:
            # Default to Backend/diseases relative to this file
            current_dir = Path(__file__).parent
            diseases_folder = current_dir.parent / "diseases"
        
        self.diseases_folder = Path(diseases_folder)
        self.diseases: List[Dict] = []
        self._load_diseases()
    
    def _load_diseases(self) -> None:
        """Load all disease JSON files from the diseases folder."""
        if not self.diseases_folder.exists():
            logger.error(f"Diseases folder not found: {self.diseases_folder}")
            return
        
        json_files = list(self.diseases_folder.glob("*.json"))
        logger.info(f"Loading {len(json_files)} disease JSON files from {self.diseases_folder}")
        
        loaded_count = 0
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    disease_data = json.load(f)
                    if disease_data:  # Skip empty files
                        self.diseases.append(disease_data)
                        loaded_count += 1
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON file {json_file.name}: {e}")
            except Exception as e:
                logger.warning(f"Error loading {json_file.name}: {e}")
        
        logger.info(f"Successfully loaded {loaded_count} disease files")
    
    def _normalize_symptom(self, symptom: str) -> str:
        """
        Normalize symptom string for comparison (lowercase, strip whitespace).
        
        Args:
            symptom: Symptom string to normalize
            
        Returns:
            Normalized symptom string
        """
        return symptom.lower().strip()
    
    def _symptom_matches(self, patient_symptom: str, disease_symptom: str) -> bool:
        """
        Check if patient symptom matches disease symptom (fuzzy matching).
        
        Args:
            patient_symptom: Symptom from patient
            disease_symptom: Symptom from disease definition
            
        Returns:
            True if symptoms match
        """
        patient_norm = self._normalize_symptom(patient_symptom)
        disease_norm = self._normalize_symptom(disease_symptom)
        
        # Exact match
        if patient_norm == disease_norm:
            return True
        
        # Substring match (patient symptom contains disease symptom or vice versa)
        if patient_norm in disease_norm or disease_norm in patient_norm:
            return True
        
        # Word-level matching (check if key words match)
        patient_words = set(patient_norm.split())
        disease_words = set(disease_norm.split())
        
        # If significant overlap in words, consider it a match
        if len(patient_words) > 0 and len(disease_words) > 0:
            overlap = patient_words.intersection(disease_words)
            # If more than 50% of words overlap, consider it a match
            min_words = min(len(patient_words), len(disease_words))
            if min_words > 0 and len(overlap) / min_words >= 0.5:
                return True
        
        return False
    
    def _get_age_range(self, disease: Dict) -> Optional[Tuple[int, int]]:
        """
        Extract age range from disease data (handles multiple formats).
        
        Args:
            disease: Disease dictionary
            
        Returns:
            Tuple of (min_age, max_age) or None if not found
        """
        # Format 1: typical_age_range as [min, max]
        if "typical_age_range" in disease and isinstance(disease["typical_age_range"], list):
            age_range = disease["typical_age_range"]
            if len(age_range) >= 2:
                return (int(age_range[0]), int(age_range[1]))
        
        # Format 2: risk_factors.age_range as [{"min": x, "max": y}]
        if "risk_factors" in disease and isinstance(disease["risk_factors"], dict):
            age_ranges = disease["risk_factors"].get("age_range", [])
            if age_ranges and isinstance(age_ranges, list) and len(age_ranges) > 0:
                first_range = age_ranges[0]
                if isinstance(first_range, dict):
                    min_age = first_range.get("min", 0)
                    max_age = first_range.get("max", 99)
                    return (int(min_age), int(max_age))
        
        # Default: no age restriction
        return None
    
    def _get_key_symptoms(self, disease: Dict) -> Dict[str, float]:
        """
        Extract key symptoms with weights from disease data.
        
        Args:
            disease: Disease dictionary
            
        Returns:
            Dictionary mapping symptom -> weight
        """
        key_symptoms = {}
        
        # Format 1: key_symptoms dictionary
        if "key_symptoms" in disease and isinstance(disease["key_symptoms"], dict):
            key_symptoms.update(disease["key_symptoms"])
        
        # Format 2: symptoms.required list (weight 1.0)
        if "symptoms" in disease and isinstance(disease["symptoms"], dict):
            required = disease["symptoms"].get("required", [])
            if isinstance(required, list):
                for symptom in required:
                    if isinstance(symptom, str):
                        key_symptoms[symptom] = 1.0
        
        return key_symptoms
    
    def _get_supportive_symptoms(self, disease: Dict) -> Dict[str, float]:
        """
        Extract supportive symptoms with weights from disease data.
        
        Args:
            disease: Disease dictionary
            
        Returns:
            Dictionary mapping symptom -> weight
        """
        supportive_symptoms = {}
        
        # Format 1: supportive_symptoms dictionary
        if "supportive_symptoms" in disease and isinstance(disease["supportive_symptoms"], dict):
            supportive_symptoms.update(disease["supportive_symptoms"])
        
        # Format 2: symptoms.common list (weight 0.4)
        if "symptoms" in disease and isinstance(disease["symptoms"], dict):
            common = disease["symptoms"].get("common", [])
            if isinstance(common, list):
                for symptom in common:
                    if isinstance(symptom, str):
                        supportive_symptoms[symptom] = 0.4
        
        # Format 2: symptoms.rare list (weight 0.3, lower than common)
        if "symptoms" in disease and isinstance(disease["symptoms"], dict):
            rare = disease["symptoms"].get("rare", [])
            if isinstance(rare, list):
                for symptom in rare:
                    if isinstance(symptom, str):
                        supportive_symptoms[symptom] = 0.3
        
        return supportive_symptoms
    
    def _get_exclude_symptoms(self, disease: Dict) -> List[str]:
        """
        Extract exclude symptoms from disease data.
        
        Args:
            disease: Disease dictionary
            
        Returns:
            List of exclude symptoms
        """
        exclude_symptoms = []
        
        # Format 1: exclude_symptoms dictionary (keys are symptoms)
        if "exclude_symptoms" in disease:
            if isinstance(disease["exclude_symptoms"], dict):
                exclude_symptoms.extend(disease["exclude_symptoms"].keys())
            elif isinstance(disease["exclude_symptoms"], list):
                exclude_symptoms.extend(disease["exclude_symptoms"])
        
        return exclude_symptoms
    
    def calculate_scores(
        self,
        patient_symptoms: List[str],
        patient_age: Optional[int] = None
    ) -> List[Dict[str, any]]:
        """
        Calculate disease scores based on patient symptoms and age.
        
        Args:
            patient_symptoms: List of patient symptoms (normalized strings)
            patient_age: Patient age in years (optional)
            
        Returns:
            List of top 5 diseases with scores, sorted by score (highest first).
            Each dict contains: name, code, score, matched_symptoms, exclude_triggered
        """
        if not patient_symptoms:
            logger.warning("No patient symptoms provided for scoring")
            return []
        
        # Normalize patient symptoms
        normalized_patient_symptoms = [self._normalize_symptom(s) for s in patient_symptoms]
        
        disease_scores = []
        
        for disease in self.diseases:
            disease_name = disease.get("name", "Unknown")
            disease_code = disease.get("code") or disease.get("id", "Unknown")
            
            # Step 1: Check exclude symptoms - if any match, score = 0
            exclude_symptoms = self._get_exclude_symptoms(disease)
            exclude_triggered = False
            
            for exclude_symptom in exclude_symptoms:
                for patient_symptom in normalized_patient_symptoms:
                    if self._symptom_matches(patient_symptom, exclude_symptom):
                        exclude_triggered = True
                        break
                if exclude_triggered:
                    break
            
            if exclude_triggered:
                # Disease excluded, score = 0
                disease_scores.append({
                    "name": disease_name,
                    "code": disease_code,
                    "score": 0.0,
                    "matched_symptoms": [],
                    "exclude_triggered": True,
                    "age_penalty_applied": False
                })
                continue
            
            # Step 2: Calculate score from key_symptoms (Weight 1.0+)
            key_symptoms = self._get_key_symptoms(disease)
            key_score = 0.0
            matched_key_symptoms = []
            
            for disease_symptom, weight in key_symptoms.items():
                for patient_symptom in normalized_patient_symptoms:
                    if self._symptom_matches(patient_symptom, disease_symptom):
                        key_score += weight
                        matched_key_symptoms.append(disease_symptom)
                        break  # Count each disease symptom only once
            
            # Step 3: Calculate score from supportive_symptoms (Weight 0.4+)
            supportive_symptoms = self._get_supportive_symptoms(disease)
            supportive_score = 0.0
            matched_supportive_symptoms = []
            
            for disease_symptom, weight in supportive_symptoms.items():
                for patient_symptom in normalized_patient_symptoms:
                    if self._symptom_matches(patient_symptom, disease_symptom):
                        supportive_score += weight
                        matched_supportive_symptoms.append(disease_symptom)
                        break  # Count each disease symptom only once
            
            # Total score
            total_score = key_score + supportive_score
            
            # Step 4: Apply age range penalty if patient age is provided
            age_penalty_applied = False
            if patient_age is not None:
                age_range = self._get_age_range(disease)
                if age_range:
                    min_age, max_age = age_range
                    if patient_age < min_age or patient_age > max_age:
                        total_score *= 0.5  # Apply 0.5x penalty
                        age_penalty_applied = True
            
            # Combine matched symptoms
            all_matched = matched_key_symptoms + matched_supportive_symptoms
            
            disease_scores.append({
                "name": disease_name,
                "code": disease_code,
                "score": total_score,
                "matched_symptoms": all_matched,
                "exclude_triggered": False,
                "age_penalty_applied": age_penalty_applied
            })
        
        # Sort by score (highest first) and return top 5
        disease_scores.sort(key=lambda x: x["score"], reverse=True)
        top_5 = disease_scores[:5]
        
        logger.debug(f"Top 5 diseases: {[(d['name'], d['score']) for d in top_5]}")
        
        return top_5
    
    def get_disease_by_name(self, name: str) -> Optional[Dict]:
        """
        Get full disease data by name (case-insensitive partial match).
        
        Args:
            name: Disease name to search for
            
        Returns:
            Disease dictionary or None if not found
        """
        name_lower = name.lower()
        for disease in self.diseases:
            disease_name = disease.get("name", "").lower()
            if name_lower in disease_name or disease_name in name_lower:
                return disease
        return None
    
    def get_disease_by_code(self, code: str) -> Optional[Dict]:
        """
        Get full disease data by code.
        
        Args:
            code: Disease code (e.g., "D011")
            
        Returns:
            Disease dictionary or None if not found
        """
        for disease in self.diseases:
            disease_code = disease.get("code") or disease.get("id", "")
            if disease_code == code:
                return disease
        return None


