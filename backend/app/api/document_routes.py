"""
ComplyFlow — Document Routes

Provides:
  POST /api/projects/{id}/documents              (upload)
  GET  /api/projects/{id}/documents              (list)
  GET  /api/projects/{id}/documents/{doc_id}     (view)
  POST /api/projects/{id}/bulk/documents/delete  (bulk delete)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api._shared import _get_storage, settings
from app.services.auth_service import get_project_member_context, require_permission
from app.services.audit_service import record_audit_event
from app.services.document_service import DocumentService

router = APIRouter()

# Module-level document service instance (same as original routes.py)
_document_service = DocumentService(upload_dir=settings.upload_dir)


@router.post("/projects/{project_id}/documents")
async def upload_documents(
    project_id: str,
    requirements_file: Optional[UploadFile] = File(None),
    evidence_files: Optional[list[UploadFile]] = File(None),
    is_remediation: bool = Form(False),
    ctx: Dict[str, Any] = Depends(require_permission("documents:upload")),
):
    """
    Upload requirements document and/or evidence files.
    On is_remediation=True, adds new evidence to existing project.
    Requires: ADMIN or AUDITOR role.

    """
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    saved_docs = []

    # Save requirements file
    if requirements_file and not is_remediation:
        content = await requirements_file.read()
        error = _document_service.validate_file(requirements_file.filename, content)
        if error:
            raise HTTPException(status_code=400, detail=error)
        chunked = _document_service.extract_chunked_document(
            requirements_file.filename, content, "requirements_doc"
        )
        now_ts = datetime.now(timezone.utc).isoformat()
        file_hash = hashlib.sha256(content).hexdigest()

        # Check for duplicate upload
        existing_doc = await storage.get_document(project_id, "requirements_doc")
        if existing_doc and existing_doc.get("file_hash") == file_hash:
            saved_docs.append({
                "doc_id": "requirements_doc",
                "name": requirements_file.filename,
                "role": "requirements",
                "status": chunked.status,
                "total_pages": chunked.total_pages,
                "total_chunks": chunked.total_chunks,
                "version_number": existing_doc.get("version_number", 1),
                "duplicate": True,
            })
        else:
            # Determine version number
            version_number = await storage.get_next_version_number(project_id, "requirements_doc")
            
            # Save file with version-aware path
            file_path = _document_service.save_upload(
                requirements_file.filename, content, project_id,
                doc_id="requirements_doc", version_number=version_number
            )
            
            try:
                analysis_data = {
                    "doc_id": "requirements_doc",
                    "name": requirements_file.filename,
                    "role": "requirements",
                    "text": chunked.raw_text,
                    "status": chunked.status,
                    "diagnostics": chunked.diagnostics,
                    "total_pages": chunked.total_pages,
                    "total_chunks": chunked.total_chunks,
                    "total_characters": chunked.total_characters,
                    "file_size": len(content),
                    "file_type": Path(requirements_file.filename).suffix.lower(),
                    "chunks": [c.model_dump() for c in chunked.chunks],
                    "uploaded_at": now_ts,
                    "file_hash": file_hash,
                    "version_number": version_number,
                }

                # Atomically update documents + create version record
                await storage.save_document_with_version(
                    project_id, "requirements_doc",
                    analysis_data,
                    {
                        "version_number": version_number,
                        "name": requirements_file.filename,
                        "role": "requirements",
                        "text": chunked.raw_text,
                        "data_json": analysis_data,
                        "file_path": str(file_path),
                        "file_hash": file_hash,
                        "uploaded_by": ctx.get("user", {}).get("user_id", ""),
                        "uploaded_at": now_ts,
                    },
                )
            except Exception:
                # If DB operations fail, clean up the newly created file
                # but do NOT delete historical version files
                try:
                    if file_path.exists():
                        file_path.unlink()
                except OSError:
                    pass
                raise

            saved_docs.append({
                "doc_id": "requirements_doc",
                "name": requirements_file.filename,
                "role": "requirements",
                "status": chunked.status,
                "total_pages": chunked.total_pages,
                "total_chunks": chunked.total_chunks,
                "version_number": version_number,
            })

        await record_audit_event(
            storage=storage,
            project_id=project_id,
            event_type="DOCUMENT_UPLOADED",
            actor_type="AUDITOR",
            document_id="requirements_doc",
            summary=f"Requirements checklist '{requirements_file.filename}' uploaded.",
            metadata={"filename": requirements_file.filename, "role": "requirements", "size": len(content), "version_number": version_number if not existing_doc or existing_doc.get("file_hash") != file_hash else existing_doc.get("version_number", 1)},
        )

    # Save evidence files
    if evidence_files:
        for ef in evidence_files:
            if not ef.filename:
                continue
            content = await ef.read()
            error = _document_service.validate_file(ef.filename, content)
            if error:
                raise HTTPException(status_code=400, detail=f"{ef.filename}: {error}")
            doc_id = Path(ef.filename).stem.replace(" ", "_")
            chunked = _document_service.extract_chunked_document(
                ef.filename, content, doc_id
            )
            now_ts = datetime.now(timezone.utc).isoformat()
            file_hash = hashlib.sha256(content).hexdigest()

            # Check for duplicate upload
            existing_doc = await storage.get_document(project_id, doc_id)
            if existing_doc and existing_doc.get("file_hash") == file_hash:
                saved_docs.append({
                    "doc_id": doc_id,
                    "name": ef.filename,
                    "role": "evidence",
                    "status": chunked.status,
                    "total_pages": chunked.total_pages,
                    "total_chunks": chunked.total_chunks,
                    "version_number": existing_doc.get("version_number", 1),
                    "duplicate": True,
                })
            else:
                # Determine version number
                version_number = await storage.get_next_version_number(project_id, doc_id)
                
                # Save file with version-aware path
                file_path = _document_service.save_upload(
                    ef.filename, content, project_id,
                    doc_id=doc_id, version_number=version_number
                )
                
                try:
                    analysis_data = {
                        "doc_id": doc_id,
                        "name": ef.filename,
                        "role": "evidence",
                        "text": chunked.raw_text,
                        "status": chunked.status,
                        "diagnostics": chunked.diagnostics,
                        "total_pages": chunked.total_pages,
                        "total_chunks": chunked.total_chunks,
                        "total_characters": chunked.total_characters,
                        "file_size": len(content),
                        "file_type": Path(ef.filename).suffix.lower(),
                        "chunks": [c.model_dump() for c in chunked.chunks],
                        "uploaded_at": now_ts,
                        "file_hash": file_hash,
                        "version_number": version_number,
                    }

                    # Atomically update documents + create version record
                    await storage.save_document_with_version(
                        project_id, doc_id,
                        analysis_data,
                        {
                            "version_number": version_number,
                            "name": ef.filename,
                            "role": "evidence",
                            "text": chunked.raw_text,
                            "data_json": analysis_data,
                            "file_path": str(file_path),
                            "file_hash": file_hash,
                            "uploaded_by": ctx.get("user", {}).get("user_id", ""),
                            "uploaded_at": now_ts,
                        },
                    )
                except Exception:
                    # If DB operations fail, clean up the newly created file
                    # but do NOT delete historical version files
                    try:
                        if file_path.exists():
                            file_path.unlink()
                    except OSError:
                        pass
                    raise

                saved_docs.append({
                    "doc_id": doc_id,
                    "name": ef.filename,
                    "role": "evidence",
                    "status": chunked.status,
                    "total_pages": chunked.total_pages,
                    "total_chunks": chunked.total_chunks,
                    "version_number": version_number,
                })

            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="DOCUMENT_UPLOADED",
                actor_type="AUDITOR",
                document_id=doc_id,
                summary=f"Evidence document '{ef.filename}' uploaded.",
                metadata={"filename": ef.filename, "role": "evidence", "size": len(content), "version_number": version_number if not existing_doc or existing_doc.get("file_hash") != file_hash else existing_doc.get("version_number", 1)},
            )

    return {"saved": saved_docs, "project_id": project_id}


@router.get("/projects/{project_id}/documents")
async def list_project_documents(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """List all uploaded documents with chunk counts, OCR status, and supported requirements."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs = await storage.list_documents(project_id)
    matches = await storage.get_matches(project_id)

    doc_supported_reqs: dict[str, list[dict]] = {}
    for match in matches:
        req_id = match.get("requirement_id")
        req_title = match.get("requirement_title") or req_id
        status = match.get("status")
        for ev in match.get("evidence", []):
            doc_name = ev.get("document_name")
            if doc_name:
                if doc_name not in doc_supported_reqs:
                    doc_supported_reqs[doc_name] = []
                if not any(r["requirement_id"] == req_id for r in doc_supported_reqs[doc_name]):
                    doc_supported_reqs[doc_name].append({
                        "requirement_id": req_id,
                        "title": req_title,
                        "status": status,
                        "quote": ev.get("quote"),
                        "page_number": ev.get("page_number"),
                    })

    enriched_docs = []
    for doc in docs:
        name = doc.get("name", "")
        doc_id = doc.get("doc_id", "")
        enriched_docs.append({
            "doc_id": doc_id,
            "name": name,
            "role": doc.get("role", "evidence"),
            "status": doc.get("status", "OK"),
            "diagnostics": doc.get("diagnostics", ""),
            "total_pages": doc.get("total_pages", 1),
            "total_chunks": doc.get("total_chunks", len(doc.get("chunks", []))),
            "total_characters": doc.get("total_characters", len(doc.get("text", ""))),
            "file_size": doc.get("file_size", len(doc.get("text", "").encode("utf-8"))),
            "file_type": doc.get("file_type", Path(name).suffix.lower() if name else ".txt"),
            "uploaded_at": doc.get("uploaded_at"),
            "supported_requirements": doc_supported_reqs.get(name, []),
        })

    return {"documents": enriched_docs}


