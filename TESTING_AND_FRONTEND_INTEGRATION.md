# Testing & Frontend Integration Guide

Complete guide for testing the multilingual translation system and integrating it with the VADG frontend.

---

## 🚀 Quick Start - Testing Locally

### Step 1: Start Translation Service

```bash
# Navigate to translation-service directory
cd translation-service

# Install dependencies (first time only)
npm install

# Copy environment file
cp env.example.txt .env

# Edit .env and add your Hugging Face API key
# HF_API_KEY=hf_your_key_here

# Start translation service
npm run dev

# Or with Docker
docker-compose up --build
```

**Verify it's running:**
```bash
curl http://localhost:8080/healthz
# Should return: {"status":"ok","redis":"connected"}
```

---

### Step 2: Configure Backend

```bash
# Navigate to Backend directory
cd Backend

# Edit .env file (or create from env.example)
nano .env
```

**Add these lines to Backend/.env:**
```bash
# Translation Service Configuration
TRANSLATION_SERVICE_URL=http://localhost:8080
TRANSLATION_SERVICE_API_KEY=your_secure_api_key_here
TRANSLATION_SERVICE_TIMEOUT=15

# Gemini API (required for diagnosis)
GEMINI_API_KEY_1=your_gemini_key_here

# MongoDB (optional)
MONGODB_URL=mongodb://localhost:27017/
MONGODB_DATABASE=vadg_db
```

**Generate a secure API key:**
```bash
# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Using OpenSSL
openssl rand -base64 32
```

---

### Step 3: Start Backend

```bash
# In Backend directory
cd Backend

# Install dependencies (first time only)
pip install -r requirements.txt

# Start backend
python app.py

# Or use uvicorn
uvicorn app:app --reload --port 8000
```

**Verify it's running:**
```bash
curl http://localhost:8000/health
# Should return: {"status":"healthy",...}
```

---

### Step 4: Start Frontend

```bash
# Navigate to Frontend directory
cd Frontend

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

**Access frontend:**
- Open browser: `http://localhost:5173` (or the port shown in terminal)

---

## 🧪 Testing the Translation System

### Test 1: Translation Service Health

```bash
# Check translation service
curl http://localhost:8080/healthz

# Expected response:
{
  "status": "ok",
  "redis": "connected",
  "timestamp": "2025-11-09T..."
}
```

---

### Test 2: Direct Translation (Translation Service)

```bash
# Translate a simple text
curl -X POST http://localhost:8080/translate \
  -H "Content-Type: application/json" \
  -d '{
    "source_lang": "en",
    "target_lang": "hi",
    "text": "Please consult a doctor immediately"
  }'

# Expected response:
{
  "translation": "कृपया तुरंत डॉक्टर से परामर्श लें",
  "model_used": "indictrans2-distill-200M",
  "cached": false,
  "latency_ms": 156
}
```

**Test cache (run same request again):**
```bash
# Second request should be much faster (cached)
curl -X POST http://localhost:8080/translate \
  -H "Content-Type: application/json" \
  -d '{
    "source_lang": "en",
    "target_lang": "hi",
    "text": "Please consult a doctor immediately"
  }'

# Expected: cached: true, latency_ms: ~5
```

---

### Test 3: Backend Translation Proxy

```bash
# Get your API key from Backend/.env (TRANSLATION_SERVICE_API_KEY)
export API_KEY="your_api_key_here"

# Test proxy endpoint
curl -X POST http://localhost:8000/internal/translate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "source_lang": "en",
    "target_lang": "hi",
    "text": "Your blood pressure is normal"
  }'

# Expected response:
{
  "translation": "आपका रक्तचाप सामान्य है",
  "model_used": "indictrans2-distill-200M",
  "cached": false,
  "latency_ms": 178
}
```

---

### Test 4: Localized Report Builder

```bash
# Create a sample report
cat > test_report.json << 'EOF'
{
  "report": {
    "PatientInfo": {
      "Age": "30 Years",
      "Gender": "Male"
    },
    "Recommendation": "Schedule an appointment with a physician within 24 hours",
    "Urgency": "Moderate",
    "MainSymptoms": [
      "Fever",
      "Headache",
      "Body ache"
    ]
  },
  "target_lang": "hi"
}
EOF

# Test localization
curl -X POST http://localhost:8000/api/localize-report \
  -H "Content-Type: application/json" \
  -d @test_report.json

# Expected: Hindi localized report
```

