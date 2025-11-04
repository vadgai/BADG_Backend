# Medical Diagnosis System - React Frontend

This is a React frontend for the Medical Diagnosis API. It provides a user-friendly interface for patients to input their symptoms and receive a medical diagnosis.

## Features

- Patient information form
- Real-time follow-up questions via WebSocket
- PDF report download
- Responsive design

## Prerequisites

- Node.js (v14 or later)
- npm or yarn
- Medical Diagnosis API running on http://127.0.0.1:8000

## Installation

1. Clone this repository
2. Navigate to the project directory
3. Install dependencies:

```bash
npm install
# or
yarn install
```

## Running the Development Server

```bash
npm start
# or
yarn start
```

The development server will start at http://localhost:3000

## Building for Production

```bash
npm run build
# or
yarn build
```

This will create a `build` directory with optimized production files.

## Integration with Medical Diagnosis API

This frontend is designed to work with the Medical Diagnosis API. Make sure the API is running at http://127.0.0.1:8000 before using this application.

The API provides:
- Symptom submission
- Follow-up questions via WebSocket
- Diagnosis report generation

## Workflow

1. Enter patient information and symptoms
2. Answer follow-up questions
3. Download the diagnosis report

## Customization

You can customize the appearance by modifying the `App.css` file.

## License

MIT

## Acknowledgements

This frontend was created to work with the Medical Diagnosis System API. 