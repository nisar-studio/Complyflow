import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, CheckCircle2, AlertTriangle, FileCheck, ArrowRight, Loader2, RefreshCw, Trash2, Clock, TrendingUp, Activity, Shield, Calendar } from 'lucide-react';
import Navbar from '../components/Navbar';
import api from '../api/client';

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const fetchPortfolio = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getPortfolioAnalytics();
      setPortfolio(data);
    } catch (err) {
      console.error('Failed to load portfolio analytics:', err);
      setError('Failed to load portfolio data');
      // Fallback to basic project list
      try {
        const projects = await api.listProjects();
        setPortfolio({ projects: projects || [], total_projects: (projects || []).length });
      } catch {
        setPortfolio({ projects: [], total_projects: 0 });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteProject = async (e, projectId, projectName) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete compliance check "${projectName}"? This action cannot be undone.`)) {
      return;
    }
    setDeletingId(projectId);
    try {
      await api.deleteProject(projectId);
      // Refresh portfolio data
      fetchPortfolio();
    } catch (err) {
      alert('Failed to delete project: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const projects = portfolio?.projects || [];
  const totalChecks = portfolio?.total_projects || projects.length;
  const readyChecks = portfolio?.compliant_projects ?? projects.filter(p => p.overall_status === 'READY' || p.compliance_score === 100).length;
  const actionNeeded = portfolio?.projects_needing_action ?? (totalChecks - readyChecks);
  const avgScore = portfolio?.average_score ?? (totalChecks > 0
    ? Math.round(projects.reduce((acc, p) => acc + (p.compliance_score || 0), 0) / totalChecks)
    : 0);
  const overdueTasks = portfolio?.overdue_tasks || { total_overdue: 0, by_project: [] };
  const scoreTrend = portfolio?.score_trend || [];
  const recentActivity = portfolio?.recent_activity || [];
  const topRisks = portfolio?.top_risks || [];

  const formatTime = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diff = now - d;
      if (diff < 60000) return 'just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        {/* Dashboard Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white">Compliance Workspace</h1>
            <p className="text-sm text-slate-400 mt-1">Portfolio overview of compliance checks and verification packages</p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={fetchPortfolio}
              className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Refresh portfolio"
            >
              <RefreshCw className="w-4 h-4" />
            </button>

            <Link
              to="/projects/new"
              className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/25 transition-all hover:scale-105"
            >
              <Plus className="w-4 h-4" />
              <span>+ New Compliance Check</span>
            </Link>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-xl bg-red-950/30 border border-red-800/60 text-xs text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-20 text-center text-slate-500">
            <Loader2 className="w-8 h-8 mx-auto animate-spin mb-3 text-slate-400" />
            <p className="text-sm">Loading portfolio analytics...</p>
          </div>
        ) : totalChecks === 0 ? (
          <div className="py-20 text-center text-slate-400">
            <FileCheck className="w-12 h-12 mx-auto text-slate-600 mb-4" />
            <h4 className="text-lg font-semibold text-white mb-2">No Compliance Checks Yet</h4>
            <p className="text-sm text-slate-500 mb-6">Start your first autonomous AI compliance check.</p>
            <Link
              to="/projects/new"
              className="inline-flex items-center space-x-2 px-5 py-3 rounded-xl text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white"
            >
              <Plus className="w-4 h-4" />
              <span>Create Compliance Check</span>
            </Link>
          </div>
        ) : (
          <>
            {/* Portfolio Metrics Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
                <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Total Checks</span>
                <div className="flex items-baseline justify-between mt-2">
                  <span className="text-3xl font-extrabold font-mono text-white">{totalChecks}</span>
                  <FileCheck className="w-6 h-6 text-brand-400" />
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
                <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Ready to Submit</span>
                <div className="flex items-baseline justify-between mt-2">
                  <span className="text-3xl font-extrabold font-mono text-emerald-400">{readyChecks}</span>
                  <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
                <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Needs Action</span>
                <div className="flex items-baseline justify-between mt-2">
                  <span className="text-3xl font-extrabold font-mono text-amber-400">{actionNeeded}</span>
                  <AlertTriangle className="w-6 h-6 text-amber-400" />
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800">
                <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Average Compliance</span>
                <div className="flex items-baseline justify-between mt-2">
                  <span className="text-3xl font-extrabold font-mono text-white">{avgScore}%</span>
                  <div className="w-8 h-8 rounded-full border-2 border-brand-500/30 flex items-center justify-center text-xs font-mono text-brand-400">
                    AVG
                  </div>
                </div>
              </div>
            </div>

            {/* Two-column layout: Score Trend + Overdue Tasks */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Score Trend */}
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp className="w-4 h-4 text-brand-400" />
                  <h3 className="text-sm font-bold text-white">Compliance Trend (6 Months)</h3>
                </div>
                {scoreTrend.length > 0 ? (
                  <div className="space-y-2">
                    {scoreTrend.map((item) => (
                      <div key={item.month} className="flex items-center gap-3">
                        <span className="text-xs font-mono text-slate-400 w-16">{item.month}</span>
                        <div className="flex-1 bg-slate-800 rounded-full h-2">
                          <div
                            className="h-2 rounded-full transition-all"
                            style={{
                              width: item.average_score !== null ? `${item.average_score}%` : '0%',
                              backgroundColor: item.average_score !== null
                                ? (item.average_score >= 80 ? '#10b981' : item.average_score >= 50 ? '#f59e0b' : '#ef4444')
                                : '#334155',
                            }}
                          />
                        </div>
                        <span className="text-xs font-mono text-slate-300 w-12 text-right">
                          {item.average_score !== null ? `${item.average_score}%` : '—'}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 py-4 text-center">No verification data yet</p>
                )}
              </div>

              {/* Overdue Tasks */}
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
                <div className="flex items-center gap-2 mb-4">
                  <Clock className="w-4 h-4 text-red-400" />
                  <h3 className="text-sm font-bold text-white">Overdue Tasks</h3>
                  {overdueTasks.total_overdue > 0 && (
                    <span className="ml-auto px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 text-xs font-mono font-bold">
                      {overdueTasks.total_overdue}
                    </span>
                  )}
                </div>
                {overdueTasks.total_overdue > 0 ? (
                  <div className="space-y-3">
                    {overdueTasks.by_project.map((proj) => (
                      <div key={proj.project_id} className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
                        <div className="flex items-center justify-between mb-2">
                          <Link
                            to={`/projects/${proj.project_id}`}
                            className="text-xs font-semibold text-white hover:text-brand-300 transition-colors"
                          >
                            {proj.project_name}
                          </Link>
                          <span className="text-[10px] font-mono text-red-400">{proj.overdue_count} overdue</span>
                        </div>
                        {proj.tasks.slice(0, 3).map((task) => (
                          <div key={task.task_id} className="flex items-center gap-2 text-[11px] text-slate-400">
                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                              task.severity === 'CRITICAL' ? 'bg-red-500' :
                              task.severity === 'HIGH' ? 'bg-orange-500' : 'bg-amber-500'
                            }`} />
                            <span className="truncate">{task.title || task.task_id}</span>
                          </div>
                        ))}
                        {proj.tasks.length > 3 && (
                          <span className="text-[10px] text-slate-500 mt-1 block">+{proj.tasks.length - 3} more</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 py-4 text-center">No overdue tasks</p>
                )}
              </div>
            </div>

            {/* Two-column: Recent Activity + Top Risks */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Recent Activity */}
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
                <div className="flex items-center gap-2 mb-4">
                  <Activity className="w-4 h-4 text-brand-400" />
                  <h3 className="text-sm font-bold text-white">Recent Activity</h3>
                </div>
                {recentActivity.length > 0 ? (
                  <div className="space-y-2">
                    {recentActivity.map((event, idx) => (
                      <Link
                        key={event.event_id || idx}
                        to={`/projects/${event.project_id}`}
                        className="flex items-start gap-3 p-2 rounded-lg hover:bg-slate-800/50 transition-colors"
                      >
                        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                          event.severity === 'ERROR' ? 'bg-red-500' :
                          event.severity === 'WARNING' ? 'bg-amber-500' : 'bg-brand-400'
                        }`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-[11px] text-slate-300 truncate">{event.summary}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[10px] font-mono text-slate-500">{event.project_name}</span>
                            <span className="text-[10px] text-slate-600">•</span>
                            <span className="text-[10px] text-slate-500">{formatTime(event.timestamp)}</span>
                          </div>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 py-4 text-center">No recent activity</p>
                )}
              </div>

              {/* Top Risks */}
              <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
                <div className="flex items-center gap-2 mb-4">
                  <Shield className="w-4 h-4 text-amber-400" />
                  <h3 className="text-sm font-bold text-white">Top Risks</h3>
                </div>
                {topRisks.length > 0 ? (
                  <div className="space-y-2">
                    {topRisks.map((risk) => (
                      <Link
                        key={risk.project_id}
                        to={`/projects/${risk.project_id}`}
                        className="flex items-center justify-between p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition-all group"
                      >
                        <div className="space-y-0.5">
                          <span className="text-xs font-semibold text-white group-hover:text-brand-300 transition-colors">
                            {risk.name}
                          </span>
                          <div className="flex items-center gap-2 text-[10px] text-slate-500">
                            <span>{risk.issues_count} issues</span>
                            <span>•</span>
                            <span>{risk.tasks_count} tasks</span>
                          </div>
                        </div>
                        <div className="text-right">
                          <span className={`text-lg font-mono font-bold ${
                            risk.compliance_score >= 80 ? 'text-emerald-400' :
                            risk.compliance_score >= 50 ? 'text-amber-400' : 'text-red-400'
                          }`}>
                            {risk.compliance_score !== null ? `${Math.round(risk.compliance_score)}%` : '—'}
                          </span>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 py-4 text-center">No risk data available</p>
                )}
              </div>
            </div>

            {/* Recent Projects Table */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                <h3 className="text-lg font-bold text-white">All Compliance Checks</h3>
                <span className="text-xs font-mono text-slate-400">{totalChecks} total</span>
              </div>

              <div className="space-y-3">
                {projects.map((proj) => {
                  const isReady = proj.overall_status === 'READY' || proj.compliance_score === 100;

                  return (
                    <Link
                      key={proj.project_id}
                      to={`/projects/${proj.project_id}`}
                      className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between hover:border-slate-700 transition-all hover:bg-slate-900/40 group"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center space-x-3">
                          <h4 className="text-base font-semibold text-white group-hover:text-brand-300 transition-colors">
                            {proj.name}
                          </h4>
                          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                            {proj.project_id.slice(0, 8)}...
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Created {new Date(proj.created_at).toLocaleDateString()} • {proj.requirements_count || 0} Requirements
                        </p>
                      </div>

                      <div className="flex items-center space-x-6">
                        <div className="text-right">
                          <div className="font-mono text-base font-bold text-white">
                            {proj.compliance_score !== null ? `${Math.round(proj.compliance_score)}%` : 'Pending'}
                          </div>
                          <span className={`inline-flex items-center text-xs font-semibold ${
                            isReady ? 'text-emerald-400' : 'text-amber-400'
                          }`}>
                            {isReady ? 'READY TO SUBMIT' : 'ACTION REQUIRED'}
                          </span>
                        </div>

                        <button
                          onClick={(e) => handleDeleteProject(e, proj.project_id, proj.name)}
                          disabled={deletingId === proj.project_id}
                          title="Delete compliance check"
                          className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          {deletingId === proj.project_id ? (
                            <Loader2 className="w-4 h-4 animate-spin text-red-400" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </button>

                        <ArrowRight className="w-5 h-5 text-slate-600 group-hover:text-white transition-colors" />
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
