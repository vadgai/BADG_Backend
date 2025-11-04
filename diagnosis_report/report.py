import os
import json
import re
import logging
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import types
load_dotenv()

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
    logger.error("❌ GEMINI API KEY NOT FOUND for report.py!")
    logger.error("   Checked: GOOGLE_API_KEY and GEMINI_API_KEY")
    logger.error("   Please set in Backend/.env file")
else:
    logger.info("✅ Gemini API key loaded successfully (report.py)")
    logger.info(f"   Key prefix: {google_api_key[:10]}..." if len(google_api_key) > 10 else "   Key too short!")

# Attempt to configure and instantiate model
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        model_available = True
        logger.info(f"✅ Successfully connected to model: {MODEL_NAME} (report.py)")
    except Exception as e:
        logger.error(f"❌ Failed to instantiate model in report.py: {e}")
        logger.error("   Report generation may fail or use fallback")

def _fallback_report(age, gender, symptoms, chat_history, mapped_diseases):
    """
    Generate a basic report when AI is unavailable.
    """
    symptom_list = symptoms if isinstance(symptoms, list) else [str(symptoms)]
    
    report = {
        "PatientInfo": {
            "Age": f"{age} Years",
            "Gender": str(gender).title()
        },
        "Recommendation": "Please consult a healthcare professional for proper diagnosis and treatment.",
        "Urgency": "Routine",
        "ReasonForConsultation": f"Patient reports symptoms: {', '.join(symptom_list)}",
        "MainSymptoms": symptom_list[:6],  # Top 6 symptoms
        "TopDiseaseMatches": [
            {
                "Disease1": {
                    "Name1": "Unable to determine - AI unavailable",
                    "MatchLevel1": "Unknown",
                    "PreHospitalCare1": ["Seek medical consultation", "Monitor symptoms"],
                    "SymptomsToWatch1": ["Worsening symptoms", "New symptoms"],
                    "SelfCare1": ["Rest", "Stay hydrated", "Monitor temperature"],
                    "MedicationSuggestion1": ["Consult doctor before taking medication"]
                }
            }
        ]
    }
    
    return json.dumps({"report": report})

def generate_report_prompt(age, gender, symptoms, chat_history, mapped_diseases):
    formatted_symptoms = ", ".join(symptoms)

    return f"""
    You are a senior medical AI assistant generating comprehensive diagnostic reports based on clinical consultations.

    ### Sample Output Format:
       { {
        "PatientInfo": {
            "Age": "42 Years",
            "Gender": "Man"
        },
        "Recommendation": "Schedule an appointment with a physician within the next 24–48 hours. Seek immediate care if high fever or breathing issues develop.",
        "Urgency": "Moderate",
        "ReasonForConsultation": "Patient reports persistent sore throat, moderate fever, headache, and fatigue over the past two days.",
        "MainSymptoms": [
            "Sore throat",
            "Headache",
            "Fatigue",
            "Moderate fever (up to 101°F)",
            "Dry cough",
            "Mild body ache"
        ],
        "NextDiagnosticSteps": [
            "Your doctor may recommend a few diagnostic tests to understand your condition better.",
            "Complete Blood Count (CBC) test helps detect any infection or inflammation in your body.",
            "Throat Culture or Rapid Antigen Test to confirm strep throat bacterial infection.",
            "C-Reactive Protein (CRP) test evaluates the level of inflammation in your body.",
            "These tests allow your doctor to identify underlying causes such as bacterial vs viral infection and determine appropriate antibiotic therapy if needed."
        ],
        "TopDiseaseMatches": [
            {
            "Disease1": {
                "Name1": "Strep throat",
                "MatchLevel1": "High",
                "PreHospitalCare1": [
                "Avoid cold beverages and spicy foods",
                "Drink warm fluids like herbal tea",
                "Use throat lozenges to soothe irritation"
                ],
                "SymptomsToWatch1": [
                "Difficulty breathing",
                "Swelling of the tonsils with white patches",
                "Persistent high fever over 102°F"
                ],
                "SelfCare1": [
                "Take rest from work or school",
                "Isolate to avoid spreading infection",
                "Maintain good oral hygiene"
                ],
                "MedicationSuggestion1": [
                "Acetaminophen (500mg every 6 hrs for fever)",
                "Amoxicillin (if prescribed by physician)",
                "Saltwater gargle (3 times daily)"
                ]
            }
            },
            {
            "Disease2": {
                "Name2": "Influenza (Flu)",
                "MatchLevel2": "Moderate",
                "SelfCare2": [
                "Get adequate rest and avoid strenuous activity",
                "Use a humidifier to ease congestion",
                "Increase intake of clear fluids (water, soup, etc.)"
                ],
                "MedicationSuggestion2": [
                "Oseltamivir (if taken within 48 hrs of symptom onset)",
                "Paracetamol (for fever and pain relief)",
                "Vitamin C supplements (optional immune support)"
                ]
            }
            },
            {
            "Disease3": {
                "Name3": "Viral pharyngitis",
                "MatchLevel3": "Low",
                "SelfCare3": [
                "Apply warm compresses to throat area",
                "Perform saltwater gargles 3-4 times daily",
                "Avoid allergens and polluted environments"
                ],
                "MedicationSuggestion3": [
                "Ibuprofen (400mg every 8 hrs for throat inflammation)",
                "Throat lozenges with benzocaine",
                "Steam inhalation for symptom relief"
                ]
            }
            }
        ]
        }
       }
   
    ***Your Output Should be a json of this Structure Only, not a single other word, just json. This is just a Sample***
    ---

### Now Generate a Report for This Case:

Age: {age} Years  
Gender: {gender}  
Symptoms: {formatted_symptoms}  

Chat History (Detailed Q&A):
{chat_history}

Disease Mapping Analysis:
{mapped_diseases}

CRITICAL INSTRUCTIONS FOR REPORT GENERATION:

1. **Analyze Symptom Pattern**: Review ALL symptoms and follow-up answers together to identify the most likely diagnosis
2. **Accurate Disease Ranking**: Rank diseases by likelihood (High/Moderate/Low) based on symptom pattern, not generic matching
3. **Match Levels**: Assign "High" only when symptoms strongly support diagnosis, "Moderate" for possible matches, "Low" for less likely

4. **Next Diagnostic Steps** (MOST IMPORTANT):
   - Generate SPECIFIC diagnostic tests based on the TOP 1-2 predicted diseases (High/Moderate match level)
   - For each recommended test, explain WHY it's needed and WHAT it will reveal
   - Use this structure:
     * Opening: "Your doctor may recommend a few diagnostic tests to understand your condition better."
     * Test 1: Name the specific test and explain its purpose (e.g., "Complete Blood Count (CBC) helps detect infection or anemia")
     * Test 2: Another relevant test with explanation
     * Test 3: Additional test if warranted (mention if optional/urgent)
     * Closing: "These tests allow your doctor to identify underlying causes such as [specific conditions based on top disease]"
   - Tests should be SPECIFIC to the predicted condition (e.g., Strep → Throat Culture, Diabetes → HbA1c, Liver issues → LFT, Heart → ECG/Troponin)
   - DO NOT give generic tests - tailor to the actual predicted disease

5. **Disease-Specific Content**:
   - PreHospitalCare: Immediate actions before seeing doctor
   - SymptomsToWatch: Red flags requiring urgent care
   - SelfCare: Home management strategies
   - MedicationSuggestion: Include dosages and frequency (educational purposes only)

6. **Language**: Use medically accurate but patient-friendly language suitable for Indian context
7. **Format**: Keep each point concise (1-2 lines max) for PDF conversion
8. **Urgency Levels**: Emergency (immediate care), Moderate (24-48 hrs), Routine (schedule appointment)

RETURN ONLY VALID JSON - NO MARKDOWN, NO EXPLANATION, NO EXTRA TEXT
"""




