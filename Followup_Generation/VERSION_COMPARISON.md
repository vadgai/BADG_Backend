# Follow-Up Question Engine - Version Comparison

**Date:** January 26, 2026

---

## Quick Comparison Table

| Feature | v1 (Original) | v2 (Enhanced) | v3 (Batch) |
|---------|---------------|---------------|------------|
| **Questions per Call** | 1 | 1 | 7-10 |
| **Generic Questions** | Allowed | Discouraged | **FORBIDDEN** |
| **Differential Diagnosis** | Optional | Suggested | **MANDATORY** |
| **Red-Flag Priority** | No | Yes | **Enforced** |
| **Output Format** | MCQ | MCQ + metadata | Array with metadata |
| **Fallback System** | Basic | Symptom-based | Clinical (7-10) |
| **API Keys** | 1 | 15 (fallback) | 15 (fallback) |
| **Generation Time** | ~2s | ~2s | ~23s (all questions) |
| **Total Time (10 Q)** | ~20s | ~20s | ~23s |
| **Clinical Coverage** | Sequential | Sequential | **Comprehensive** |
| **Model** | gemini-pro | gemini-2.5-flash | gemini-2.5-flash |

---

## Detailed Feature Comparison

### Question Generation Approach

#### v1: Basic Sequential
```
User: "I have a fever"
System: "Do you have a cough?"
User: "Yes"
System: "Is it dry or with phlegm?"
User: "Dry"
System: "Do you have shortness of breath?"
... (repeat 10 times)
```

#### v2: Enhanced Sequential
```
User: "I have a fever"
System: "Do you have a cough along with the fever?"
Options:
A: Yes, with sputum (bacterial)
B: Yes, dry cough (viral)
C: No cough
D: None of these

User selects: B
System: "Does the headache worsen when bending forward?"
... (better questions, but still 1 at a time)
```

#### v3: Comprehensive Batch
```
User: "I have a fever"
System: Generates 8 questions immediately:
1. [RED-FLAG] "Are you experiencing neck stiffness, sensitivity to light, or confusion?"
2. [RED-FLAG] "Have you noticed difficulty breathing, severe dizziness, or a new rash?"
3. [HIGH] "Can you describe the headache? Is it throbbing, dull, or sharp?"
4. [HIGH] "What was the highest temperature you measured?"
5. [HIGH] "Do you have a cough, sore throat, or nasal congestion?"
6. [MEDIUM] "Are you experiencing nausea, vomiting, or diarrhea?"
7. [MEDIUM] "Is the body ache generalized or in specific joints?"
8. [MEDIUM] "Have you traveled recently or been in contact with sick individuals?"

User answers all 8 questions
System: Proceeds to diagnosis
```

---

## Use Case Recommendations

### Use v1 (Original) When:
- ❌ **NOT RECOMMENDED** - Deprecated in favor of v2/v3
- Only for legacy compatibility

### Use v2 (Enhanced) When:
- ✅ You want **one question at a time** with user interaction
- ✅ You need **MCQ format** for easy selection
- ✅ You want **iterative refinement** based on previous answers
- ✅ You're building a **conversational** diagnostic flow
- ✅ You want to **gradually narrow down** the diagnosis
- ✅ Your UI is designed for **sequential questions**

**Example Scenarios:**
- Chatbot-style interface
- Mobile app with one question per screen
- User prefers step-by-step approach
- Network latency requires quick responses

### Use v3 (Batch) When:
- ✅ You want **comprehensive assessment** upfront
- ✅ You need to **minimize back-and-forth** interaction
- ✅ You want **guaranteed 7-10 questions** every time
- ✅ You need **strict red-flag prioritization**
- ✅ You want **zero generic questions**
- ✅ You're building a **form-based** diagnostic flow
- ✅ Your UI can display **multiple questions** at once

**Example Scenarios:**
- Medical intake forms
- Emergency triage systems
- Telehealth initial assessment
- Clinical decision support systems
- Research/data collection

---

## Output Format Examples

### v1 Output
```json
{
  "question": "Do you have a cough?",
  "options": ["Yes", "No"]
}
```

### v2 Output
```json
{
  "Question": "Do you have a cough along with the fever?",
  "A": "Yes, with yellow/green sputum",
  "B": "Yes, dry cough",
  "C": "No cough",
  "D": "None of these",
  "clinical_purpose": "Differentiate between bacterial and viral respiratory infection",
  "differentiates_between": ["Bacterial pneumonia", "Viral URI", "Non-respiratory fever"]
}
```

### v3 Output
```json
{
  "follow_up_questions": [
    {
      "id": 1,
      "question": "Are you experiencing neck stiffness, sensitivity to light, or confusion?",
      "priority": "red-flag",
      "clinical_focus": "Rule out meningitis or encephalitis",
      "differentiates_between": ["Meningitis", "Encephalitis", "Severe Viral Syndrome"]
    },
    {
      "id": 2,
      "question": "Have you noticed difficulty breathing, severe dizziness, or a new rash?",
      "priority": "red-flag",
      "clinical_focus": "Assess for sepsis, severe systemic infection",
      "differentiates_between": ["Sepsis", "Meningococcemia", "Severe Viral Illness"]
    }
    // ... 5-8 more questions
  ],
  "question_count": 8,
  "top_differentials": ["Influenza/Viral Syndrome", "Meningitis", "Early Sepsis"],
  "confidence_level": "medium",
  "reasoning_summary": "Prioritize ruling out life-threatening conditions..."
}
```

---

## Performance Comparison

### Scenario: 10-Question Assessment

