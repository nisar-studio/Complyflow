# ComplyFlow Custom Compliance Framework Schema Specification

> **Specification Version**: 1.0.0  
> **Supported Formats**: JSON (`.json`), CSV (`.csv`), XLSX (`.xlsx`)

---

## 1. Overview & Data Hierarchy

ComplyFlow allows enterprise compliance teams to import custom control frameworks. A framework contains top-level metadata and a list of requirement definitions.

---

## 2. JSON Format Specification (`.json`)

### Structure:
```json
{
  "framework": {
    "name": "Custom Enterprise Security Standard",
    "version": "1.0",
    "description": "Internal baseline controls for cloud infrastructure and data privacy.",
    "source": "Internal Compliance Committee"
  },
  "requirements": [
    {
      "external_id": "SEC-001",
      "title": "Access Control & Password Policy",
      "description": "All employee and system accounts must enforce multi-factor authentication (MFA) and minimum 14-character passwords.",
      "category": "Access Management",
      "severity": "CRITICAL",
      "priority": "CRITICAL",
      "guidance": "Provide active identity provider configuration screenshots and MFA enrollment reports.",
      "source_reference": "Section 4.1"
    },
    {
      "external_id": "SEC-002",
      "title": "Encryption in Transit & at Rest",
      "description": "Customer data stored in databases must be encrypted using AES-256 and transmitted over TLS 1.3.",
      "category": "Cryptography",
      "severity": "HIGH",
      "priority": "HIGH",
      "guidance": "Submit TLS configuration audit reports and cloud KMS encryption status.",
      "source_reference": "Section 4.2"
    }
  ]
}
```

---

## 3. CSV & XLSX Format Specification (`.csv`, `.xlsx`)

For tabular formats (CSV or XLSX), the first row must contain column headers matching the field names below. For XLSX, the framework metadata can be specified via a sheet named `Framework` or inferred from the file name and table headers.

### Required & Optional Columns:

| Column Name | Required? | Type | Allowed Values / Validation Rules | Example |
| :--- | :---: | :---: | :--- | :--- |
| `external_id` (or `requirement_id`) | **YES** | String | 1–64 characters, alphanumeric + `-_.:/` | `SEC-001` |
| `title` | **YES** | String | 3–256 characters | `Access Control Policy` |
| `description` | **YES** | String | 5–4000 characters | `Multi-factor authentication must be enabled...` |
| `category` | NO | String | Max 100 characters (Defaults to `"General"`) | `Access Management` |
| `severity` | NO | String | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` (Defaults to `"MEDIUM"`) | `HIGH` |
| `priority` | NO | String | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` (Defaults to `severity` or `"MEDIUM"`) | `HIGH` |
| `guidance` (or `required_evidence`) | NO | String | Max 2000 characters | `Provide Okta export logs.` |
| `source_reference` | NO | String | Max 256 characters | `SOC 2 CC6.1` |

### Sample CSV Content:
```csv
external_id,title,description,category,severity,priority,guidance,source_reference
SEC-001,MFA Enforcement,MFA is enforced on all corporate systems,Access,CRITICAL,CRITICAL,Okta admin report,Policy 1.1
SEC-002,Data Encryption,Customer PII is encrypted with AES-256 at rest,Data Security,HIGH,HIGH,KMS configuration,Policy 2.4
SEC-003,Audit Logging,Centralized immutable audit trail enabled,Auditing,HIGH,HIGH,SIEM dashboard logs,Policy 3.1
```

---

## 4. Strict Validation & Security Rules

1. **Duplicate ID Prevention**: Every `external_id` within the import must be unique. Duplicate IDs trigger atomic rejection.
2. **Formula Injection Neutralization**: In spreadsheet formats (`.csv`, `.xlsx`), any cell starting with `=`, `+`, `-`, or `@` has the trigger character stripped to prevent CSV/Excel injection vulnerabilities.
3. **Control Characters & Null Bytes**: Control characters (`\x00`, `\r\n` line manipulation in identifiers) are stripped.
4. **Enum Enforcement**: Values for `severity` and `priority` must match valid enums (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`). Unknown values produce a structured error with exact row/field pointer.
5. **AI Safety Guarantee**: Framework requirement text is treated as passive compliance data and never as executable prompt instructions.
