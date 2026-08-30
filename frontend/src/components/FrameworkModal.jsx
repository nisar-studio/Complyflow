import React, { useState, useEffect } from 'react';
import { 
  BookOpen, Upload, CheckCircle2, AlertTriangle, AlertCircle, X, 
  Layers, FileText, Check, Trash2, ArrowRight, ShieldCheck, RefreshCw, Eye
} from 'lucide-react';
import api from '../api/client';

export default function FrameworkModal({ projectId, isOpen, onClose, onFrameworkApplied }) {
  const [frameworks, setFrameworks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('list'); // 'list' | 'import' | 'detail'
  
  // Selected framework detail
  const [selectedFramework, setSelectedFramework] = useState(null);
  const [frameworkReqs, setFrameworkReqs] = useState([]);
  const [loadingReqs, setLoadingReqs] = useState(false);

  // Import State
  const [importFile, setImportFile] = useState(null);
  const [customName, setCustomName] = useState('');
  const [customVersion, setCustomVersion] = useState('');
  const [previewData, setPreviewData] = useState(null);
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importSuccess, setImportSuccess] = useState(false);

  // Action status / banner
  const [actionMessage, setActionMessage] = useState(null);
  const [actionError, setActionError] = useState(null);

  const loadFrameworks = async () => {
    try {
      setLoading(true);
      const list = await api.listFrameworks(projectId);
      setFrameworks(list || []);
    } catch (err) {
      console.error('Failed to load frameworks:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadFrameworks();
      setActiveTab('list');
      setPreviewData(null);
      setValidationError(null);
      setActionMessage(null);
      setActionError(null);
    }
  }, [isOpen, projectId]);

  // Handle File Selection & Pre-validation Preview
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportFile(file);
      setPreviewData(null);
      setValidationError(null);
    }
  };

  const handleValidatePreview = async (e) => {
    e.preventDefault();
    if (!importFile) return;

    try {
      setValidating(true);
      setValidationError(null);
      const res = await api.previewFramework(
        projectId,
        importFile,
        customName.trim() || undefined,
        customVersion.trim() || undefined,
      );
      setPreviewData(res);
    } catch (err) {
      console.error('Validation failed:', err);
      const errData = err.response?.data;
      if (errData?.error === 'FRAMEWORK_IMPORT_INVALID') {
        setValidationError({
          message: errData.message,
          details: errData.details || [],
        });
      } else {
        setValidationError({
          message: errData?.detail || err.message || 'Validation failed',
          details: [],
        });
      }
    } finally {
      setValidating(false);
    }
  };

  // Confirm Import
  const handleConfirmImport = async () => {
    if (!previewData) return;

    try {
      setImporting(true);
      setActionError(null);
      await api.importFramework(projectId, {
        framework: previewData.framework,
        requirements: previewData.requirements,
      });

      setImportSuccess(true);
      await loadFrameworks();
      setTimeout(() => {
        setImportSuccess(false);
        setActiveTab('list');
        setPreviewData(null);
        setImportFile(null);
      }, 1000);
    } catch (err) {
      console.error('Failed to import framework:', err);
      setActionError(err.response?.data?.detail || err.message || 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  // View Framework Detail
  const handleViewDetail = async (fw) => {
    setSelectedFramework(fw);
    setActiveTab('detail');
    try {
      setLoadingReqs(true);
      const reqs = await api.getFrameworkRequirements(projectId, fw.framework_id);
      setFrameworkReqs(reqs || []);
    } catch (err) {
      console.error('Failed to load framework requirements:', err);
    } finally {
      setLoadingReqs(false);
    }
  };

  // Apply Framework to Project
  const handleApplyFramework = async (fw) => {
    if (!window.confirm(`Apply framework '${fw.name}' v${fw.version} (${fw.requirement_count} requirements) to this project? This will set the active project requirements.`)) {
      return;
    }

    try {
      setActionError(null);
      await api.applyFramework(projectId, fw.framework_id);
      setActionMessage(`Framework '${fw.name}' v${fw.version} successfully applied to project workspace.`);
      if (onFrameworkApplied) onFrameworkApplied();
      setTimeout(() => setActionMessage(null), 3000);
    } catch (err) {
      console.error('Failed to apply framework:', err);
      setActionError(err.response?.data?.detail || err.message || 'Failed to apply framework');
    }
  };

  // Delete Framework
  const handleDeleteFramework = async (fw, e) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete framework '${fw.name}' v${fw.version}?`)) {
      return;
    }

    try {
      setActionError(null);
      await api.deleteFramework(projectId, fw.framework_id);
      await loadFrameworks();
      if (activeTab === 'detail') setActiveTab('list');
    } catch (err) {
      console.error('Failed to delete framework:', err);
      setActionError(err.response?.data?.detail || err.message || 'Failed to delete framework');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-fade-in">
        {/* MODAL HEADER */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-2.5">
            <BookOpen className="w-5 h-5 text-brand-400" />
            <div>
              <h3 className="text-base font-bold text-white">Compliance Framework Catalog</h3>
              <p className="text-xs text-slate-400">
                Import and manage versioned standards (JSON, CSV, XLSX) for compliance verification
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* NAVIGATION TABS */}
        <div className="px-6 pt-3 border-b border-slate-800 bg-slate-950/30 flex items-center space-x-4 text-xs font-mono">
          <button
            onClick={() => setActiveTab('list')}
            className={`pb-2.5 font-bold transition-all border-b-2 ${
              activeTab === 'list'
                ? 'border-brand-500 text-brand-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Available Frameworks ({frameworks.length})
          </button>
          <button
            onClick={() => {
              setActiveTab('import');
              setPreviewData(null);
              setValidationError(null);
            }}
            className={`pb-2.5 font-bold transition-all border-b-2 flex items-center space-x-1.5 ${
              activeTab === 'import'
                ? 'border-brand-500 text-brand-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Import Custom Framework</span>
          </button>
          {activeTab === 'detail' && selectedFramework && (
            <button
              className="pb-2.5 font-bold border-b-2 border-brand-500 text-brand-400"
            >
              {selectedFramework.name} v{selectedFramework.version}
            </button>
          )}
        </div>

        {/* ACTION FEEDBACK BANNERS */}
        {actionMessage && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs font-mono flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{actionMessage}</span>
          </div>
        )}

        {actionError && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-red-950/40 border border-red-800 text-red-300 text-xs font-mono flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* MODAL BODY */}
        <div className="flex-1 overflow-y-auto p-6 text-xs">
          {/* TAB 1: FRAMEWORKS LIST */}
          {activeTab === 'list' && (
            <div className="space-y-4">
              {loading ? (
                <div className="p-8 text-center text-slate-400 font-mono">
                  Loading compliance frameworks...
                </div>
              ) : frameworks.length === 0 ? (
                <div className="p-10 text-center bg-slate-950/50 border border-slate-800 rounded-xl space-y-3">
                  <Layers className="w-8 h-8 text-slate-600 mx-auto" />
                  <h4 className="text-sm font-bold text-white">No Custom Frameworks Imported</h4>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    Import custom standards or internal control frameworks using JSON, CSV, or Excel spreadsheets.
                  </p>
                  <button
                    onClick={() => setActiveTab('import')}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-lg"
                  >
                    Import First Framework
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {frameworks.map((fw) => (
                    <div
                      key={fw.framework_id}
                      onClick={() => handleViewDetail(fw)}
                      className="p-4 bg-slate-950/60 border border-slate-800 hover:border-slate-700 rounded-xl space-y-3 cursor-pointer transition-all hover:bg-slate-950"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center space-x-2">
                            <h4 className="text-sm font-bold text-white">{fw.name}</h4>
                            <span className="px-2 py-0.2 rounded bg-brand-950 text-brand-400 border border-brand-800 font-mono text-[10px] font-bold">
                              v{fw.version}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                            {fw.description || 'Custom imported compliance framework'}
                          </p>
                        </div>

                        <span className={`px-2 py-0.5 rounded font-mono text-[10px] font-bold uppercase ${
                          fw.status === 'ACTIVE'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}>
                          {fw.status}
                        </span>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 font-mono text-[11px] text-slate-400">
                        <span>{fw.requirement_count} Requirements</span>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApplyFramework(fw);
                            }}
                            className="px-2.5 py-1 bg-brand-600/80 hover:bg-brand-500 text-white rounded font-bold text-[10px]"
                          >
                            Apply to Project
                          </button>
                          <button
                            onClick={(e) => handleDeleteFramework(fw, e)}
                            className="p-1 text-slate-500 hover:text-red-400 rounded"
                            title="Delete Framework"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: IMPORT CUSTOM FRAMEWORK (2-STEP PREVIEW -> CONFIRM) */}
          {activeTab === 'import' && (
            <div className="space-y-6 max-w-2xl mx-auto">
              {!previewData ? (
                <form onSubmit={handleValidatePreview} className="space-y-4">
                  <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-xl space-y-3">
                    <span className="font-mono font-bold text-slate-300 block uppercase tracking-wider">
                      1. Select Framework Spreadsheet or JSON File:
                    </span>
                    <input
                      type="file"
                      accept=".json,.csv,.xlsx,.xlsm"
                      onChange={handleFileChange}
                      className="w-full text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-brand-600 file:text-white hover:file:bg-brand-500 cursor-pointer font-mono"
                    />
                    <div className="text-[11px] font-mono text-slate-500">
                      Supported extensions: <b>.json</b>, <b>.csv</b>, <b>.xlsx</b> (Max 10MB)
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 font-mono">
                    <div className="space-y-1">
                      <label className="text-slate-400 text-[11px] block">Optional Name Override:</label>
                      <input
                        type="text"
                        placeholder="e.g. Custom SOC 2 Matrix"
                        value={customName}
                        onChange={(e) => setCustomName(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded text-white text-xs focus:outline-none focus:border-brand-500"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-slate-400 text-[11px] block">Optional Version:</label>
                      <input
                        type="text"
                        placeholder="e.g. 1.0"
                        value={customVersion}
                        onChange={(e) => setCustomVersion(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded text-white text-xs focus:outline-none focus:border-brand-500"
                      />
                    </div>
                  </div>

                  {validationError && (
                    <div className="p-4 bg-red-950/40 border border-red-800 rounded-xl space-y-2 text-red-300 font-mono text-xs">
                      <div className="font-bold flex items-center space-x-1.5">
                        <AlertCircle className="w-4 h-4 text-red-400" />
                        <span>{validationError.message}</span>
                      </div>
                      {validationError.details?.length > 0 && (
                        <div className="max-h-32 overflow-y-auto space-y-1 pt-1 border-t border-red-900/40 text-[11px]">
                          {validationError.details.map((d, i) => (
                            <div key={i} className="text-red-200">
                              • Row {d.row} [{d.field}]: {d.message}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={!importFile || validating}
                    className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-xl flex items-center justify-center space-x-2 font-mono"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    <span>{validating ? 'Parsing & Pre-validating...' : 'Validate & Preview Framework'}</span>
                  </button>
                </form>
              ) : (
                /* STEP 2: PREVIEW & EXPLICIT CONFIRMATION */
                <div className="space-y-5 animate-fade-in font-mono">
                  <div className="p-4 bg-slate-950/80 border border-brand-500/50 rounded-xl space-y-3">
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                      <div>
                        <h4 className="text-sm font-bold text-white">{previewData.framework.name}</h4>
                        <span className="text-brand-400 text-xs">Version: {previewData.framework.version}</span>
                      </div>
                      <span className="px-2.5 py-1 rounded bg-brand-950 text-brand-300 border border-brand-800 text-xs font-bold">
                        {previewData.requirement_count} Requirements
                      </span>
                    </div>

                    <p className="text-slate-300 text-xs">
                      {previewData.framework.description}
                    </p>

                    {/* Breakdown Pills */}
                    <div className="grid grid-cols-2 gap-3 pt-2">
                      <div className="p-2.5 bg-slate-900 rounded border border-slate-800 space-y-1">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Severity Breakdown:</span>
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(previewData.severity_breakdown || {}).map(([sev, count]) => (
                            <span key={sev} className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-200">
                              {sev}: {count}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div className="p-2.5 bg-slate-900 rounded border border-slate-800 space-y-1">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Categories:</span>
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(previewData.category_breakdown || {}).map(([cat, count]) => (
                            <span key={cat} className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-brand-300">
                              {cat} ({count})
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Sample Requirements Table */}
                  <div className="space-y-2">
                    <span className="text-slate-400 text-xs font-bold uppercase block">
                      Sample Requirements (First 5):
                    </span>
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {previewData.sample_requirements?.map((req, i) => (
                        <div key={i} className="p-2.5 bg-slate-950/60 border border-slate-800 rounded text-[11px] space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-brand-400 font-bold">{req.requirement_id}</span>
                            <span className="text-slate-400">{req.category} · {req.severity}</span>
                          </div>
                          <div className="text-white font-semibold">{req.title}</div>
                          <div className="text-slate-400 line-clamp-1">{req.description}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Confirmation Actions */}
                  <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
                    <button
                      onClick={() => setPreviewData(null)}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold"
                    >
                      Back to Upload
                    </button>
                    <button
                      onClick={handleConfirmImport}
                      disabled={importing || importSuccess}
                      className="px-5 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-xs font-bold flex items-center space-x-1.5 shadow-lg shadow-brand-600/30"
                    >
                      <Check className="w-4 h-4" />
                      <span>{importing ? 'Importing...' : importSuccess ? 'Imported!' : 'Confirm & Persist Framework'}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: FRAMEWORK DETAIL & REQUIREMENTS LIST */}
          {activeTab === 'detail' && selectedFramework && (
            <div className="space-y-5 font-mono">
              <div className="flex items-start justify-between pb-3 border-b border-slate-800">
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="text-base font-bold text-white">{selectedFramework.name}</h3>
                    <span className="px-2 py-0.5 rounded bg-brand-950 text-brand-400 border border-brand-800 font-mono text-xs font-bold">
                      v{selectedFramework.version}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{selectedFramework.description}</p>
                </div>
                <button
                  onClick={() => handleApplyFramework(selectedFramework)}
                  className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-lg text-xs flex items-center space-x-1.5"
                >
                  <span>Apply to Workspace</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>

              {loadingReqs ? (
                <div className="p-8 text-center text-slate-400">Loading requirements...</div>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {frameworkReqs.map((req) => (
                    <div key={req.requirement_id} className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl space-y-1.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-brand-400">{req.requirement_id}</span>
                        <span className="text-[10px] text-slate-400">{req.category} · {req.severity}</span>
                      </div>
                      <div className="text-sm font-semibold text-white">{req.title}</div>
                      <p className="text-slate-300 text-[11px] leading-relaxed font-sans">{req.description}</p>
                      {req.guidance && (
                        <div className="text-[10px] text-slate-400 bg-slate-900/60 p-1.5 rounded">
                          <b>Required Evidence:</b> {req.guidance}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
