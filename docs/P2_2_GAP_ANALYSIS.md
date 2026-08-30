# ComplyFlow — P2 #2 UX Gap Analysis
> **Audit Date**: 2026-08-30  
> **Scope**: Auditor Productivity Bottlenecks in Frontend (No invented problems)

---

## 1. Requirements Workspace

### GAP-A-01 [P2] No Bulk Selection or Bulk Actions
`RequirementsList.jsx` renders each requirement as a standalone expand/collapse row. There is **no checkbox**, no "Select All", no bulk operation toolbar. An auditor with 50 MISSING requirements must open each one individually to set an override — this is the dominant time sink in the whole application.

### GAP-A-02 [P2] Filter State Lost on Navigation
Search query, status filter, priority filter and sort order are React `useState` only. Refreshing the browser, using browser back/forward, or sharing a link drops all filters. An auditor mid-investigation has to reconstruct their workspace every time.

### GAP-A-03 [P2] No Quick-View / Detail Drawer
To read evidence details, auditor must expand an accordion row. There is no side-drawer or modal that allows full detail review without leaving context. The expanded accordion collapses if any other row is clicked (the `expandedId` is singular).

### GAP-A-04 [P3] Keyboard Navigation Missing
No `j/k` list navigation, no `/` to focus search, no `Esc` to dismiss drawer/modal. Entirely mouse-driven.

---

## 2. Document & Evidence Library

### GAP-B-01 [P2] No Multi-Select or Bulk Delete in DocumentViewer
`DocumentViewer.jsx` shows a left-panel list of documents with no checkbox, no selection state, and no bulk delete control. Auditors managing a large evidence library must delete files one at a time — and currently there is **no delete control at all** in the document library UI (the route exists in the backend for uploads only, not for primary documents).

### GAP-B-02 [P2] No File-Type or Role Filtering in Document Library
All documents (requirements + evidence) are shown in a single flat list. Filtering by `.pdf`, `.docx`, `.txt`, by `role` (requirements vs evidence), or by OCR status does not exist.

### GAP-B-03 [P2] No Document Search by Filename
The full-text search in `DocumentViewer` searches chunk text — there is no filter/search box for the document list sidebar itself by filename.

### GAP-B-04 [P3] No Aggregate Metrics (document count by type/role)
No summary badges showing "5 PDFs, 3 TXT, 1 requirements document" before the list.

---

## 3. Remediation Task List

### GAP-C-01 [P2] RemediationList Has No Filtering or Search
`RemediationList.jsx` is 79 lines. It renders a flat, unsorted list of tasks with no search, no severity filter, no related-requirement filter, no status indicator per task, and no empty-state feedback per task. With 50+ tasks this is unnavigable.

### GAP-C-02 [P2] No Bulk Upload Selection
Each task's remediation upload is individual. There is no multi-task bulk upload or any cross-task operation.

### GAP-C-03 [P3] Task Status Not Visible
The task model has a `status` field (`OPEN`/`RESOLVED`/`PENDING`) but the UI does not surface it. Auditors cannot see which tasks already have uploads without opening each one.

---

## 4. Verification History

### GAP-D-01 [P2] Run Selection UI is Implicit
The run selection in `VerificationHistory.jsx` auto-selects the latest run. There is no explicit "compare run X vs run Y" picker — the delta is always first vs last. Auditors cannot compare two arbitrary runs.

### GAP-D-02 [P3] No Run-Level Metadata Summary
No display of: which documents were present for that run, how many overrides existed at snapshot time, or auditor notes linked to that run.

---

## 5. Audit Activity Log

### GAP-E-01 [P2] AuditTimeline Has No Filtering by Event Type
`AuditTimeline.jsx` shows all events in chronological order with no filter for `MEMBER_ADDED`, `OVERRIDE_CREATED`, etc. In a mature project with hundreds of audit events, this is noise-heavy.

### GAP-E-02 [P3] No Date Range Filter in AuditTimeline
No from/to date pickers for scoping events to a sprint or review period.

---

## 6. Project Dashboard

### GAP-F-01 [P3] Dashboard Shows All Projects Without Filtering
The project list in `Dashboard.jsx` has no search or status filter. A user with 20+ projects has to scroll to find one.

---

## 7. Project Members

### GAP-G-01 [P3] ProjectMembersModal Shows No Audit History
The members modal shows the current member list but does not link to the audit events for member changes (MEMBER_ADDED, MEMBER_REMOVED, MEMBER_ROLE_UPDATED). The events are recorded but not surfaced.

---

## 8. Auditor Override Workflow

### GAP-H-01 [P2] Single-Requirement Override Only
Overrides are created one at a time via the modal in `RequirementsList.jsx`. There is no way to bulk-override multiple MISSING requirements after an audit round determines they are all SATISFIED following a policy update.

### GAP-H-02 [P2] No Override Audit History Inline
After setting an override, the auditor cannot see the history of previous overrides on that requirement without going to the AuditTimeline and searching.

---

## Priority Summary

| ID | Severity | Description |
|---|---|---|
| GAP-A-01 | **P2** | No bulk selection/action in RequirementsList |
| GAP-A-02 | **P2** | Filter state lost on navigation |
| GAP-A-03 | **P2** | No quick-view/detail drawer |
| GAP-A-04 | P3 | Keyboard navigation missing |
| GAP-B-01 | **P2** | No multi-select or document filtering in DocumentViewer |
| GAP-B-02 | **P2** | No file-type/role filter in document library |
| GAP-B-03 | **P2** | No filename search in document sidebar |
| GAP-B-04 | P3 | No aggregate document metrics |
| GAP-C-01 | **P2** | No filtering/search in RemediationList |
| GAP-C-02 | **P2** | No cross-task bulk operations |
| GAP-C-03 | P3 | Task status not visible |
| GAP-D-01 | **P2** | No arbitrary run comparison in VerificationHistory |
| GAP-E-01 | **P2** | No event-type filter in AuditTimeline |
| GAP-F-01 | P3 | Dashboard lacks project search |
| GAP-G-01 | P3 | Member changes not linked from members modal |
| GAP-H-01 | **P2** | Single-requirement override only |
| GAP-H-02 | **P2** | No inline override history |
