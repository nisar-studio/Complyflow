"""
Tool 2: analyze_documents

Uses Gemini to reason over each evidence document's text content and extract
structured facts, evidence statements, and potential inconsistencies.

The deterministic work (file reading, chunking) is done by document_service / chunking_service
before the tool is called. This tool receives extracted text and uses
Gemini for structured fact extraction across all document chunks.
"""
from __future__ import annotations

import json
import os
from typing import List

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


def _analyze_single_document(client: genai.Client, model: str, doc_name: str, doc_text: str) -> dict:
    """Analyze a single document across its chunks and return structured analysis."""
    chunker = get_chunking_service()
    chunks = chunker.chunk_plain_text(text=doc_text, document_name=doc_name)
    assembled_context = chunker.assemble_context(
        chunks=chunks,
        max_tokens=20000,
        header_prefix=f"--- DOCUMENT: {doc_name} ---",
    )

    prompt = f"""You are a compliance document analyst. Analyze this document and extract structured facts and evidence statements.

Document name: {doc_name}

Return ONLY valid JSON with exactly this structure:
{{
  "doc_name": "{doc_name}",
  "doc_type": "<type: certificate | policy | registration | financial_statement | agreement | report | other>",
  "key_facts": ["<fact 1>", "<fact 2>", ...],
  "dates": ["<date 1>", ...],
  "organizations": ["<org name 1>", ...],
  "identifiers": ["<ID/policy/registration number 1>", ...],
  "evidence_statements": ["<specific verifiable statement/excerpt that could satisfy a compliance requirement>", ...],
  "possible_inconsistencies": ["<any address, numerical, or date inconsistency noted>", ...]
}}

Document content:
---
{assembled_context}
---

Extract all relevant facts. Be specific about dates, names, amounts, addresses, and identifiers.
Return valid JSON only."""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    raw = response.text.strip()
    return json.loads(raw)


def analyze_documents(documents_json: str) -> dict:
    """
    Analyze a list of evidence documents and extract structured facts from each.

    For each document, extracts: document type, key facts, dates, organizations,
    identifiers, evidence statements that could satisfy requirements, and
    any possible inconsistencies found within the document.

    Args:
        documents_json: A JSON string representing a list of document objects.
            Each object must have:
              - "name": the document filename
              - "text": the full extracted text content of the document

    Returns:
        A dict with key "analyses" containing a list of DocumentAnalysis objects,
        one per input document.
    """
    client = _get_gemini_client()
    model = _get_model()

    documents: List[dict] = json.loads(documents_json)

    analyses = []
    for doc in documents:
        doc_name = doc.get("name", "unknown")
        doc_text = doc.get("text", "")

        if not doc_text.strip():
            analyses.append({
                "doc_name": doc_name,
                "doc_type": "unknown",
                "key_facts": [],
                "dates": [],
                "organizations": [],
                "identifiers": [],
                "evidence_statements": [],
                "possible_inconsistencies": [f"Document '{doc_name}' has no extractable text."],
            })
            continue

        try:
            analysis = _analyze_single_document(client, model, doc_name, doc_text)
            analyses.append(analysis)
        except Exception as e:
            analyses.append({
                "doc_name": doc_name,
                "doc_type": "error",
                "key_facts": [],
                "dates": [],
                "organizations": [],
                "identifiers": [],
                "evidence_statements": [],
                "possible_inconsistencies": [f"Analysis failed: {str(e)}"],
            })

    return {"analyses": analyses}