import json
import re
from google.generativeai import types
def final_report(age, gender, symptoms, chat_history, mapped_diseases, weight=None, height=None, occupation=None, location=None, physical_activity=None, diet_type=None):
    """
    Generate final diagnosis report using Gemini AI.
    Falls back to basic report if model is unavailable.
    """
    if not model_available or model is None:
        logger.error("Model not available for report generation, using fallback")
        return _fallback_report(age, gender, symptoms, chat_history, mapped_diseases)
    
    try:
        response = model.generate_content(generate_report_prompt(age, gender, symptoms, chat_history, mapped_diseases))
        raw_response = response.text.strip() 

        
        cleaned_res = raw_response
        if cleaned_res.startswith("```json"):
             cleaned_res = cleaned_res[len("```json"):].strip()
        if cleaned_res.endswith("```"):
             cleaned_res = cleaned_res[:-len("```")].strip()

        
        try:
            
            if cleaned_res.startswith('{') and cleaned_res.endswith('}'):
                parsed_json = json.loads(cleaned_res)
                
                # Add context metadata to the report
                from datetime import datetime
                parsed_json["meta"] = {
                    "context_used": [],
                    "timestamp": str(datetime.now()),
                    "analysis_type": "personalized"
                }
                
                # Add which context fields were used
                if weight and height:
                    parsed_json["meta"]["context_used"].append("weight")
                    parsed_json["meta"]["context_used"].append("height")
                    bmi = weight / ((height/100) ** 2)
                    parsed_json["meta"]["bmi"] = round(bmi, 1)
                if occupation:
                    parsed_json["meta"]["context_used"].append("occupation")
                if physical_activity:
                    parsed_json["meta"]["context_used"].append("activity")
                if diet_type:
                    parsed_json["meta"]["context_used"].append("diet")
                if location:
                    parsed_json["meta"]["context_used"].append("location")
                
                # Add personalized analysis note
                if parsed_json["meta"]["context_used"]:
                    parsed_json["meta"]["note"] = "Analysis personalized using your physical and lifestyle profile."
                else:
                    parsed_json["meta"]["note"] = "Basic analysis using symptoms and demographics only."
                
                return parsed_json
            else:
                 print(f"Warning: Model returned unexpected format (not 'Ready for diagnosis' and not JSON-like): {raw_response}")
                 return None 

        except json.JSONDecodeError as e:
            print(f"JSONDecodeError: Could not parse response as JSON: {e}")
            print(f"Problematic string was:\n{raw_response}")
            return None 
    except Exception as e:
        print(f"An API error occurred during content generation: {e}")
        return None





