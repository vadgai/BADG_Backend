# Medical Diagnosis System API Reference

This document outlines all available API endpoints for the Medical Diagnosis System. Use these endpoints to integrate with your frontend application.

## Base URL

```
http://127.0.0.1:8000
```

## Endpoints

### 1. Submit Patient Symptoms

Submits initial patient information and symptoms to begin the diagnosis process.

**Endpoint:** `POST /symptom`

**Request Body:**
```json
{
  "name": "string",
  "age": "integer",
  "gender": "string",
  "symptoms": "string"
}
```

**Example:**
```json
{
  "name": "John Doe",
  "age": 35,
  "gender": "male",
  "symptoms": "I have been experiencing headache, fever, and fatigue for the past 3 days"
}
```

**Response:**
```json
{
  "message": "Symptoms received",
  "status": "symptom_submitted",
  "session_id": "uuid-string"
}
```

**Notes:**
- The `session_id` is required for all subsequent API calls
- Store this value in your frontend application

### 2. Get Session Data

Retrieves all the current patient session data.

**Endpoint:** `GET /session/{session_id}`

**Parameters:**
- `session_id`: The UUID of the patient session (received from the symptoms submission)

**Response:**
```json
{
  "name": "string",
  "age": "integer",
  "gender": "string",
  "symptoms": ["string", "string", ...],
  "chat_history": []
}
```

### 3. Follow-up Questions (WebSocket)

Establishes a WebSocket connection for interactive follow-up questions.

**Endpoint:** `WebSocket /followup/{session_id}`

**Parameters:**
- `session_id`: The UUID of the patient session

**Connection Flow:**
1. Connect to the WebSocket
2. Receive initial question with multiple choice options
3. Send response (option key like "A", "B", "C", or "D")
4. Receive next question or diagnosis ready notification
5. Repeat steps 3-4 until diagnosis is ready

**Messages Received:**

Initial Question:
```json
{
  "question": "string",
  "options": [
    {"key": "A", "value": "string"},
    {"key": "B", "value": "string"},
    {"key": "C", "value": "string"},
    {"key": "D", "value": "string"}
  ],
  "status": "waiting_for_answer"
}
```

Diagnosis Ready:
```json
{
  "message": "Diagnosis is ready",
  "status": "ready_for_diagnosis"
}
```

**Messages to Send:**
- Send the option key (e.g., "A", "B", "C", or "D") as a plain text string

### 4. Generate Report

Generates and returns a PDF diagnosis report.

**Endpoint:** `GET /generate_report/{session_id}`

**Parameters:**
- `session_id`: The UUID of the patient session

**Response:**
- A PDF file containing the medical diagnosis report
- Content-Type: application/pdf

## Integration Example (JavaScript)

```javascript
// 1. Submit symptoms
async function submitSymptoms(patientData) {
  const response = await fetch('http://127.0.0.1:8000/symptom', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(patientData)
  });
  
  return await response.json();
}

// 2. Get session data
async function getSessionData(sessionId) {
  const response = await fetch(`http://127.0.0.1:8000/session/${sessionId}`);
  return await response.json();
}

// 3. Handle WebSocket connection for follow-up questions
function connectToFollowup(sessionId, onQuestion, onComplete, onError) {
  const socket = new WebSocket(`ws://127.0.0.1:8000/followup/${sessionId}`);
  
  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.status === 'waiting_for_answer') {
      onQuestion(data.question, data.options, (answer) => {
        socket.send(answer);
      });
    } else if (data.status === 'ready_for_diagnosis') {
      onComplete(data.message);
      socket.close();
    } else if (data.error) {
      onError(data.error);
    }
  };
  
  socket.onerror = (error) => {
    onError(error);
  };
  
  return socket;
}

// 4. Download the diagnosis report
function downloadReport(sessionId) {
  const reportUrl = `http://127.0.0.1:8000/generate_report/${sessionId}`;
  window.open(reportUrl, '_blank');
  // Alternatively for in-app download:
  // window.location.href = reportUrl;
}
```

## Error Handling

All endpoints return appropriate HTTP status codes:
- 200: Success
- 404: Session not found
- 500: Server error

Error responses include a detail message:
```json
{
  "detail": "error message"
}
```

## CORS Support

The API supports Cross-Origin Resource Sharing (CORS) with these settings:
- Allow all origins: `*`
- Allow credentials: `true`
- Allow all methods: `*`
- Allow all headers: `*`

This enables integration with frontend applications running on different domains or ports. 