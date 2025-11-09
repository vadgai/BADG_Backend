"""
Localized Report Builder
Translates diagnosis reports from English to Indian languages using the Translation Service.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
import httpx

# Initialize logging
logger = logging.getLogger(__name__)

# Translation Service configuration
import os
from dotenv import load_dotenv

load_dotenv()

TRANSLATION_SERVICE_URL = os.getenv("TRANSLATION_SERVICE_URL", "http://localhost:8080")
TRANSLATION_SERVICE_API_KEY = os.getenv("TRANSLATION_SERVICE_API_KEY", "")
TRANSLATION_SERVICE_TIMEOUT = int(os.getenv("TRANSLATION_SERVICE_TIMEOUT", "15"))


class LocalizedReportBuilder:
    """
    Builds localized versions of diagnosis reports by translating text fields.
    """
    
    def __init__(self):
        self.translation_endpoint = f"{TRANSLATION_SERVICE_URL.rstrip('/')}/translate"
        self.api_key = TRANSLATION_SERVICE_API_KEY
        self.timeout = TRANSLATION_SERVICE_TIMEOUT
        
        if not TRANSLATION_SERVICE_URL:
            logger.warning("⚠️  TRANSLATION_SERVICE_URL not configured")
        if not TRANSLATION_SERVICE_API_KEY:
            logger.warning("⚠️  TRANSLATION_SERVICE_API_KEY not configured")
    
    async def translate_text(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "hi"
    ) -> str:
        """
        Translate a single text string using the translation service.
        Returns original text on failure (safe fallback).
        """
        if not text or not text.strip():
            return text
        
        # Skip if service not configured
        if not self.translation_endpoint or not self.api_key:
            logger.warning("Translation service not configured, returning original text")
            return text
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            
            payload = {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "text": text,
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.translation_endpoint,
                    json=payload,
                    headers=headers,
                )
            
            if response.status_code == 200:
                result = response.json()
                translated = result.get("translation", text)
                
                logger.info(
                    f"Translated text to {target_lang}: {text[:50]}... -> {translated[:50]}..."
                )
                
                return translated
            else:
                logger.warning(
                    f"Translation service returned {response.status_code}, using original text"
                )
                return text
        
        except httpx.TimeoutException:
            logger.warning(f"Translation timeout for: {text[:50]}... - using original")
            return text
        
        except Exception as e:
            logger.warning(f"Translation error: {str(e)} - using original text")
            return text
    
    async def translate_list(
        self,
        items: List[str],
        source_lang: str = "en",
        target_lang: str = "hi"
    ) -> List[str]:
        """
        Translate a list of strings concurrently.
        """
        if not items:
            return items
        
        # Translate all items concurrently
        tasks = [
            self.translate_text(item, source_lang, target_lang)
            for item in items
        ]
        
        translated_items = await asyncio.gather(*tasks)
        return list(translated_items)
    
    async def localize_report(
        self,
        report: Dict[str, Any],
        target_lang: str = "hi"
    ) -> Dict[str, Any]:
        """
        Localize a diagnosis report by translating all patient-facing text.
        
        Args:
            report: The diagnosis report dictionary (English)
            target_lang: Target language code (hi, ta, te, bn, kn)
        
        Returns:
            Localized report dictionary with translated text
        """
        if not report:
            return report
        
        # Skip if service not configured
        if not self.translation_endpoint or not self.api_key:
            logger.warning("Translation service not configured, returning original report")
            return report
        
        logger.info(f"Starting report localization to {target_lang}")
        
        try:
            localized = report.copy()
            
            # Translate PatientInfo (gender label only, not age number)
            if "PatientInfo" in localized:
                patient_info = localized["PatientInfo"]
                if "Gender" in patient_info:
                    patient_info["Gender"] = await self.translate_text(
                        patient_info["Gender"],
                        "en",
                        target_lang
                    )
            
            # Translate Recommendation
            if "Recommendation" in localized:
                localized["Recommendation"] = await self.translate_text(
                    localized["Recommendation"],
                    "en",
                    target_lang
                )
            
            # Translate Urgency
            if "Urgency" in localized:
                localized["Urgency"] = await self.translate_text(
                    localized["Urgency"],
                    "en",
                    target_lang
                )
            
            # Translate ReasonForConsultation
            if "ReasonForConsultation" in localized:
                localized["ReasonForConsultation"] = await self.translate_text(
                    localized["ReasonForConsultation"],
                    "en",
                    target_lang
                )
            
            # Translate MainSymptoms list
            if "MainSymptoms" in localized and isinstance(localized["MainSymptoms"], list):
                localized["MainSymptoms"] = await self.translate_list(
                    localized["MainSymptoms"],
                    "en",
                    target_lang
                )
            
            # Translate NextDiagnosticSteps list
            if "NextDiagnosticSteps" in localized and isinstance(localized["NextDiagnosticSteps"], list):
                localized["NextDiagnosticSteps"] = await self.translate_list(
                    localized["NextDiagnosticSteps"],
                    "en",
                    target_lang
                )
            
            # Translate TopDiseaseMatches
            if "TopDiseaseMatches" in localized and isinstance(localized["TopDiseaseMatches"], list):
                for disease_entry in localized["TopDiseaseMatches"]:
                    for disease_key, disease_data in disease_entry.items():
                        if isinstance(disease_data, dict):
                            # Translate disease name
                            if "Name1" in disease_data:
                                disease_data["Name1"] = await self.translate_text(
                                    disease_data["Name1"],
                                    "en",
                                    target_lang
                                )
                            
                            # Translate match level
                            if "MatchLevel1" in disease_data:
                                disease_data["MatchLevel1"] = await self.translate_text(
                                    disease_data["MatchLevel1"],
                                    "en",
                                    target_lang
                                )
                            
                            # Translate PreHospitalCare list
                            if "PreHospitalCare1" in disease_data and isinstance(disease_data["PreHospitalCare1"], list):
                                disease_data["PreHospitalCare1"] = await self.translate_list(
                                    disease_data["PreHospitalCare1"],
                                    "en",
                                    target_lang
                                )
                            
                            # Translate SymptomsToWatch list
                            if "SymptomsToWatch1" in disease_data and isinstance(disease_data["SymptomsToWatch1"], list):
                                disease_data["SymptomsToWatch1"] = await self.translate_list(
                                    disease_data["SymptomsToWatch1"],
                                    "en",
                                    target_lang
                                )
                            
                            # Translate SelfCare list
                            if "SelfCare1" in disease_data and isinstance(disease_data["SelfCare1"], list):
                                disease_data["SelfCare1"] = await self.translate_list(
                                    disease_data["SelfCare1"],
                                    "en",
                                    target_lang
                                )
                            
                            # Translate MedicationSuggestion list
                            if "MedicationSuggestion1" in disease_data and isinstance(disease_data["MedicationSuggestion1"], list):
                                disease_data["MedicationSuggestion1"] = await self.translate_list(
                                    disease_data["MedicationSuggestion1"],
                                    "en",
                                    target_lang
                                )
            
            logger.info(f"✅ Report localization to {target_lang} completed successfully")
            return localized
        
        except Exception as e:
            logger.error(f"Error localizing report: {str(e)}", exc_info=True)
            # Return original report on error (safe fallback)
            return report


# Singleton instance
_localized_report_builder = None


def get_localized_report_builder() -> LocalizedReportBuilder:
    """Get or create the singleton LocalizedReportBuilder instance"""
    global _localized_report_builder
    
    if _localized_report_builder is None:
        _localized_report_builder = LocalizedReportBuilder()
    
    return _localized_report_builder


async def localize_diagnosis_report(
    report: Dict[str, Any],
    target_lang: str = "hi"
) -> Dict[str, Any]:
    """
    Convenience function to localize a diagnosis report.
    
    Args:
        report: The diagnosis report dictionary (English)
        target_lang: Target language code (hi, ta, te, bn, kn)
    
    Returns:
        Localized report dictionary
    
    Example:
        >>> english_report = {...}
        >>> hindi_report = await localize_diagnosis_report(english_report, "hi")
    """
    builder = get_localized_report_builder()
    return await builder.localize_report(report, target_lang)

