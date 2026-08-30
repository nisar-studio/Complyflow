import React from 'react';
import { 
  Bot, CheckCircle2, AlertTriangle, Loader2, Sparkles, 
  FileSearch, CheckSquare, ShieldAlert, ListCheck, RefreshCw, Cpu
} from 'lucide-react';

const TOOL_ICONS = {
  extract_requirements: FileSearch,
  analyze_documents: Bot,
  match_evidence: CheckSquare,
  detect_gaps: ShieldAlert,
  create_remediation_plan: ListCheck,
  verify_compliance: RefreshCw,
};

const TOOL_NAMES = {
  extract_requirements: 'Requirements Extraction',
  analyze_documents: 'Document Analysis',
  match_evidence: 'Evidence Mapping',
  detect_gaps: 'Gap Analysis',
  create_remediation_plan: 'Remediation Planning',
  verify_compliance: 'Verification Reasoning',
};

export default function AgentActivity({ events, isLive, currentTool, agentStatus }) {
  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center">
              <Cpu className="w-5 h-5 text-brand-400" />
            </div>
            {agentStatus === 'running' && (
              <span className="absolute -top-1 -right-1 flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-brand-500"></span>
              </span>
            )}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-lg font-semibold text-white">ComplyFlow ADK Agent</h2>
              {isLive ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
                  Live SSE
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  Polling Sync
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 font-mono">
              Framework: Google ADK 2.8.0 • Model: {import.meta.env.VITE_GEMINI_MODEL || 'Gemini 3.5+'}
            </p>
          </div>
        </div>

        <div className="text-right">
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${
            agentStatus === 'completed'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : agentStatus === 'running'
              ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20 animate-pulse'
              : agentStatus === 'error'
              ? 'bg-red-500/10 text-red-400 border border-red-500/20'
              : 'bg-slate-800 text-slate-400'
          }`}>
            {agentStatus === 'running' && <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />}
            {agentStatus === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />}
            {agentStatus === 'error' && <AlertTriangle className="w-3.5 h-3.5 mr-1.5 text-red-400" />}
            {agentStatus.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Live Active Tool Banner */}
      {currentTool && agentStatus === 'running' && (
        <div className="mt-4 p-3 bg-brand-500/10 border border-brand-500/20 rounded-xl flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Loader2 className="w-4 h-4 text-brand-400 animate-spin" />
            <div>
              <span className="text-xs font-mono uppercase tracking-wider text-brand-400 font-semibold">
                Executing ADK Tool
              </span>
              <p className="text-sm font-medium text-white">
                {TOOL_NAMES[currentTool] || currentTool}
              </p>
            </div>
          </div>
          <span className="text-xs font-mono text-slate-400">tool: {currentTool}</span>
        </div>
      )}

      {/* Event Timeline Stream */}
      <div className="mt-6 space-y-3 max-h-96 overflow-y-auto pr-2">
        {events.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-sm">
            <Loader2 className="w-6 h-6 mx-auto mb-2 animate-spin text-slate-600" />
            Initializing ADK Agent...
          </div>
        ) : (
          events.map((evt, idx) => {
            const Icon = (evt.tool && TOOL_ICONS[evt.tool]) || Bot;
            const isError = evt.status === 'error' || evt.type === 'AGENT_ERROR';
            const isCompleted = evt.status === 'completed' || evt.type.includes('COMPLETED');
            
            return (
              <div
                key={evt.event_id || idx}
                className={`p-3.5 rounded-xl border transition-all animate-fade-in ${
                  isError
                    ? 'bg-red-950/20 border-red-900/50 text-red-200'
                    : isCompleted
                    ? 'bg-slate-950/60 border-slate-800 text-slate-200'
                    : 'bg-brand-950/20 border-brand-900/40 text-brand-100'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3">
                    <div className={`p-1.5 rounded-lg mt-0.5 ${
                      isError
                        ? 'bg-red-500/10 text-red-400'
                        : isCompleted
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-brand-500/10 text-brand-400'
                    }`}>
                      {isError ? (
                        <AlertTriangle className="w-4 h-4" />
                      ) : isCompleted ? (
                        <CheckCircle2 className="w-4 h-4" />
                      ) : (
                        <Icon className="w-4 h-4 animate-spin" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
                          {evt.tool ? TOOL_NAMES[evt.tool] || evt.tool : evt.type}
                        </span>
                        {evt.tool && (
                          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                            {evt.tool}
                          </span>
                        )}
                      </div>
                      <p className="text-sm font-medium mt-0.5 text-white">
                        {evt.summary}
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500 shrink-0 ml-4">
                    {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString() : ''}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
