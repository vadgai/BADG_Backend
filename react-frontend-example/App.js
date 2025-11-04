import React, { useState } from 'react';
import './App.css';

function App() {
  const [step, setStep] = useState('input'); // input, followup, complete
  const [patientData, setPatientData] = useState({
    name: '',
    age: '',
    gender: '',
    symptoms: ''
  });
  const [sessionId, setSessionId] = useState(null);
  const [question, setQuestion] = useState(null);
  const [options, setOptions] = useState([]);
  const [error, setError] = useState(null);
  const [socket, setSocket] = useState(null);

  // Handle input form changes
  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setPatientData(prev => ({
      ...prev,
      [name]: name === 'age' ? parseInt(value) || '' : value
    }));
  };

  // Submit symptoms to start diagnosis
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    try {
      const response = await fetch('http://127.0.0.1:8000/symptom', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(patientData)
      });

      const data = await response.json();
      
      if (response.ok) {
        setSessionId(data.session_id);
        setStep('followup');
        connectToFollowup(data.session_id);
      } else {
        setError(data.detail || 'Error submitting symptoms');
      }
    } catch (error) {
      setError('Network error: ' + error.message);
    }
  };

  // Connect to WebSocket for followup questions
  const connectToFollowup = (sid) => {
    const ws = new WebSocket(`ws://127.0.0.1:8000/followup/${sid}`);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.status === 'waiting_for_answer') {
        setQuestion(data.question);
        setOptions(data.options);
      } else if (data.status === 'ready_for_diagnosis') {
        setStep('complete');
        ws.close();
      } else if (data.error) {
        setError(data.error);
      }
    };
    
    ws.onerror = (error) => {
      setError('WebSocket error: ' + error.message);
    };
    
    setSocket(ws);
  };

  // Submit answer to followup question
  const submitAnswer = (key) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(key);
    }
  };

  // Download diagnosis report
  const downloadReport = () => {
    window.open(`http://127.0.0.1:8000/generate_report/${sessionId}`, '_blank');
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Medical Diagnosis System</h1>
      </header>

      <main>
        {error && (
          <div className="error-container">
            <p className="error-message">{error}</p>
            <button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}

        {step === 'input' && (
          <div className="patient-form-container">
            <h2>Enter Patient Information</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="name">Full Name</label>
                <input
                  type="text"
                  id="name"
                  name="name"
                  value={patientData.name}
                  onChange={handleInputChange}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="age">Age</label>
                <input
                  type="number"
                  id="age"
                  name="age"
                  value={patientData.age}
                  onChange={handleInputChange}
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="gender">Gender</label>
                <select
                  id="gender"
                  name="gender"
                  value={patientData.gender}
                  onChange={handleInputChange}
                  required
                >
                  <option value="">Select Gender</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="symptoms">Describe Your Symptoms</label>
                <textarea
                  id="symptoms"
                  name="symptoms"
                  value={patientData.symptoms}
                  onChange={handleInputChange}
                  rows="5"
                  required
                ></textarea>
              </div>

              <button type="submit" className="submit-button">Start Diagnosis</button>
            </form>
          </div>
        )}

        {step === 'followup' && (
          <div className="followup-container">
            <h2>Follow-up Questions</h2>
            {question && (
              <div className="question-container">
                <p className="question">{question}</p>
                <div className="options-container">
                  {options.map((option) => (
                    <button
                      key={option.key}
                      className="option-button"
                      onClick={() => submitAnswer(option.key)}
                    >
                      <span className="option-key">{option.key}</span>
                      <span className="option-value">{option.value}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {step === 'complete' && (
          <div className="complete-container">
            <h2>Diagnosis Complete</h2>
            <p>Thank you for using our Medical Diagnosis System.</p>
            <p>Your diagnosis report is ready.</p>
            <button onClick={downloadReport} className="download-button">
              Download Diagnosis Report
            </button>
            <button onClick={() => {
              setStep('input');
              setSessionId(null);
              setQuestion(null);
              setOptions([]);
              setPatientData({
                name: '',
                age: '',
                gender: '',
                symptoms: ''
              });
            }} className="new-diagnosis-button">
              Start New Diagnosis
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default App; 