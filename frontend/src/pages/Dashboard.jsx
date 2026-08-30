import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, CheckCircle2, AlertTriangle, FileCheck, ArrowRight, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import Navbar from '../components/Navbar';
import api from '../api/client';

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const data = await api.listProjects();
      setProjects(data || []);
    } catch (err) {
      console.error('Failed to list projects:', err);
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
      setProjects(prev => prev.filter(p => p.project_id !== projectId));
    } catch (err) {
      alert('Failed to delete project: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const totalChecks = projects.length;
  const readyChecks = projects.filter(p => p.overall_status === 'READY' || p.compliance_score === 100).length;
  const actionNeeded = totalChecks - readyChecks;
  const avgScore = totalChecks > 0 
    ? Math.round(projects.reduce((acc, p) => acc + (p.compliance_score || 0), 0) / totalChecks) 
    : 0;


  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
        {/* Dashboard Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white">Compliance Workspace</h1>
            <p className="text-sm text-slate-400 mt-1">Overview of active agent compliance checks and verification packages</p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={fetchProjects}
              className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Refresh projects"
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

        {/* Metrics Grid */}
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

        {/* Recent Projects Table */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
            <h3 className="text-lg font-bold text-white">Recent Compliance Checks</h3>
            <span className="text-xs font-mono text-slate-400">Showing recent activity</span>
          </div>

          {loading ? (
            <div className="py-12 text-center text-slate-500">
              <Loader2 className="w-6 h-6 mx-auto animate-spin mb-2 text-slate-400" />
              Loading compliance checks...
            </div>
          ) : projects.length === 0 ? (
            <div className="py-12 text-center text-slate-400">
              <FileCheck className="w-10 h-10 mx-auto text-slate-600 mb-3" />
              <h4 className="text-base font-semibold text-white">No Compliance Checks Yet</h4>
              <p className="text-xs text-slate-500 mt-1 mb-4">Start your first autonomous AI check with NovaTech demo or custom files.</p>
              <Link
                to="/projects/new"
                className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white"
              >
                <Plus className="w-4 h-4" />
                <span>Create Compliance Check</span>
              </Link>
            </div>
          ) : (
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
                        Created {new Date(proj.created_at).toLocaleDateString()} • {proj.requirements_count || 12} Requirements
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
          )}
        </div>
      </main>
    </div>
  );
}
