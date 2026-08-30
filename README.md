# ComplyFlow

> Autonomous AI Compliance Agent
> *"From requirements to ready-to-submit. Autonomously."*

Built for the **All Things Agentic Hackathon**.

---

## 1. Overview

**ComplyFlow** is an autonomous compliance verification agent designed to tackle document-heavy application and certification workflows. Users upload a requirements document (PDF, TXT, DOCX) alongside supporting evidence files (certificates, policies, statements, forms). 

Rather than acting as a generic QA chatbot, ComplyFlow acts as an **Action-Oriented Agent**:
- Extracts structured requirements
- Analyzes supporting evidence documents
- Maps evidence to requirements
- Detects missing evidence, expired documents, and cross-document inconsistencies
- Generates a prioritized step-by-step remediation plan
- Re-verifies the package after corrections to deliver a final **READY TO SUBMIT** or **ACTION REQUIRED** verdict with audit trail

---

## 2. Problem

Organizational compliance submissions involve scattered PDFs, policies, forms, and financial statements. Manually verifying every single requirement against every document is slow, repetitive, and error-prone. Generic AI chat tools stop at text summarization. ComplyFlow automates the end-to-end verification lifecycle:

**Goal → Plan → Analyze → Act → Verify → Result**

---

## 3. Solution

ComplyFlow uses **Google ADK** (Agent Development Kit 2.8.0) and **Gemini 3.5+** to autonomously orchestrate 6 specialized compliance tools:
1. `extract_requirements`: Interprets requirement text into structured JSON models
2. `analyze_documents`: Extracts facts, dates, entities, and evidence statements
3. `match_evidence`: Maps evidence to requirements (SATISFIED, PARTIAL, MISSING, CONFLICT)
4. `detect_gaps`: Classifies gaps by severity (CRITICAL, HIGH, MEDIUM, LOW)
5. `create_remediation_plan`: Generates actionable remediation tasks
6. `verify_compliance`: Performs post-remediation verification

---

## 4. Agent Workflow

```
User Uploads Package
         │
         ▼
 ┌──────────────────────┐
 │   Google ADK Agent   │
 └──────────┬───────────┘
            │
            ├──► Tool 1: extract_requirements
            ├──► Tool 2: analyze_documents
            ├──► Tool 3: match_evidence
            ├──► Tool 4: detect_gaps
            └──► Tool 5: create_remediation_plan
            │
            ▼
 Initial Result: 75% Score (ACTION REQUIRED)
            │
            ▼
 User Uploads Remediation Evidence
            │
            ▼
 ┌──────────────────────┐
 │ Re-Verification Run  │
 └──────────┬───────────┘
            │
            ├──► Tool 2: analyze_documents (updated set)
            └──► Tool 6: verify_compliance
            │
            ▼
 Final Result: 100% Score (READY TO SUBMIT)
```

---

## 5. Architecture

- **Frontend**: React 18 + Vite + TailwindCSS + Lucide Icons + EventSource (SSE)
- **Backend**: Python 3.11 + FastAPI + Async Uvicorn
- **Agent Orchestrator**: **Google ADK 2.8.0** (`google-adk`)
- **LLM Reasoning**: **Gemini 3.5+** via `google-genai` SDK (`GEMINI_MODEL` configurable)
- **Document Engine**: `pypdf` (PDF), `python-docx` (DOCX), built-in UTF-8 parser (TXT)
- **Database**: **Google Cloud Firestore** (`google-cloud-firestore`)
- **Deployment**: Docker container prepared for **Google Cloud Run**

---

## 6. Google Technology Usage

- **Gemini 3.5+ / Gemini Flash**: Powers all document reasoning, evidence matching, gap detection, remediation planning, and verification logic using structured Pydantic schema enforcement.
- **Google ADK (Agent Development Kit)**: Orchestrates tool invocation, goal tracking, and agent reasoning loops.
- **Google Cloud Firestore**: Persists project state, requirements, matches, issues, tasks, and real-time agent execution events.
- **Google Cloud Run**: Serverless container hosting backend deployment.

---

## 7. Quick Demo (NovaTech Vendor Certification)

1. Start backend and frontend (see Local Setup below).
2. Open `http://localhost:5173`.
3. Click **"New Compliance Check"**.
4. Click **"Load NovaTech Demo (1-Click)"**.
5. Watch the live **Agent Workspace UI** as ADK executes tools via SSE.
6. Observe initial status: **75% — ACTION REQUIRED** (9 Satisfied, 2 Missing, 1 Conflict).
7. Click **"Upload Missing Evidence"** → **"Auto-Upload Demo Fix & Re-Verify"**.
8. Observe re-verification result: **100% — READY TO SUBMIT**.

---

## 8. Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- Gemini API Key ([Google AI Studio](https://aistudio.google.com))

### Backend Setup
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# Environment variables
cp ../.env.example .env
# Edit .env and add your GEMINI_API_KEY and GEMINI_MODEL (e.g. gemini-2.5-flash or eligible Gemini 3.5+ model)

# Run FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 9. Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google AI Studio API Key | *(Required)* |
| `GEMINI_MODEL` | Gemini model (Gemini 3.5+ / Flash) | `gemini-3.5-flash` |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID | `complyflow-demo` |
| `FIRESTORE_EMULATOR` | Use Firestore emulator locally | `false` |
| `BACKEND_PORT` | Backend port | `8000` |
| `VITE_API_BASE_URL` | Frontend API URL | `http://localhost:8000` |

---

## 10. Deployment (Cloud Run)

### Docker Build & Deploy
```bash
cd backend
docker build -t gcr.io/YOUR_PROJECT_ID/complyflow-backend:latest .
docker push gcr.io/YOUR_PROJECT_ID/complyflow-backend:latest

gcloud run deploy complyflow-api \
  --image gcr.io/YOUR_PROJECT_ID/complyflow-backend:latest \
  --platform managed \
  --region us-central1 \
  --set-env-vars GEMINI_API_KEY=YOUR_KEY,GEMINI_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID \
  --allow-unauthenticated
```

---

## 11. Hackathon & Attribution

Built for the **All Things Agentic Hackathon**.
Uses official Google technologies: Gemini, Google ADK, Google Cloud Firestore, and Cloud Run.
*(Note: Independent hackathon submission; not an official Google product).*
