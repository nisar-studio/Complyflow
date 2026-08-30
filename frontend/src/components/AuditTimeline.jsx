import React, { useState, useEffect, useMemo } from 'react';
import {
  Clock, Shield, Bot, UserCheck, AlertTriangle, AlertCircle, Info,
  Search, Filter, RotateCcw, ChevronDown, ChevronRight, FileText,
  UploadCloud, CheckCircle2, XCircle, FileSpreadsheet, RefreshCw,
  ExternalLink, Layers, ArrowUpRight, Copy, Check
} from 'lucide-react';
import api from '../api/client';

export default function AuditTimeline({ projectId, onNavigateTab }) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const limit = 50;

  // Filters
  const [selectedEventType, setSelectedEventType] = useState('');
  const [selectedActorType, setSelectedActorType] = useState('');
  const [selectedSeverity, setSelectedSeverity] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Expanded event metadata state
  const [expandedEventIds, setExpandedEventIds] = useState(new Set());
  const [copiedId, setCopiedId] = useState(null);

  const fetchEvents = async (newOffset = 0, append = false) => {
    try {
      if (append) setLoadingMore(true);
      else setLoading(true);

      const params = {
        limit,
        offset: newOffset,
      };
      if (selectedEventType) params.event_type = selectedEventType;
      if (selectedActorType) params.actor_type = selectedActorType;
      if (selectedSeverity) params.severity = selectedSeverity;

      const res = await api.listAuditEvents(projectId, params);
      if (append) {
        setEvents(prev => [...prev, ...(res.events || [])]);
      } else {
        setEvents(res.events || []);
      }
      setTotal(res.total || 0);
      setOffset(newOffset);
    } catch (err) {
      console.error('Failed to load audit events:', err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchEvents(0, false);
  }, [projectId, selectedEventType, selectedActorType, selectedSeverity]);

  const handleResetFilters = () => {
    setSelectedEventType('');
    setSelectedActorType('');
    setSelectedSeverity('');
    setSearchQuery('');
  };

  const toggleExpand = (id) => {
    setExpandedEventIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCopy = (id, text) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Client-side search filtering across summary, description, requirement_id, run_id, task_id
  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return events;
    const q = searchQuery.toLowerCase().trim();
    return events.filter(e => {
      const summary = (e.summary || '').toLowerCase();
      const desc = (e.description || '').toLowerCase();
      const reqId = (e.requirement_id || '').toLowerCase();
      const runId = (e.run_id || '').toLowerCase();
      const taskId = (e.task_id || '').toLowerCase();
      const docId = (e.document_id || '').toLowerCase();
      const evtId = (e.event_id || '').toLowerCase();
      const etype = (e.event_type || '').toLowerCase();
      return (
        summary.includes(q) ||
        desc.includes(q) ||
        reqId.includes(q) ||
        runId.includes(q) ||
        taskId.includes(q) ||
        docId.includes(q) ||
        evtId.includes(q) ||
        etype.includes(q)
      );
    });
  }, [events, searchQuery]);

  const getActorBadge = (actorType) => {
    switch (actorType) {
      case 'AUDITOR':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <UserCheck className="w-3 h-3" />
            <span>AUDITOR</span>
          </span>
        );
      case 'AI_AGENT':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-brand-500/10 text-brand-400 border border-brand-500/30">
            <Bot className="w-3 h-3" />
            <span>AI AGENT</span>
          </span>
        );
      case 'SYSTEM':
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">
            <Shield className="w-3 h-3" />
            <span>SYSTEM</span>
          </span>
        );
    }
  };

  const getSeverityBadge = (severity) => {
    switch (severity) {
      case 'ERROR':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-red-500/10 text-red-400 border border-red-500/30">
            <XCircle className="w-3 h-3" />
            <span>ERROR</span>
          </span>
        );
      case 'WARNING':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <AlertTriangle className="w-3 h-3" />
            <span>WARNING</span>
          </span>
        );
      case 'INFO':
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800/80 text-slate-400 border border-slate-700/60">
            <Info className="w-3 h-3" />
            <span>INFO</span>
          </span>
        );
    }
  };

  const getEventIcon = (eventType, severity) => {
    if (severity === 'ERROR') return <XCircle className="w-4 h-4 text-red-400" />;
    if (severity === 'WARNING') return <AlertTriangle className="w-4 h-4 text-amber-400" />;

    switch (eventType) {
      case 'PROJECT_CREATED':
        return <Shield className="w-4 h-4 text-brand-400" />;
      case 'DOCUMENT_UPLOADED':
        return <FileText className="w-4 h-4 text-blue-400" />;
      case 'DOCUMENT_DELETED':
        return <FileText className="w-4 h-4 text-slate-400" />;
      case 'ANALYSIS_STARTED':
      case 'VERIFICATION_STARTED':
        return <RefreshCw className="w-4 h-4 text-brand-400 animate-spin" />;
      case 'ANALYSIS_COMPLETED':
      case 'VERIFICATION_COMPLETED':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
      case 'REQUIREMENT_CONFLICT_DETECTED':
        return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case 'REQUIREMENT_GAP_DETECTED':
        return <AlertCircle className="w-4 h-4 text-amber-400" />;
      case 'REMEDIATION_TASK_CREATED':
        return <Layers className="w-4 h-4 text-purple-400" />;
      case 'REMEDIATION_UPLOAD_CREATED':
        return <UploadCloud className="w-4 h-4 text-emerald-400" />;
      case 'AUDITOR_OVERRIDE_CREATED':
      case 'AUDITOR_OVERRIDE_UPDATED':
      case 'AUDITOR_OVERRIDE_REVOKED':
        return <UserCheck className="w-4 h-4 text-emerald-400" />;
      case 'AUDITOR_NOTE_CREATED':
      case 'AUDITOR_NOTE_DELETED':
        return <FileText className="w-4 h-4 text-indigo-400" />;
      case 'REPORT_EXPORTED':
        return <FileSpreadsheet className="w-4 h-4 text-brand-400" />;
      default:
        return <Clock className="w-4 h-4 text-slate-400" />;
    }
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return isoStr;
    }
  };

  const hasActiveFilters = Boolean(selectedEventType || selectedActorType || selectedSeverity || searchQuery);

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-brand-500/10 border border-brand-500/30 text-brand-400">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center space-x-2">
                <span>Enterprise Audit Activity Log</span>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  Append-Only
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Immutable, chronological provenance trail of all agent analyses, auditor overrides, document actions, and reports.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => fetchEvents(0, false)}
              className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center space-x-1.5 transition-colors border border-slate-700"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="pt-4 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs">
          {/* Search Box */}
          <div className="relative col-span-1 sm:col-span-2">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search summary, req ID, run ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-500 transition-colors"
            />
          </div>

          {/* Event Type Filter */}
          <div>
            <select
              value={selectedEventType}
              onChange={(e) => setSelectedEventType(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
            >
              <option value="">All Event Types</option>
              <option value="PROJECT_CREATED">PROJECT_CREATED</option>
              <option value="DOCUMENT_UPLOADED">DOCUMENT_UPLOADED</option>
              <option value="DOCUMENT_DELETED">DOCUMENT_DELETED</option>
              <option value="ANALYSIS_STARTED">ANALYSIS_STARTED</option>
              <option value="ANALYSIS_COMPLETED">ANALYSIS_COMPLETED</option>
              <option value="ANALYSIS_FAILED">ANALYSIS_FAILED</option>
              <option value="VERIFICATION_STARTED">VERIFICATION_STARTED</option>
              <option value="VERIFICATION_COMPLETED">VERIFICATION_COMPLETED</option>
              <option value="VERIFICATION_FAILED">VERIFICATION_FAILED</option>
              <option value="REQUIREMENT_CONFLICT_DETECTED">REQUIREMENT_CONFLICT_DETECTED</option>
              <option value="REQUIREMENT_GAP_DETECTED">REQUIREMENT_GAP_DETECTED</option>
              <option value="REMEDIATION_TASK_CREATED">REMEDIATION_TASK_CREATED</option>
              <option value="REMEDIATION_UPLOAD_CREATED">REMEDIATION_UPLOAD_CREATED</option>
              <option value="REMEDIATION_UPLOAD_DELETED">REMEDIATION_UPLOAD_DELETED</option>
              <option value="AUDITOR_OVERRIDE_CREATED">AUDITOR_OVERRIDE_CREATED</option>
              <option value="AUDITOR_OVERRIDE_UPDATED">AUDITOR_OVERRIDE_UPDATED</option>
              <option value="AUDITOR_OVERRIDE_REVOKED">AUDITOR_OVERRIDE_REVOKED</option>
              <option value="AUDITOR_NOTE_CREATED">AUDITOR_NOTE_CREATED</option>
              <option value="AUDITOR_NOTE_DELETED">AUDITOR_NOTE_DELETED</option>
              <option value="REPORT_EXPORTED">REPORT_EXPORTED</option>
            </select>
          </div>

          {/* Actor Filter */}
          <div>
            <select
              value={selectedActorType}
              onChange={(e) => setSelectedActorType(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
            >
              <option value="">All Actors</option>
              <option value="AUDITOR">Auditor (Human)</option>
              <option value="AI_AGENT">AI Agent</option>
              <option value="SYSTEM">System</option>
            </select>
          </div>

          {/* Severity Filter */}
          <div className="flex items-center space-x-2">
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
            >
              <option value="">All Severities</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>

            {hasActiveFilters && (
              <button
                onClick={handleResetFilters}
                title="Reset all filters"
                className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Timeline Stream */}
      {loading ? (
        <div className="p-12 rounded-2xl bg-slate-900 border border-slate-800 text-center space-y-3">
          <RefreshCw className="w-6 h-6 animate-spin text-brand-400 mx-auto" />
          <p className="text-xs text-slate-400">Loading audit activity trail...</p>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="p-12 rounded-2xl bg-slate-900 border border-slate-800 text-center space-y-3">
          <Clock className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300">No Audit Events Found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {hasActiveFilters
              ? 'No events match your selected filters. Try resetting the filters.'
              : 'Actions will automatically be logged here as they occur in this compliance workspace.'}
          </p>
          {hasActiveFilters && (
            <button
              onClick={handleResetFilters}
              className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 text-xs font-semibold hover:bg-slate-700"
            >
              Reset Filters
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-400 px-1">
            <span>Showing {filteredEvents.length} of {total} recorded audit events</span>
            <span className="font-mono text-[11px] text-slate-500">Ordered newest first</span>
          </div>

          <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-800">
            {filteredEvents.map((evt) => {
              const isExpanded = expandedEventIds.has(evt.event_id);
              const metaKeys = evt.metadata ? Object.keys(evt.metadata) : [];
              const hasMetadata = metaKeys.length > 0 || evt.description;

              return (
                <div
                  key={evt.event_id}
                  className="relative group bg-slate-900/90 hover:bg-slate-900 border border-slate-800/90 hover:border-slate-700/80 rounded-2xl p-4 transition-all shadow-sm"
                >
                  {/* Timeline node icon */}
                  <div className="absolute -left-[27px] top-4.5 w-6 h-6 rounded-full bg-slate-950 border border-slate-700 flex items-center justify-center shadow">
                    {getEventIcon(evt.event_type, evt.severity)}
                  </div>

                  <div className="space-y-2.5">
                    {/* Header line */}
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {getActorBadge(evt.actor_type)}
                        <span className="font-mono text-xs font-bold text-slate-200 tracking-wide">
                          {evt.event_type}
                        </span>
                        {getSeverityBadge(evt.severity)}
                      </div>

                      <div className="flex items-center space-x-2 text-xs text-slate-400">
                        <span className="font-mono text-[11px]">{formatDate(evt.timestamp)}</span>
                      </div>
                    </div>

                    {/* Summary text */}
                    <p className="text-xs text-slate-200 leading-relaxed font-medium">
                      {evt.summary}
                    </p>

                    {/* Context Deep-Link References */}
                    {(evt.requirement_id || evt.run_id || evt.task_id || evt.document_id || evt.upload_id) && (
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        {evt.requirement_id && (
                          <button
                            onClick={() => onNavigateTab && onNavigateTab('results')}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800/90 hover:bg-brand-600/20 text-brand-300 hover:text-brand-200 border border-slate-700/80 text-[11px] transition-colors"
                            title="Jump to requirement"
                          >
                            <span>Req: {evt.requirement_id}</span>
                            <ArrowUpRight className="w-3 h-3" />
                          </button>
                        )}

                        {evt.run_id && (
                          <button
                            onClick={() => onNavigateTab && onNavigateTab('history')}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800/90 hover:bg-brand-600/20 text-indigo-300 hover:text-indigo-200 border border-slate-700/80 text-[11px] transition-colors"
                            title="Jump to verification history"
                          >
                            <span>Run: {evt.run_id}</span>
                            <ArrowUpRight className="w-3 h-3" />
                          </button>
                        )}

                        {evt.task_id && (
                          <button
                            onClick={() => onNavigateTab && onNavigateTab('remediation')}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800/90 hover:bg-brand-600/20 text-purple-300 hover:text-purple-200 border border-slate-700/80 text-[11px] transition-colors"
                            title="Jump to remediation tasks"
                          >
                            <span>Task: {evt.task_id}</span>
                            <ArrowUpRight className="w-3 h-3" />
                          </button>
                        )}

                        {evt.document_id && (
                          <button
                            onClick={() => onNavigateTab && onNavigateTab('documents')}
                            className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800/90 hover:bg-brand-600/20 text-sky-300 hover:text-sky-200 border border-slate-700/80 text-[11px] transition-colors"
                            title="Jump to document viewer"
                          >
                            <span>Doc: {evt.document_id}</span>
                            <ArrowUpRight className="w-3 h-3" />
                          </button>
                        )}

                        {evt.upload_id && (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/60 text-[11px]">
                            <span>Upload: {evt.upload_id.slice(0, 8)}</span>
                          </span>
                        )}
                      </div>
                    )}

                    {/* Metadata Accordion Toggle */}
                    {hasMetadata && (
                      <div className="pt-2">
                        <button
                          onClick={() => toggleExpand(evt.event_id)}
                          className="flex items-center space-x-1.5 text-[11px] font-semibold text-slate-400 hover:text-slate-200 transition-colors"
                        >
                          {isExpanded ? (
                            <ChevronDown className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronRight className="w-3.5 h-3.5" />
                          )}
                          <span>{isExpanded ? 'Hide Details & Metadata' : 'Inspect Audit Metadata'}</span>
                        </button>

                        {isExpanded && (
                          <div className="mt-2.5 p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-2">
                            {evt.description && (
                              <p className="text-slate-300 leading-relaxed font-sans pb-2 border-b border-slate-800/80">
                                {evt.description}
                              </p>
                            )}

                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[10px] uppercase text-slate-500">
                                Event ID: {evt.event_id}
                              </span>
                              <button
                                onClick={() => handleCopy(evt.event_id, JSON.stringify(evt, null, 2))}
                                className="flex items-center space-x-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
                              >
                                {copiedId === evt.event_id ? (
                                  <>
                                    <Check className="w-3 h-3 text-emerald-400" />
                                    <span className="text-emerald-400">Copied</span>
                                  </>
                                ) : (
                                  <>
                                    <Copy className="w-3 h-3" />
                                    <span>Copy JSON</span>
                                  </>
                                )}
                              </button>
                            </div>

                            <pre className="text-[11px] font-mono text-slate-300 bg-slate-900/80 p-2.5 rounded-lg overflow-x-auto border border-slate-800/80">
                              {JSON.stringify(evt.metadata || {}, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Load More Button */}
          {events.length < total && (
            <div className="pt-4 text-center">
              <button
                onClick={() => fetchEvents(offset + limit, true)}
                disabled={loadingMore}
                className="px-5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors disabled:opacity-50 inline-flex items-center space-x-2 border border-slate-700"
              >
                {loadingMore && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Load More ({total - events.length} remaining)</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
