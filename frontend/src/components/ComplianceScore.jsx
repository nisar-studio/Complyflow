import React from 'react';
import { ShieldCheck, AlertCircle, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function ComplianceScore({ 
  score, 
  overallStatus, 
  satisfiedCount, 
  totalCount, 
  missingCount, 
  conflictCount,
  aiScore = null,
  adjustedScore = null,
  hasOverrides = false,
}) {
  const displayScore = hasOverrides && adjustedScore !== null ? adjustedScore : score;
  const isReady = overallStatus === 'READY' || displayScore === 100;

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl shadow-2xl">
      <div className="flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Gauge / Score Badge */}
        <div className="flex items-center space-x-6">
          <div className="relative w-28 h-28 flex items-center justify-center">
            {/* SVG Ring */}
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-slate-800"
                strokeWidth="3.5"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                className={isReady ? 'text-emerald-500' : 'text-amber-500'}
                strokeDasharray={`${displayScore || 0}, 100`}
                strokeWidth="3.5"
                strokeLinecap="round"
                stroke="currentColor"
                fill="none"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center">
              <span className="text-2xl font-bold font-mono text-white">
                {Math.round(displayScore || 0)}%
              </span>
              <span className="text-[10px] font-mono uppercase text-slate-400">Score</span>
            </div>
          </div>

          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-xl font-bold text-white">Compliance Status</h3>
            </div>
            
            <div className="mt-2 flex items-center flex-wrap gap-2">
              {isReady ? (
                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle className="w-4 h-4 mr-1.5" />
                  READY TO SUBMIT
                </span>
              ) : (
                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <AlertTriangle className="w-4 h-4 mr-1.5" />
                  ACTION REQUIRED
                </span>
              )}

              {hasOverrides && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  Auditor Overrides Active
                </span>
              )}
            </div>

            {/* Score provenance breakdown if overrides exist */}
            {hasOverrides && aiScore !== null && (
              <div className="flex items-center space-x-3 text-xs font-mono mt-2 text-slate-300">
                <span>AI Automated: <b className="text-white">{Math.round(aiScore)}%</b></span>
                <span>·</span>
                <span>Auditor-Adjusted: <b className="text-emerald-400">{Math.round(displayScore)}%</b></span>
              </div>
            )}

            <p className="text-xs text-slate-400 mt-2">
              {satisfiedCount} of {totalCount} requirements fully satisfied with verified evidence.
            </p>
          </div>
        </div>

        {/* Breakdown Stats */}
        <div className="grid grid-cols-3 gap-3 w-full md:w-auto">
          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-center min-w-[100px]">
            <div className="flex items-center justify-center text-emerald-400 mb-1">
              <CheckCircle className="w-4 h-4" />
            </div>
            <span className="text-lg font-bold font-mono text-white">{satisfiedCount || 0}</span>
            <p className="text-[11px] text-slate-400">Satisfied</p>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-center min-w-[100px]">
            <div className="flex items-center justify-center text-amber-400 mb-1">
              <AlertCircle className="w-4 h-4" />
            </div>
            <span className="text-lg font-bold font-mono text-white">{missingCount || 0}</span>
            <p className="text-[11px] text-slate-400">Missing</p>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-center min-w-[100px]">
            <div className="flex items-center justify-center text-purple-400 mb-1">
              <XCircle className="w-4 h-4" />
            </div>
            <span className="text-lg font-bold font-mono text-white">{conflictCount || 0}</span>
            <p className="text-[11px] text-slate-400">Conflicts</p>
          </div>
        </div>
      </div>
    </div>
  );
}
