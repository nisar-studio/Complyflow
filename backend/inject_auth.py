"""
Inject auth dependencies into routes.py for all project-scoped endpoints.
Run once from the backend directory.
"""
import re

with open("app/api/routes.py", encoding="utf-8") as f:
    content = f.read()

# Map: function_name -> (old_signature_fragment, new_signature_fragment)
# We add ctx dependency (get_project_member_context) to view-only endpoints,
# and require_permission() for mutating endpoints.

PATCHES = [
    # analyze_project — requires analysis:run
    (
        "async def analyze_project(project_id: str, background_tasks: BackgroundTasks):",
        "async def analyze_project(project_id: str, background_tasks: BackgroundTasks, ctx: Dict[str, Any] = Depends(require_permission(\"analysis:run\"))):",
    ),
    # get_project_details — requires project:view (any member)
    (
        "async def get_project_details(project_id: str):",
        "async def get_project_details(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_project_results — requires project:view
    (
        "async def get_project_results(project_id: str):",
        "async def get_project_results(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # verify_project — requires verification:run
    (
        "async def verify_project(project_id: str, background_tasks: BackgroundTasks):",
        "async def verify_project(project_id: str, background_tasks: BackgroundTasks, ctx: Dict[str, Any] = Depends(require_permission(\"verification:run\"))):",
    ),
    # list_verification_runs — requires project:view
    (
        "async def list_verification_runs(project_id: str):",
        "async def list_verification_runs(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_verification_run_snapshot — requires project:view
    (
        "async def get_verification_run_snapshot(project_id: str, run_id: str):",
        "async def get_verification_run_snapshot(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_run_delta_from_predecessor — requires project:view
    (
        "async def get_run_delta_from_predecessor(project_id: str, run_id: str):",
        "async def get_run_delta_from_predecessor(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # list_project_documents — requires project:view
    (
        "async def list_project_documents(project_id: str):",
        "async def list_project_documents(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_document_details — requires project:view
    (
        "async def get_document_details(project_id: str, doc_id: str):",
        "async def get_document_details(project_id: str, doc_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # list_project_overrides — requires project:view
    (
        "async def list_project_overrides(project_id: str):",
        "async def list_project_overrides(project_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_requirement_override — requires project:view
    (
        "async def get_requirement_override(project_id: str, requirement_id: str):",
        "async def get_requirement_override(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # delete_requirement_override — requires overrides:revoke
    (
        "async def delete_requirement_override(project_id: str, requirement_id: str):",
        "async def delete_requirement_override(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"overrides:revoke\"))):",
    ),
    # list_requirement_notes — requires project:view
    (
        "async def list_requirement_notes(project_id: str, requirement_id: str):",
        "async def list_requirement_notes(project_id: str, requirement_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # delete_auditor_note — requires notes:delete
    (
        "async def delete_auditor_note(project_id: str, note_id: str):",
        "async def delete_auditor_note(project_id: str, note_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"notes:delete\"))):",
    ),
    # list_task_uploads — requires project:view
    (
        "async def list_task_uploads(project_id: str, task_id: str):",
        "async def list_task_uploads(project_id: str, task_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # get_upload — requires project:view
    (
        "async def get_upload(project_id: str, upload_id: str):",
        "async def get_upload(project_id: str, upload_id: str, ctx: Dict[str, Any] = Depends(get_project_member_context)):",
    ),
    # delete_upload — requires remediation:delete
    (
        "async def delete_upload(project_id: str, upload_id: str):",
        "async def delete_upload(project_id: str, upload_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"remediation:delete\"))):",
    ),
    # get_single_audit_event — requires audit:view
    (
        "async def get_single_audit_event(project_id: str, event_id: str):",
        "async def get_single_audit_event(project_id: str, event_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"audit:view\"))):",
    ),
]

# Multi-line function signature patches
MULTILINE_PATCHES = [
    # save_requirement_override — requires overrides:create
    (
        "async def save_requirement_override(\n    project_id: str,\n    requirement_id: str,",
        "async def save_requirement_override(\n    project_id: str,\n    requirement_id: str,\n    ctx: Dict[str, Any] = Depends(require_permission(\"overrides:create\")),",
    ),
    # add_auditor_note — requires notes:create
    (
        "async def add_auditor_note(\n    project_id: str,\n    requirement_id: str,",
        "async def add_auditor_note(\n    project_id: str,\n    requirement_id: str,\n    ctx: Dict[str, Any] = Depends(require_permission(\"notes:create\")),",
    ),
    # upload_remediation_evidence — requires remediation:upload
    (
        "async def upload_remediation_evidence(\n    project_id: str,\n    task_id: str,",
        "async def upload_remediation_evidence(\n    project_id: str,\n    task_id: str,\n    ctx: Dict[str, Any] = Depends(require_permission(\"remediation:upload\")),",
    ),
    # get_custom_verification_delta — requires project:view
    (
        "async def get_custom_verification_delta(\n    project_id: str,",
        "async def get_custom_verification_delta(\n    project_id: str,\n    ctx: Dict[str, Any] = Depends(get_project_member_context),",
    ),
    # list_project_audit_events — requires audit:view
    (
        "async def list_project_audit_events(\n    project_id: str,",
        "async def list_project_audit_events(\n    project_id: str,\n    ctx: Dict[str, Any] = Depends(require_permission(\"audit:view\")),",
    ),
    # export_verification_run_pdf — requires reports:export
    (
        "async def export_verification_run_pdf(project_id: str, run_id: str):",
        "async def export_verification_run_pdf(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"reports:export\"))):",
    ),
    # export_verification_run_json — requires reports:export
    (
        "async def export_verification_run_json(project_id: str, run_id: str):",
        "async def export_verification_run_json(project_id: str, run_id: str, ctx: Dict[str, Any] = Depends(require_permission(\"reports:export\"))):",
    ),
]

for old, new in PATCHES:
    if old in content:
        content = content.replace(old, new, 1)
        print(f"  PATCHED: {old[:60]}...")
    else:
        print(f"  SKIP (not found): {old[:60]}...")

for old, new in MULTILINE_PATCHES:
    if old in content:
        content = content.replace(old, new, 1)
        print(f"  PATCHED multi: {old[:60]}...")
    else:
        print(f"  SKIP multi (not found): {old[:60]}...")

with open("app/api/routes.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\nDone. Verifying syntax...")
import ast
ast.parse(content)
print("Syntax OK!")
