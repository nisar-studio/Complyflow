import React, { useState, useMemo } from "react";
import { CheckCircle2, Search, Filter, RotateCcw, AlertTriangle, AlertCircle, Undo2, CheckSquare, Loader2, UserPlus, User } from "lucide-react";
import TaskUploadPanel from "./TaskUploadPanel";
import api from "../api/client";

export default function RemediationList({ tasks = [], projectId, requirements = [], members = [] }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [updatingTaskId, setUpdatingTaskId] = useState(null);
  const [assigningTaskId, setAssigningTaskId] = useState(null);
  const [taskError, setTaskError] = useState(null);
  const [taskSuccess, setTaskSuccess] = useState(null);

  const handleToggleTaskStatus = async (task, e) => {
    e.stopPropagation();
    const newStatus = task.status === "RESOLVED" ? "OPEN" : "RESOLVED";
    setUpdatingTaskId(task.task_id);
    setTaskError(null);
    setTaskSuccess(null);
    try {
      await api.updateTaskStatus(projectId, task.task_id, newStatus);
      task.status = newStatus;
      setTaskSuccess(`Task ${task.task_id} ${newStatus === "RESOLVED" ? "resolved" : "reopened"} successfully.`);
      setTimeout(() => setTaskSuccess(null), 3000);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message || "Failed to update task status");
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const handleAssignTask = async (task, userId) => {
    setAssigningTaskId(task.task_id);
    try {
      await api.assignTask(projectId, task.task_id, userId);
      task.assigned_to = userId;
      setTaskSuccess(`Task ${task.task_id} assigned successfully.`);
      setTimeout(() => setTaskSuccess(null), 3000);
    } catch (err) {
      setTaskError(err.response?.data?.detail || err.message || "Failed to assign task");
    } finally {
      setAssigningTaskId(null);
    }
  };

  const getSeverityBadge = (severity) => {
    const s = (severity || "MEDIUM").toUpperCase();
    const styles = {
      CRITICAL: "bg-red-500/10 text-red-400 border-red-500/30",
      HIGH: "bg-orange-500/10 text-orange-400 border-orange-500/30",
      MEDIUM: "bg-amber-500/10 text-amber-400 border-amber-500/30",
      LOW: "bg-slate-800 text-slate-400 border-slate-700",
    };
    return (
      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase ${styles[s] || styles.MEDIUM}`}>
        {s} SEVERITY
      </span>
    );
  };

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      const q = searchQuery.toLowerCase().trim();
      if (q) {
        const titleMatch = (t.title || "").toLowerCase().includes(q);
        const descMatch = (t.description || "").toLowerCase().includes(q);
        const idMatch = (t.task_id || "").toLowerCase().includes(q);
        const reqMatch = (t.related_requirement_id || "").toLowerCase().includes(q);
        if (!titleMatch && !descMatch && !idMatch && !reqMatch) return false;
      }
      if (severityFilter !== "ALL" && (t.severity || "MEDIUM").toUpperCase() !== severityFilter) {
        return false;
      }
      if (statusFilter !== "ALL" && (t.status || "OPEN").toUpperCase() !== statusFilter) {
        return false;
      }
      return true;
    });
  }, [tasks, searchQuery, severityFilter, statusFilter]);

  const counts = useMemo(() => {
    return {
      total: tasks.length,
      critical: tasks.filter(t => (t.severity || "").toUpperCase() === "CRITICAL").length,
      high: tasks.filter(t => (t.severity || "").toUpperCase() === "HIGH").length,
      medium: tasks.filter(t => (t.severity || "").toUpperCase() === "MEDIUM").length,
    };
  }, [tasks]);

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-2xl space-y-6">
      {/* TASK STATUS FEEDBACK */}
      {taskSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/60 flex items-center space-x-2 text-xs text-emerald-300">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{taskSuccess}</span>
        </div>
      )}
      {taskError && (
        <div className="p-3 rounded-xl bg-red-950/30 border border-red-800/60 flex items-center justify-between text-xs text-red-300">
          <span>{taskError}</span>
          <button onClick={() => setTaskError(null)} className="text-red-400 hover:text-red-200">✕</button>
        </div>
      )}

      {/* HEADER & COUNTS */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h3 className="text-lg font-bold text-white">Prioritized Remediation Plan</h3>
          <p className="text-xs text-slate-400">
            Actionable tasks created by the agent to resolve compliance gaps
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold">
            {tasks.length} Action Items
          </span>
          {counts.critical > 0 && (
            <span className="px-2.5 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/20 font-semibold">
              {counts.critical} Critical
            </span>
          )}
        </div>
      </div>

      {/* FILTER BAR */}
      {tasks.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-slate-950/60 p-3 rounded-xl border border-slate-800 text-xs font-mono">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search tasks by ID, title, description, or requirement..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-brand-500"
            />
          </div>

          <div className="flex items-center space-x-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-slate-300 rounded p-1.5 focus:outline-none focus:border-brand-500"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical ({counts.critical})</option>
              <option value="HIGH">High ({counts.high})</option>
              <option value="MEDIUM">Medium ({counts.medium})</option>
              <option value="LOW">Low</option>
            </select>

            {(searchQuery || severityFilter !== "ALL") && (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setSeverityFilter("ALL");
                }}
                className="p-1.5 text-slate-400 hover:text-white"
                title="Reset Filters"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* TASK LIST */}
      {tasks.length === 0 ? (
        <div className="py-12 text-center text-slate-400">
          <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-400 mb-3" />
          <h4 className="text-base font-semibold text-white">No Action Items Required!</h4>
          <p className="text-xs text-slate-500 mt-1">All compliance requirements have been fully satisfied.</p>
        </div>
      ) : filteredTasks.length === 0 ? (
        <div className="py-8 text-center text-slate-400 font-mono text-xs">
          No remediation tasks match your current filters.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredTasks.map((task) => (
            <div
              key={task.task_id}
              className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-all space-y-3"
            >
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                <div className="space-y-1.5 max-w-2xl">
                  <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                    {getSeverityBadge(task.severity)}
                    <span className="text-xs font-mono text-brand-400 font-semibold">
                      {task.task_id}
                    </span>
                    <span className="text-xs font-mono text-slate-500">+</span>
                    <span className="text-xs text-slate-400 font-mono">
                      Related: {task.related_requirement_id}
                    </span>
                  </div>
                  <h4 className="text-base font-semibold text-white">{task.title}</h4>
                  <p className="text-xs text-slate-300">{task.description}</p>
                </div>
              </div>

              {/* ASSIGNMENT INFO */}
              {projectId && members.length > 0 && (
                <div className="flex items-center gap-2 text-xs">
                  {task.assigned_to ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700 text-slate-300">
                      <User className="w-3 h-3 text-slate-400" />
                      <span className="font-mono text-slate-400">Assigned:</span>
                      <span className="font-semibold text-white">
                        {members.find(m => m.user_id === task.assigned_to)?.name || task.assigned_to}
                      </span>
                    </span>
                  ) : (
                    <select
                      value=""
                      onChange={(e) => {
                        if (e.target.value) handleAssignTask(task, e.target.value);
                      }}
                      disabled={assigningTaskId === task.task_id}
                      className="bg-slate-900 border border-slate-700 text-slate-400 rounded-lg px-2.5 py-1 text-[11px] font-mono focus:outline-none focus:border-brand-500 disabled:opacity-50"
                    >
                      <option value="">Assign to member...</option>
                      {members.filter(m => m.is_active !== false).map(m => (
                        <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {/* RESOLVE / REOPEN BUTTON */}
              {projectId && (
                <div className="flex items-center gap-2 pt-2 border-t border-slate-800/60">
                  <button
                    onClick={(e) => handleToggleTaskStatus(task, e)}
                    disabled={updatingTaskId === task.task_id}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition-all disabled:opacity-50 ${
                      task.status === "RESOLVED"
                        ? "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                        : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20"
                    }`}
                  >
                    {updatingTaskId === task.task_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : task.status === "RESOLVED" ? (
                      <Undo2 className="w-3.5 h-3.5" />
                    ) : (
                      <CheckSquare className="w-3.5 h-3.5" />
                    )}
                    <span>{task.status === "RESOLVED" ? "Reopen" : "Mark Resolved"}</span>
                  </button>
                  <span className="text-[10px] font-mono text-slate-500">
                    {task.status === "RESOLVED" ? "This task has been completed" : "Upload evidence and mark when done"}
                  </span>
                </div>
              )}

              {projectId && (
                <TaskUploadPanel
                  projectId={projectId}
                  task={task}
                  requirements={requirements}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
