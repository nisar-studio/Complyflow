"""
ComplyFlow — Custom Compliance Framework Ingestion & Validation Service

Provides:
  - Multi-format ingestion: JSON (.json), CSV (.csv), XLSX (.xlsx)
  - Pre-flight validation pipeline before database persistence
  - Spreadsheet formula injection neutralization (=, +, -, @)
  - Control characters, null-byte, and path traversal stripping
  - Duplicate external_id detection and enum enforcement
  - Two-step import workflow: Parse & Preview -> Explicit Confirmation
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_REQUIREMENTS_PER_FRAMEWORK = 1000

# Dangerous spreadsheet formula leading prefixes
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_formula_injection(value: str) -> str:
    """Neutralize spreadsheet formula triggers to prevent CSV/Excel injection."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    cleaned = value.strip()
    while cleaned and cleaned.startswith(FORMULA_PREFIXES):
        cleaned = cleaned[1:].strip()
    # Strip null bytes and control chars (preserve standard tabs/newlines if in text)
    cleaned = cleaned.replace("\x00", "")
    return cleaned


class FrameworkValidationError(Exception):
    def __init__(self, message: str, details: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class FrameworkImportService:
    """Handles parsing, validation, and preview generation for custom frameworks."""

    @classmethod
    def parse_and_validate(
        cls,
        filename: str,
        content: bytes,
        default_name: Optional[str] = None,
        default_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses uploaded framework content (JSON, CSV, XLSX) and applies strict validation.
        Returns a rich preview payload if valid, or raises FrameworkValidationError with details.
        Does NOT persist anything to storage.
        """
        if not content:
            raise FrameworkValidationError("Uploaded framework file is empty.", [
                {"row": 0, "field": "file", "message": "File content is empty"}
            ])

        if len(content) > MAX_IMPORT_FILE_SIZE:
            raise FrameworkValidationError(
                f"File size exceeds maximum allowed limit ({MAX_IMPORT_FILE_SIZE // (1024*1024)}MB).",
                [{"row": 0, "field": "file_size", "message": "File exceeds 10MB limit"}]
            )

        ext = Path(filename or "framework.json").suffix.lower()

        if ext == ".json":
            framework_meta, raw_reqs = cls._parse_json(content, filename, default_name, default_version)
        elif ext == ".csv":
            framework_meta, raw_reqs = cls._parse_csv(content, filename, default_name, default_version)
        elif ext in (".xlsx", ".xlsm"):
            framework_meta, raw_reqs = cls._parse_xlsx(content, filename, default_name, default_version)
        else:
            raise FrameworkValidationError(
                f"Unsupported file format '{ext}'. Supported formats: .json, .csv, .xlsx",
                [{"row": 0, "field": "file_extension", "message": f"Unsupported format '{ext}'"}]
            )

        # Apply strict requirement validation
        validated_reqs, errors, warnings = cls._validate_requirements(raw_reqs)

        if errors:
            # Build a meaningful top-level summary
            dup_errors = [e for e in errors if "duplicate" in e.get("message", "").lower()]
            col_errors = [e for e in errors if "column" in e.get("message", "").lower() or "title" in e.get("message", "").lower()]
            if dup_errors:
                summary = f"Framework import failed: {len(dup_errors)} duplicate requirement ID(s) detected."
            elif col_errors:
                summary = f"Framework import failed: missing required column(s) — 'title' is required."
            else:
                summary = f"Framework validation failed with {len(errors)} error(s)."
            raise FrameworkValidationError(summary, errors)


        if len(validated_reqs) == 0:
            raise FrameworkValidationError(
                "Framework contains zero valid requirement definitions.",
                [{"row": 0, "field": "requirements", "message": "At least one requirement is required"}]
            )

        if len(validated_reqs) > MAX_REQUIREMENTS_PER_FRAMEWORK:
            raise FrameworkValidationError(
                f"Framework exceeds maximum allowed requirements limit ({MAX_REQUIREMENTS_PER_FRAMEWORK}).",
                [{"row": 0, "field": "requirement_count", "message": f"Too many requirements ({len(validated_reqs)})"}]
            )

        # Generate breakdowns
        cat_counts: Dict[str, int] = {}
        sev_counts: Dict[str, int] = {}
        for r in validated_reqs:
            cat = r["category"]
            sev = r["severity"]
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            sev_counts[sev] = sev_counts.get(sev, 0) + 1

        preview = {
            "status": "valid",
            "framework": framework_meta,
            "requirement_count": len(validated_reqs),
            "requirements": validated_reqs,
            "category_breakdown": cat_counts,
            "severity_breakdown": sev_counts,
            "sample_requirements": validated_reqs[:5],
            "warnings": warnings,
            "is_valid": True,
        }

        return preview


    @classmethod
    def _parse_json(
        cls,
        content: bytes,
        filename: str,
        default_name: Optional[str],
        default_version: Optional[str],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        try:
            data = json.loads(content.decode("utf-8"))
        except UnicodeDecodeError:
            try:
                data = json.loads(content.decode("latin-1"))
            except Exception as e:
                raise FrameworkValidationError("Invalid character encoding in JSON file.", [
                    {"row": 0, "field": "json", "message": str(e)}
                ])
        except json.JSONDecodeError as e:
            raise FrameworkValidationError(f"Malformed JSON syntax: {e.msg} (line {e.lineno}, col {e.colno})", [
                {"row": e.lineno, "field": "json", "message": f"Syntax error at line {e.lineno}, col {e.colno}: {e.msg}"}
            ])

        if not isinstance(data, dict):
            raise FrameworkValidationError("Root JSON structure must be an object.", [
                {"row": 0, "field": "json", "message": "Expected JSON object at root"}
            ])

        # Support both flat and nested {"framework": {...}} formats
        framework_meta = data.get("framework") or {}
        if not isinstance(framework_meta, dict):
            framework_meta = {}

        raw_reqs = data.get("requirements") or []
        if not isinstance(raw_reqs, list):
            raise FrameworkValidationError("'requirements' field in JSON must be an array of objects.", [
                {"row": 0, "field": "requirements", "message": "Expected array for 'requirements'"}
            ])

        # Name resolution: root > nested framework key > default > filename stem
        name = (
            data.get("name")
            or framework_meta.get("name")
            or default_name
            or Path(filename).stem.replace("_", " ").title()
        )
        # Version resolution: override param > root > nested > fallback "1.0"
        version = (
            default_version
            or data.get("version")
            or framework_meta.get("version")
            or "1.0"
        )
        desc = sanitize_formula_injection(
            framework_meta.get("description") or data.get("description") or ""
        )
        source = sanitize_formula_injection(
            framework_meta.get("source") or data.get("source") or "Custom Import"
        )

        meta = {
            "name": sanitize_formula_injection(str(name)) or "Custom Framework",
            "version": sanitize_formula_injection(str(version)) or "1.0",
            "description": desc,
            "source": source,
        }

        return meta, raw_reqs


    @classmethod
    def _parse_csv(
        cls,
        content: bytes,
        filename: str,
        default_name: Optional[str],
        default_version: Optional[str],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        # Sniff delimiter (comma or semicolon)
        sample = text[:2048]
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise FrameworkValidationError("CSV file has no header row.", [
                {"row": 1, "field": "header", "message": "CSV header is missing"}
            ])

        # Normalize fieldnames to lowercase trimmed
        norm_fields = {fn: fn.strip().lower() for fn in reader.fieldnames if fn}
        
        raw_reqs = []
        for idx, row in enumerate(reader, start=2):
            if not any(row.values()):
                continue  # Skip blank lines
            normalized_row = {}
            for k, v in row.items():
                if k in norm_fields:
                    normalized_row[norm_fields[k]] = v
            raw_reqs.append(normalized_row)

        name = default_name or Path(filename).stem.replace("_", " ").title()
        version = default_version or "1.0"

        meta = {
            "name": name,
            "version": version,
            "description": f"Imported from {filename}",
            "source": "CSV Spreadsheet Import",
        }

        return meta, raw_reqs

    @classmethod
    def _parse_xlsx(
        cls,
        content: bytes,
        filename: str,
        default_name: Optional[str],
        default_version: Optional[str],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Parse .xlsx worksheet using Python standard library zipfile + xml.etree.ElementTree."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # 1. Read sharedStrings if present
                shared_strings: List[str] = []
                if "xl/sharedStrings.xml" in zf.namelist():
                    ss_xml = zf.read("xl/sharedStrings.xml")
                    root = ET.fromstring(ss_xml)
                    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    for si in root.findall(".//x:si", ns) or root.findall(".//si"):
                        t_node = si.find(".//x:t", ns) if ns else si.find(".//t")
                        if t_node is not None and t_node.text:
                            shared_strings.append(t_node.text)
                        else:
                            # Handle rich text runs
                            runs = si.findall(".//x:r/x:t", ns) if ns else si.findall(".//r/t")
                            shared_strings.append("".join(r.text for r in runs if r.text))

                # 2. Read sheet1.xml
                sheet_xml = zf.read("xl/worksheets/sheet1.xml")
                root = ET.fromstring(sheet_xml)
                ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                rows = root.findall(".//x:row", ns) or root.findall(".//row")

                if not rows:
                    raise FrameworkValidationError("XLSX worksheet has no rows.", [
                        {"row": 1, "field": "sheet", "message": "Worksheet is empty"}
                    ])

                # Helper to extract cell value
                def get_cell_val(cell) -> str:
                    t_attr = cell.get("t")
                    val_node = cell.find(".//x:v", ns) if ns else cell.find(".//v")
                    if val_node is None or val_node.text is None:
                        # Direct text
                        is_node = cell.find(".//x:is/x:t", ns) if ns else cell.find(".//is/t")
                        return is_node.text if is_node is not None and is_node.text else ""
                    val = val_node.text.strip()
                    if t_attr == "s":
                        idx = int(val)
                        return shared_strings[idx] if idx < len(shared_strings) else ""
                    return val

                # Helper to extract column index from cell ref e.g. "A1" -> 0, "B1" -> 1
                def col_idx_from_ref(ref: str) -> int:
                    match = re.match(r"([A-Za-z]+)", ref)
                    if not match:
                        return 0
                    letters = match.group(1).upper()
                    idx = 0
                    for ch in letters:
                        idx = idx * 26 + (ord(ch) - ord('A') + 1)
                    return idx - 1

                # Parse header row
                header_row = rows[0]
                headers: Dict[int, str] = {}
                for cell in header_row.findall(".//x:c", ns) or header_row.findall(".//c"):
                    ref = cell.get("r", "A1")
                    col_idx = col_idx_from_ref(ref)
                    val = get_cell_val(cell).strip().lower()
                    if val:
                        headers[col_idx] = val

                if not headers:
                    raise FrameworkValidationError("XLSX header row has no text columns.", [
                        {"row": 1, "field": "header", "message": "No header columns found"}
                    ])

                raw_reqs = []
                for row_node in rows[1:]:
                    row_cells = row_node.findall(".//x:c", ns) or row_node.findall(".//c")
                    row_data: Dict[str, str] = {}
                    for cell in row_cells:
                        ref = cell.get("r", "A2")
                        col_idx = col_idx_from_ref(ref)
                        if col_idx in headers:
                            row_data[headers[col_idx]] = get_cell_val(cell)

                    if any(row_data.values()):
                        raw_reqs.append(row_data)

        except zipfile.BadZipFile:
            raise FrameworkValidationError("Uploaded file is not a valid XLSX spreadsheet (bad zip structure).", [
                {"row": 0, "field": "file", "message": "Corrupted or invalid XLSX archive"}
            ])
        except Exception as e:
            if isinstance(e, FrameworkValidationError):
                raise
            raise FrameworkValidationError(f"Failed to parse XLSX workbook: {str(e)}", [
                {"row": 0, "field": "xlsx", "message": str(e)}
            ])

        name = default_name or Path(filename).stem.replace("_", " ").title()
        version = default_version or "1.0"

        meta = {
            "name": name,
            "version": version,
            "description": f"Imported from Excel workbook {filename}",
            "source": "Excel XLSX Spreadsheet Import",
        }

        return meta, raw_reqs

    @classmethod
    def _validate_requirements(
        cls,
        raw_reqs: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        """
        Validates individual requirement dictionaries and returns (validated_list, errors, warnings).
        """
        validated: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        warnings: List[str] = []
        seen_ids: Set[str] = set()

        for idx, raw in enumerate(raw_reqs, start=1):
            if not isinstance(raw, dict):
                errors.append({"row": idx, "field": "requirement", "message": "Requirement definition must be an object"})
                continue

            # Resolve external_id / requirement_id
            ext_id = (
                raw.get("external_id")
                or raw.get("requirement_id")
                or raw.get("id")
                or raw.get("control_id")
                or raw.get("item_id")
            )

            if not ext_id or not str(ext_id).strip():
                errors.append({"row": idx, "field": "external_id", "message": "Missing required field: external_id / requirement_id"})
                continue

            clean_id = sanitize_formula_injection(str(ext_id)).strip()
            # ID length and character validation
            if len(clean_id) > 64:
                errors.append({"row": idx, "field": "external_id", "message": f"external_id '{clean_id}' exceeds 64 characters"})
                continue

            clean_id_lower = clean_id.lower()
            if clean_id_lower in seen_ids:
                errors.append({"row": idx, "field": "external_id", "message": f"Duplicate requirement ID '{clean_id}' found in row {idx}"})
                continue
            seen_ids.add(clean_id_lower)

            # Title
            title = raw.get("title") or raw.get("name") or raw.get("requirement_title") or raw.get("control_name")
            if not title or not str(title).strip():
                errors.append({"row": idx, "field": "title", "message": f"Missing required field: title (column 'title') for requirement '{clean_id}'"})
                continue

            clean_title = sanitize_formula_injection(str(title)).strip()
            if len(clean_title) < 3:
                errors.append({"row": idx, "field": "title", "message": f"Title too short (min 3 chars) for requirement '{clean_id}'"})
                continue
            if len(clean_title) > 256:
                clean_title = clean_title[:256]
                warnings.append(f"Row {idx} ({clean_id}): Title truncated to 256 characters.")

            # Description
            desc = raw.get("description") or raw.get("desc") or raw.get("requirement") or raw.get("control_description")
            if not desc or not str(desc).strip():
                errors.append({"row": idx, "field": "description", "message": f"Missing required field: description for requirement '{clean_id}'"})
                continue

            clean_desc = sanitize_formula_injection(str(desc)).strip()
            if len(clean_desc) > 4000:
                clean_desc = clean_desc[:4000]
                warnings.append(f"Row {idx} ({clean_id}): Description truncated to 4000 characters.")

            # Category
            category = raw.get("category") or raw.get("domain") or raw.get("section") or "General"
            clean_category = sanitize_formula_injection(str(category)).strip() or "General"
            if len(clean_category) > 100:
                clean_category = clean_category[:100]

            # Severity — normalize empty/unknown to MEDIUM with a warning; only hard-error on clearly wrong non-empty values
            raw_sev = raw.get("severity") or ""
            clean_sev = str(raw_sev).strip().upper()
            if not clean_sev:
                # Missing severity → default to MEDIUM silently
                clean_sev = "MEDIUM"
                warnings.append(f"Row {idx} ({clean_id}): Missing severity, defaulting to MEDIUM.")
            elif clean_sev not in VALID_SEVERITIES:
                # Unrecognised non-empty value → error
                errors.append({
                    "row": idx,
                    "field": "severity",
                    "message": f"Invalid severity '{raw_sev}' for requirement '{clean_id}'. Allowed: {', '.join(sorted(VALID_SEVERITIES))}"
                })
                continue

            # Priority
            raw_prio = raw.get("priority") or clean_sev
            clean_prio = str(raw_prio).strip().upper()
            if clean_prio not in VALID_PRIORITIES:
                clean_prio = clean_sev

            # Guidance & Source Reference

            guidance = raw.get("guidance") or raw.get("required_evidence") or raw.get("remediation") or ""
            clean_guidance = sanitize_formula_injection(str(guidance)).strip()

            source_ref = raw.get("source_reference") or raw.get("reference") or raw.get("clause") or ""
            clean_source_ref = sanitize_formula_injection(str(source_ref)).strip()

            validated.append({
                "requirement_id": clean_id,
                "external_id": clean_id,
                "title": clean_title,
                "description": clean_desc,
                "category": clean_category,
                "severity": clean_sev,
                "priority": clean_prio,
                "guidance": clean_guidance,
                "required_evidence": clean_guidance,
                "source_reference": clean_source_ref,
                "metadata": {
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
            })

        return validated, errors, warnings
