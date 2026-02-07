# Clinical Follow-Up Question Engine - Design Specification

## Core Principles

1. **ALWAYS Generate Questions**: No empty responses allowed
2. **Clinical Precision**: Each question must differentiate between top competing diagnoses
3. **Structured Output**: Mandatory JSON format with clinical reasoning metadata
4. **Fallback Strategy**: Multi-layer fallback to ensure continuity

## Prompt Architecture

### Stage 1: Differential Diagnosis Analysis
```
INPUT: Symptoms + Patient Context + Conversation History
↓
ANALYZE: Pattern recognition → Identify top 3 probable diseases
↓
COMPARE: What single clinical feature best differentiates them?
↓
OUTPUT: Targeted question about that feature
```

### Stage 2: Clinical Reasoning Framework

**Priority Order for Questions:**
1. RED FLAGS (life-threatening signs)
2. PATHOGNOMONIC FEATURES (disease-specific symptoms)
3. TEMPORAL PATTERNS (onset, duration, progression)
4. SEVERITY INDICATORS (impact on daily function)
5. ASSOCIATED SYMPTOMS (constellation patterns)
6. RISK FACTORS (demographics, exposures, comorbidities)

### Stage 3: Question Quality Criteria

✅ **Good Question:**
- "Does the headache worsen when bending forward or lying flat?" 
  - Differentiates: Sinusitis vs Migraine vs Intracranial pressure
  
✅ **Good Question:**
- "Is there blood or coffee-ground material in vomit?"
  - Differentiates: GI bleeding vs Gastritis vs Food poisoning

❌ **Bad Question:**
- "Any other symptoms?" (too vague)
- "How are you feeling?" (doesn't differentiate)
- "Do you have pain?" (already answered)

## JSON Output Format (MANDATORY)

```json
{
  "follow_up_questions": [
    {
      "id": 1,
      "question": "Clinical question text in patient-friendly language",
      "clinical_purpose": "What this question helps determine",
      "differentiates_between": ["Disease A", "Disease B", "Disease C"],
      "red_flag_assessment": true|false,
      "options": {
        "A": "Option text pointing to Disease A",
        "B": "Option text pointing to Disease B", 
        "C": "Option text pointing to Disease C",
        "D": "None of these"
      }
    }
  ],
  "confidence_level": "low|medium|high",
  "questions_remaining": 8,
  "top_differentials": ["Disease 1", "Disease 2", "Disease 3"],
  "ready_for_diagnosis": false
}
```

## Fallback Logic Layers

### Layer 1: Gemini API with Multi-Key Fallback
- Try all configured API keys (up to 15)
- Temperature: 0.3 (consistent but not deterministic)
- Max tokens: 1500

### Layer 2: Symptom-Pattern Fallback
If ALL API keys fail, generate questions based on symptom patterns:

**Pattern: Fever Present**
→ "Do you have a cough along with the fever?"
→ Differentiates: URI vs Pneumonia vs Flu vs Dengue

**Pattern: Pain Present**
→ "Is the pain sharp/stabbing or dull/aching?"
→ Differentiates: Inflammatory vs Neuropathic vs Musculoskeletal

**Pattern: GI Symptoms**
→ "Is there blood in stool or vomit?"
→ Differentiates: Infection vs Ulcer vs IBD

### Layer 3: Generic Safety Questions
Last resort - still clinically useful:
- "Has this symptom started suddenly or gradually?"
- "Is the symptom constant or intermittent?"
- "Does anything make it better or worse?"

## Decision Rules

### Rule 1: When to Continue Asking
```python
if question_count < 5:
    # Always ask more - insufficient data
    continue_questioning = True
elif question_count < 10 and confidence < 0.75:
    # Medium phase - ask if confidence low
    continue_questioning = True
else:
    # Ready for diagnosis
    continue_questioning = False
```

### Rule 2: Confidence Calculation
```python
confidence = min(1.0, (
    answered_red_flags * 0.3 +
    answered_pathognomonic * 0.3 +
    temporal_clarity * 0.2 +
    severity_assessed * 0.2
))
```

### Rule 3: Question Deduplication
- Check conversation history
- Never repeat a question
- Never ask what's already answered

## Implementation Notes

1. **Parse Robustness**: Handle markdown, code fences, malformed JSON
2. **Timeout Protection**: Max 10s per API call
3. **Logging**: Log ALL raw responses for debugging
4. **Error Recovery**: NEVER crash - always provide fallback question
5. **Option D**: Always "None of these" - allows escape hatch

## Testing Scenarios

### Scenario 1: Clear Pattern
```
Input: "fever, cough, body ache"
Top Differentials: Flu, COVID-19, Pneumonia
Question: "Do you have difficulty breathing or chest pain?"
Differentiates: Pneumonia from Flu/COVID
```

### Scenario 2: Vague Pattern
```
Input: "stomach pain"
Top Differentials: Gastritis, Appendicitis, IBS, Gastroenteritis
Question: "Where exactly is the pain located?"
→ "A: Right lower abdomen"  → Appendicitis
→ "B: Upper center/left"     → Gastritis/Ulcer
→ "C: Cramping all over"     → IBS/Gastroenteritis
```

### Scenario 3: Red Flag Detection
```
Input: "severe headache, confusion"
Top Differentials: Migraine, Meningitis, Stroke, Intracranial bleed
Question: "Do you have fever, stiff neck, or sensitivity to light?"
RED FLAG: Meningitis vs other causes
```

## Performance Metrics

- **Success Rate**: >99% (with fallbacks)
- **Avg Generation Time**: <2s
- **Clinical Relevance Score**: Manual review by physicians
- **Question Redundancy Rate**: <5%
- **Diagnostic Accuracy Improvement**: Measure pre/post questions

## Maintenance

- **Weekly Review**: Check logs for failed generations
- **Monthly Update**: Refine prompt based on physician feedback
- **Quarterly Audit**: Validate against clinical guidelines
