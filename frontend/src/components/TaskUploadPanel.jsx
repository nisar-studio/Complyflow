import React, { useState, useEffect, useRef } from 'react';
import {
  Upload, Trash2, FileText, CheckCircle2, Clock, AlertCircle,
  Loader2, X, ChevronDown, ChevronUp, Paperclip,
} from 'lucide-react';
import api from '../api/client';

/**
 * TaskUploadPanel
 *
 * Renders an inline upload panel inside a remediation task card.
 * Shows existing uploads and lets the auditor add / remove evidence files.
 *
 * Props:
 *   projectId  – string
 *   task       – task object (must have task_id, related_requirement_id)
 *   requirements – full requirements array (for requirement_id lookup)
 */
export default function TaskUploadPanel({ projectId, task, requirements = [] }) {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [description, setDescription] = useState('');
  const fileInputRef = useRef(null);

  // Use task's related requirement as default; allow override via UI
  const defaultReqId = task?.related_requirement_id || (requirements[0]?.requirement_id ?? '');
  const [selectedReqId, setSelectedReqId] = useState(defaultReqId);

  // Refresh requirement selector when task changes
  useEffect(() => {
    setSelectedReqId(task?.related_requirement_id || (requirements[0]?.requirement_id ?? ''));
  }, [task?.task_id]);

  // Fetch existing uploads whenever panel is expanded
  useEffect(() => {
    if (expanded && projectId && task?.task_id) {
      fetchUploads();
    }
  }, [expanded, projectId, task?.task_id]);

  const fetchUploads = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listTaskUploads(projectId, task.task_id);
      setUploads(data || []);
    } catch (e) {
      setError('Failed to load uploads.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!selectedReqId) {
      setError('Please select a requirement before uploading.');
      return;
    }

    setUploading(true);
    setError('');
    try {
      await api.uploadRemediationEvidence(
        projectId,
        task.task_id,
        selectedReqId,
        file,
        description,
      );
      setDescription('');
      if (fileInputRef.current) fileInputRef.current.value = '';
      await fetchUploads();
    } catch (e) {
      const msg =
        e?.response?.data?.detail ||
        e?.message ||
        'Upload failed. Check file type and size (max 10 MiB).';
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (uploadId) => {
    if (!window.confirm('Delete this upload? This cannot be undone.')) return;
    setError('');
    try {
      await api.deleteUpload(projectId, uploadId);
      setUploads((prev) => prev.filter((u) => u.upload_id !== uploadId));
    } catch (e) {
      setError('Delete failed.');
    }
  };

  const statusIcon = (status) => {
    if (status === 'PENDING_VERIFICATION')
      return <Clock className="w-3.5 h-3.5 text-amber-400" />;
    if (status === 'VERIFIED')
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
    return <AlertCircle className="w-3.5 h-3.5 text-slate-400" />;
  };

  const statusLabel = (status) => {
    const map = {
      PENDING_VERIFICATION: 'Pending Verification',
      VERIFIED: 'Verified',
      REJECTED: 'Rejected',
    };
    return map[status] || status;
  };

  const formatSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDate = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="mt-3 border border-slate-700/60 rounded-xl overflow-hidden bg-slate-950/60">
      {/* Header toggle */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Paperclip className="w-3.5 h-3.5 text-brand-400" />
          Evidence Uploads
          {uploads.length > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-brand-600/20 text-brand-400 border border-brand-600/30 font-mono">
              {uploads.length}
            </span>
          )}
        </span>
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        )}
      </button>

      {expanded && (
        <div className="p-4 border-t border-slate-700/60 space-y-4">
          {/* Error banner */}
          {error && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{error}</span>
              <button className="ml-auto" onClick={() => setError('')}>
                <X className="w-3 h-3" />
              </button>
            </div>
          )}

          {/* Upload form */}
          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              Upload New Evidence
            </p>

            {/* Requirement selector */}
            <div>
              <label className="text-[10px] text-slate-400 mb-1 block">Requirement</label>
              <select
                value={selectedReqId}
                onChange={(e) => setSelectedReqId(e.target.value)}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {requirements.map((r) => (
                  <option key={r.requirement_id} value={r.requirement_id}>
                    {r.requirement_id} – {r.title || r.description?.slice(0, 60) || ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Description */}
            <div>
              <label className="text-[10px] text-slate-400 mb-1 block">
                Description <span className="text-slate-600">(optional)</span>
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Updated insurance certificate Q3 2026"
                className="w-full rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-xs px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-500 placeholder-slate-600"
              />
            </div>

            {/* File picker */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.png,.jpg,.jpeg,.txt"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || !selectedReqId}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white shadow-md shadow-brand-600/20 transition-all hover:scale-[1.02]"
            >
              {uploading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Upload className="w-3.5 h-3.5" />
              )}
              {uploading ? 'Uploading…' : 'Choose File & Upload'}
            </button>
            <p className="text-[10px] text-slate-600">
              Accepted: PDF, DOCX, PNG, JPG, TXT — max 10 MiB
            </p>
          </div>

          {/* Existing uploads list */}
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-2">
              Uploaded Evidence ({uploads.length})
            </p>
            {loading ? (
              <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
              </div>
            ) : uploads.length === 0 ? (
              <p className="text-xs text-slate-600 italic">No uploads yet for this task.</p>
            ) : (
              <div className="space-y-2">
                {uploads.map((u) => (
                  <div
                    key={u.upload_id}
                    className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-4 h-4 text-brand-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-white truncate">
                          {u.filename}
                        </p>
                        <p className="text-[10px] text-slate-500 truncate">
                          {u.requirement_id} · {formatSize(u.file_size)} · {formatDate(u.uploaded_at)}
                        </p>
                        {u.description && (
                          <p className="text-[10px] text-slate-400 italic truncate">
                            {u.description}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="flex items-center gap-1 text-[10px] font-mono text-slate-400">
                        {statusIcon(u.upload_status)}
                        {statusLabel(u.upload_status)}
                      </span>
                      <button
                        onClick={() => handleDelete(u.upload_id)}
                        title="Delete upload"
                        className="p-1 rounded hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Informational note */}
          <p className="text-[10px] text-slate-600">
            <span className="text-amber-400 font-semibold">Note:</span> Uploaded files are
            included as additional evidence in the next verification run. They do not automatically
            mark a requirement as Satisfied — the AI agent will re-evaluate all evidence.
          </p>
        </div>
      )}
    </div>
  );
}
