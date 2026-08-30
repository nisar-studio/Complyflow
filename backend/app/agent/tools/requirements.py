"""
Tool 1: extract_requirements

Uses Gemini to interpret and extract structured requirements from a requirements document.
The DETERMINISTIC work (file reading and chunking) happens in document_service / chunking_service.
Gemini is used here for REASONING: interpreting requirement text into structured data.
"""
from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from app.services.chunking_service import get_chunking_service


def _get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return genai.Client(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def extract_requirements(requirements_document_text: str) -> dict:
    """
    Extract structured compliance requirements from a requirements document.

    Analyzes the provided document text and returns a structured list of
    individual requirements, each with an ID, title, description, required
    evidence type, priority level, and source reference.

    Args:
        requirements_document_text: The full text content of the requirements document.

    Returns:
        A dict with keys:
          - requirements: list of requirement objects (each has requirement_id,
            title, description, required_evidence, priority, source_reference)
          - total_count: total number of extracted requirements
          - extraction_notes: any notes about the extraction process
    """
    client = _get_gemini_client()
    model = _get_model()

    # Intelligent chunking and context assembly (replaces naive [:15000] text slicing)
    chunker = get_chunking_service()
    chunks = chunker.chunk_plain_text(
        text=requirements_document_text,
        document_name="requirements_document",
    )
    assembled_context = chunker.assemble_context(
        chunks=chunks,
        max_tokens=25000,
        header_prefix="--- REQUIREMENTS DOCUMENT SECTIONS ---",
    )

    prompt = f"""You are a senior compliance audit analyst. Analyze the following requirements document and extract ALL individual requirements.

For each requirement, return a JSON object with exactly these fields:
- requirement_id: string, format "REQ-001", "REQ-002", etc., numbered sequentially
- title: string, a short descriptive title (5-10 words)
- description: string, the full description of what is required
- required_evidence: string, what specific document/evidence would satisfy this requirement
- priority: string, one of "CRITICAL", "HIGH", "MEDIUM", "LOW" based on importance
- source_reference: string, exact section/page reference if available, else "General"

Return ONLY valid JSON with this structure:
{{
  "requirements": [...],
  "total_count": <number>,
  "extraction_notes": "<any notes>"
}}

Requirements document content:
---
{assembled_context}
---

Extract ALL requirements. Do not miss any. Return valid JSON only."""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    raw = response.text.strip()
    result = json.loads(raw)

    # Validate structure
    if "requirements" not in result:
        result = {"requirements": [], "total_count": 0, "extraction_notes": "Extraction failed"}

    # Ensure requirement_ids are consistent
    for i, req in enumerate(result["requirements"]):
        if "requirement_id" not in req or not req["requirement_id"]:
            req["requirement_id"] = f"REQ-{i+1:03d}"

    result["total_count"] = len(result["requirements"])
    return result
