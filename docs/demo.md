# ComplyFlow Demo Script & NovaTech Regression Guide

## 1. Scenario: NovaTech Vendor Certification Program

**Goal**: Demonstrate how ComplyFlow autonomously transforms a compliance package from **75% ACTION REQUIRED** to **100% READY TO SUBMIT**.

### Step 1: Initial Upload & Analysis
1. Open ComplyFlow (`http://localhost:5173`)
2. Click **"+ New Compliance Check"** or **"Start Compliance Check"**
3. Click **"Load NovaTech Demo (1-Click)"** (or upload `requirements.txt` + evidence files)
4. The system automatically launches the **Google ADK Agent**

### Step 2: Live Agent Workspace
Observe the live **Agent Workspace UI**:
- `extract_requirements`: Extracted 12 requirements from NovaTech Vendor Certification
- `analyze_documents`: Analyzed supporting documents with section/chunk awareness
- `match_evidence`: 9 Satisfied, 2 Missing, 1 Conflict
- `detect_gaps`: Identified 3 compliance gaps
- `create_remediation_plan`: Created 3 prioritized remediation tasks

**Initial Result (Run 1 Snapshot)**:
- Score: **75.0%**
- Status: **ACTION REQUIRED**
- Breakdown: 9 Satisfied, 2 Missing (Insurance Cert, DPA), 1 Conflict (Company Address Suite 400 vs Suite 800)

### Step 3: Prioritized Remediation Plan
1. Switch to the **Remediation Plan** tab.
2. Observe the top 3 action items:
   - **CRITICAL**: Upload Insurance Certificate (USD 2,000,000 limit)
   - **CRITICAL**: Upload signed Data Processing Agreement (DPA)
   - **HIGH**: Reconcile company address discrepancy (Suite 400 in profile vs Suite 800 in registration)

### Step 4: Re-Verification & 100% Verdict (Run 2 Snapshot)
1. Click **"Upload Missing Evidence"**
2. Click **"Auto-Upload Demo Fix & Re-Verify"** (or upload `remediation_insurance_certificate.txt`, `remediation_data_processing_agreement.txt`, `remediation_company_profile_corrected.txt`)
3. The ADK Agent runs `analyze_documents` on the updated document set and executes `verify_compliance`.
4. **Final Result**:
   - Score: **100.0%**
   - Status: **READY**
   - 12/12 Requirements Satisfied
   - 0 Unresolved Issues

---

## 2. Automated Regression Benchmark Guarantees

The automated regression test (`backend/test_novatech_regression.py`) asserts the following deterministic guarantees:

1. **Evidence-First Grounding Principle**:
   - Every AI-attributed quote is strictly verified against source text.
   - Missing requirements are strictly enforced to have `evidence = []`.
   - Zero hallucinated quotes are presented to the user.

2. **Immutable Point-in-Time Snapshots**:
   - Initial analysis is permanently preserved as `run_1`.
   - Final verification is permanently preserved as `run_2`.
   - `run_1` is never overwritten or mutated when new files are uploaded.

3. **Deterministic Comparative Delta**:
   - Score Progression: `75.0% → 100.0%` (`score_diff = +25.0%`)
   - Status Transition: `ACTION_REQUIRED → READY`
   - Resolved Count: `3` (`REQ-003`, `REQ-006`, `REQ-010`)
   - Newly Failed Count: `0`
   - Unchanged Count: `9`

### Running the Regression Test

```bash
cd backend
pytest test_novatech_regression.py -v
```