---

### Test 5: Complete Diagnosis Flow with Localization

**Step 1: Create a diagnosis session**
```bash
curl -X POST http://localhost:8000/symptom \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Patient",
    "age": 30,
    "gender": "male",
    "symptoms": ["fever", "headache", "body ache"]
  }'

# Save the session_id from response
export SESSION_ID="abc123..."
```

**Step 2: Generate English report**
```bash
curl "http://localhost:8000/generate_report/$SESSION_ID"

# Returns: English diagnosis report
```

**Step 3: Generate Hindi report**
```bash
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=hi"

# Returns: Hindi diagnosis report (all patient-facing text translated)
```

**Step 4: Try other languages**
```bash
# Tamil
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=ta"

# Telugu
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=te"

# Bengali
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=bn"

# Kannada
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=kn"
```

---

## 🔗 Frontend Integration

### Option 1: Modify Existing Report Page

**Location**: `Frontend/src/pages/DiagnosisReport.tsx` (or similar)

**Add language selector:**

```typescript
import { useState } from 'react';

// Language options
const LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिंदी' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ' },
];

function DiagnosisReport({ sessionId }) {
  const [language, setLanguage] = useState('en');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  const generateReport = async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/generate_report/${sessionId}?lang=${language}`
      );
      
      if (!response.ok) {
        throw new Error('Failed to generate report');
      }
      
      const data = await response.json();
      setReport(data.report);
      
      console.log('Report language:', data.language);
      console.log('Report data:', data.report);
    } catch (error) {
      console.error('Error generating report:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="diagnosis-report">
      <h1>Diagnosis Report</h1>
      
      {/* Language Selector */}
      <div className="language-selector">
        <label htmlFor="language">Select Language:</label>
        <select
          id="language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="language-dropdown"
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.name} ({lang.nativeName})
            </option>
          ))}
        </select>
      </div>

      {/* Generate Report Button */}
      <button
        onClick={generateReport}
        disabled={loading}
        className="btn-primary"
      >
        {loading ? 'Generating...' : 'Generate Report'}
      </button>

      {/* Display Report */}
      {report && (
        <div className="report-content">
          {/* Patient Info */}
          <section>
            <h2>Patient Information</h2>
            <p>Age: {report.PatientInfo?.Age}</p>
            <p>Gender: {report.PatientInfo?.Gender}</p>
          </section>

          {/* Recommendation */}
          <section>
            <h2>Recommendation</h2>
            <p>{report.Recommendation}</p>
            <p><strong>Urgency:</strong> {report.Urgency}</p>
          </section>

          {/* Main Symptoms */}
          <section>
            <h2>Main Symptoms</h2>
            <ul>
              {report.MainSymptoms?.map((symptom, idx) => (
                <li key={idx}>{symptom}</li>
              ))}
            </ul>
          </section>

          {/* Diagnostic Steps */}
          {report.NextDiagnosticSteps && (
            <section>
              <h2>Next Diagnostic Steps</h2>
              <ul>
                {report.NextDiagnosticSteps.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Diseases */}
          {report.TopDiseaseMatches && (
            <section>
              <h2>Possible Conditions</h2>
              {report.TopDiseaseMatches.map((disease, idx) => {
                const diseaseData = Object.values(disease)[0];
                return (
                  <div key={idx} className="disease-card">
                    <h3>{diseaseData.Name1}</h3>
                    <p><strong>Match Level:</strong> {diseaseData.MatchLevel1}</p>
                    
                    {diseaseData.PreHospitalCare1 && (
                      <div>
                        <h4>Pre-Hospital Care</h4>
                        <ul>
                          {diseaseData.PreHospitalCare1.map((care, i) => (
                            <li key={i}>{care}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {diseaseData.SymptomsToWatch1 && (
                      <div>
                        <h4>Symptoms to Watch</h4>
                        <ul>
                          {diseaseData.SymptomsToWatch1.map((symptom, i) => (
                            <li key={i}>{symptom}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

export default DiagnosisReport;
```

---

### Option 2: Create Standalone Language Selector Component

**File**: `Frontend/src/components/LanguageSelector.tsx`

```typescript
import React from 'react';

interface Language {
  code: string;
  name: string;
  nativeName: string;
  flag?: string;
}

const SUPPORTED_LANGUAGES: Language[] = [
  { code: 'en', name: 'English', nativeName: 'English', flag: '🇬🇧' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिंदी', flag: '🇮🇳' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', flag: '🇮🇳' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', flag: '🇮🇳' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', flag: '🇮🇳' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', flag: '🇮🇳' },
];

interface LanguageSelectorProps {
  value: string;
  onChange: (languageCode: string) => void;
  className?: string;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  value,
  onChange,
  className = '',
}) => {
  return (
    <div className={`language-selector ${className}`}>
      <label htmlFor="language-select" className="text-sm font-medium">
        Report Language:
      </label>
      <select
        id="language-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
      >
        {SUPPORTED_LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.flag} {lang.name} ({lang.nativeName})
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs text-gray-500">
        Select your preferred language for the diagnosis report
      </p>
    </div>
  );
};

export default LanguageSelector;
```

**Usage:**
```typescript
import LanguageSelector from '@/components/LanguageSelector';

function MyPage() {
  const [language, setLanguage] = useState('en');
  
  return (
    <div>
      <LanguageSelector
        value={language}
        onChange={setLanguage}
      />
      
      {/* Rest of your page */}
    </div>
  );
}
```

---

### Option 3: Add to Existing API Service

**File**: `Frontend/src/services/api.ts` (or create if doesn't exist)

```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface DiagnosisReport {
  PatientInfo: {
    Age: string;
    Gender: string;
  };
  Recommendation: string;
  Urgency: string;
  MainSymptoms: string[];
  NextDiagnosticSteps?: string[];
  TopDiseaseMatches?: any[];
  // Add other fields as needed
}

export interface GenerateReportResponse {
  patient_details: {
    name: string;
    age: number;
    gender: string;
  };
  report: DiagnosisReport;
  session_id: string;
  language: string;
  generated_at: string;
}

/**
 * Generate diagnosis report in specified language
 */
export async function generateReport(
  sessionId: string,
  language: string = 'en'
): Promise<GenerateReportResponse> {
  const response = await fetch(
    `${API_BASE_URL}/generate_report/${sessionId}?lang=${language}`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to generate report: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Localize an existing report
 */
export async function localizeReport(
  report: DiagnosisReport,
  targetLang: string
): Promise<DiagnosisReport> {
  const response = await fetch(
    `${API_BASE_URL}/api/localize-report`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        report,
        target_lang: targetLang,
      }),
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to localize report: ${response.statusText}`);
  }
  
  const data = await response.json();
  return data.localized_report;
}

/**
 * Check if translation service is healthy
 */
export async function checkTranslationHealth(): Promise<boolean> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/localize-report/health`
    );
    const data = await response.json();
    return data.status === 'healthy';
  } catch {
    return false;
  }
}
```

**Usage in component:**
```typescript
import { generateReport } from '@/services/api';

async function handleGenerateReport() {
  try {
    const data = await generateReport(sessionId, selectedLanguage);
    setReport(data.report);
    console.log('Report generated in:', data.language);
  } catch (error) {
    console.error('Error:', error);
  }
}
```

---

## 🎨 Styling the Language Selector

### TailwindCSS Example

```tsx
<div className="w-full max-w-md mx-auto">
  <label className="block text-sm font-medium text-gray-700 mb-2">
    Select Report Language
  </label>
  <select
    value={language}
    onChange={(e) => setLanguage(e.target.value)}
    className="block w-full px-4 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
  >
    <option value="en">🇬🇧 English</option>
    <option value="hi">🇮🇳 हिंदी (Hindi)</option>
    <option value="ta">🇮🇳 தமிழ் (Tamil)</option>
    <option value="te">🇮🇳 తెలుగు (Telugu)</option>
    <option value="bn">🇮🇳 বাংলা (Bengali)</option>
    <option value="kn">🇮🇳 ಕನ್ನಡ (Kannada)</option>
  </select>
</div>
```

### Custom CSS

```css
/* styles/language-selector.css */
.language-selector {
  margin: 20px 0;
}

.language-selector label {
  display: block;
  font-weight: 600;
  margin-bottom: 8px;
  color: #374151;
}

.language-selector select {
  width: 100%;
  padding: 10px 12px;
  font-size: 16px;
  border: 2px solid #d1d5db;
  border-radius: 8px;
  background-color: white;
  cursor: pointer;
  transition: all 0.2s ease;
}

.language-selector select:hover {
  border-color: #6366f1;
}

.language-selector select:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.language-selector select option {
  padding: 10px;
}
```

---

## 🐛 Troubleshooting

### Issue 1: "Translation Service not available"

**Check:**
```bash
# Is translation service running?
curl http://localhost:8080/healthz

# If not, start it:
cd translation-service
npm run dev
```

### Issue 2: "502 translation failed"

**Check:**
1. Translation service API key is set in Backend/.env
2. Translation service is accessible from backend
3. Redis is running (required for translation service)

```bash
# Check Redis
redis-cli ping
# Should return: PONG

# If Redis not running:
redis-server
# Or with Docker:
docker run -d -p 6379:6379 redis:6-alpine
```

### Issue 3: "Report still in English after selecting Hindi"

**Check:**
1. Language parameter is being sent: `?lang=hi`
2. Check browser network tab for the request URL
3. Check backend logs for localization attempts

```bash
# Check backend logs
tail -f logs/backend.log

# Should see:
# "Localizing report for session abc123 to language: hi"
# "✅ Report localized successfully to hi"
```

### Issue 4: CORS Errors in Frontend

**Add to Backend/.env:**
```bash
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173
```

### Issue 5: Slow Translation (>10 seconds)

**Check:**
1. Translation service timeout setting
2. Network latency between backend and translation service
3. Hugging Face API rate limits

**Increase timeout if needed:**
```bash
# In Backend/.env
TRANSLATION_SERVICE_TIMEOUT=30
```

---

## 📊 Monitoring Translation Usage

### Check Translation Service Metrics

```bash
curl http://localhost:8080/metrics

# Look for:
# translation_requests_total{result="success",cached="false"} 42
# translation_requests_total{result="success",cached="true"} 128
# translation_cache_hits_total 128
```

### Check Backend Logs

```bash
# View localization logs
grep "Localizing report" logs/backend.log

# View successful localizations
grep "✅ Report localized" logs/backend.log

# View failed localizations
grep "Failed to localize" logs/backend.log
```

---

## 🎬 Complete Test Scenario

### Full End-to-End Test

```bash
# 1. Start all services
cd translation-service && npm run dev &
cd Backend && python app.py &
cd Frontend && npm run dev &

# 2. Wait for services to start (30 seconds)
sleep 30

# 3. Create diagnosis session
SESSION_ID=$(curl -s -X POST http://localhost:8000/symptom \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Patient",
    "age": 30,
    "gender": "male",
    "symptoms": ["fever", "headache"]
  }' | jq -r '.session_id')

echo "Session ID: $SESSION_ID"

# 4. Generate English report
curl "http://localhost:8000/generate_report/$SESSION_ID" | jq .

# 5. Generate Hindi report
curl "http://localhost:8000/generate_report/$SESSION_ID?lang=hi" | jq .

# 6. Open frontend
open http://localhost:5173
```

---

## 📝 Environment Variables Checklist

### Translation Service (translation-service/.env)
```bash
✅ HF_API_KEY=hf_your_key_here
✅ HF_200M_ENDPOINT_URL=https://api-inference.huggingface.co/...
✅ REDIS_URL=redis://localhost:6379
✅ CACHE_TTL_SECONDS=86400
✅ PORT=8080
✅ TIMEOUT_MS=8000
```

### Backend (Backend/.env)
```bash
✅ TRANSLATION_SERVICE_URL=http://localhost:8080
✅ TRANSLATION_SERVICE_API_KEY=your_generated_key
✅ TRANSLATION_SERVICE_TIMEOUT=15
✅ GEMINI_API_KEY_1=your_gemini_key
✅ MONGODB_URL=mongodb://localhost:27017/
✅ ALLOWED_ORIGINS=http://localhost:5173,...
```

### Frontend (Frontend/.env)
```bash
✅ VITE_API_URL=http://localhost:8000
```

---

## 🎉 Success Indicators

You'll know it's working when:

1. ✅ Translation service `/healthz` returns `{"status":"ok"}`
2. ✅ Backend `/health` returns `{"status":"healthy"}`
3. ✅ English report generates successfully
4. ✅ Hindi report shows translated text (not English)
5. ✅ Second request is faster (cache working)
6. ✅ Frontend language selector changes report language
7. ✅ PDF downloads in selected language

---

**Need help?** Check the logs and verify all services are running! 🚀