@router.get("/projects/{project_id}/documents/{doc_id}")
async def get_document_details(project_id: str, doc_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):
    """Get full document with all structured chunks and cited evidence excerpts."""
    safe_doc_id = Path(doc_id).name.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_doc_id:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = await storage.get_document(project_id, safe_doc_id)
    if not doc:
        all_docs = await storage.list_documents(project_id)
        for d in all_docs:
            if d.get("name") == doc_id or d.get("doc_id") == doc_id:
                doc = d
                break

    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    chunks = doc.get("chunks")
    if not chunks:
        from app.services.chunking_service import get_chunking_service
        chunker = get_chunking_service()
        raw_text = doc.get("text", "")
        doc_chunks = chunker.chunk_plain_text(
            text=raw_text,
            document_name=doc.get("name", safe_doc_id),
            document_id=safe_doc_id,
            page_number=1,
        )
        chunks = [c.model_dump() for c in doc_chunks]

    matches = await storage.get_matches(project_id)
    name = doc.get("name", safe_doc_id)
    supported_reqs = []
    for match in matches:
        req_id = match.get("requirement_id")
        req_title = match.get("requirement_title") or req_id
        for ev in match.get("evidence", []):
            if ev.get("document_name") == name or ev.get("document_id") == safe_doc_id:
                supported_reqs.append({
                    "requirement_id": req_id,
                    "title": req_title,
                    "status": match.get("status"),
                    "quote": ev.get("quote"),
                    "page_number": ev.get("page_number"),
                    "section": ev.get("section"),
                    "relevance": ev.get("relevance"),
                })

    return {
        "document": {
            "doc_id": doc.get("doc_id", safe_doc_id),
            "name": name,
            "role": doc.get("role", "evidence"),
            "status": doc.get("status", "OK"),
            "diagnostics": doc.get("diagnostics", ""),
            "total_pages": doc.get("total_pages", 1),
            "total_chunks": len(chunks),
            "total_characters": doc.get("total_characters", len(doc.get("text", ""))),
            "file_size": doc.get("file_size", len(doc.get("text", "").encode("utf-8"))),
            "file_type": doc.get("file_type", Path(name).suffix.lower() if name else ".txt"),
            "uploaded_at": doc.get("uploaded_at"),
            "raw_text": doc.get("text", ""),
            "chunks": chunks,
            "supported_requirements": supported_reqs,
        }
    }


