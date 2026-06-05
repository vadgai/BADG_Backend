import spacy
from spacy import displacy
import os
import json
import logging
from dotenv import load_dotenv
load_dotenv()

# Import centralized Gemini API manager
from utils.gemini_api_manager import get_gemini_model, MODEL_NAME, generate_content_with_fallback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get model from centralized manager (with 15-key fallback support)
model_available, model = get_gemini_model()

if model_available:
    logger.info("="*80)
    logger.info(f"✅ Gemini model available for symptom processing (via API manager)")
    logger.info(f"   Model: {MODEL_NAME}")
    logger.info("="*80)
else:
    logger.warning("="*80)
    logger.warning("⚠️ Gemini model not available for symptom processing")
    logger.warning("   Symptom extraction will use fallback behavior")
    logger.warning("="*80)


def extract_medical_terms(text):
    try:
        # Try to load the spacy model if available
        nlp = spacy.load("en_core_web_sm")  # Use standard English model instead of scientific
        doc = nlp(text)
        medical_entities = [ent.text.lower() for ent in doc.ents if ent.label_ in ["DISEASE", "CONDITION", "SYMPTOM"]]
        return list(set(medical_entities))
    except:
        # If spaCy model fails, return empty list
        return []


def _parse_symptom_array(text: str):
    if not text:
        return None
    try:
        data = json.loads(text.strip())
        return data if isinstance(data, list) else None
    except Exception:
        return None


def clarify_symptoms(text):
    """
    Use LLM to extract symptoms from natural language text.
    Returns a JSON array string for safe parsing.
    """
    if not model_available or model is None:
        logger.warning("Model not available for symptom clarification")
        return "[]"
    
    prompt = f"""You are a clinical NLP extractor.
TASK: Extract only patient-reported symptoms from the sentence.
STRICT:
- Include symptoms only (no diagnoses, no medicines, no tests, no advice).
- Normalize to concise medical symptom terms.
- Return WITH A SINGLE JSON ARRAY and nothing else. Example: ["headache", "fever"].

Sentence: "{text}"
Return only the JSON array (no text, no Markdown, no explanation)."""

    retry_prompt = """Previous response could not be parsed. RETURN ONLY a JSON array in this exact format:
["symptom1","symptom2"]
No markdown, no explanation, no extra keys."""
    
    try:
        success, response_text, error = generate_content_with_fallback(
            prompt=prompt,
            max_retries=None,
            temperature=0.2,
            max_output_tokens=300,
        )
        if not success or not response_text:
            logger.error(f"Error in clarify_symptoms: {error}")
            return "[]"

        parsed = _parse_symptom_array(response_text)
        if parsed is None:
            success, response_text, error = generate_content_with_fallback(
                prompt=retry_prompt,
                max_retries=None,
                temperature=0.2,
                max_output_tokens=200,
            )
            if not success or not response_text:
                logger.error(f"Error in clarify_symptoms retry: {error}")
                return "[]"
            parsed = _parse_symptom_array(response_text)

        if parsed is None:
            return "[]"

        return json.dumps(parsed)
    except Exception as e:
        logger.error(f"Error in clarify_symptoms: {e}")
        return "[]"


def hybrid_symptom_extraction(text):
    """
    Extract medical symptoms using hybrid approach: spaCy NER + LLM
    
    SECURITY: Uses safe JSON parsing instead of eval()
    """
    # Try spacy extraction first
    sci_terms = extract_medical_terms(text)
    logger.debug(f"SpaCy extracted terms: {sci_terms}")
    
    llm_terms = []
    if model_available:
        try:
            # Then use LLM-based extraction
            llm_response = clarify_symptoms(text)
            logger.debug(f"LLM raw response: {llm_response}")
            
            # SECURITY FIX: Use safe JSON parsing instead of eval()
            # Try to parse as JSON array
            try:
                llm_terms = json.loads(llm_response)
                if not isinstance(llm_terms, list):
                    llm_terms = []
            except json.JSONDecodeError:
                # If not valid JSON, try to extract list-like patterns
                import re
                # Match patterns like ['symptom1', 'symptom2'] or ["symptom1", "symptom2"]
                match = re.search(r'\[(.*?)\]', llm_response)
                if match:
                    # Extract items between quotes
                    items = re.findall(r'["\']([^"\']+)["\']', match.group(1))
                    llm_terms = items
                else:
                    llm_terms = []
            
            logger.debug(f"LLM extracted terms: {llm_terms}")
        except Exception as e:
            logger.warning(f"LLM symptom extraction failed: {e}")
            llm_terms = []
    else:
        logger.warning("Model not available, skipping LLM symptom extraction")
    
    # If spacy extraction failed or returned nothing, rely only on LLM
    if not sci_terms:
        return llm_terms
    
    return list(set(sci_terms + llm_terms))  
