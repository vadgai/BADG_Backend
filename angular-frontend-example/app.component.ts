import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

interface PatientData {
  name: string;
  age: number;
  gender: string;
  symptoms: string;
}

interface Option {
  key: string;
  value: string;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Medical Diagnosis System';
  patientForm: FormGroup;
  currentView: 'input' | 'followup' | 'complete' = 'input';
  sessionId: string | null = null;
  question: string | null = null;
  options: Option[] = [];
  error: string | null = null;
  socket: WebSocket | null = null;
  
  private readonly API_URL = 'http://127.0.0.1:8000';

  constructor(
    private fb: FormBuilder,
    private http: HttpClient
  ) {
    this.patientForm = this.fb.group({
      name: ['', Validators.required],
      age: ['', [Validators.required, Validators.min(0), Validators.max(120)]],
      gender: ['', Validators.required],
      symptoms: ['', [Validators.required, Validators.minLength(10)]]
    });
  }

  ngOnInit(): void {
    // Initialize any resources if needed
  }

  ngOnDestroy(): void {
    // Close WebSocket connection if open
    if (this.socket) {
      this.socket.close();
    }
  }

  submitSymptoms(): void {
    if (this.patientForm.invalid) {
      this.markFormGroupTouched(this.patientForm);
      return;
    }

    this.error = null;
    
    const patientData: PatientData = {
      name: this.patientForm.value.name,
      age: this.patientForm.value.age,
      gender: this.patientForm.value.gender,
      symptoms: this.patientForm.value.symptoms
    };

    this.http.post<any>(`${this.API_URL}/symptom`, patientData)
      .subscribe({
        next: (response) => {
          this.sessionId = response.session_id;
          this.currentView = 'followup';
          this.connectToFollowup(response.session_id);
        },
        error: (error) => {
          this.error = error.error?.detail || 'Error submitting symptoms. Please try again.';
        }
      });
  }

  connectToFollowup(sessionId: string): void {
    this.socket = new WebSocket(`ws://127.0.0.1:8000/followup/${sessionId}`);
    
    this.socket.onopen = () => {
      console.log('WebSocket connected');
    };
    
    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.status === 'waiting_for_answer') {
        this.question = data.question;
        this.options = data.options;
      } else if (data.status === 'ready_for_diagnosis') {
        this.currentView = 'complete';
        this.socket?.close();
        this.socket = null;
      } else if (data.error) {
        this.error = data.error;
      }
    };
    
    this.socket.onerror = (error) => {
      this.error = 'WebSocket error: Unable to connect to the diagnosis server.';
    };
  }

  submitAnswer(key: string): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(key);
    }
  }

  downloadReport(): void {
    if (!this.sessionId) return;
    
    window.open(`${this.API_URL}/generate_report/${this.sessionId}`, '_blank');
  }

  startNewDiagnosis(): void {
    this.currentView = 'input';
    this.sessionId = null;
    this.question = null;
    this.options = [];
    this.patientForm.reset();
    
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  dismissError(): void {
    this.error = null;
  }

  // Helper method to mark all controls as touched
  private markFormGroupTouched(formGroup: FormGroup): void {
    Object.values(formGroup.controls).forEach(control => {
      control.markAsTouched();
      
      if ((control as any).controls) {
        this.markFormGroupTouched(control as FormGroup);
      }
    });
  }
} 