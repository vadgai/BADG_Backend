import spacy
from spacy import displacy
import os
import json
import logging
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dual API key checking (GOOGLE_API_KEY or GEMINI_API_KEY)
google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"

# Model initialization with error handling
model_available = False
model = None

# Log API key status
if not google_api_key:
    logger.error("❌ GEMINI API KEY NOT FOUND for symptom.py!")
    logger.error("   Checked: GOOGLE_API_KEY and GEMINI_API_KEY")
    logger.error("   Please set in Backend/.env file")
else:
    logger.info("✅ Gemini API key loaded successfully (symptom.py)")
    logger.info(f"   Key prefix: {google_api_key[:10]}..." if len(google_api_key) > 10 else "   Key too short!")

# Attempt to configure and instantiate model
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        model_available = True
        logger.info(f"✅ Successfully connected to model: {MODEL_NAME} (symptom.py)")
    except Exception as e:
        logger.error(f"❌ Failed to instantiate model in symptom.py: {e}")
        logger.error("   Symptom extraction may use fallback behavior")


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


def clarify_symptoms(text):
    """
    Use LLM to extract symptoms from natural language text.
    Returns a JSON array string for safe parsing.
    """
    if not model_available or model is None:
        logger.warning("Model not available for symptom clarification")
        return "[]"
    
    prompt = f"""You are a medical expert. Extract only medical symptoms from this sentence:
    "{text}".
    
    Return ONLY a valid JSON array of symptoms, nothing else.
    Example: ["headache", "fever", "cough"]
    
    JSON array:"""
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
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