# ── Bulk Document Operations ──────────────────────────────────────

class BulkDeleteDocumentsPayload(BaseModel):
    doc_ids: List[str]


@router.post("/projects/{project_id}/bulk/documents/delete")
async def bulk_delete_documents(
    project_id: str,
    payload: BulkDeleteDocumentsPayload,
    ctx: Dict[str, Any] = Depends(require_permission("documents:delete")),
):
    """
    Delete multiple project documents by doc_id.
    Removes database records and physical files safely.
    Returns per-item results — never silently discards failures.
    Filesystem paths are never exposed in the response.
    """
    import shutil
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids cannot be empty")

    if len(payload.doc_ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot bulk-delete more than 100 documents at once")

    actor = ctx.get("user", {})
    actor_id = actor.get("user_id")

    seen = set()
    unique_ids = [did for did in payload.doc_ids if did not in seen and not seen.add(did)]

    results_success = []
    results_failed = []
    errors = []

    for doc_id in unique_ids:
        try:
            doc = await storage.get_document(project_id, doc_id)
            if not doc:
                # Try by name
                all_docs = await storage.list_documents(project_id)
                doc = next((d for d in all_docs if d.get("doc_id") == doc_id or d.get("name") == doc_id), None)

            if not doc:
                results_failed.append(doc_id)
                errors.append({"doc_id": doc_id, "error": "Document not found in this project"})
                continue

            doc_name = doc.get("name", doc_id)

            # Delete physical file(s) safely - handle both legacy and versioned paths
            # Legacy path: uploads/{project_id}/{filename}
            legacy_path = Path(settings.upload_dir) / project_id / doc_name
            if legacy_path.exists() and legacy_path.is_file():
                try:
                    legacy_path.unlink()
                except OSError:
                    pass
            
            # Versioned path: uploads/{project_id}/{doc_id}/ (contains v1/, v2/, etc.)
            versioned_dir = Path(settings.upload_dir) / project_id / doc_id
            if versioned_dir.exists() and versioned_dir.is_dir():
                try:
                    import shutil
                    shutil.rmtree(versioned_dir)
                except OSError:
                    pass

            # Delete from database (also removes version records)
            deleted = await storage.delete_document(project_id, doc_id)

            await record_audit_event(
                storage=storage,
                project_id=project_id,
                event_type="DOCUMENT_DELETED",
                actor_type="AUDITOR",
                actor_id=actor_id,
                summary=f"Document '{doc_name}' deleted.",
                metadata={"doc_id": doc_id, "doc_name": doc_name, "bulk_operation": True},
            )

            results_success.append({"doc_id": doc_id, "name": doc_name})

        except Exception as exc:
            results_failed.append(doc_id)
            errors.append({"doc_id": doc_id, "error": str(exc)})

    return {
        "status": "partial" if results_failed else "success",
        "success": results_success,
        "failed": results_failed,
        "errors": errors,
        "total_requested": len(unique_ids),
        "total_succeeded": len(results_success),
        "total_failed": len(results_failed),
    }


# ── Document Versioning ──────────────────────────────────────────


@router.get("/projects/{project_id}/documents/{doc_id}/versions")
async def list_document_versions(
    project_id: str,
    doc_id: str,
    ctx: Dict[str, Any] = Depends(get_project_member_context),
):
    """List all versions of a document."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_doc_id = Path(doc_id).name.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_doc_id:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    versions = await storage.list_document_versions(project_id, safe_doc_id)
    return {"versions": versions, "doc_id": safe_doc_id}


@router.get("/projects/{project_id}/documents/{doc_id}/versions/{version_number}")
async def get_document_version(
    project_id: str,
    doc_id: str,
    version_number: int,
    ctx: Dict[str, Any] = Depends(get_project_member_context),
):
    """Get a specific document version."""
    storage = _get_storage()
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    safe_doc_id = Path(doc_id).name.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_doc_id:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    version = await storage.get_document_version(project_id, safe_doc_id, version_number)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_number} not found for document '{safe_doc_id}'")

    return {"version": version}
