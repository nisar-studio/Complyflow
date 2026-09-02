import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  withCredentials: true,
  xsrfCookieName: 'complyflow_csrf',
  xsrfHeaderName: 'X-CSRF-Token',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
});

export const api = {
  // ── Projects ──────────────────────────────────────────
  createProject: async (name) => {
    const formData = new FormData();
    formData.append('name', name);
    const res = await client.post('/projects', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  listProjects: async () => {
    const res = await client.get('/projects');
    return res.data.projects;
  },

  getProject: async (id) => {
    const res = await client.get(`/projects/${id}`);
    return res.data;
  },

  deleteProject: async (id) => {
    const res = await client.delete(`/projects/${id}`);
    return res.data;
  },


  uploadDocuments: async (id, reqFile, evidenceFiles, isRemediation = false) => {
    const formData = new FormData();
    if (reqFile) {
      formData.append('requirements_file', reqFile);
    }
    if (evidenceFiles && evidenceFiles.length > 0) {
      for (const file of evidenceFiles) {
        formData.append('evidence_files', file);
      }
    }
    formData.append('is_remediation', isRemediation ? 'true' : 'false');
    const res = await client.post(`/projects/${id}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  startAnalysis: async (id) => {
    const res = await client.post(`/projects/${id}/analyze`);
    return res.data;
  },

  getEvents: async (id) => {
    const res = await client.get(`/projects/${id}/events`);
    return res.data.events;
  },

  getResults: async (id) => {
    const res = await client.get(`/projects/${id}/results`);
    return res.data;
  },

  startVerification: async (id) => {
    const res = await client.post(`/projects/${id}/verify`);
    return res.data;
  },

  // ── Verification Snapshots & Delta ────────────────────
  getVerificationRuns: async (id) => {
    const res = await client.get(`/projects/${id}/verification-runs`);
    return res.data.runs;
  },

  getVerificationRun: async (id, runId) => {
    const res = await client.get(`/projects/${id}/verification-runs/${runId}`);
    return res.data.run;
  },

  getRunDelta: async (id, runId) => {
    const res = await client.get(`/projects/${id}/verification-runs/${runId}/delta`);
    return res.data;
  },

  getVerificationDelta: async (id, fromRun, toRun) => {
    const res = await client.get(`/projects/${id}/verification-delta?from_run=${fromRun}&to_run=${toRun}`);
    return res.data;
  },

  // ── Document & Evidence Inspection ────────────────────
  getDocuments: async (id) => {
    const res = await client.get(`/projects/${id}/documents`);
    return res.data.documents;
  },

  getDocument: async (id, docId) => {
    const res = await client.get(`/projects/${id}/documents/${encodeURIComponent(docId)}`);
    return res.data.document;
  },

  // ── Auditor Overrides & Notes ─────────────────────────
  getOverrides: async (id) => {
    const res = await client.get(`/projects/${id}/overrides`);
    return res.data.overrides;
  },

  getOverride: async (id, reqId) => {
    const res = await client.get(`/projects/${id}/requirements/${encodeURIComponent(reqId)}/override`);
    return res.data.override;
  },

  saveOverride: async (id, reqId, payload) => {
    const res = await client.post(`/projects/${id}/requirements/${encodeURIComponent(reqId)}/override`, payload);
    return res.data;
  },

  deleteOverride: async (id, reqId) => {
    const res = await client.delete(`/projects/${id}/requirements/${encodeURIComponent(reqId)}/override`);
    return res.data;
  },

  saveNote: async (id, reqId, text) => {
    const res = await client.post(`/projects/${id}/requirements/${encodeURIComponent(reqId)}/notes`, { note_text: text });
    return res.data;
  },

  getNotes: async (id, reqId) => {
    const res = await client.get(`/projects/${id}/requirements/${encodeURIComponent(reqId)}/notes`);
    return res.data.notes;
  },

  deleteNote: async (id, noteId) => {
    const res = await client.delete(`/projects/${id}/notes/${encodeURIComponent(noteId)}`);
    return res.data;
  },

  // ── Bulk Auditor Operations ───────────────────────────
  bulkSaveOverrides: async (projectId, payload) => {
    const res = await client.post(`/projects/${projectId}/bulk/overrides`, payload);
    return res.data;
  },

  bulkSaveNotes: async (projectId, payload) => {
    const res = await client.post(`/projects/${projectId}/bulk/notes`, payload);
    return res.data;
  },

  bulkDeleteDocuments: async (projectId, docIds) => {
    const res = await client.post(`/projects/${projectId}/bulk/documents/delete`, { doc_ids: docIds });
    return res.data;
  },

  // ── Remediation Uploads ───────────────────────────────

  uploadRemediationEvidence: async (projectId, taskId, requirementId, file, description = '') => {
    const formData = new FormData();
    formData.append('requirement_id', requirementId);
    if (description) formData.append('description', description);
    formData.append('file', file);
    const res = await client.post(
      `/projects/${projectId}/tasks/${taskId}/uploads`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return res.data;
  },

  listTaskUploads: async (projectId, taskId) => {
    const res = await client.get(`/projects/${projectId}/tasks/${taskId}/uploads`);
    return res.data.uploads;
  },

  getUpload: async (projectId, uploadId) => {
    const res = await client.get(`/projects/${projectId}/uploads/${uploadId}`);
    return res.data.upload;
  },

  deleteUpload: async (projectId, uploadId) => {
    const res = await client.delete(`/projects/${projectId}/uploads/${uploadId}`);
    return res.data;
  },

  // ── Compliance Report Export ──────────────────────────
  getReportJson: async (projectId, runId) => {
    const res = await client.get(`/projects/${projectId}/verification-runs/${runId}/report.json`);
    return res.data;
  },

  downloadReportPdf: async (projectId, runId) => {
    const res = await client.get(`/projects/${projectId}/verification-runs/${runId}/report.pdf`, {
      responseType: 'blob',
    });
    const blob = new Blob([res.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `compliance_report_${projectId}_${runId}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return true;
  },

  downloadReportJson: async (projectId, runId) => {
    const data = await api.getReportJson(projectId, runId);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `compliance_report_${projectId}_${runId}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return true;
  },

  // ── Audit Activity Events ─────────────────────────────
  listAuditEvents: async (projectId, params = {}) => {
    const res = await client.get(`/projects/${projectId}/audit-events`, { params });
    return res.data;
  },

  getAuditEvent: async (projectId, eventId) => {
    const res = await client.get(`/projects/${projectId}/audit-events/${eventId}`);
    return res.data.event;
  },

  // ── Authentication & Users (Pure HttpOnly Cookie) ─────
  login: async (email, password) => {
    const res = await client.post('/auth/login', { email, password });
    return res.data;
  },

  register: async (email, name, password) => {
    const res = await client.post('/auth/register', { email, name, password });
    return res.data;
  },

  logout: async () => {
    const res = await client.post('/auth/logout');
    return res.data;
  },

  getMe: async () => {
    const res = await client.get('/auth/me');
    return res.data.user;
  },

  bootstrapAdmin: async () => {
    const res = await client.post('/auth/bootstrap');
    return res.data;
  },

  // ── Project Members (RBAC) ────────────────────────────
  listMembers: async (projectId) => {
    const res = await client.get(`/projects/${projectId}/members`);
    return res.data.members;
  },

  addMember: async (projectId, email, role) => {
    const res = await client.post(`/projects/${projectId}/members`, { email, role });
    return res.data;
  },

  updateMemberRole: async (projectId, userId, role) => {
    const res = await client.put(`/projects/${projectId}/members/${userId}`, { role });
    return res.data;
  },

  removeMember: async (projectId, userId) => {
    const res = await client.delete(`/projects/${projectId}/members/${userId}`);
    return res.data;
  },

  listAllUsers: async () => {
    const res = await client.get('/admin/users');
    return res.data.users;
  },

  // ── Custom Compliance Frameworks ──────────────────────
  previewFramework: async (projectId, file, name, version) => {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);
    if (version) formData.append('version', version);
    const res = await client.post(`/projects/${projectId}/frameworks/preview`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  importFramework: async (projectId, payload) => {
    const res = await client.post(`/projects/${projectId}/frameworks/import`, payload);
    return res.data;
  },

  listFrameworks: async (projectId) => {
    const res = await client.get(`/projects/${projectId}/frameworks`);
    return res.data.frameworks;
  },

  getFramework: async (projectId, frameworkId) => {
    const res = await client.get(`/projects/${projectId}/frameworks/${encodeURIComponent(frameworkId)}`);
    return res.data;
  },

  getFrameworkRequirements: async (projectId, frameworkId) => {
    const res = await client.get(`/projects/${projectId}/frameworks/${encodeURIComponent(frameworkId)}/requirements`);
    return res.data.requirements;
  },

  activateFramework: async (projectId, frameworkId, status) => {
    const res = await client.post(`/projects/${projectId}/frameworks/${encodeURIComponent(frameworkId)}/activate`, { status });
    return res.data;
  },

  applyFramework: async (projectId, frameworkId) => {
    const res = await client.post(`/projects/${projectId}/frameworks/${encodeURIComponent(frameworkId)}/apply`);
    return res.data;
  },

  deleteFramework: async (projectId, frameworkId) => {
    const res = await client.delete(`/projects/${projectId}/frameworks/${encodeURIComponent(frameworkId)}`);
    return res.data;
  },

  // ── Document Versioning ──────────────────────────────
  getDocumentVersions: async (projectId, docId) => {
    const res = await client.get(`/projects/${projectId}/documents/${encodeURIComponent(docId)}/versions`);
    return res.data.versions;
  },

  getDocumentVersion: async (projectId, docId, versionNumber) => {
    const res = await client.get(`/projects/${projectId}/documents/${encodeURIComponent(docId)}/versions/${versionNumber}`);
    return res.data.version;
  },

  // ── Remediation Task Status ────────────────────────────
  updateTaskStatus: async (projectId, taskId, status) => {
    const res = await client.put(`/projects/${projectId}/tasks/${taskId}/status`, { status });
    return res.data;
  },

  // ── Task Assignment ───────────────────────────────────
  assignTask: async (projectId, taskId, assignedTo, dueDate = null) => {
    const payload = { assigned_to: assignedTo };
    if (dueDate) payload.due_date = dueDate;
    const res = await client.put(`/projects/${projectId}/tasks/${taskId}/assign`, payload);
    return res.data;
  },

  // ── Due Date Management ───────────────────────────────
  setTaskDueDate: async (projectId, taskId, dueDate) => {
    const res = await client.put(`/projects/${projectId}/tasks/${taskId}/due-date`, { due_date: dueDate });
    return res.data;
  },

  // ── Bulk Task Operations ─────────────────────────────
  bulkUpdateTaskStatus: async (projectId, taskIds, status) => {
    const res = await client.post(`/projects/${projectId}/bulk/tasks/status`, {
      task_ids: taskIds,
      status,
    });
    return res.data;
  },

  bulkAssignTasks: async (projectId, taskIds, assignedTo, dueDate = null) => {
    const payload = { task_ids: taskIds, assigned_to: assignedTo };
    if (dueDate) payload.due_date = dueDate;
    const res = await client.post(`/projects/${projectId}/bulk/tasks/assign`, payload);
    return res.data;
  },

  // ── In-App Notifications ──────────────────────────────
  getNotifications: async (params = {}) => {
    const res = await client.get('/notifications', { params });
    return res.data;
  },

  getUnreadCount: async (projectId = null) => {
    const params = {};
    if (projectId) params.project_id = projectId;
    const res = await client.get('/notifications/unread-count', { params });
    return res.data;
  },

  markNotificationRead: async (notificationId) => {
    const res = await client.put(`/notifications/${notificationId}/read`);
    return res.data;
  },

  markAllNotificationsRead: async (projectId = null) => {
    const params = {};
    if (projectId) params.project_id = projectId;
    const res = await client.put('/notifications/read-all', null, { params });
    return res.data;
  },

  // ── Enterprise Compliance Analytics ─────────────────────
  getProjectAnalytics: async (projectId) => {
    const res = await client.get(`/projects/${projectId}/analytics`);
    return res.data;
  },

  getPortfolioAnalytics: async () => {
    const res = await client.get('/analytics/portfolio');
    return res.data;
  },
};


export default api;