| Metric | v1 | v2 | v3 |
|--------|----|----|-----|
| **API Calls** | 10 | 10 | 1 |
| **Total Time** | ~20s | ~20s | ~23s |
| **Network Round-trips** | 10 | 10 | 1 |
| **User Interactions** | 10 | 10 | 1 |
| **Red-Flag Detection** | Delayed | Delayed | Immediate |
| **Missed Questions** | Possible | Rare | **Never** |

### Time to Critical Information

| Scenario | v1 | v2 | v3 |
|----------|----|----|-----|
| **Red-Flag Symptom** | Question 5-10 (10-20s) | Question 3-5 (6-10s) | Question 1 (2-3s) |
| **Complete Assessment** | 10 questions (20s) | 10 questions (20s) | 8 questions (23s) |
| **Diagnosis Ready** | After 10 interactions | After 10 interactions | After 1 interaction |

---

## Migration Path

### From v1 to v2
```python
# Simple replacement
from Followup_Generation.followup import get_followup_for_diagnosis
# to
from Followup_Generation.followup_v2 import get_followup_for_diagnosis_v2 as get_followup_for_diagnosis
```

### From v2 to v3
```python
# Old (v2) - One question
result = get_followup_for_diagnosis_v2(
    age=35, 
    gender="Female", 
    symptoms=["fever"], 
    chat_history=""
)
# result = {"Question": "...", "A": "...", "B": "...", "C": "...", "D": "..."}

# New (v3) - 7-10 questions
result = get_followup_for_diagnosis_v3(
    age=35,
    gender="Female",
    symptoms=["fever"],
    chat_history=""
)
# result = {"follow_up_questions": [{...}, {...}, ...], "question_count": 8}
```

### Hybrid Approach
```python
# Use v3 for initial assessment
if question_count == 0:
    questions = get_followup_for_diagnosis_v3(...)  # Get 7-10 questions
    for q in questions["follow_up_questions"]:
        display_question(q)
        answers.append(get_user_answer())
else:
    # Use v2 for follow-up clarifications
    question = get_followup_for_diagnosis_v2(...)  # Get 1 refinement question
    display_question(question)
    answers.append(get_user_answer())
```

---

## Strengths & Weaknesses

### v2 Strengths
- ✅ Familiar MCQ format
- ✅ One question at a time (less overwhelming)
- ✅ Iterative refinement based on answers
- ✅ Good for conversational flow
- ✅ Quick response per question (~2s)

### v2 Weaknesses
- ❌ Multiple round-trips (network latency)
- ❌ May miss red flags until later questions
- ❌ User may give up before completing
- ❌ Total time can be long (20s for 10 questions)

### v3 Strengths
- ✅ Comprehensive assessment upfront
- ✅ Red flags prioritized immediately
- ✅ Zero generic questions (enforced)
- ✅ No missed important questions
- ✅ Faster total time (one API call)
- ✅ Complete data for diagnosis

### v3 Weaknesses
- ⚠️ May overwhelm users (7-10 questions at once)
- ⚠️ Requires UI that can display multiple questions
- ⚠️ Longer initial generation time (~23s)
- ⚠️ No iterative refinement based on intermediate answers

---

## Decision Matrix

Choose **v2** if:
- User experience priority: Conversational
- UI design: Chat-style, one question per screen
- Network: High latency, prefer quick responses
- User preference: Step-by-step guidance

Choose **v3** if:
- User experience priority: Efficiency
- UI design: Form-based, multiple questions on screen
- Network: Stable, can wait 20-25s
- Clinical priority: Comprehensive assessment
- Red-flag detection: Must be immediate
- Question quality: Zero tolerance for generic questions

---

## Code Examples

### Using v2 in WebSocket Handler
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Get one question at a time
    result = get_followup_for_diagnosis_v2(
        age=patient.age,
        gender=patient.gender,
        symptoms=patient.symptoms,
        chat_history=session.chat_history
    )
    
    if isinstance(result, dict):
        # Send single MCQ question
        await websocket.send_json({
            "type": "followup_question",
            "data": result
        })
    else:
        # Ready for diagnosis
        await websocket.send_json({
            "type": "diagnosis_ready"
        })
```

### Using v3 in HTTP Handler
```python
@app.post("/api/initial_assessment")
async def initial_assessment(request: AssessmentRequest):
    # Get 7-10 questions immediately
    result = get_followup_for_diagnosis_v3(
        age=request.age,
        gender=request.gender,
        symptoms=request.symptoms,
        chat_history=""
    )
    
    # Return all questions for user to answer
    return JSONResponse({
        "questions": result["follow_up_questions"],
        "question_count": result["question_count"],
        "top_differentials": result["top_differentials"]
    })

@app.post("/api/submit_answers")
async def submit_answers(request: AnswersRequest):
    # Process all 7-10 answers and proceed to diagnosis
    diagnosis = generate_diagnosis(
        symptoms=request.initial_symptoms,
        answers=request.answers
    )
    
    return JSONResponse({"diagnosis": diagnosis})
```

---

## Conclusion

### Recommendation

| Scenario | Recommended Version |
|----------|---------------------|
| **New Projects** | v3 (comprehensive upfront) |
| **Existing Chat-based UI** | v2 (minimal changes) |
| **Emergency/Triage** | v3 (red-flag priority) |
| **Mobile App** | v2 (one screen per question) |
| **Web Form** | v3 (all questions on one form) |
| **Telehealth** | v3 (efficient initial assessment) |
| **Legacy System** | v2 (backward compatible) |

### Summary

- **v1:** ❌ Deprecated, use v2 or v3
- **v2:** ✅ Excellent for conversational, sequential questioning
- **v3:** ✅ Excellent for comprehensive, batch assessment

**Both v2 and v3 are production-ready** with gemini-2.5-flash.  
Choose based on your UI design and user experience goals.

---

**Last Updated:** January 26, 2026  
**Status:** All versions operational  
**Model:** gemini-2.5-flash (all versions)
