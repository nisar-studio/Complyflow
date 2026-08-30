import React, { useState, useEffect, useCallback } from 'react';
import { X, Users, Plus, Trash2, RefreshCw, AlertCircle, CheckCircle2, Shield } from 'lucide-react';
import api from '../api/client';

const ROLES = ['ADMIN', 'AUDITOR', 'REVIEWER', 'VIEWER'];

const ROLE_COLORS = {
  ADMIN:    'text-purple-400 bg-purple-500/10 border-purple-500/20',
  AUDITOR:  'text-brand-400 bg-brand-500/10 border-brand-500/20',
  REVIEWER: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20',
  VIEWER:   'text-slate-400 bg-slate-500/10 border-slate-500/20',
};

export default function ProjectMembersModal({ projectId, onClose }) {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Add member form
  const [addEmail, setAddEmail] = useState('');
  const [addRole, setAddRole] = useState('REVIEWER');
  const [adding, setAdding] = useState(false);

  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const list = await api.listMembers(projectId);
      setMembers(list || []);
    } catch (e) {
      setError('Failed to load members.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!addEmail.trim()) return;
    setAdding(true);
    setError('');
    setSuccess('');
    try {
      await api.addMember(projectId, addEmail.trim(), addRole);
      setSuccess(`${addEmail.trim()} added as ${addRole}.`);
      setAddEmail('');
      await loadMembers();
    } catch (e) {
      const msg = e?.response?.data?.error?.message || 'Failed to add member.';
      setError(msg);
    } finally {
      setAdding(false);
    }
  };

  const handleRoleChange = async (userId, newRole) => {
    setError('');
    setSuccess('');
    try {
      await api.updateMemberRole(projectId, userId, newRole);
      setSuccess('Role updated.');
      await loadMembers();
    } catch (e) {
      const msg = e?.response?.data?.error?.message || 'Failed to update role.';
      setError(msg);
    }
  };

  const handleRemove = async (userId, memberName) => {
    if (!window.confirm(`Remove ${memberName} from this project?`)) return;
    setError('');
    setSuccess('');
    try {
      await api.removeMember(projectId, userId);
      setSuccess(`${memberName} removed.`);
      await loadMembers();
    } catch (e) {
      const msg = e?.response?.data?.error?.message || 'Failed to remove member.';
      setError(msg);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-brand-400" />
            <h2 className="text-base font-semibold text-white">Project Members</h2>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* Status messages */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {success && (
            <div className="flex items-center gap-2 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2.5 text-sm text-green-300">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {/* Add member */}
          <form onSubmit={handleAddMember} className="flex gap-2">
            <input
              type="email"
              required
              value={addEmail}
              onChange={(e) => setAddEmail(e.target.value)}
              placeholder="user@company.com"
              className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500/50 transition"
            />
            <select
              value={addRole}
              onChange={(e) => setAddRole(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800/50 px-2 py-2 text-sm text-white focus:border-brand-500 focus:outline-none transition"
            >
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button
              type="submit"
              disabled={adding}
              className="flex items-center gap-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 disabled:opacity-60 px-3 py-2 text-sm font-medium text-white transition"
            >
              {adding ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              Add
            </button>
          </form>

          {/* Members list */}
          {loading ? (
            <div className="flex items-center justify-center py-8 text-slate-500 text-sm gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" /> Loading members…
            </div>
          ) : members.length === 0 ? (
            <p className="text-center text-slate-500 text-sm py-6">No members found.</p>
          ) : (
            <div className="space-y-2">
              {members.map((m) => (
                <div
                  key={m.user_id}
                  className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg border border-slate-800 bg-slate-800/30"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center shrink-0">
                      <Shield className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white truncate">{m.name || m.email}</p>
                      <p className="text-xs text-slate-500 truncate">{m.email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <select
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                      className={`rounded border px-1.5 py-0.5 text-xs font-mono uppercase font-medium ${ROLE_COLORS[m.role] || ROLE_COLORS.VIEWER} bg-transparent focus:outline-none transition`}
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                    <button
                      onClick={() => handleRemove(m.user_id, m.name || m.email)}
                      className="text-slate-600 hover:text-red-400 transition"
                      title="Remove member"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
