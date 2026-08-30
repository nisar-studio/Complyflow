import React, { useState, useEffect } from 'react';
import { 
  History, ArrowRight, CheckCircle2, AlertTriangle, XCircle, 
  Sparkles, Layers, ShieldCheck, ChevronRight, RefreshCw, Award,
  Download, FileText, FileCode, Loader2, AlertCircle, Check
} from 'lucide-react';
import api from '../api/client';

export default function VerificationHistory({ projectId, onSelectRun }) {
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [delta, setDelta] = useState(null);
  const [loading, setLoading] = useState(true);

  // Export states
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);
  const [exportSuccess, setExportSuccess] = useState('');
  const [exportError, setExportError] = useState('');

  const loadRuns = async () => {
    try {
      const runsData = await api.getVerificationRuns(projectId);
      setRuns(runsData || []);
      if (runsData && runsData.length > 0) {
        const latest = runsData[runsData.length - 1];
        setSelectedRunId(latest.run_id);
        if (runsData.length >= 2) {
          const deltaData = await api.getVerificationDelta(
            projectId, 
            runsData[0].run_id, 
            runsData[runsData.length - 1].run_id
          );
          setDelta(deltaData);
        }
      }
    } catch (err) {
      console.error('Failed to load verification runs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, [projectId]);

  const handleExportPdf = async (runId) => {
    setExportingPdf(true);
    setExportError('');
    setExportSuccess('');
    try {
      await api.downloadReportPdf(projectId, runId);
      setExportSuccess(`PDF compliance report for ${runId.toUpperCase()} downloaded successfully.`);
      setTimeout(() => setExportSuccess(''), 4000);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to generate PDF report.';
      setExportError(msg);
    } finally {
      setExportingPdf(false);
    }
  };

  const handleExportJson = async (runId) => {
    setExportingJson(true);
    setExportError('');
    setExportSuccess('');
    try {
      await api.downloadReportJson(projectId, runId);
      setExportSuccess(`JSON audit export for ${runId.toUpperCase()} downloaded successfully.`);
      setTimeout(() => setExportSuccess(''), 4000);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to generate JSON audit export.';
      setExportError(msg);
    } finally {
      setExportingJson(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400 font-mono text-xs animate-pulse">
        Loading verification history...
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="p-8 text-center bg-slate-900/50 border border-slate-800 rounded-2xl">
        <History className="w-8 h-8 text-slate-500 mx-auto mb-2" />
        <h4 className="text-sm font-bold text-white">No Verification Runs Yet</h4>
        <p className="text-xs text-slate-400 mt-1">
          Historical snapshots will be recorded every time an analysis or verification is run.
        </p>
      </div>
    );
  }

  const selectedRun = runs.find(r => r.run_id === selectedRunId) || runs[runs.length - 1];

  return (
    <div className="space-y-6">
      {/* 1. BEFORE → AFTER COMPARATIVE DELTA CARD (When 2+ runs exist) */}
      {delta && (
        <div className="p-6 bg-slate-900/80 border border-brand-500/30 rounded-2xl backdrop-blur-xl shadow-2xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-brand-400" />
              <h3 className="text-sm font-bold text-white">
                Before → After Verification Progress
              </h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              +{delta.score_diff}% Improvement
            </span>
          </div>

          {/* Visual Progression Banner */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            {/* Before */}
            <div className="text-center md:text-left space-y-1">
              <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
                Run {delta.from_run_number} (Initial)
              </span>
              <div className="text-2xl font-black font-mono text-amber-400">
                {delta.score_before}%
              </div>
              <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20">
                {delta.status_before}
              </span>
            </div>

            {/* Arrow & Metrics */}
            <div className="flex flex-col items-center justify-center space-y-1">
              <div className="flex items-center space-x-2 text-brand-400 font-mono text-xs">
                <span>Resolved {delta.resolved_count} Gap(s)</span>
                <ArrowRight className="w-4 h-4" />
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div 
                  className="bg-brand-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, delta.score_after))}%` }}
                />
              </div>
            </div>

            {/* After */}
            <div className="text-center md:text-right space-y-1">
              <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
                Run {delta.to_run_number} (Verified)
              </span>
              <div className="text-2xl font-black font-mono text-emerald-400">
                {delta.score_after}%
              </div>
              <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                {delta.status_after}
              </span>
            </div>
          </div>

          {/* Requirement-Level Transitions */}
          <div className="space-y-2 pt-2">
            <span className="text-[11px] font-mono text-slate-400 uppercase font-bold tracking-wider block">
              Requirement Status Transitions:
            </span>
            <div className="grid grid-cols-1 gap-2">
              {delta.resolved_requirements?.map(req => (
                <div 
                  key={req.requirement_id}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs"
                >
                  <div className="flex items-center space-x-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="font-mono font-bold text-emerald-300">{req.requirement_id}</span>
                    <span className="text-white font-medium">{req.title}</span>
                  </div>
                  <div className="flex items-center space-x-2 font-mono text-[11px]">
                    <span className="text-amber-400">{req.status_before}</span>
                    <ArrowRight className="w-3 h-3 text-slate-500" />
                    <span className="text-emerald-400 font-bold">{req.status_after}</span>
                  </div>
                </div>
              ))}

              {delta.unchanged_requirements?.map(req => (
                <div 
                  key={req.requirement_id}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/40 border border-slate-800 text-xs text-slate-400"
                >
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-semibold text-slate-400">{req.requirement_id}</span>
                    <span className="text-slate-300">{req.title}</span>
                  </div>
                  <div className="flex items-center space-x-2 font-mono text-[11px]">
                    <span>{req.status_before}</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-slate-300">{req.status_after}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 2. IMMUTABLE RUNS TIMELINE & REPORT EXPORT CONTROLS */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-2">
              <History className="w-4 h-4 text-brand-400" />
              <h3 className="text-base font-bold text-white">Verification Snapshots & Audit Reports</h3>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Select any immutable point-in-time run to inspect findings or export enterprise compliance reports.
            </p>
          </div>
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700 font-semibold self-start sm:self-auto">
            {runs.length} Recorded Snapshot(s)
          </span>
        </div>

        {/* Snapshots Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {runs.map(run => {
            const isSelected = run.run_id === selectedRunId;
            const isReady = run.overall_status === 'READY';

            return (
              <button
                key={run.run_id}
                onClick={() => {
                  setSelectedRunId(run.run_id);
                  setExportError('');
                  setExportSuccess('');
                }}
                className={`p-4 rounded-xl text-left border transition-all cursor-pointer ${
                  isSelected 
                    ? 'bg-brand-950/40 border-brand-500 shadow-lg shadow-brand-950/40 ring-1 ring-brand-500/30' 
                    : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className={`px-2 py-0.5 rounded font-mono text-xs font-bold ${
                      isSelected ? 'bg-brand-600 text-white' : 'bg-slate-800 text-slate-200'
                    }`}>
                      Run {run.run_number}
                    </span>
                    <span className="text-[11px] font-mono text-slate-400">
                      {run.trigger === 'INITIAL_ANALYSIS' ? 'Initial Analysis' : 'Remediation Verified'}
                    </span>
                  </div>
                  <span className={`text-xs font-mono font-bold ${isReady ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {run.compliance_score}% ({run.overall_status})
                  </span>
                </div>

                <p className="text-xs text-slate-300 line-clamp-2 mb-3">
                  {run.summary}
                </p>

                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 pt-2 border-t border-slate-800/60">
                  <span>Satisfied: {run.satisfied_count}/{run.total_count}</span>
                  <span>{new Date(run.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* Selected Snapshot Export & Audit Action Panel */}
        {selectedRun && (
          <div className="p-5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-800/80">
              <div>
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <h4 className="text-sm font-bold text-white">
                    Export Audit Report for <span className="font-mono text-brand-400">Run {selectedRun.run_number} ({selectedRun.run_id})</span>
                  </h4>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Point-in-Time Snapshot from {new Date(selectedRun.timestamp).toLocaleString()} • Score: {selectedRun.compliance_score}%
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-3 shrink-0">
                <button
                  onClick={() => handleExportPdf(selectedRun.run_id)}
                  disabled={exportingPdf || exportingJson}
                  className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white shadow-md shadow-brand-600/20 transition-all hover:scale-[1.02] cursor-pointer"
                >
                  {exportingPdf ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <FileText className="w-3.5 h-3.5" />
                  )}
                  <span>{exportingPdf ? 'Generating PDF...' : 'Download Audit PDF'}</span>
                </button>

                <button
                  onClick={() => handleExportJson(selectedRun.run_id)}
                  disabled={exportingPdf || exportingJson}
                  className="inline-flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 border border-slate-700 transition-all cursor-pointer"
                  title="Export complete structured audit data in JSON format"
                >
                  {exportingJson ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <FileCode className="w-3.5 h-3.5 text-slate-400" />
                  )}
                  <span>{exportingJson ? 'Exporting...' : 'Export JSON'}</span>
                </button>
              </div>
            </div>

            {/* Inline Notifications / Errors */}
            {exportError && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center space-x-2 text-xs text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{exportError}</span>
              </div>
            )}

            {exportSuccess && (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center space-x-2 text-xs text-emerald-400">
                <Check className="w-4 h-4 shrink-0" />
                <span>{exportSuccess}</span>
              </div>
            )}

            <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono">
              <span>• Complete evidence quotes included</span>
              <span>• Source contradiction side-by-side comparison</span>
              <span>• Human auditor governance log distinguished</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
