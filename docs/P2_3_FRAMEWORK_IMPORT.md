# ComplyFlow — Custom Compliance Framework Importer (P2 #3)

## 1. Executive Summary

ComplyFlow P2 #3 introduces a production-grade **Custom Compliance Framework Importer** that enables enterprise administrators and auditors to ingest, pre-validate, version, and apply organization-specific or industry-specific compliance frameworks directly into workspace projects.

Instead of being restricted to built-in templates (ISO 27001, GDPR, SOC 2), organizations can now import their internal control standards, custom spreadsheets, or regulatory frameworks formatted in **JSON**, **CSV**, or **Excel (.xlsx)**.

---

## 2. Architecture & Design Principles

### Local-First & Zero-Cloud Infrastructure
- Preserves the local-first architecture: SQLite database + Local filesystem document storage + Google ADK + Gemini API.
- No Google Cloud, Vertex AI, Cloud SQL, or Cloud Storage dependency.
- Ingestion of `.xlsx` files is implemented purely with the Python standard library (`zipfile` + `xml.etree.ElementTree`) with **zero external heavy dependencies**.

### Two-Step Ingestion Workflow (Preview -> Confirm)
Ingestion enforces strict separation between parsing/validation and database persistence:
1. **Step 1: Upload & Pre-Validate (`POST /api/projects/{id}/frameworks/preview`)**:
   - Parses the uploaded file.
   - Applies formula injection neutralization and data validation.
   - Computes requirement counts, severity breakdowns, category distributions, and sample rows.
   - **Nothing is written to database storage.**
   - Emits `FRAMEWORK_IMPORT_VALIDATED` (or `FRAMEWORK_IMPORT_FAILED` on invalid input) to the immutable audit timeline.
2. **Step 2: Explicit Confirmation (`POST /api/projects/{id}/frameworks/import`)**:
   - The user reviews the parsed preview metrics and sample requirements.
   - Upon explicit confirmation, the framework metadata and normalized control definitions are atomically saved to the database.
   - Emits `FRAMEWORK_IMPORTED` audit event.

---

## 3. Data Model & Storage Schema

### `frameworks` Table
| Column | Type | Description |
| :--- | :--- | :--- |
| `framework_id` | TEXT PRIMARY KEY | Unique UUID identifier |
| `project_id` | TEXT | Scoped project ID or null for global |
| `name` | TEXT NOT NULL | Framework display name |
| `version` | TEXT NOT NULL | Version string (e.g. `1.0`, `2.1`) |
| `description` | TEXT | Overview description |
| `source` | TEXT | Import source (e.g. `JSON Import`, `Excel XLSX`) |
| `status` | TEXT NOT NULL | `ACTIVE`, `INACTIVE`, or `DRAFT` |
| `requirement_count` | INTEGER NOT NULL | Total number of requirements |
| `created_by` | TEXT | User ID of the importer |
| `created_at` | TEXT NOT NULL | ISO 8601 UTC timestamp |
| `updated_at` | TEXT NOT NULL | ISO 8601 UTC timestamp |
| `metadata_json` | TEXT | Custom metadata / breakdowns JSON |
| **Constraint** | `UNIQUE(name, version)` | Guarantees framework version immutability |

### `framework_requirements` Table
| Column | Type | Description |
| :--- | :--- | :--- |
| `framework_id` | TEXT NOT NULL | Foreign key to `frameworks.framework_id` |
| `requirement_id` | TEXT NOT NULL | Normalized unique requirement ID within framework |
| `title` | TEXT NOT NULL | Control title (min 3 chars, max 256) |
| `description` | TEXT NOT NULL | Control requirements description (max 4000) |
| `category` | TEXT | Category / domain classification |
| `severity` | TEXT NOT NULL | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `priority` | TEXT NOT NULL | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `guidance` | TEXT | Guidance or required evidence criteria |
| `source_reference` | TEXT | External clause or section reference |
| `data_json` | TEXT | Raw metadata JSON |
| **Constraint** | `PRIMARY KEY(framework_id, requirement_id)` | Enforces unique control ID per framework |

---

## 4. Security Controls & Defenses

### 1. Spreadsheet Formula Injection Neutralization
All incoming string values across JSON, CSV, and XLSX are sanitized by `sanitize_formula_injection`:
- Leading formula trigger prefixes (`=`, `+`, `-`, `@`, `\t`, `\r`) are iteratively stripped.
- Prevents CSV/Excel formula injection (DDE attacks) when spreadsheets are exported or viewed by auditors in Excel.
- Null bytes (`\x00`) and control characters are stripped.

### 2. Prompt Injection Defense
- Imported framework control titles, descriptions, and guidance are strictly treated as **DATA**, never as instructions to the AI agent.
- During AI compliance evaluation, system instructions maintain strict priority boundary over user-supplied framework data.
- Unit and adversarial tests verify that embedded instructions (e.g., `"Ignore previous instructions"`, `"[INST] SYSTEM: ..."`) are stored inert and treated as pure evaluation criteria.

### 3. Historical Verification Run Snapshot Immutability
- Point-in-time verification runs record `framework_id`, `framework_name`, and `framework_version` immutably in their snapshot payloads.
- Deletion guard: `storage.is_framework_referenced_in_runs(framework_id)` prevents deletion of any framework that has been referenced in a completed audit run.
- Attempting to delete a referenced framework returns `400 Bad Request` with an explicit governance rejection message.

---

## 5. RBAC Permission Matrix

| Role | `frameworks:view` | `frameworks:import` | `frameworks:apply` | `frameworks:manage` |
| :--- | :---: | :---: | :---: | :---: |
| **ADMIN** | ✅ | ✅ | ✅ | ✅ |
| **AUDITOR** | ✅ | ✅ | ✅ | ❌ |
| **REVIEWER** | ✅ | ❌ | ❌ | ❌ |
| **VIEWER** | ✅ | ❌ | ❌ | ❌ |

- **`frameworks:import`**: Upload, pre-validate, and confirm framework imports.
- **`frameworks:apply`**: Apply framework requirements to a project workspace.
- **`frameworks:manage`**: Activate/deactivate frameworks or delete unused frameworks.
- **`frameworks:view`**: View available frameworks and control definitions.

---

## 6. Audit Trail Integration

The immutable audit log tracks the complete framework lifecycle:
- `FRAMEWORK_IMPORT_VALIDATED` — Emitted when a preview is parsed and validated.
- `FRAMEWORK_IMPORT_FAILED` — Emitted with error details if validation fails.
- `FRAMEWORK_IMPORTED` — Emitted when a framework is confirmed and stored.
- `FRAMEWORK_APPLIED` — Emitted when a framework is applied to a project workspace.
- `FRAMEWORK_ACTIVATED` / `FRAMEWORK_DEACTIVATED` — Emitted when status changes.
- `FRAMEWORK_DELETED` — Emitted when an unused framework is removed.

---

## 7. Quality & Verification Summary

| Test Suite | Tests | Result |
| :--- | :---: | :---: |
| **`test_custom_framework_import.py`** (P2 #3 suite) | 61 | **61 / 61 PASS** |
| **`test_novatech_regression.py`** (75% → 100% Golden Path) | 1 | **1 / 1 PASS** |
| **`test_enterprise_audit_adversarial.py`** (Adversarial Suite) | 8 | **8 / 8 PASS** |
| **`test_production_e2e_journey.py`** (End-to-End Suite) | 15 | **15 / 15 PASS** |
| **Full Backend Pytest Suite** | **302** | **302 / 302 PASS** |
| **Frontend Production Build (`npm run build`)** | — | **0 errors (4.56s)** |
