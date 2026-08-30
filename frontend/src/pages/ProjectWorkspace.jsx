import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ShieldCheck, RefreshCw, Upload, CheckCircle2, AlertTriangle, 
  ArrowLeft, FileText, Sparkles, Loader2, Award, History, BookOpen, Clock, Layers
} from 'lucide-react';
import Navbar from '../components/Navbar';
import AgentActivity from '../components/AgentActivity';
import ComplianceScore from '../components/ComplianceScore';
import RequirementsList from '../components/RequirementsList';
import RemediationList from '../components/RemediationList';
import VerificationHistory from '../components/VerificationHistory';
import DocumentViewer from '../components/DocumentViewer';
import AuditTimeline from '../components/AuditTimeline';
import ProjectMembersModal from '../components/ProjectMembersModal';
import FrameworkModal from '../components/FrameworkModal';
import { useAgentEvents } from '../hooks/useAgentEvents';
import { useAuth } from '../context/AuthContext';

import api from '../api/client';


export default function ProjectWorkspace() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [project, setProject] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('activity'); // activity | results | remediation | summary
  const [projectRole, setProjectRole] = useState(null); // current user's role in this project
  const [showMembersModal, setShowMembersModal] = useState(false);
  const [showFrameworkModal, setShowFrameworkModal] = useState(false);



  // Upload modal state for remediation
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [selectedTask, setSelectedTask] = useState(null);
  const [remediationFiles, setRemediationFiles] = useState([]);
  const [uploadingRemediation, setUploadingRemediation] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const [errorBanner, setErrorBanner] = useState(null);
  const isAnalyzing = project?.status === 'ANALYZING';

  // Live Agent Event Stream (SSE + Polling fallback)
  const { events, isLive, currentTool, agentStatus, errorMessage } = useAgentEvents(projectId, isAnalyzing);

  const loadProjectData = async () => {
    try {
      const projData = await api.getProject(projectId);
      setProject(projData);

      // Fetch current user's role in this project
      if (user) {
        try {
          const membersData = await api.listMembers(projectId);
          const me = membersData?.find((m) => m.user_id === user.user_id);
          setProjectRole(me?.role || null);
        } catch {
          setProjectRole(null);
        }
      }

      if (projData.status !== 'ANALYZING') {
        const resultsData = await api.getResults(projectId);
        setResults(resultsData);
      }
    } catch (err) {
      console.error('Failed to load project data:', err);
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    loadProjectData();
  }, [projectId]);

  // When agent finishes running, reload project results
  useEffect(() => {
    if (agentStatus === 'completed') {
      loadProjectData();
      setActiveTab('results');
    }
  }, [agentStatus]);

  // 1-Click Load NovaTech Remediation Docs (Insurance + DPA + Corrected Profile)
  const handleLoadDemoRemediation = async () => {
    setUploadingRemediation(true);
    setErrorBanner(null);
    try {
      const f1 = new File([DEMO_REMEDIATION_INSURANCE], 'remediation_insurance_certificate.txt', { type: 'text/plain' });
      const f2 = new File([DEMO_REMEDIATION_DPA], 'remediation_data_processing_agreement.txt', { type: 'text/plain' });
      const f3 = new File([DEMO_REMEDIATION_PROFILE], 'remediation_company_profile_corrected.txt', { type: 'text/plain' });

      await api.uploadDocuments(projectId, null, [f1, f2, f3], true);
      setShowUploadModal(false);

      // Immediately trigger verification
      await handleTriggerVerification();
    } catch (err) {
      console.error('Failed to upload demo remediation:', err);
      setErrorBanner('Failed to upload demo evidence: ' + (err.response?.data?.error?.message || err.message || err));
    } finally {
      setUploadingRemediation(false);
    }
  };

  const handleCustomUploadRemediation = async (e) => {
    e.preventDefault();
    if (remediationFiles.length === 0) return;

    setUploadingRemediation(true);
    setErrorBanner(null);
    try {
      await api.uploadDocuments(projectId, null, remediationFiles, true);
      setShowUploadModal(false);
      setRemediationFiles([]);
      
      // Trigger verification
      await handleTriggerVerification();
    } catch (err) {
      console.error('Failed to upload remediation files:', err);
      setErrorBanner('Upload failed: ' + (err.response?.data?.error?.message || err.message || err));
    } finally {
      setUploadingRemediation(false);
    }
  };

  const handleTriggerVerification = async () => {
    setVerifying(true);
    setErrorBanner(null);
    try {
      await api.startVerification(projectId);
      setProject(prev => ({ ...prev, status: 'ANALYZING' }));
      setActiveTab('activity');
    } catch (err) {
      console.error('Failed to start verification:', err);
      setErrorBanner('Verification failed to start: ' + (err.response?.data?.error?.message || err.message || err));
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
        <Navbar projectRole={projectRole} />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-brand-400" />
        </div>
      </div>
    );
  }

  const score = results?.project?.compliance_score ?? project?.compliance_score ?? 0;
  const overallStatus = results?.project?.overall_status ?? project?.overall_status ?? 'ACTION_REQUIRED';
  const matches = results?.matches || [];
  const requirements = results?.requirements || [];
  const tasks = results?.tasks || [];
  const isReady = overallStatus === 'READY' || score === 100;

  const satisfiedCount = matches.filter(m => m.status === 'SATISFIED').length;
  const missingCount = matches.filter(m => m.status === 'MISSING').length;
  const conflictCount = matches.filter(m => m.status === 'CONFLICT').length;

  const canManage = projectRole === 'ADMIN';
  const canOverride = projectRole === 'ADMIN' || projectRole === 'AUDITOR';
  const canUpload = projectRole === 'ADMIN' || projectRole === 'AUDITOR' || projectRole === 'REVIEWER';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar projectRole={projectRole} />

      {showMembersModal && (
        <ProjectMembersModal projectId={projectId} onClose={() => setShowMembersModal(false)} />
      )}

      {showFrameworkModal && (
        <FrameworkModal
          projectId={projectId}
          isOpen={showFrameworkModal}
          onClose={() => setShowFrameworkModal(false)}
          onFrameworkApplied={() => loadProjectData()}
        />
      )}

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Workspace Top Navigation Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center space-x-3">
                <h1 className="text-xl font-bold text-white">{project?.name || 'Compliance Check'}</h1>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                  {projectId.slice(0, 8)}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Created {new Date(project?.created_at).toLocaleString()}
              </p>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setShowFrameworkModal(true)}
              className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-800 hover:bg-slate-700 text-brand-300 border border-slate-700 transition-all flex items-center space-x-2"
              title="Manage & Import Custom Compliance Frameworks"
            >
              <Layers className="w-3.5 h-3.5 text-brand-400" />
              <span>Frameworks</span>
            </button>

            {canManage && (
              <button
                onClick={() => setShowMembersModal(true)}
                className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all flex items-center space-x-2"
              >
                <span>👥</span>
                <span>Members</span>
              </button>
            )}

            {!isReady && canUpload && (
              <button
                onClick={() => setShowUploadModal(true)}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/20 transition-all flex items-center space-x-2"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Missing Evidence</span>
              </button>
            )}

            {isReady && (
              <div className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold">
                <Award className="w-4 h-4" />
                <span>PACKAGE READY TO SUBMIT</span>
              </div>
            )}
          </div>
        </div>



        {/* ERROR BANNER */}
        {(errorBanner || errorMessage || agentStatus === 'error') && (
          <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/60 flex items-center justify-between animate-fade-in text-xs">
            <div className="flex items-center space-x-3 text-red-300">
              <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
              <div>
                <h4 className="font-bold text-red-200">Execution / Action Error</h4>
                <p>{errorBanner || errorMessage || 'Agent execution encountered an issue. You can retry or inspect the live logs below.'}</p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => handleTriggerVerification()}
                className="px-3 py-1.5 rounded-lg bg-red-800 hover:bg-red-700 text-white font-semibold text-xs"
              >
                Retry
              </button>
              <button
                onClick={() => setErrorBanner(null)}
                className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Tab Selection */}
        <div className="flex items-center space-x-2 border-b border-slate-800/80 pb-2">
          <button
            onClick={() => setActiveTab('activity')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'activity'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            Agent Workspace & Live Logs
          </button>

          <button
            onClick={() => setActiveTab('results')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'results'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            Compliance Results ({Math.round(score)}%)
          </button>

          <button
            onClick={() => setActiveTab('remediation')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
              activeTab === 'remediation'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            Remediation Plan ({tasks.length})
          </button>

          <button
            onClick={() => setActiveTab('history')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all flex items-center space-x-1.5 ${
              activeTab === 'history'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>Verification History & Deltas</span>
          </button>

          <button
            onClick={() => setActiveTab('documents')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all flex items-center space-x-1.5 ${
              activeTab === 'documents'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>Document & Evidence Library</span>
          </button>

          <button
            onClick={() => setActiveTab('audit')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all flex items-center space-x-1.5 ${
              activeTab === 'audit'
                ? 'bg-brand-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Audit Activity Log</span>
          </button>
        </div>

        {/* TAB 1: AGENT ACTIVITY WORKSPACE */}
        {activeTab === 'activity' && (
          <div className="space-y-6">
            <AgentActivity
              events={events}
              isLive={isLive}
              currentTool={currentTool}
              agentStatus={agentStatus}
            />

            {/* Quick jump to results if completed */}
            {agentStatus === 'completed' && (
              <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-900/50 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <div>
                    <h4 className="text-sm font-semibold text-white">Agent Execution Completed</h4>
                    <p className="text-xs text-slate-300">Full analysis result: {score}% — {overallStatus}</p>
                  </div>
                </div>
                <button
                  onClick={() => setActiveTab('results')}
                  className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-500"
                >
                  View Results
                </button>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: COMPLIANCE RESULTS */}
        {activeTab === 'results' && (
          <div className="space-y-6">
            <ComplianceScore
              score={score}
              overallStatus={overallStatus}
              satisfiedCount={satisfiedCount}
              totalCount={requirements.length || 12}
              missingCount={missingCount}
              conflictCount={conflictCount}
              aiScore={results?.ai_compliance_score}
              adjustedScore={results?.auditor_adjusted_score}
              hasOverrides={results?.has_auditor_overrides}
            />

            <RequirementsList 
              matches={matches} 
              requirements={requirements} 
              overrides={results?.auditor_overrides || []}
              projectId={projectId} 
              onOverrideUpdated={loadProjectData}
            />
          </div>
        )}

        {/* TAB 3: REMEDIATION PLAN */}
        {activeTab === 'remediation' && (
          <div className="space-y-6">
            <RemediationList
              tasks={tasks}
              projectId={projectId}
              requirements={results?.requirements || []}
            />
          </div>
        )}


        {/* TAB 4: VERIFICATION HISTORY & DELTAS */}
        {activeTab === 'history' && (
          <div className="space-y-6">
            <VerificationHistory projectId={projectId} />
          </div>
        )}

        {/* TAB 5: DOCUMENT & EVIDENCE LIBRARY */}
        {activeTab === 'documents' && (
          <div className="space-y-6">
            <DocumentViewer projectId={projectId} />
          </div>
        )}

        {/* TAB 6: AUDIT ACTIVITY LOG */}
        {activeTab === 'audit' && (
          <div className="space-y-6">
            <AuditTimeline
              projectId={projectId}
              onNavigateTab={setActiveTab}
            />
          </div>
        )}


        {/* REMEDIATION UPLOAD MODAL */}
        {showUploadModal && (
          <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full space-y-6 shadow-2xl animate-fade-in">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div className="flex items-center space-x-2">
                  <Upload className="w-5 h-5 text-brand-400" />
                  <h3 className="text-lg font-bold text-white">Upload Remediation Evidence</h3>
                </div>
                <button
                  onClick={() => setShowUploadModal(false)}
                  className="text-slate-400 hover:text-white text-sm"
                >
                  ✕
                </button>
              </div>

              {/* 1-Click Demo Remediation Banner */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-brand-950/50 to-purple-950/30 border border-brand-500/30 space-y-3">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-brand-400" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-brand-300">NovaTech Demo 1-Click Fix</h4>
                </div>
                <p className="text-xs text-slate-300">
                  Instantly upload the missing Insurance Cert + signed DPA + corrected Company Profile to trigger re-verification.
                </p>
                <button
                  onClick={handleLoadDemoRemediation}
                  disabled={uploadingRemediation || verifying}
                  className="w-full py-2.5 rounded-lg text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-md transition-all flex items-center justify-center space-x-2 disabled:opacity-50"
                >
                  {uploadingRemediation || verifying ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <span>Auto-Upload Demo Fix & Re-Verify (100% READY)</span>
                  )}
                </button>
              </div>

              {/* Custom File Upload */}
              <form onSubmit={handleCustomUploadRemediation} className="space-y-4">
                <div>
                  <label className="block text-xs font-mono uppercase text-slate-300 font-semibold mb-2">
                    Select Corrected Documents
                  </label>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.txt,.docx"
                    onChange={(e) => setRemediationFiles(Array.from(e.target.files))}
                    className="w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
                  />
                </div>

                <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowUploadModal(false)}
                    className="px-4 py-2 rounded-lg text-xs font-semibold text-slate-400 hover:bg-slate-800"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={remediationFiles.length === 0 || uploadingRemediation}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white disabled:opacity-50 flex items-center space-x-2"
                  >
                    {uploadingRemediation ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <span>Upload & Run Verification</span>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// Inline fallback demo text blobs for 1-click remediation demo
const DEMO_REMEDIATION_INSURANCE = `CERTIFICATE OF LIABILITY INSURANCE
Certificate Number: CLI-2025-NTS-00441
INSURED: NovaTech Solutions Ltd., 42 Innovation Drive, Suite 800, Tech City, TC 10001
ADDITIONAL INSURED: NovaTech Solutions Ltd. named as additional insured.
COVERAGE: General Liability USD 2,000,000 per occurrence.
Expiration: December 31, 2025
Status: CURRENT & IN FORCE`;

const DEMO_REMEDIATION_DPA = `DATA PROCESSING AGREEMENT
Reference: DPA-NTS-NOVA-2025-001
DATA CONTROLLER: NovaTech Solutions Ltd., 42 Innovation Drive, Suite 800, Tech City, TC 10001
Governs processing of personal data in compliance with GDPR.
Signed by: Alexandra Chen, CEO
Date: February 1, 2025`;

const DEMO_REMEDIATION_PROFILE = `COMPANY PROFILE — CORRECTED VERSION
Company Name: NovaTech Solutions Ltd.
REGISTERED OFFICE ADDRESS: 42 Innovation Drive, Suite 800, Tech City, TC 10001
(Corrected address matches Suite 800 across all documents).
CLIENT REFERENCES (3 confirmed):
1. Meridian Financial Group (Sarah Thompson)
2. Atlas Healthcare Networks (Dr. Mark Osei)
3. Pinnacle Retail Corp (Lisa Harrington)`;
