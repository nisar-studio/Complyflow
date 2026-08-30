import React, { useState, useMemo, useEffect, useRef } from 'react';
import { 
  CheckCircle2, AlertCircle, AlertTriangle, XCircle, FileText, 
  ChevronDown, ChevronUp, Quote, ShieldCheck, ExternalLink, 
  BookOpen, Layers, Search, Sparkles, ArrowRightLeft, HelpCircle, 
  X, Filter, ArrowUpDown, RotateCcw, UserCheck, Edit3, Trash2, Shield,
  CheckSquare, Square, MinusSquare, MessageSquare, CornerDownRight,
  Eye, Check, ListChecks, ArrowRight, Clock, AlertOctagon
} from 'lucide-react';
import DocumentViewer from './DocumentViewer';
import api from '../api/client';

export default function RequirementsList({ 
  matches = [], 
  requirements = [], 
  overrides = [], 
  projectId = null,
  onOverrideUpdated = null,
}) {
  const [expandedId, setExpandedId] = useState(null);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [drawerReq, setDrawerReq] = useState(null); // Requirement Quick View Drawer
  const [activeKeyboardIndex, setActiveKeyboardIndex] = useState(-1);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL'); // ALL | SATISFIED | MISSING | CONFLICT | PARTIAL
  const [priorityFilter, setPriorityFilter] = useState('ALL'); // ALL | CRITICAL | HIGH | MEDIUM | LOW
  const [sortBy, setSortBy] = useState('severity_desc'); // severity_desc | severity_asc | status | req_id_asc | req_id_desc | title_asc

  // Multi-selection state
  const [selectedReqIds, setSelectedReqIds] = useState(new Set());

  // Single Override Modal state
  const [overrideModalReq, setOverrideModalReq] = useState(null);
  const [overrideStatus, setOverrideStatus] = useState('SATISFIED');
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideNote, setOverrideNote] = useState('');
  const [savingOverride, setSavingOverride] = useState(false);
  const [overrideError, setOverrideError] = useState(null);

  // Bulk Override Modal state
  const [showBulkOverrideModal, setShowBulkOverrideModal] = useState(false);
  const [bulkOverrideStatus, setBulkOverrideStatus] = useState('SATISFIED');
  const [bulkOverrideReason, setBulkOverrideReason] = useState('');
  const [bulkOverrideNote, setBulkOverrideNote] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkError, setBulkError] = useState(null);

  // Bulk Note Modal state
  const [showBulkNoteModal, setShowBulkNoteModal] = useState(false);
  const [bulkNoteText, setBulkNoteText] = useState('');
  const [bulkNoteSaving, setBulkNoteSaving] = useState(false);
  const [bulkNoteError, setBulkNoteError] = useState(null);

  const searchInputRef = useRef(null);

  // URL Query Param Sync (Read on mount)
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const q = params.get('q');
      const status = params.get('status');
      const priority = params.get('priority');
      const sort = params.get('sort');
      const reqParam = params.get('req');

      if (q) setSearchQuery(q);
      if (status && ['ALL', 'SATISFIED', 'MISSING', 'CONFLICT', 'PARTIAL'].includes(status)) setStatusFilter(status);
      if (priority && ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(priority)) setPriorityFilter(priority);
      if (sort) setSortBy(sort);
      if (reqParam) {
        setExpandedId(reqParam);
      }
    } catch {
      // Ignore URL parsing errors
    }
  }, []);

  // URL Query Param Sync (Write on change)
  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      if (searchQuery.trim()) url.searchParams.set('q', searchQuery.trim());
      else url.searchParams.delete('q');

      if (statusFilter !== 'ALL') url.searchParams.set('status', statusFilter);
      else url.searchParams.delete('status');

      if (priorityFilter !== 'ALL') url.searchParams.set('priority', priorityFilter);
      else url.searchParams.delete('priority');

      if (sortBy !== 'severity_desc') url.searchParams.set('sort', sortBy);
      else url.searchParams.delete('sort');

      if (expandedId) url.searchParams.set('req', expandedId);
      else url.searchParams.delete('req');

      window.history.replaceState({}, '', url.toString());
    } catch {
      // Ignore URL write errors
    }
  }, [searchQuery, statusFilter, priorityFilter, sortBy, expandedId]);

  // Combine requirement definitions with match results and human overrides
  const allItems = useMemo(() => {
    const overrideMap = {};
    (overrides || []).forEach(o => {
      overrideMap[o.requirement_id] = o;
    });

    return (matches.length > 0 ? matches : requirements).map(item => {
      const match = matches.find(m => m.requirement_id === item.requirement_id) || item;
      const req = requirements.find(r => r.requirement_id === item.requirement_id) || item;
      const aiStatus = match.status || 'UNKNOWN';
      const override = overrideMap[item.requirement_id];
      const effectiveStatus = override ? override.overridden_status : aiStatus;

      return {
        ...req,
        ...match,
        ai_status: aiStatus,
        status: effectiveStatus,
        has_override: !!override,
        override_data: override || null,
        priority: (req.priority || match.priority || 'MEDIUM').toUpperCase(),
        evidence: match.evidence || [],
      };
    });
  }, [matches, requirements, overrides]);

  // Priority weight for deterministic sorting
  const priorityWeight = {
    CRITICAL: 4,
    HIGH: 3,
    MEDIUM: 2,
    LOW: 1,
  };

  // Status weight for sorting
  const statusWeight = {
    CONFLICT: 4,
    MISSING: 3,
    PARTIAL: 2,
    SATISFIED: 1,
    UNKNOWN: 0,
  };

  // Metric counts across full dataset
  const counts = useMemo(() => {
    return {
      total: allItems.length,
      satisfied: allItems.filter(i => i.status === 'SATISFIED').length,
      missing: allItems.filter(i => i.status === 'MISSING').length,
      conflict: allItems.filter(i => i.status === 'CONFLICT').length,
      partial: allItems.filter(i => i.status === 'PARTIAL').length,
      critical: allItems.filter(i => i.priority === 'CRITICAL').length,
      high: allItems.filter(i => i.priority === 'HIGH').length,
      overridden: allItems.filter(i => i.has_override).length,
    };
  }, [allItems]);

  // Filtered & Sorted items
  const filteredItems = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();

    const filtered = allItems.filter(item => {
      // 1. Status filter
      if (statusFilter !== 'ALL' && item.status !== statusFilter) {
        return false;
      }

      // 2. Priority/Severity filter
      if (priorityFilter !== 'ALL' && item.priority !== priorityFilter) {
        return false;
      }

      // 3. Search query filter
      if (q) {
        const matchId = item.requirement_id.toLowerCase().includes(q);
        const matchTitle = (item.title || item.requirement_title || '').toLowerCase().includes(q);
        const matchDesc = (item.description || '').toLowerCase().includes(q);
        const matchEvidence = item.evidence?.some(ev => 
          (ev.document_name || '').toLowerCase().includes(q) ||
          (ev.quote || '').toLowerCase().includes(q)
        );
        const matchReason = (item.override_data?.auditor_reason || '').toLowerCase().includes(q);

        if (!matchId && !matchTitle && !matchDesc && !matchEvidence && !matchReason) {
          return false;
        }
      }

      return true;
    });

    // Sort items deterministically
    return filtered.sort((a, b) => {
      switch (sortBy) {
        case 'severity_desc': {
          const diff = (priorityWeight[b.priority] || 0) - (priorityWeight[a.priority] || 0);
          return diff !== 0 ? diff : a.requirement_id.localeCompare(b.requirement_id);
        }
        case 'severity_asc': {
          const diff = (priorityWeight[a.priority] || 0) - (priorityWeight[b.priority] || 0);
          return diff !== 0 ? diff : a.requirement_id.localeCompare(b.requirement_id);
        }
        case 'status': {
          const diff = (statusWeight[b.status] || 0) - (statusWeight[a.status] || 0);
          return diff !== 0 ? diff : a.requirement_id.localeCompare(b.requirement_id);
        }
        case 'req_id_asc':
          return a.requirement_id.localeCompare(b.requirement_id);
        case 'req_id_desc':
          return b.requirement_id.localeCompare(a.requirement_id);
        case 'title_asc':
          return (a.title || a.requirement_title || '').localeCompare(b.title || b.requirement_title || '');
        default:
          return 0;
      }
    });
  }, [allItems, searchQuery, statusFilter, priorityFilter, sortBy]);

  const hasActiveFilters = searchQuery.trim() !== '' || statusFilter !== 'ALL' || priorityFilter !== 'ALL';

  const handleResetFilters = () => {
    setSearchQuery('');
    setStatusFilter('ALL');
    setPriorityFilter('ALL');
    setSortBy('severity_desc');
  };

  // Keyboard Shortcuts Listener
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't trigger shortcuts if active element is an input, textarea, or select
      const activeTag = document.activeElement?.tagName?.toLowerCase();
      const isInput = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

      // "/" -> Focus Search
      if (e.key === '/' && !isInput) {
        e.preventDefault();
        searchInputRef.current?.focus();
        return;
      }

      // "Esc" -> Close Modals / Drawer
      if (e.key === 'Escape') {
        if (drawerReq) setDrawerReq(null);
        if (overrideModalReq) setOverrideModalReq(null);
        if (showBulkOverrideModal) setShowBulkOverrideModal(false);
        if (showBulkNoteModal) setShowBulkNoteModal(false);
        if (selectedCitation) setSelectedCitation(null);
        return;
      }

      // "j" / "k" -> List navigation
      if (!isInput && filteredItems.length > 0) {
        if (e.key === 'j') {
          e.preventDefault();
          setActiveKeyboardIndex(prev => Math.min(prev + 1, filteredItems.length - 1));
        } else if (e.key === 'k') {
          e.preventDefault();
          setActiveKeyboardIndex(prev => Math.max(prev - 1, 0));
        } else if (e.key === 'Enter' && activeKeyboardIndex >= 0 && activeKeyboardIndex < filteredItems.length) {
          e.preventDefault();
          setDrawerReq(filteredItems[activeKeyboardIndex]);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [drawerReq, overrideModalReq, showBulkOverrideModal, showBulkNoteModal, selectedCitation, filteredItems, activeKeyboardIndex]);

  // Multi-selection handlers
  const handleToggleSelect = (reqId, e) => {
    if (e) e.stopPropagation();
    setSelectedReqIds(prev => {
      const next = new Set(prev);
      if (next.has(reqId)) next.delete(reqId);
      else next.add(reqId);
      return next;
    });
  };

  const handleSelectAllVisible = () => {
    const visibleIds = filteredItems.map(i => i.requirement_id);
    setSelectedReqIds(new Set(visibleIds));
  };

  const handleClearSelection = () => {
    setSelectedReqIds(new Set());
  };

  const isAllVisibleSelected = filteredItems.length > 0 && filteredItems.every(i => selectedReqIds.has(i.requirement_id));
  const isSomeVisibleSelected = filteredItems.some(i => selectedReqIds.has(i.requirement_id)) && !isAllVisibleSelected;

  // Single Override Modal handlers
  const handleOpenOverrideModal = (item, e) => {
    if (e) e.stopPropagation();
    setOverrideModalReq(item);
    setOverrideStatus(item.override_data?.overridden_status || (item.ai_status === 'SATISFIED' ? 'MISSING' : 'SATISFIED'));
    setOverrideReason(item.override_data?.auditor_reason || '');
    setOverrideNote(item.override_data?.auditor_note || '');
    setOverrideError(null);
  };

  const handleSaveOverride = async (e) => {
    e.preventDefault();
    if (!overrideReason.trim()) {
      setOverrideError('Auditor justification / reason is mandatory.');
      return;
    }

    try {
      setSavingOverride(true);
      setOverrideError(null);
      await api.saveOverride(projectId, overrideModalReq.requirement_id, {
        overridden_status: overrideStatus,
        auditor_reason: overrideReason.trim(),
        auditor_note: overrideNote.trim(),
      });
      setOverrideModalReq(null);
      if (onOverrideUpdated) onOverrideUpdated();
    } catch (err) {
      console.error('Failed to save override:', err);
      setOverrideError(err.response?.data?.detail || err.response?.data?.error?.message || err.message || 'Failed to save override');
    } finally {
      setSavingOverride(false);
    }
  };

  const handleRevokeOverride = async (reqId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm(`Are you sure you want to revoke the auditor override for ${reqId}? It will revert to the AI determination.`)) {
      return;
    }

    try {
      await api.deleteOverride(projectId, reqId);
      if (onOverrideUpdated) onOverrideUpdated();
    } catch (err) {
      console.error('Failed to revoke override:', err);
      alert('Failed to revoke override: ' + (err.response?.data?.detail || err.message || err));
    }
  };

  // Bulk Override Handlers
  const handleOpenBulkOverrideModal = () => {
    setBulkOverrideStatus('SATISFIED');
    setBulkOverrideReason('');
    setBulkOverrideNote('');
    setBulkError(null);
    setBulkResult(null);
    setShowBulkOverrideModal(true);
  };

  const handleExecuteBulkOverride = async (e) => {
    e.preventDefault();
    if (!bulkOverrideReason.trim()) {
      setBulkError('Auditor justification / reason is mandatory for bulk overrides.');
      return;
    }

    const reqIds = Array.from(selectedReqIds);
    if (reqIds.length === 0) {
      setBulkError('No requirements selected.');
      return;
    }

    try {
      setBulkSaving(true);
      setBulkError(null);
      const res = await api.bulkSaveOverrides(projectId, {
        requirement_ids: reqIds,
        overridden_status: bulkOverrideStatus,
        auditor_reason: bulkOverrideReason.trim(),
        auditor_note: bulkOverrideNote.trim(),
      });

      setBulkResult(res);
      if (onOverrideUpdated) onOverrideUpdated();

      if (res.failed?.length === 0) {
        setTimeout(() => {
          setShowBulkOverrideModal(false);
          handleClearSelection();
        }, 1200);
      }
    } catch (err) {
      console.error('Bulk override failed:', err);
      setBulkError(err.response?.data?.detail || err.message || 'Bulk override failed');
    } finally {
      setBulkSaving(false);
    }
  };

  // Bulk Note Handlers
  const handleOpenBulkNoteModal = () => {
    setBulkNoteText('');
    setBulkNoteError(null);
    setShowBulkNoteModal(true);
  };

  const handleExecuteBulkNote = async (e) => {
    e.preventDefault();
    if (!bulkNoteText.trim()) {
      setBulkNoteError('Note text cannot be empty.');
      return;
    }

    const reqIds = Array.from(selectedReqIds);
    try {
      setBulkNoteSaving(true);
      setBulkNoteError(null);
      await api.bulkSaveNotes(projectId, {
        requirement_ids: reqIds,
        note_text: bulkNoteText.trim(),
      });
      setShowBulkNoteModal(false);
      handleClearSelection();
      if (onOverrideUpdated) onOverrideUpdated();
    } catch (err) {
      console.error('Bulk note failed:', err);
      setBulkNoteError(err.response?.data?.detail || err.message || 'Failed to add bulk notes');
    } finally {
      setBulkNoteSaving(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'SATISFIED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            SATISFIED
          </span>
        );
      case 'MISSING':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertCircle className="w-3.5 h-3.5 mr-1" />
            MISSING
          </span>
        );
      case 'CONFLICT':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            CONFLICT
          </span>
        );
      case 'PARTIAL':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <AlertTriangle className="w-3.5 h-3.5 mr-1" />
            PARTIAL
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
            {status}
          </span>
        );
    }
  };

  const getPriorityBadge = (priority) => {
    const p = (priority || 'MEDIUM').toUpperCase();
    const colors = {
      CRITICAL: 'text-red-400 border-red-500/30 bg-red-500/10',
      HIGH: 'text-orange-400 border-orange-500/30 bg-orange-500/10',
      MEDIUM: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
      LOW: 'text-slate-400 border-slate-700 bg-slate-800/50',
    };
    return (
      <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${colors[p] || colors.MEDIUM}`}>
        {p}
      </span>
    );
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-2xl space-y-5">
      {/* HEADER & PROVENANCE BADGE */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-lg font-bold text-white">Evidence-Grounded Requirements Analysis</h3>
            <span className="px-2 py-0.5 rounded bg-brand-500/10 text-brand-400 border border-brand-500/20 text-[10px] font-mono uppercase">
              100% Source Traceable
            </span>
            {counts.overridden > 0 && (
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono uppercase flex items-center space-x-1">
                <UserCheck className="w-3 h-3" />
                <span>{counts.overridden} Human Override(s)</span>
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Every compliance decision is backed by verified excerpts and fact-level discrepancy analysis
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded bg-slate-800 text-slate-300">
            Showing {filteredItems.length} of {allItems.length}
          </span>
          <span className="hidden sm:inline-block px-2 py-1 rounded bg-slate-950 text-slate-500 text-[10px]">
            Press <kbd className="text-slate-300 font-bold">/</kbd> to search · <kbd className="text-slate-300 font-bold">j/k</kbd> to navigate · <kbd className="text-slate-300 font-bold">Enter</kbd> for quick view
          </span>
        </div>
      </div>

      {/* QUICK STATUS METRIC FILTER PILLS */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs font-mono">
        <button
          onClick={() => setStatusFilter('ALL')}
          className={`p-2 rounded-xl border text-left transition-all ${
            statusFilter === 'ALL'
              ? 'bg-slate-800 border-slate-600 text-white shadow-md'
              : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:text-white'
          }`}
        >
          <span className="text-[10px] text-slate-400 block uppercase">All Reqs</span>
          <span className="text-base font-bold text-white">{counts.total}</span>
        </button>

        <button
          onClick={() => setStatusFilter('SATISFIED')}
          className={`p-2 rounded-xl border text-left transition-all ${
            statusFilter === 'SATISFIED'
              ? 'bg-emerald-950/50 border-emerald-500 text-emerald-300 shadow-md'
              : 'bg-slate-950/60 border-slate-800 text-emerald-400/80 hover:text-emerald-300'
          }`}
        >
          <span className="text-[10px] text-slate-400 block uppercase">Satisfied</span>
          <span className="text-base font-bold text-emerald-400">{counts.satisfied}</span>
        </button>

        <button
          onClick={() => setStatusFilter('MISSING')}
          className={`p-2 rounded-xl border text-left transition-all ${
            statusFilter === 'MISSING'
              ? 'bg-amber-950/50 border-amber-500 text-amber-300 shadow-md'
              : 'bg-slate-950/60 border-slate-800 text-amber-400/80 hover:text-amber-300'
          }`}
        >
          <span className="text-[10px] text-slate-400 block uppercase">Missing</span>
          <span className="text-base font-bold text-amber-400">{counts.missing}</span>
        </button>

        <button
          onClick={() => setStatusFilter('CONFLICT')}
          className={`p-2 rounded-xl border text-left transition-all ${
            statusFilter === 'CONFLICT'
              ? 'bg-purple-950/50 border-purple-500 text-purple-300 shadow-md'
              : 'bg-slate-950/60 border-slate-800 text-purple-400/80 hover:text-purple-300'
          }`}
        >
          <span className="text-[10px] text-slate-400 block uppercase">Conflict</span>
          <span className="text-base font-bold text-purple-400">{counts.conflict}</span>
        </button>

        <button
          onClick={() => setStatusFilter('PARTIAL')}
          className={`p-2 rounded-xl border text-left transition-all ${
            statusFilter === 'PARTIAL'
              ? 'bg-blue-950/50 border-blue-500 text-blue-300 shadow-md'
              : 'bg-slate-950/60 border-slate-800 text-blue-400/80 hover:text-blue-300'
          }`}
        >
          <span className="text-[10px] text-slate-400 block uppercase">Partial</span>
          <span className="text-base font-bold text-blue-400">{counts.partial}</span>
        </button>
      </div>

      {/* INTERACTIVE CONTROLS BAR: SEARCH, SEVERITY, SORT */}
      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between bg-slate-950/60 p-3 rounded-xl border border-slate-800">
        {/* Search Box */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search by ID, title, description, document, quote, or auditor reason... (Press /)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-8 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 font-mono"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-2.5 text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Severity / Priority Filter */}
        <div className="flex items-center space-x-2">
          <Filter className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            aria-label="Filter by Severity"
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-lg px-2.5 py-2 focus:outline-none focus:border-brand-500 font-mono"
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">Critical Priority ({counts.critical})</option>
            <option value="HIGH">High Priority ({counts.high})</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>
        </div>

        {/* Sort Select */}
        <div className="flex items-center space-x-2">
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            aria-label="Sort Requirements"
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-lg px-2.5 py-2 focus:outline-none focus:border-brand-500 font-mono"
          >
            <option value="severity_desc">Priority: High → Low</option>
            <option value="severity_asc">Priority: Low → High</option>
            <option value="status">Status: Issues First</option>
            <option value="req_id_asc">ID: Ascending (REQ-001)</option>
            <option value="req_id_desc">ID: Descending</option>
            <option value="title_asc">Title: A → Z</option>
          </select>
        </div>
      </div>

      {/* ACTIVE FILTER CHIPS & RESET */}
      {hasActiveFilters && (
        <div className="flex items-center justify-between flex-wrap gap-2 text-xs">
          <div className="flex items-center flex-wrap gap-2">
            <span className="text-[11px] font-mono text-slate-400">Active Filters:</span>

            {searchQuery && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono bg-brand-950 text-brand-300 border border-brand-800">
                Query: "{searchQuery}"
                <button onClick={() => setSearchQuery('')} className="ml-1 text-brand-400 hover:text-white">✕</button>
              </span>
            )}

            {statusFilter !== 'ALL' && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono bg-slate-800 text-slate-200 border border-slate-700">
                Status: {statusFilter}
                <button onClick={() => setStatusFilter('ALL')} className="ml-1 text-slate-400 hover:text-white">✕</button>
              </span>
            )}

            {priorityFilter !== 'ALL' && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-mono bg-slate-800 text-slate-200 border border-slate-700">
                Priority: {priorityFilter}
                <button onClick={() => setPriorityFilter('ALL')} className="ml-1 text-slate-400 hover:text-white">✕</button>
              </span>
            )}
          </div>

          <button
            onClick={handleResetFilters}
            className="flex items-center space-x-1 text-[11px] font-mono text-slate-400 hover:text-white underline cursor-pointer"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset Filters</span>
          </button>
        </div>
      )}

      {/* BULK SELECTION ACTIONS TOOLBAR (Sticky when items selected) */}
      {selectedReqIds.size > 0 && (
        <div className="p-3 bg-brand-950/70 border border-brand-600/60 rounded-xl flex items-center justify-between flex-wrap gap-3 shadow-lg shadow-brand-950/30 animate-fade-in">
          <div className="flex items-center space-x-3 text-xs font-mono">
            <span className="font-bold text-white bg-brand-600/30 px-2.5 py-1 rounded-lg border border-brand-500/40">
              {selectedReqIds.size} requirement{selectedReqIds.size > 1 ? 's' : ''} selected
            </span>
            <button
              onClick={handleClearSelection}
              className="text-slate-400 hover:text-white underline text-[11px]"
            >
              Clear selection
            </button>
          </div>

          <div className="flex items-center space-x-2">
            {projectId && (
              <>
                <button
                  onClick={handleOpenBulkOverrideModal}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-md shadow-blue-600/20"
                >
                  <UserCheck className="w-3.5 h-3.5" />
                  <span>Bulk Status Override</span>
                </button>

                <button
                  onClick={handleOpenBulkNoteModal}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs flex items-center space-x-1.5 border border-slate-700"
                >
                  <MessageSquare className="w-3.5 h-3.5 text-brand-400" />
                  <span>Bulk Add Note</span>
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* SELECT ALL VISIBLE CONTROLS */}
      {filteredItems.length > 0 && (
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 px-2">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => isAllVisibleSelected ? handleClearSelection() : handleSelectAllVisible()}
              className="flex items-center space-x-1.5 text-slate-300 hover:text-white"
            >
              {isAllVisibleSelected ? (
                <CheckSquare className="w-4 h-4 text-brand-400" />
              ) : isSomeVisibleSelected ? (
                <MinusSquare className="w-4 h-4 text-brand-400" />
              ) : (
                <Square className="w-4 h-4 text-slate-500" />
              )}
              <span>
                {isAllVisibleSelected ? 'Deselect All Visible' : 'Select All Visible'} ({filteredItems.length})
              </span>
            </button>
          </div>
        </div>
      )}

      {/* REQUIREMENTS LIST OR EMPTY STATE */}
      {filteredItems.length === 0 ? (
        <div className="p-10 text-center bg-slate-950/60 border border-slate-800 rounded-2xl space-y-3">
          <Search className="w-8 h-8 text-slate-600 mx-auto" />
          <h4 className="text-sm font-bold text-white">No Matching Requirements</h4>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            No requirements match your current search and filter combination.
          </p>
          <button
            onClick={handleResetFilters}
            className="px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs transition-colors"
          >
            Clear All Filters
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item, index) => {
            const isExpanded = expandedId === item.requirement_id;
            const isSelected = selectedReqIds.has(item.requirement_id);
            const isKeyboardActive = activeKeyboardIndex === index;
            const isConflict = item.ai_status === 'CONFLICT';

            // Extract conflict details if available
            const conflict = item.conflict_details || (isConflict && item.evidence.length >= 2 ? {
              fact_label: 'Contradictory Information',
              source_a: { citation: item.evidence[0], value: item.evidence[0].quote },
              source_b: { citation: item.evidence[1], value: item.evidence[1].quote },
              explanation: item.reasoning,
              recommended_action: 'Confirm the authoritative document and update inconsistent records.',
            } : null);

            return (
              <div
                key={item.requirement_id}
                className={`bg-slate-950/60 border rounded-xl overflow-hidden transition-all ${
                  isSelected ? 'border-brand-500/80 bg-brand-950/20' : 
                  isExpanded ? 'border-brand-500/40 shadow-lg shadow-brand-950/20' : 
                  isKeyboardActive ? 'border-slate-500 bg-slate-900/50' :
                  'border-slate-800/80 hover:border-slate-700'
                }`}
              >
                {/* Header row */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : item.requirement_id)}
                  className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-900/40 transition-colors flex-wrap gap-2"
                >
                  <div className="flex items-center space-x-3 min-w-0">
                    {/* Checkbox */}
                    <button
                      type="button"
                      onClick={(e) => handleToggleSelect(item.requirement_id, e)}
                      className="text-slate-400 hover:text-white p-1 -ml-1 rounded focus:outline-none"
                    >
                      {isSelected ? (
                        <CheckSquare className="w-4 h-4 text-brand-400" />
                      ) : (
                        <Square className="w-4 h-4 text-slate-600 hover:text-slate-400" />
                      )}
                    </button>

                    <span className="font-mono text-xs font-bold text-brand-400 shrink-0">
                      {item.requirement_id}
                    </span>
                    <span className="text-sm font-semibold text-white truncate max-w-md">
                      {item.title || item.requirement_title}
                    </span>
                    {getPriorityBadge(item.priority)}
                  </div>

                  <div className="flex items-center space-x-3 shrink-0 ml-auto">
                    {/* DUAL STATUS BADGE IF OVERRIDDEN */}
                    {item.has_override ? (
                      <div className="flex items-center space-x-1.5">
                        <span className="text-[10px] font-mono line-through text-slate-500">
                          AI: {item.ai_status}
                        </span>
                        <span className="text-slate-500">→</span>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-500/15 text-blue-300 border border-blue-500/30">
                          <UserCheck className="w-3 h-3 mr-1 text-blue-400" />
                          Auditor: {item.status}
                        </span>
                      </div>
                    ) : (
                      getStatusBadge(item.status)
                    )}

                    {/* QUICK VIEW BUTTON */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setDrawerReq(item);
                      }}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-slate-300 hover:text-white flex items-center space-x-1"
                      title="Open Quick View Detail Drawer"
                    >
                      <Eye className="w-3 h-3 text-slate-400" />
                      <span className="hidden sm:inline">Quick View</span>
                    </button>

                    {/* OVERRIDE BUTTON */}
                    {projectId && (
                      <button
                        onClick={(e) => handleOpenOverrideModal(item, e)}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-slate-300 hover:text-white flex items-center space-x-1"
                        title={item.has_override ? "Edit Auditor Override" : "Create Human Override"}
                      >
                        <UserCheck className="w-3 h-3 text-blue-400" />
                        <span className="hidden sm:inline">{item.has_override ? "Edit Override" : "Override"}</span>
                      </button>
                    )}

                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-2 border-t border-slate-800/60 space-y-4 text-xs">
                    {/* AUDITOR HUMAN OVERRIDE BOX (If present) */}
                    {item.has_override && item.override_data && (
                      <div className="p-3.5 rounded-xl bg-blue-950/30 border border-blue-600/50 space-y-2">
                        <div className="flex items-center justify-between pb-1.5 border-b border-blue-900/40">
                          <div className="flex items-center space-x-2 text-blue-300">
                            <UserCheck className="w-4 h-4 text-blue-400" />
                            <span className="font-bold uppercase tracking-wider font-mono text-xs">
                              Human Auditor Decision: {item.override_data.overridden_status}
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            <button
                              onClick={(e) => handleOpenOverrideModal(item, e)}
                              className="text-[11px] font-mono text-blue-400 hover:text-blue-200 underline flex items-center space-x-1"
                            >
                              <Edit3 className="w-3 h-3" />
                              <span>Edit</span>
                            </button>
                            <button
                              onClick={(e) => handleRevokeOverride(item.requirement_id, e)}
                              className="text-[11px] font-mono text-red-400 hover:text-red-300 underline flex items-center space-x-1"
                            >
                              <Trash2 className="w-3 h-3" />
                              <span>Revoke</span>
                            </button>
                          </div>
                        </div>

                        <div>
                          <span className="font-mono text-[10px] text-blue-400 uppercase font-bold block">
                            Auditor Justification / Reason:
                          </span>
                          <p className="text-blue-100 font-mono text-xs mt-0.5 leading-relaxed bg-slate-950/60 p-2.5 rounded-lg border border-blue-900/30">
                            {item.override_data.auditor_reason}
                          </p>
                        </div>

                        {item.override_data.auditor_note && (
                          <div>
                            <span className="font-mono text-[10px] text-slate-400 uppercase font-bold block">
                              Auditor Internal Note:
                            </span>
                            <p className="text-slate-300 text-xs mt-0.5 leading-relaxed bg-slate-950/40 p-2 rounded-lg border border-slate-800">
                              {item.override_data.auditor_note}
                            </p>
                          </div>
                        )}

                        <div className="text-[10px] font-mono text-slate-400 pt-1">
                          Applied: {new Date(item.override_data.updated_at || item.override_data.created_at).toLocaleString()} · Underlying AI Result ({item.ai_status}) preserved for audit compliance.
                        </div>
                      </div>
                    )}

                    {/* Description */}
                    <div>
                      <span className="font-mono text-[11px] text-slate-400 uppercase tracking-wider block mb-1">
                        Requirement Scope & Description:
                      </span>
                      <p className="text-slate-300 leading-relaxed bg-slate-900/40 p-3 rounded-lg border border-slate-800/80">
                        {item.description || 'No detailed description provided.'}
                      </p>
                    </div>

                    {/* Required Evidence Specification */}
                    {item.required_evidence && (
                      <div>
                        <span className="font-mono text-[11px] text-slate-400 uppercase tracking-wider block mb-1">
                          Mandatory Evidence Specification:
                        </span>
                        <p className="text-slate-300 font-mono bg-slate-900/40 p-2.5 rounded-lg border border-slate-800/80 text-[11px]">
                          {item.required_evidence}
                        </p>
                      </div>
                    )}

                    {/* DUAL-SOURCE CONFLICT COMPARISON INSPECTOR */}
                    {isConflict && conflict && (
                      <div className="bg-purple-950/20 border border-purple-800/50 rounded-xl p-4 space-y-3">
                        <div className="flex items-center justify-between pb-2 border-b border-purple-900/40">
                          <div className="flex items-center space-x-2">
                            <ArrowRightLeft className="w-4 h-4 text-purple-400" />
                            <h4 className="font-bold text-purple-200 text-xs uppercase tracking-wider">
                              AI Fact-Level Conflict: {conflict.fact_label || 'Conflicting Document Values'}
                            </h4>
                          </div>
                          <span className="px-2 py-0.5 rounded bg-purple-900/60 text-purple-200 border border-purple-700/50 font-mono text-[10px] uppercase font-semibold">
                            AI Conflict
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                          {/* Source A */}
                          <div className="p-3.5 rounded-xl bg-slate-950/90 border border-purple-800/40 space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[10px] text-purple-400 uppercase font-bold tracking-wider">
                                Source A
                              </span>
                              <div className="flex items-center space-x-2">
                                <span className="font-mono text-[10px] text-slate-400">
                                  {conflict.source_a?.citation?.document_name || 'Document A'}
                                </span>
                                {conflict.source_a?.citation && (
                                  <button
                                    onClick={() => setSelectedCitation(conflict.source_a.citation)}
                                    className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-brand-400 text-[10px] font-mono flex items-center space-x-1"
                                    title="View Source Page in Document Viewer"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    <span>Page {conflict.source_a.citation.page_number || 1}</span>
                                  </button>
                                )}
                              </div>
                            </div>
                            <p className="text-purple-200 font-mono text-xs bg-purple-950/40 p-2.5 rounded-lg border border-purple-900/30">
                              "{conflict.source_a?.value || conflict.source_a?.citation?.quote || 'Excerpt A'}"
                            </p>
                          </div>

                          {/* Source B */}
                          <div className="p-3.5 rounded-xl bg-slate-950/90 border border-purple-800/40 space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-mono text-[10px] text-purple-400 uppercase font-bold tracking-wider">
                                Source B
                              </span>
                              <div className="flex items-center space-x-2">
                                <span className="font-mono text-[10px] text-slate-400">
                                  {conflict.source_b?.citation?.document_name || 'Document B'}
                                </span>
                                {conflict.source_b?.citation && (
                                  <button
                                    onClick={() => setSelectedCitation(conflict.source_b.citation)}
                                    className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-brand-400 text-[10px] font-mono flex items-center space-x-1"
                                    title="View Source Page in Document Viewer"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    <span>Page {conflict.source_b.citation.page_number || 1}</span>
                                  </button>
                                )}
                              </div>
                            </div>
                            <p className="text-purple-200 font-mono text-xs bg-purple-950/40 p-2.5 rounded-lg border border-purple-900/30">
                              "{conflict.source_b?.value || conflict.source_b?.citation?.quote || 'Excerpt B'}"
                            </p>
                          </div>
                        </div>

                        {conflict.explanation && (
                          <div className="p-2.5 rounded-lg bg-slate-950/60 border border-purple-900/30 text-[11px] text-purple-300">
                            <b>Discrepancy Analysis:</b> {conflict.explanation}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Cited Evidence Excerpts */}
                    {item.evidence && item.evidence.length > 0 && (
                      <div className="space-y-2">
                        <span className="font-mono text-[11px] text-slate-400 uppercase tracking-wider block font-bold">
                          Verified Documentary Evidence Citations ({item.evidence.length}):
                        </span>
                        <div className="space-y-2">
                          {item.evidence.map((ev, idx) => (
                            <div
                              key={idx}
                              className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 flex items-start justify-between gap-3"
                            >
                              <div className="space-y-1 max-w-2xl">
                                <div className="flex items-center space-x-2 text-[10px] font-mono text-slate-400">
                                  <FileText className="w-3 h-3 text-brand-400" />
                                  <span className="font-bold text-white">{ev.document_name}</span>
                                  <span>·</span>
                                  <span>Page {ev.page_number || 1}</span>
                                  {ev.section && <span>· Section {ev.section}</span>}
                                </div>
                                <p className="text-slate-200 italic font-mono text-xs bg-slate-900/60 p-2 rounded border border-slate-800/80">
                                  "{ev.quote}"
                                </p>
                              </div>
                              <button
                                onClick={() => setSelectedCitation(ev)}
                                className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-brand-400 text-xs font-mono flex items-center space-x-1 shrink-0"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                                <span>Inspect</span>
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* General Auditor Synthesis */}
                    {item.reasoning && !isConflict && (
                      <div>
                        <span className="font-mono text-[11px] text-brand-400 uppercase tracking-wider block mb-1 font-bold">
                          Auditor AI Synthesis & Reasoning:
                        </span>
                        <p className="text-slate-200 bg-brand-950/20 p-3 rounded-lg border border-brand-900/30 leading-relaxed">
                          {item.reasoning}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* REQUIREMENT DETAIL DRAWER / QUICK VIEW */}
      {drawerReq && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex justify-end animate-fade-in">
          <div className="bg-slate-900 border-l border-slate-800 w-full max-w-2xl h-full flex flex-col shadow-2xl overflow-hidden animate-slide-left">
            {/* Drawer Header */}
            <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-mono text-sm font-bold text-brand-400">
                    {drawerReq.requirement_id}
                  </span>
                  {getPriorityBadge(drawerReq.priority)}
                  {drawerReq.has_override ? (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                      Auditor: {drawerReq.status}
                    </span>
                  ) : (
                    getStatusBadge(drawerReq.status)
                  )}
                </div>
                <h3 className="text-base font-bold text-white">
                  {drawerReq.title || drawerReq.requirement_title}
                </h3>
              </div>
              <button
                onClick={() => setDrawerReq(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs font-mono">
              {/* Description */}
              <div className="space-y-1.5">
                <span className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
                  Description:
                </span>
                <p className="text-slate-200 bg-slate-950/60 p-3 rounded-xl border border-slate-800 font-sans leading-relaxed text-sm">
                  {drawerReq.description || 'No description provided.'}
                </p>
              </div>

              {/* Required Evidence */}
              {drawerReq.required_evidence && (
                <div className="space-y-1.5">
                  <span className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
                    Required Evidence:
                  </span>
                  <p className="text-slate-300 bg-slate-950/40 p-3 rounded-xl border border-slate-800 leading-relaxed">
                    {drawerReq.required_evidence}
                  </p>
                </div>
              )}

              {/* AI Determination vs Auditor Decision */}
              <div className="grid grid-cols-2 gap-3 p-3.5 bg-slate-950/80 rounded-xl border border-slate-800">
                <div>
                  <span className="text-[10px] text-slate-400 uppercase block">AI Automated Status</span>
                  <span className="text-sm font-bold text-white">{drawerReq.ai_status}</span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-400 uppercase block">Effective Status</span>
                  <span className="text-sm font-bold text-brand-400">{drawerReq.status}</span>
                </div>
              </div>

              {/* Citations List */}
              {drawerReq.evidence && drawerReq.evidence.length > 0 && (
                <div className="space-y-2">
                  <span className="text-[11px] text-slate-400 uppercase font-bold tracking-wider">
                    Document Evidence Citations ({drawerReq.evidence.length}):
                  </span>
                  <div className="space-y-2">
                    {drawerReq.evidence.map((ev, idx) => (
                      <div
                        key={idx}
                        className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2"
                      >
                        <div className="flex items-center justify-between text-[11px] text-brand-300">
                          <span className="font-bold">{ev.document_name}</span>
                          <span>Page {ev.page_number || 1}</span>
                        </div>
                        <p className="text-slate-300 italic bg-slate-900/60 p-2 rounded border border-slate-800">
                          "{ev.quote}"
                        </p>
                        <button
                          onClick={() => setSelectedCitation(ev)}
                          className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-brand-400 rounded text-[11px] font-bold flex items-center space-x-1"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span>Inspect in Document Viewer</span>
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-slate-800 bg-slate-950/50 flex items-center justify-between">
              <button
                onClick={() => setDrawerReq(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold"
              >
                Close Drawer
              </button>

              {projectId && (
                <button
                  onClick={() => {
                    const req = drawerReq;
                    setDrawerReq(null);
                    handleOpenOverrideModal(req);
                  }}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-bold flex items-center space-x-1.5"
                >
                  <UserCheck className="w-4 h-4" />
                  <span>{drawerReq.has_override ? 'Edit Override' : 'Override Status'}</span>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* SINGLE HUMAN AUDITOR OVERRIDE MODAL */}
      {overrideModalReq && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full space-y-5 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <UserCheck className="w-5 h-5 text-blue-400" />
                <h3 className="text-base font-bold text-white">Human Auditor Decision Override</h3>
              </div>
              <button
                onClick={() => setOverrideModalReq(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveOverride} className="space-y-4 text-xs">
              <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="font-mono font-bold text-brand-400">{overrideModalReq.requirement_id}</span>
                  <span className="text-slate-200 font-semibold truncate">{overrideModalReq.title}</span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  Current AI Automated Determination: <b className="text-purple-300">{overrideModalReq.ai_status}</b>
                </div>
              </div>

              {overrideError && (
                <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs">
                  {overrideError}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-300 font-bold block uppercase">
                  Override Decision Status:
                </label>
                <select
                  value={overrideStatus}
                  onChange={(e) => setOverrideStatus(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500"
                >
                  <option value="SATISFIED">SATISFIED — Meets compliance requirements</option>
                  <option value="PARTIAL">PARTIAL — Partially meets requirements</option>
                  <option value="MISSING">MISSING — Insufficient or missing evidence</option>
                  <option value="CONFLICT">CONFLICT — Inconsistent documentary facts</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-300 font-bold block uppercase">
                  Auditor Justification / Reason * (Mandatory):
                </label>
                <textarea
                  rows={3}
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Explain why the AI determination is overridden..."
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500 placeholder-slate-600"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-400 font-bold block uppercase">
                  Internal Auditor Note (Optional):
                </label>
                <textarea
                  rows={2}
                  value={overrideNote}
                  onChange={(e) => setOverrideNote(e.target.value)}
                  placeholder="Optional internal audit note or reference ticket..."
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500 placeholder-slate-600"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setOverrideModalReq(null)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingOverride}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-blue-600/20"
                >
                  <UserCheck className="w-3.5 h-3.5" />
                  <span>{savingOverride ? "Saving..." : "Save Auditor Override"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* BULK OVERRIDE MODAL */}
      {showBulkOverrideModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full space-y-5 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <UserCheck className="w-5 h-5 text-blue-400" />
                <h3 className="text-base font-bold text-white">Bulk Status Override</h3>
              </div>
              <button
                onClick={() => setShowBulkOverrideModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleExecuteBulkOverride} className="space-y-4 text-xs">
              <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1">
                <span className="font-mono text-slate-400 block">
                  Applying override across <b>{selectedReqIds.size}</b> selected requirements:
                </span>
                <div className="flex flex-wrap gap-1.5 pt-1 max-h-24 overflow-y-auto">
                  {Array.from(selectedReqIds).map(id => (
                    <span key={id} className="px-2 py-0.5 rounded bg-slate-800 text-brand-300 font-mono text-[11px]">
                      {id}
                    </span>
                  ))}
                </div>
              </div>

              {bulkError && (
                <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs">
                  {bulkError}
                </div>
              )}

              {bulkResult && (
                <div className="p-2.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-xs font-mono">
                  ✓ Successfully updated {bulkResult.total_succeeded} of {bulkResult.total_requested} requirements.
                </div>
              )}

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-300 font-bold block uppercase">
                  Target Override Status:
                </label>
                <select
                  value={bulkOverrideStatus}
                  onChange={(e) => setBulkOverrideStatus(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500"
                >
                  <option value="SATISFIED">SATISFIED — Meets compliance requirements</option>
                  <option value="PARTIAL">PARTIAL — Partially meets requirements</option>
                  <option value="MISSING">MISSING — Insufficient or missing evidence</option>
                  <option value="CONFLICT">CONFLICT — Inconsistent documentary facts</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-300 font-bold block uppercase">
                  Auditor Justification / Reason * (Mandatory):
                </label>
                <textarea
                  rows={3}
                  value={bulkOverrideReason}
                  onChange={(e) => setBulkOverrideReason(e.target.value)}
                  placeholder="Explain why these requirements are being updated in bulk..."
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500 placeholder-slate-600"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-400 font-bold block uppercase">
                  Optional Bulk Note:
                </label>
                <textarea
                  rows={2}
                  value={bulkOverrideNote}
                  onChange={(e) => setBulkOverrideNote(e.target.value)}
                  placeholder="Optional note for all selected requirements..."
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500 placeholder-slate-600"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowBulkOverrideModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={bulkSaving}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs flex items-center space-x-1.5"
                >
                  <UserCheck className="w-3.5 h-3.5" />
                  <span>{bulkSaving ? "Applying Overrides..." : `Apply to ${selectedReqIds.size} Requirements`}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* BULK NOTE MODAL */}
      {showBulkNoteModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full space-y-5 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <MessageSquare className="w-5 h-5 text-brand-400" />
                <h3 className="text-base font-bold text-white">Add Bulk Auditor Note</h3>
              </div>
              <button
                onClick={() => setShowBulkNoteModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleExecuteBulkNote} className="space-y-4 text-xs">
              <div className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 space-y-1">
                <span className="font-mono text-slate-400 block">
                  Adding note to <b>{selectedReqIds.size}</b> selected requirements:
                </span>
                <div className="flex flex-wrap gap-1.5 pt-1 max-h-24 overflow-y-auto">
                  {Array.from(selectedReqIds).map(id => (
                    <span key={id} className="px-2 py-0.5 rounded bg-slate-800 text-brand-300 font-mono text-[11px]">
                      {id}
                    </span>
                  ))}
                </div>
              </div>

              {bulkNoteError && (
                <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-xs">
                  {bulkNoteError}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="font-mono text-[11px] text-slate-300 font-bold block uppercase">
                  Auditor Note Text * (Mandatory):
                </label>
                <textarea
                  rows={4}
                  value={bulkNoteText}
                  onChange={(e) => setBulkNoteText(e.target.value)}
                  placeholder="Enter note text to attach to all selected requirements..."
                  className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg p-2.5 font-mono focus:outline-none focus:border-brand-500 placeholder-slate-600"
                />
              </div>

              <div className="pt-3 border-t border-slate-800 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowBulkNoteModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={bulkNoteSaving}
                  className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white font-bold text-xs flex items-center space-x-1.5"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span>{bulkNoteSaving ? "Saving..." : `Add Note to ${selectedReqIds.size} Items`}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EVIDENCE & PROVENANCE DOCUMENT INSPECTOR MODAL */}
      {selectedCitation && (
        <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-5xl w-full space-y-4 shadow-2xl animate-fade-in max-h-[90vh] overflow-y-auto">
            <DocumentViewer
              projectId={projectId}
              initialDocName={selectedCitation.document_name}
              highlightQuote={selectedCitation.quote}
              highlightPage={selectedCitation.page_number}
              onClose={() => setSelectedCitation(null)}
              isModal={true}
            />
          </div>
        </div>
      )}
    </div>
  );
}
