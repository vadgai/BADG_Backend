"""
Entropy Tracking for Method 2 - Smart Detective Stopping Logic

This module tracks differential diagnosis changes over time to implement
entropy reduction and information gain checks using pure LLM reasoning.
"""

import logging
from typing import Dict, List, Optional, Tuple
from copy import deepcopy

logger = logging.getLogger(__name__)


class EntropyTracker:
    """
    Tracks differential diagnosis changes over time to detect entropy reduction and information gain.
    Now works with LLM-generated differential diagnoses instead of disease scores.
    """
    
    def __init__(self):
        """Initialize the entropy tracker."""
        self.differential_history: List[List[Dict]] = []  # List of differential diagnosis lists
        self.question_history: List[str] = []  # List of questions asked
        self.stopping_reason: Optional[str] = None  # Reason for stopping
    
    def record_differential(self, differential: List[Dict], question: Optional[str] = None) -> None:
        """
        Record differential diagnosis after a question-answer turn.
        
        Args:
            differential: List of conditions with name, confidence, reasoning
            question: Optional question that was asked
        """
        # Store the differential diagnosis list
        self.differential_history.append(differential[:5])  # Track top 5
        if question:
            self.question_history.append(question)
    
    def record_scores(self, top_diseases: List[Dict], question: Optional[str] = None) -> None:
        """
        Legacy method for compatibility - converts disease scores to differential format.
        
        Args:
            top_diseases: List of top diseases with scores (legacy format)
            question: Optional question that was asked
        """
        # Convert to differential format
        differential = []
        for disease in top_diseases[:5]:
            name = disease.get("name", "Unknown")
            score = disease.get("score", 0.0)
            # Convert score to confidence
            if score >= 0.7:
                confidence = "High"
            elif score >= 0.5:
                confidence = "Moderate"
            else:
                confidence = "Low"
            differential.append({
                "name": name,
                "confidence": confidence,
                "reasoning": f"Score: {score:.2f}"
            })
        self.record_differential(differential, question)
    
    def _confidence_to_numeric(self, confidence: str) -> float:
        """
        Convert confidence string to numeric value for comparison.
        
        Args:
            confidence: "High", "Moderate", or "Low"
            
        Returns:
            Numeric value (0.0 to 1.0)
        """
        confidence_map = {
            "High": 0.8,
            "Moderate": 0.5,
            "Low": 0.2
        }
        return confidence_map.get(confidence, 0.0)
    
    def check_top3_changes(self) -> Tuple[float, Dict[str, float]]:
        """
        Check how much the Top 3 conditions changed in the last turn.
        Compares differential diagnoses between turns.
        
        Returns:
            Tuple of (max_change, changes_dict) where:
            - max_change: Maximum change in any top 3 condition (0.0 to 1.0)
            - changes_dict: Dict mapping condition names to their changes
        """
        if len(self.differential_history) < 2:
            return 0.0, {}
        
        current_diff = self.differential_history[-1]
        previous_diff = self.differential_history[-2]
        
        # Create dicts mapping name to confidence value
        current_map = {}
        for condition in current_diff[:3]:
            name = condition.get("name", "Unknown")
            confidence = condition.get("confidence", "Low")
            current_map[name] = self._confidence_to_numeric(confidence)
        
        previous_map = {}
        for condition in previous_diff[:3]:
            name = condition.get("name", "Unknown")
            confidence = condition.get("confidence", "Low")
            previous_map[name] = self._confidence_to_numeric(confidence)
        
        # Calculate changes
        changes = {}
        max_change = 0.0
        
        # Check all conditions that appear in either turn
        all_names = set(list(current_map.keys()) + list(previous_map.keys()))
        
        for name in all_names:
            current_val = current_map.get(name, 0.0)
            previous_val = previous_map.get(name, 0.0)
            
            # Calculate absolute change
            change = abs(current_val - previous_val)
            changes[name] = change
            max_change = max(max_change, change)
        
        return max_change, changes
    
    def simulate_information_gain(
        self,
        disease_engine,  # Deprecated - kept for compatibility
        current_symptoms: List[str],
        patient_age: Optional[int],
        potential_new_symptom: str
    ) -> float:
        """
        Simulate information gain (deprecated - kept for compatibility).
        In pure LLM approach, information gain is determined by the LLM itself.
        
        Returns:
            0.0 (not used in pure LLM approach)
        """
        # In pure LLM approach, information gain is determined by the LLM's reasoning
        # This method is kept for compatibility but not actively used
        return 0.0
    
    def check_stopping_rules(
        self,
        differential: List[Dict],  # Changed from top_diseases to differential
        turn_count: int,
        emergency_detected: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if stopping conditions are met based on High-Performance Smart Stop logic.
        
        IMPORTANT: This function is only called when 5 <= turn_count < 12.
        Minimum 5 and maximum 12 are enforced in methods.py.
        
        Args:
            differential: Current differential diagnosis (Top 3 suspects with name, confidence, reasoning)
            turn_count: Current number of questions asked (should be 5-11 when called)
            emergency_detected: Whether an emergency condition was detected
            
        Returns:
            Tuple of (should_stop, reason)
        """
        # Note: Minimum 5 and maximum 12 are enforced in methods.py, not here
        # This function only checks smart stop conditions when 5 <= turn_count < 12
        
        if not differential or len(differential) == 0:
            return False, ""
        
        # Rule 1: High Confidence - Stop if top condition has "High" confidence (>90% equivalent)
        top_condition = differential[0]
        top_confidence = top_condition.get("confidence", "Low")
        if top_confidence == "High":
            # Additional check: if top condition is clearly leading and others are much lower
            if len(differential) > 1:
                second_confidence = differential[1].get("confidence", "Low")
                if second_confidence in ["Low", "Moderate"]:
                    self.stopping_reason = "confidence"
                    return True, "confidence"
            else:
                # Only one condition with High confidence
                self.stopping_reason = "confidence"
                return True, "confidence"
        
        # Rule 2: Information Plateau - Check last 2 questions
        if len(self.differential_history) >= 3:  # Need at least 2 turns of history
            # Check if last 2 questions changed differential by less than threshold
            max_change, _ = self.check_top3_changes()
            
            # Check previous turn as well
            if len(self.differential_history) >= 4:
                # Get changes for previous turn
                prev_current = self.differential_history[-2]
                prev_previous = self.differential_history[-3]
                
                # Calculate change for previous turn
                prev_current_map = {}
                for condition in prev_current[:3]:
                    name = condition.get("name", "Unknown")
                    confidence = condition.get("confidence", "Low")
                    prev_current_map[name] = self._confidence_to_numeric(confidence)
                
                prev_previous_map = {}
                for condition in prev_previous[:3]:
                    name = condition.get("name", "Unknown")
                    confidence = condition.get("confidence", "Low")
                    prev_previous_map[name] = self._confidence_to_numeric(confidence)
                
                prev_max_change = 0.0
                all_prev_names = set(list(prev_current_map.keys()) + list(prev_previous_map.keys()))
                for name in all_prev_names:
                    current_val = prev_current_map.get(name, 0.0)
                    previous_val = prev_previous_map.get(name, 0.0)
                    change = abs(current_val - previous_val)
                    prev_max_change = max(prev_max_change, change)
                
                # If both last 2 turns had minimal change (< 0.1), stop
                if max_change < 0.1 and prev_max_change < 0.1:
                    self.stopping_reason = "uselessness"
                    return True, "uselessness"
        
        # Rule 3: Emergency - Can stop early if turn_count >= 5
        # Note: Emergency detection with turn_count < 5 is handled in methods.py (forces continuation)
        if emergency_detected and turn_count >= 5:
            self.stopping_reason = "emergency_detected"
            return True, "emergency_detected"
        
        return False, ""
    
    def get_clarity_disclaimer(self, language: str = "en") -> str:
        """
        Get clarity disclaimer message based on stopping reason.
        
        Args:
            language: Language code ("en" or "hi")
            
        Returns:
            Disclaimer message
        """
        if self.stopping_reason in ["uselessness", "exhaustion"]:
            if language == "hi":
                return "हमें पूरी जानकारी नहीं मिल पाई है, कृपया डॉक्टर से मिलें।"
            else:
                return "We couldn't reach a definitive conclusion. Please consult a professional."
        
        return ""

