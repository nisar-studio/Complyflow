import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileText, Sparkles, ArrowRight, Loader2, CheckCircle2, ShieldCheck } from 'lucide-react';
import Navbar from '../components/Navbar';
import api from '../api/client';

export default function NewProject() {
  const navigate = useNavigate();
  const [projectName, setProjectName] = useState('NovaTech Vendor Certification');
  const [reqFile, setReqFile] = useState(null);
  const [evidenceFiles, setEvidenceFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // 1-Click Load NovaTech Demo Dataset
  const handleLoadDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Create project
      const proj = await api.createProject('NovaTech Vendor Certification');
      const projectId = proj.project_id;

      // Fetch sample text files from demo folder (we will provide demo files via API or fetch)
      // Since demo files are in demo/novatech directory on backend, we can load them or upload sample text blobs
      const reqBlob = new Blob([DEMO_REQ_TEXT], { type: 'text/plain' });
      const reqDocFile = new File([reqBlob], 'requirements.txt');

      const evidenceBlobs = DEMO_EVIDENCE_FILES.map(f => {
        return new File([new Blob([f.content], { type: 'text/plain' })], f.name);
      });

      // 2. Upload documents
      await api.uploadDocuments(projectId, reqDocFile, evidenceBlobs);

      // 3. Start ADK agent analysis
      await api.startAnalysis(projectId);

      // Navigate to project workspace
      navigate(`/projects/${projectId}`);
    } catch (err) {
      console.error('Failed to load demo:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to start demo project');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!projectName.trim()) {
      setError('Please enter a project name');
      return;
    }
    if (!reqFile) {
      setError('Please select a requirements document');
      return;
    }
    if (evidenceFiles.length === 0) {
      setError('Please select at least one supporting evidence document');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // 1. Create project
      const proj = await api.createProject(projectName);
      const projectId = proj.project_id;

      // 2. Upload documents
      await api.uploadDocuments(projectId, reqFile, evidenceFiles);

      // 3. Start ADK agent analysis
      await api.startAnalysis(projectId);

      // Navigate to project workspace
      navigate(`/projects/${projectId}`);
    } catch (err) {
      console.error('Failed to submit compliance check:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to start compliance check');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="space-y-8">
          <div>
            <span className="text-xs font-mono text-brand-400 uppercase tracking-wider">New Compliance Analysis</span>
            <h1 className="text-3xl font-bold text-white mt-1">Create Compliance Check</h1>
            <p className="text-sm text-slate-400 mt-1">Upload requirements document and supporting evidence files for autonomous AI agent analysis</p>
          </div>

          {/* Quick Hackathon Demo Banner */}
          <div className="p-6 rounded-2xl bg-gradient-to-r from-brand-950/40 via-indigo-950/30 to-slate-900 border border-brand-500/30 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-xl">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-5 h-5 text-brand-400" />
                <h3 className="text-base font-bold text-white">Live Demo Dataset: NovaTech Certification</h3>
              </div>
              <p className="text-xs text-slate-300">
                Instantly load 12 requirements & 8 supporting documents. Pre-configured to demonstrate 75% ACTION REQUIRED → 100% READY transformation.
              </p>
            </div>

            <button
              onClick={handleLoadDemo}
              disabled={loading}
              className="w-full sm:w-auto px-5 py-3 rounded-xl text-xs font-bold bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white shadow-lg shadow-brand-600/30 shrink-0 transition-all hover:scale-105 flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <span>Load NovaTech Demo (1-Click)</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Custom Upload Form */}
          <form onSubmit={handleSubmit} className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 space-y-6 backdrop-blur-xl">
            <div>
              <label className="block text-xs font-mono uppercase text-slate-300 font-semibold mb-2">
                Project Name
              </label>
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="e.g. Vendor Certification Application"
                className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-brand-500 transition-colors"
                required
              />
            </div>

            {/* Requirements PDF Upload */}
            <div>
              <label className="block text-xs font-mono uppercase text-slate-300 font-semibold mb-2">
                1. Requirements Document (PDF, TXT, DOCX)
              </label>
              <div className="relative border-2 border-dashed border-slate-800 hover:border-brand-500/50 rounded-xl p-6 text-center transition-colors bg-slate-950/40">
                <input
                  type="file"
                  accept=".pdf,.txt,.docx"
                  onChange={(e) => setReqFile(e.target.files[0])}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
                {reqFile ? (
                  <div className="flex items-center justify-center space-x-2 text-emerald-400">
                    <FileText className="w-5 h-5" />
                    <span className="text-sm font-medium">{reqFile.name}</span>
                    <span className="text-xs text-slate-500">({Math.round(reqFile.size / 1024)} KB)</span>
                  </div>
                ) : (
                  <div>
                    <Upload className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                    <p className="text-sm font-medium text-slate-300">Drop requirements document here or click to browse</p>
                    <p className="text-xs text-slate-500 mt-1">Supports PDF, TXT, DOCX checklist documents</p>
                  </div>
                )}
              </div>
            </div>

            {/* Evidence Files Upload */}
            <div>
              <label className="block text-xs font-mono uppercase text-slate-300 font-semibold mb-2">
                2. Supporting Evidence Documents (Multiple)
              </label>
              <div className="relative border-2 border-dashed border-slate-800 hover:border-brand-500/50 rounded-xl p-6 text-center transition-colors bg-slate-950/40">
                <input
                  type="file"
                  multiple
                  accept=".pdf,.txt,.docx"
                  onChange={(e) => setEvidenceFiles(Array.from(e.target.files))}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
                {evidenceFiles.length > 0 ? (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-emerald-400">
                      {evidenceFiles.length} evidence file(s) selected
                    </p>
                    <p className="text-xs text-slate-400">
                      {evidenceFiles.map(f => f.name).join(', ')}
                    </p>
                  </div>
                ) : (
                  <div>
                    <Upload className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                    <p className="text-sm font-medium text-slate-300">Drop supporting certificates, policies, and forms here</p>
                    <p className="text-xs text-slate-500 mt-1">Select multiple files (PDF, TXT, DOCX)</p>
                  </div>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 rounded-xl text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-xl shadow-brand-600/30 transition-all hover:scale-[1.01] active:scale-[0.99] flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Launching ADK Agent...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-5 h-5" />
                  <span>Start AI Compliance Check</span>
                </>
              )}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

// Inline fallback demo text generator for instant frontend demo loading
const DEMO_REQ_TEXT = `NovaTech Solutions Ltd. — Vendor Certification Requirements

REQ-001: Business Registration Certificate
Vendors must provide a valid business registration certificate issued by government authority.
Required evidence: Official business registration certificate (PDF/TXT)
Priority: HIGH

REQ-002: Tax Compliance Certificate
Vendors must provide a tax compliance certificate issued by tax authority dated within last 12 months.
Required evidence: Tax compliance certificate
Priority: HIGH

REQ-003: Company Address Confirmation
The vendor's registered company address as stated in ALL submitted documents must be consistent.
Required evidence: Consistent address across all submitted documents
Priority: MEDIUM

REQ-004: Financial Statement
Vendors must provide audited financial statements for the most recent fiscal year signed by auditor.
Required evidence: Audited financial statement
Priority: HIGH

REQ-005: Bank Reference Letter
Vendors must provide a bank reference letter confirming account in good standing.
Required evidence: Bank reference letter
Priority: MEDIUM

REQ-006: General Liability Insurance Certificate
Vendors must carry general liability insurance min USD 2,000,000 naming NovaTech as additional insured.
Required evidence: Current insurance certificate
Priority: CRITICAL

REQ-007: Data Processing Agreement
Vendors must execute a signed Data Processing Agreement (DPA).
Required evidence: Signed Data Processing Agreement
Priority: CRITICAL

REQ-008: Quality Management Manual
Vendors must provide evidence of a documented quality management process.
Required evidence: Quality manual or QA policy
Priority: MEDIUM

REQ-009: Organizational Chart
Vendors must provide an organizational chart showing reporting structure and NovaTech contact.
Required evidence: Organizational chart
Priority: LOW

REQ-010: Technical Specifications Document
Vendors must provide technical specifications describing service offering and SLA.
Required evidence: Technical specifications document
Priority: MEDIUM

REQ-011: Client Reference List
Vendors must provide a list of at least 3 client references.
Required evidence: Client reference list
Priority: LOW

REQ-012: Company Profile
Vendors must provide a company profile matching the registered address.
Required evidence: Company profile document
Priority: LOW`;

const DEMO_EVIDENCE_FILES = [
  { name: '01_business_registration.txt', content: 'CERTIFICATE OF BUSINESS REGISTRATION\nLegal Business Name: NovaTech Solutions Ltd.\nRegistration: NTS-2024-047821\nRegistered Address: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nStatus: ACTIVE' },
  { name: '02_tax_certificate.txt', content: 'CERTIFICATE OF TAX COMPLIANCE\nTaxpayer Name: NovaTech Solutions Ltd.\nRegistered Address: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nStatus: COMPLIANT\nIssue Date: February 1, 2025' },
  { name: '03_financial_statement.txt', content: 'AUDITED FINANCIAL STATEMENT FY2024\nCompany: NovaTech Solutions Ltd.\nAddress: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nAuditor: Thornton & Associates CPA\nOpinion: Unqualified / Clean' },
  { name: '04_bank_reference.txt', content: 'BANK REFERENCE LETTER\nBank: Citywide Commercial Bank\nAccount Holder: NovaTech Solutions Ltd.\nAddress: 42 Innovation Drive, Suite 800, Tech City, TC 10001\nStatus: GOOD STANDING' },
  { name: '05_quality_manual.txt', content: 'QUALITY MANAGEMENT MANUAL QM-2025-001\nCompany: NovaTech Solutions Ltd.\nISO 9001:2015 Compliant QMS System\nApproved by COO' },
  { name: '06_org_chart.txt', content: 'ORGANIZATIONAL CHART\nNovaTech Solutions Ltd.\nCEO: Alexandra Chen\nCTO: Dr. Priya Sharma\nNovaTech Contact: David Okafor (d.okafor@novatech.example.com)' },
  { name: '07_technical_specs.txt', content: 'TECHNICAL SPECIFICATIONS DOCUMENT\nServices: Cloud Infrastructure Management, Software Dev, Cybersecurity\nSLA: 99.9% Uptime\nISO 27001 Certified' },
  { name: '08_company_profile.txt', content: 'COMPANY PROFILE\nCompany Name: NovaTech Solutions Ltd.\nREGISTERED OFFICE ADDRESS: 42 Innovation Drive, Suite 400, Tech City, TC 10001\nNote: Suite 400 address creates the intentional conflict against Suite 800.' },
];
