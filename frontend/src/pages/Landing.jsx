import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowRight, CheckCircle2, Cpu, FileCheck, Layers, Play } from 'lucide-react';
import Navbar from '../components/Navbar';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />

      {/* Hero Section */}
      <main className="flex-1 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 md:py-24 flex flex-col items-center text-center">
        {/* Hackathon Badge */}
        <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-brand-500/10 border border-brand-500/20 text-brand-300 text-xs font-mono mb-8 animate-fade-in">
          <Cpu className="w-3.5 h-3.5 text-brand-400" />
          <span>All Things Agentic Hackathon Project</span>
          <span className="text-slate-600">•</span>
          <span className="text-slate-400">Google ADK & Gemini 3.5+</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight max-w-4xl text-white">
          From requirements to ready-to-submit.{' '}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-brand-400 via-indigo-300 to-purple-400">
            Autonomously.
          </span>
        </h1>

        {/* Tagline / Subtitle */}
        <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-2xl font-normal leading-relaxed">
          ComplyFlow is an autonomous compliance agent that analyzes complex requirements and supporting documents, identifies evidence gaps and conflicts, creates prioritized remediation plans, and re-verifies package readiness.
        </p>

        {/* CTA Buttons */}
        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          <Link
            to="/projects/new"
            className="w-full sm:w-auto px-8 py-4 rounded-xl text-base font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-xl shadow-brand-600/30 transition-all hover:scale-105 active:scale-95 flex items-center justify-center space-x-2"
          >
            <span>Start Compliance Check</span>
            <ArrowRight className="w-5 h-5" />
          </Link>

          <Link
            to="/dashboard"
            className="w-full sm:w-auto px-8 py-4 rounded-xl text-base font-semibold bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 transition-all flex items-center justify-center space-x-2"
          >
            <Play className="w-4 h-4 text-brand-400" />
            <span>View Demo Dashboard</span>
          </Link>
        </div>

        {/* 6-Step Workflow Section */}
        <div className="mt-24 w-full">
          <h2 className="text-2xl font-bold text-white text-center mb-2">Autonomous Agent Workflow</h2>
          <p className="text-sm text-slate-400 text-center mb-12">Goal → Plan → Analyze → Act → Verify → Result</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-brand-500/10 text-brand-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                01
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Requirement Extraction</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Extracts structured compliance requirements from PDF, DOCX, or TXT checklist documents.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                02
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Document Analysis</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Extracts key facts, dates, organization identifiers, and evidence statements from all uploaded files.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                03
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Evidence Mapping</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Maps each document fact against individual requirements to determine satisfaction status.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                04
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Gap & Conflict Detection</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Identifies missing evidence, expired certificates, and cross-document address or numerical conflicts.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 text-cyan-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                05
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Prioritized Remediation</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Generates a step-by-step action plan telling the user exactly what missing document to upload.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-left">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4 font-mono font-bold text-sm">
                06
              </div>
              <h3 className="text-base font-semibold text-white mb-1">Re-Verification</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Re-analyzes updated document set after fixes to verify full package compliance (100% READY).
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500 font-mono">
        ComplyFlow • All Things Agentic Hackathon • Google ADK + Gemini + FastAPI + Firestore
      </footer>
    </div>
  );
}
