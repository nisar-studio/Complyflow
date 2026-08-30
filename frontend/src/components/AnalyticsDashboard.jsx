import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp, AlertTriangle, CheckCircle2, Clock, FileText, Users, Shield, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import api from '../api/client';

// ── Mini Bar Chart (pure CSS) ───────────────────────────────
function MiniBarChart({ data, maxVal }) {
  if (!data || data.length === 0) return <p className="text-xs text-slate-500">No data</p>;
  const max = maxVal || Math.max(...data.map(d => d.value), 1);
  return (
    <div className="flex items-end gap-1 h-20">
      {data.map((d, i) => (
        <div key={i} className="flex flex-col items-center gap-1 flex-1 min-w-0" title={`${d.label}: ${d.value}`}>
          <span className="text-[10px] font-mono text-slate-400">{d.value}</span>
          <div
            className="w-full rounded-t transition-all duration-300"
            style={{
              height: `${Math.max((d.value / max) * 60, 2)}px`,
              backgroundColor: d.color || '#2563eb',
            }}
          />
          <span className="text-[9px] font-mono text-slate-500 truncate w-full text-center">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Score Trend Line (pure CSS) ─────────────────────────────
function ScoreTrendLine({ data }) {
  if (!data || data.length === 0) return <p className="text-xs text-slate-500">No verification runs yet</p>;
  return (
    <div className="relative h-24 w-full">
      <svg className="w-full h-full" viewBox={`0 0 ${Math.max(data.length * 50, 100)} 100`} preserveAspectRatio="none">
        {/* Grid lines */}
        {[0, 25, 50, 75, 100].map(v => (
          <line key={v} x1="0" y1={100 - v} x2="100%" y2={100 - v} stroke="#334155" strokeWidth="0.5" strokeDasharray="2,4" />
        ))}
        {/* Polyline */}
        <polyline
          fill="none"
          stroke="#2563eb"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={data.map((d, i) => {
            const x = data.length === 1 ? 50 : (i / (data.length - 1)) * 100;
            const y = 100 - d.score;
            return `${x},${y}`;
          }).join(' ')}
        />
        {/* Data points */}
        {data.map((d, i) => {
          const x = data.length === 1 ? 50 : (i / (data.length - 1)) * 100;
          const y = 100 - d.score;
          return (
            <g key={i}>
              <circle cx={`${x}%`} cy={y} r="3" fill="#2563eb" stroke="#0f172a" strokeWidth="1.5" />
              <title>Run #{d.run_number}: {d.score}%</title>
            </g>
          );
        })}
      </svg>
      {/* Labels */}
      <div className="absolute bottom-0 left-0 right-0 flex justify-between px-1">
        {data.map((d, i) => (
          <span key={i} className="text-[9px] font-mono text-slate-500">R{d.run_number}</span>
        ))}
      </div>
    </div>
  );
}

// ── Donut/Pie via CSS ───────────────────────────────────────
function StatusRing({ segments, size = 64 }) {
  if (!segments || segments.length === 0) return null;
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  let cumPct = 0;
  const gradientParts = segments.map(seg => {
    const pct = (seg.value / total) * 100;
    const start = cumPct;
    cumPct += pct;
    return `${seg.color} ${start}% ${cumPct}%`;
  });
  const gradient = `conic-gradient(${gradientParts.join(', ')})`;
  return (
    <div
      className="rounded-full flex items-center justify-center"
      style={{
        width: size,
        height: size,
        background: gradient,
      }}
    >
      <div className="rounded-full bg-slate-900 flex items-center justify-center" style={{ width: size - 10, height: size - 10 }}>
        <span className="text-xs font-mono font-bold text-white">{total}</span>
      </div>
    </div>
  );
}

// ── Stat Card ───────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, color = 'text-white' }) {
  return (
    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center gap-3">
      {Icon && <Icon className={`w-5 h-5 shrink-0`} style={{ color: color === 'text-white' ? '#94a3b8' : color }} />}
      <div>
        <p className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">{label}</p>
        <p className={`text-lg font-bold font-mono ${color}`}>{value}</p>
        {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
      </div>
    </div>
  );
}

// ── Legend Item ──────────────────────────────────────────────
function Legend({ items }) {
  return (
    <div className="flex flex-wrap gap-3 mt-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
          <span className="text-[10px] text-slate-400">{item.label}: {item.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main Analytics Dashboard ────────────────────────────────
export default function AnalyticsDashboard({ projectId }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAnalytics();
  }, [projectId]);

  const loadAnalytics = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getProjectAnalytics(projectId);
      setAnalytics(data);
    } catch (err) {
      console.error('Failed to load analytics:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-brand-400/30 border-t-brand-400 rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 text-red-300 text-xs">
        <AlertTriangle className="w-4 h-4 inline mr-2" />
        {error}
      </div>
    );
  }

  if (!analytics) return null;

  const { score_trend, requirement_status, issue_severity, task_status, audit_summary, remediation_effectiveness, documents_analyzed, override_impact, framework_coverage } = analytics;

  // Prepare chart data
  const reqChartData = requirement_status ? Object.entries(requirement_status.ai_baseline || {}).map(([k, v]) => ({
    label: k.slice(0, 6),
    value: v,
    color: k === 'SATISFIED' ? '#059669' : k === 'MISSING' ? '#dc2626' : k === 'CONFLICT' ? '#7c3aed' : k === 'PARTIAL' ? '#d97706' : '#475569',
  })) : [];

  const issueChartData = issue_severity ? Object.entries(issue_severity.by_severity || {}).map(([k, v]) => ({
    label: k.slice(0, 6),
    value: v,
    color: k === 'CRITICAL' ? '#dc2626' : k === 'HIGH' ? '#ea580c' : k === 'MEDIUM' ? '#d97706' : '#475569',
  })) : [];

  const taskStatusData = task_status ? Object.entries(task_status.by_status || {}).map(([k, v]) => ({
    label: k.slice(0, 6),
    value: v,
    color: k === 'RESOLVED' ? '#059669' : '#dc2626',
  })) : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-brand-400" />
          <h3 className="text-lg font-bold text-white">Enterprise Compliance Analytics</h3>
        </div>
        <button
          onClick={loadAnalytics}
          className="text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 transition-colors"
        >
          Refresh
        </button>
      </div>

      {/* Key Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          icon={Shield}
          label="Current Score"
          value={`${Math.round(analytics.current_score || 0)}%`}
          sub={analytics.overall_status}
          color={analytics.current_score >= 80 ? '#059669' : analytics.current_score >= 50 ? '#d97706' : '#dc2626'}
        />
        <StatCard
          icon={TrendingUp}
          label="Verification Runs"
          value={analytics.total_verification_runs || 0}
          sub="Total snapshots"
        />
        <StatCard
          icon={CheckCircle2}
          label="Resolution Rate"
          value={`${task_status?.resolution_rate || 0}%`}
          sub={`${task_status?.resolved_count || 0}/${task_status?.total || 0} tasks`}
          color="#059669"
        />
        <StatCard
          icon={FileText}
          label="Documents"
          value={documents_analyzed?.total_documents || 0}
          sub={`${documents_analyzed?.total_chunks || 0} chunks analyzed`}
        />
      </div>

      {/* Score Trend */}
      {score_trend && score_trend.length > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-brand-400" />
            Compliance Score Trend
          </h4>
          <ScoreTrendLine data={score_trend} />
          <div className="flex gap-4 mt-3 text-[10px] font-mono text-slate-500">
            {score_trend.map(s => (
              <span key={s.run_number}>
                Run #{s.run_number}: <span className="text-white">{s.score}%</span> ({s.trigger?.replace('_', ' ')})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Two-column: Requirements + Issues */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Requirement Status */}
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3">Requirement Status</h4>
          <MiniBarChart data={reqChartData} />
          <Legend items={reqChartData.map(d => ({ color: d.color, label: d.label, value: d.value }))} />
          {requirement_status?.has_overrides && (
            <p className="text-[10px] text-blue-400 mt-2">
              ✓ {requirement_status.override_count} auditor override(s) applied
            </p>
          )}
        </div>

        {/* Issue Severity */}
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3">Issue Severity Distribution</h4>
          <MiniBarChart data={issueChartData} />
          <Legend items={issueChartData.map(d => ({ color: d.color, label: d.label, value: d.value }))} />
          {issue_severity?.by_gap_type && Object.keys(issue_severity.by_gap_type).length > 0 && (
            <div className="mt-2">
              <p className="text-[10px] text-slate-400 mb-1">Gap Types:</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(issue_severity.by_gap_type).map(([type, count]) => (
                  <span key={type} className="text-[9px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                    {type.replace(/_/g, ' ')}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Two-column: Tasks + Audit */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Task Status */}
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-brand-400" />
            Remediation Tasks
          </h4>
          <MiniBarChart data={taskStatusData} />
          <Legend items={taskStatusData.map(d => ({ color: d.color, label: d.label, value: d.value }))} />
          {task_status?.by_severity && (
            <div className="mt-3 grid grid-cols-4 gap-2">
              {Object.entries(task_status.by_severity).map(([sev, count]) => (
                <div key={sev} className="text-center p-2 rounded-lg bg-slate-950/60 border border-slate-800">
                  <span className="text-[10px] font-mono text-slate-400 block">{sev}</span>
                  <span className="text-sm font-bold text-white">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Audit Activity */}
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-brand-400" />
            Audit Activity
          </h4>
          {audit_summary?.by_actor_type && (
            <div className="space-y-2">
              {Object.entries(audit_summary.by_actor_type).map(([actor, count]) => (
                <div key={actor} className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">{actor.replace(/_/g, ' ')}</span>
                  <span className="text-xs font-mono text-white">{count}</span>
                </div>
              ))}
            </div>
          )}
          {audit_summary?.by_severity && (
            <div className="mt-3 pt-3 border-t border-slate-800">
              <p className="text-[10px] text-slate-400 mb-2">By Severity:</p>
              <div className="flex gap-2">
                {Object.entries(audit_summary.by_severity).map(([sev, count]) => (
                  <span key={sev} className="text-[10px] font-mono px-2 py-0.5 rounded" style={{
                    backgroundColor: sev === 'ERROR' ? '#dc262620' : sev === 'WARNING' ? '#d9770620' : '#33415520',
                    color: sev === 'ERROR' ? '#f87171' : sev === 'WARNING' ? '#fbbf24' : '#94a3b8',
                  }}>
                    {sev}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="mt-3 pt-3 border-t border-slate-800">
            <div className="flex justify-between text-[10px]">
              <span className="text-slate-400">Event Types</span>
              <span className="text-white font-mono">{audit_summary?.by_event_type ? Object.keys(audit_summary.by_event_type).length : 0} types</span>
            </div>
          </div>
        </div>
      </div>

      {/* Remediation Effectiveness */}
      {remediation_effectiveness && remediation_effectiveness.total_runs > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3">Remediation Effectiveness</h4>
          <div className="grid grid-cols-3 gap-4 mb-3">
            <div className="text-center p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-xs text-slate-400 block">Resolved Gaps</span>
              <span className="text-lg font-bold text-emerald-400">{remediation_effectiveness.total_resolved_gaps}</span>
            </div>
            <div className="text-center p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-xs text-slate-400 block">Remaining Gaps</span>
              <span className="text-lg font-bold text-amber-400">{remediation_effectiveness.total_remaining_gaps}</span>
            </div>
            <div className="text-center p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-xs text-slate-400 block">Total Runs</span>
              <span className="text-lg font-bold text-white">{remediation_effectiveness.total_runs}</span>
            </div>
          </div>
          {remediation_effectiveness.gap_resolution_history?.length > 0 && (
            <div className="space-y-1">
              {remediation_effectiveness.gap_resolution_history.map(h => (
                <div key={h.run_number} className="flex items-center gap-3 text-[10px] font-mono">
                  <span className="text-slate-400 w-16">Run #{h.run_number}</span>
                  <span className="text-emerald-400">✓ {h.resolved_count} resolved</span>
                  <span className="text-amber-400">○ {h.remaining_count} remaining</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Auditor Override Impact */}
      {override_impact?.has_overrides && (
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-blue-500/20">
          <h4 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
            <Users className="w-4 h-4 text-blue-400" />
            Auditor Override Impact
          </h4>
          <div className="flex items-center gap-4 mb-3">
            <div className="text-center px-4 py-2 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">AI Score</span>
              <span className="text-lg font-mono font-bold text-white">{override_impact.ai_score}%</span>
            </div>
            <span className="text-slate-600">→</span>
            <div className="text-center px-4 py-2 rounded-lg bg-slate-950/60 border border-blue-500/30">
              <span className="text-[10px] text-blue-400 block">Adjusted</span>
              <span className="text-lg font-mono font-bold text-blue-400">{override_impact.auditor_adjusted_score}%</span>
            </div>
            <span className={`text-xs font-mono font-bold flex items-center gap-1 ${override_impact.score_delta > 0 ? 'text-emerald-400' : override_impact.score_delta < 0 ? 'text-red-400' : 'text-slate-400'}`}>
              {override_impact.score_delta > 0 ? <ArrowUp className="w-3 h-3" /> : override_impact.score_delta < 0 ? <ArrowDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
              {override_impact.score_delta > 0 ? '+' : ''}{override_impact.score_delta}%
            </span>
          </div>
          {override_impact.overrides?.length > 0 && (
            <div className="space-y-1 mt-2">
              {override_impact.overrides.map((o, i) => (
                <div key={i} className="text-[10px] font-mono flex items-center gap-2">
                  <span className="text-white font-bold">{o.requirement_id}</span>
                  <span className="text-slate-500">{o.original_status}</span>
                  <span className="text-slate-600">→</span>
                  <span className="text-blue-400 font-bold">{o.overridden_status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Framework Coverage */}
      {framework_coverage?.framework_name && (
        <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
          <h4 className="text-sm font-bold text-white mb-3">Framework Coverage</h4>
          <div className="flex items-center gap-4">
            <div>
              <span className="text-xs text-slate-400">Active Framework</span>
              <p className="text-sm font-bold text-white">{framework_coverage.framework_name} v{framework_coverage.framework_version}</p>
            </div>
            <div className="text-center px-4 py-2 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Coverage</span>
              <span className="text-lg font-mono font-bold text-white">{framework_coverage.coverage_pct}%</span>
            </div>
            <div className="text-center px-4 py-2 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-400 block">Requirements</span>
              <span className="text-lg font-mono font-bold text-white">{framework_coverage.total_requirements}</span>
            </div>
          </div>
          {framework_coverage.category_breakdown && Object.keys(framework_coverage.category_breakdown).length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap gap-2">
              {Object.entries(framework_coverage.category_breakdown).map(([cat, count]) => (
                <span key={cat} className="text-[9px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                  {cat}: {count}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
