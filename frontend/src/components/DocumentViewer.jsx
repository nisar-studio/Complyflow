import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  FileText, Search, AlertTriangle, CheckCircle2, ChevronRight, 
  ExternalLink, Layers, Eye, Download, ShieldCheck, X, Sparkles, BookOpen,
  Trash2, Filter, CheckSquare, Square, MinusSquare, Check, RefreshCw
} from 'lucide-react';
import api from '../api/client';

export default function DocumentViewer({ 
  projectId, 
  initialDocName = null, 
  highlightQuote = null, 
  highlightPage = null,
  onClose = null,
  isModal = false,
}) {
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [activeDoc, setActiveDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activePage, setActivePage] = useState(1);
  const chunkRefs = useRef({});

  // Document Library Filtering & Search
  const [docSearchQuery, setDocSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('ALL'); // ALL | requirements | evidence
  const [typeFilter, setTypeFilter] = useState('ALL'); // ALL | .pdf | .docx | .txt
  const [ocrOnly, setOcrOnly] = useState(false);

  // Multi-Selection State for Bulk Deletion
  const [selectedDocIds, setSelectedDocIds] = useState(new Set());
  const [deletingDocs, setDeletingDocs] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Version state
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [loadingVersions, setLoadingVersions] = useState(false);

  // Load document library
  const loadLibrary = async () => {
    try {
      setLoading(true);
      const docs = await api.getDocuments(projectId);
      setDocuments(docs || []);

      if (docs && docs.length > 0) {
        let target = docs[0];
        if (initialDocName) {
          const found = docs.find(d => d.name === initialDocName || d.doc_id === initialDocName);
          if (found) target = found;
        }
        setSelectedDocId(target.doc_id || target.name);
      } else {
        setSelectedDocId(null);
        setActiveDoc(null);
      }
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLibrary();
  }, [projectId, initialDocName]);

  // Load detailed document with chunks when selection changes
  useEffect(() => {
    if (!selectedDocId) {
      setActiveDoc(null);
      setVersions([]);
      setSelectedVersion(null);
      return;
    }

    async function loadDocDetail() {
      try {
        setLoadingDoc(true);
        const detail = await api.getDocument(projectId, selectedDocId);
        setActiveDoc(detail);
        if (highlightPage) {
          setActivePage(highlightPage);
        } else {
          setActivePage(1);
        }
        // Load version history
        try {
          setLoadingVersions(true);
          const vers = await api.getDocumentVersions(projectId, selectedDocId);
          setVersions(vers || []);
          if (vers && vers.length > 0) {
            setSelectedVersion(vers[vers.length - 1]); // Latest version
          }
        } catch {
          setVersions([]);
        } finally {
          setLoadingVersions(false);
        }
      } catch (err) {
        console.error('Failed to load document detail:', err);
      } finally {
        setLoadingDoc(false);
      }
    }
    loadDocDetail();
  }, [projectId, selectedDocId, highlightPage]);

  // Auto-scroll to highlighted quote if present
  useEffect(() => {
    if (!activeDoc || !highlightQuote) return;
    const targetChunk = activeDoc.chunks?.find(c => 
      c.text.toLowerCase().includes(highlightQuote.toLowerCase().slice(0, 30))
    );
    if (targetChunk && chunkRefs.current[targetChunk.chunk_id]) {
      chunkRefs.current[targetChunk.chunk_id].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeDoc, highlightQuote]);

  // Filtered Documents in Sidebar
  const filteredDocs = useMemo(() => {
    return documents.filter(doc => {
      const name = (doc.name || '').toLowerCase();
      if (docSearchQuery.trim() && !name.includes(docSearchQuery.toLowerCase().trim())) {
        return false;
      }
      if (roleFilter !== 'ALL' && doc.role !== roleFilter) {
        return false;
      }
      if (typeFilter !== 'ALL' && doc.file_type !== typeFilter && !name.endsWith(typeFilter)) {
        return false;
      }
      if (ocrOnly && doc.status !== 'OCR_REQUIRED') {
        return false;
      }
      return true;
    });
  }, [documents, docSearchQuery, roleFilter, typeFilter, ocrOnly]);

  // Document Counts
  const docCounts = useMemo(() => {
    return {
      total: documents.length,
      requirements: documents.filter(d => d.role === 'requirements').length,
      evidence: documents.filter(d => d.role === 'evidence').length,
      ocr: documents.filter(d => d.status === 'OCR_REQUIRED').length,
    };
  }, [documents]);

  // Multi-Selection Handlers
  const handleToggleSelect = (docId, e) => {
    e.stopPropagation();
    setSelectedDocIds(prev => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const handleSelectAllVisible = () => {
    const visibleIds = filteredDocs.map(d => d.doc_id || d.name);
    setSelectedDocIds(new Set(visibleIds));
  };

  const handleClearSelection = () => {
    setSelectedDocIds(new Set());
  };

  const isAllVisibleSelected = filteredDocs.length > 0 && filteredDocs.every(d => selectedDocIds.has(d.doc_id || d.name));
  const isSomeVisibleSelected = filteredDocs.some(d => selectedDocIds.has(d.doc_id || d.name)) && !isAllVisibleSelected;

  // Bulk Delete Documents
  const handleBulkDelete = async () => {
    const ids = Array.from(selectedDocIds);
    if (ids.length === 0) return;

    if (!window.confirm(`Are you sure you want to permanently delete ${ids.length} document(s)? This will remove physical files and document records.`)) {
      return;
    }

    try {
      setDeletingDocs(true);
      setDeleteError(null);
      await api.bulkDeleteDocuments(projectId, ids);
      handleClearSelection();
      await loadLibrary();
    } catch (err) {
      console.error('Failed to bulk delete documents:', err);
      setDeleteError(err.response?.data?.detail || err.message || 'Failed to delete documents');
    } finally {
      setDeletingDocs(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400 font-mono text-xs animate-pulse">
        Loading document library and evidence provenance...
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="p-8 text-center bg-slate-900/50 border border-slate-800 rounded-2xl">
        <FileText className="w-8 h-8 text-slate-500 mx-auto mb-2" />
        <h4 className="text-sm font-bold text-white">No Documents Uploaded</h4>
        <p className="text-xs text-slate-400 mt-1">
          Upload requirements and supporting evidence files to inspect provenance and text chunks.
        </p>
      </div>
    );
  }

  // Filter chunks for active page if multi-page
  const filteredChunks = activeDoc?.chunks?.filter(chunk => {
    if (!searchQuery.trim()) {
      if (activeDoc.total_pages > 1 && chunk.page_number) {
        return chunk.page_number === activePage;
      }
      return true;
    }
    return chunk.text.toLowerCase().includes(searchQuery.toLowerCase());
  }) || [];

  return (
    <div className={`space-y-6 ${isModal ? 'max-h-[85vh] flex flex-col' : ''}`}>
      {/* HEADER / MODAL BAR */}
      {isModal && (
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <BookOpen className="w-5 h-5 text-brand-400" />
            <h3 className="text-sm font-bold text-white">Document & Evidence Inspector</h3>
          </div>
          {onClose && (
            <button 
              onClick={onClose}
              className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 text-xs"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      )}

      {/* METRICS & SUMMARY BAR */}
      <div className="flex items-center justify-between flex-wrap gap-2 text-xs font-mono bg-slate-950/60 p-2.5 rounded-xl border border-slate-800">
        <div className="flex items-center space-x-3 text-slate-300">
          <span><b>{docCounts.total}</b> Total Files</span>
          <span>·</span>
          <span className="text-brand-300"><b>{docCounts.evidence}</b> Evidence</span>
          <span>·</span>
          <span className="text-purple-300"><b>{docCounts.requirements}</b> Requirements</span>
          {docCounts.ocr > 0 && (
            <>
              <span>·</span>
              <span className="text-amber-400"><b>{docCounts.ocr}</b> OCR Required</span>
            </>
          )}
        </div>

        {selectedDocIds.size > 0 && (
          <div className="flex items-center space-x-2">
            <span className="text-brand-400 font-bold">{selectedDocIds.size} selected</span>
            <button
              onClick={handleBulkDelete}
              disabled={deletingDocs}
              className="px-2.5 py-1 bg-red-600/80 hover:bg-red-500 text-white rounded font-bold text-[11px] flex items-center space-x-1"
            >
              <Trash2 className="w-3 h-3" />
              <span>{deletingDocs ? 'Deleting...' : 'Delete Selected'}</span>
            </button>
            <button
              onClick={handleClearSelection}
              className="text-slate-400 hover:text-white text-[10px] underline"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {deleteError && (
        <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800 text-red-300 text-xs font-mono">
          {deleteError}
        </div>
      )}

      {/* 2-COLUMN INSPECTOR LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: DOCUMENT LIBRARY LIST (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          {/* Search & Filters */}
          <div className="space-y-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Search file names..."
                value={docSearchQuery}
                onChange={(e) => setDocSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 font-mono"
              />
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 text-slate-300 rounded p-1.5 focus:outline-none focus:border-brand-500"
              >
                <option value="ALL">All Roles</option>
                <option value="evidence">Evidence Files</option>
                <option value="requirements">Requirements</option>
              </select>

              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 text-slate-300 rounded p-1.5 focus:outline-none focus:border-brand-500"
              >
                <option value="ALL">All Formats</option>
                <option value=".pdf">PDF (.pdf)</option>
                <option value=".docx">DOCX (.docx)</option>
                <option value=".txt">TXT (.txt)</option>
              </select>
            </div>

            {/* Select All Checkbox */}
            {filteredDocs.length > 0 && (
              <div className="flex items-center justify-between pt-1 text-[11px] font-mono text-slate-400">
                <button
                  onClick={() => isAllVisibleSelected ? handleClearSelection() : handleSelectAllVisible()}
                  className="flex items-center space-x-1.5 text-slate-300 hover:text-white"
                >
                  {isAllVisibleSelected ? (
                    <CheckSquare className="w-3.5 h-3.5 text-brand-400" />
                  ) : isSomeVisibleSelected ? (
                    <MinusSquare className="w-3.5 h-3.5 text-brand-400" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-slate-500" />
                  )}
                  <span>Select All ({filteredDocs.length})</span>
                </button>
              </div>
            )}
          </div>

          <div className="space-y-2 max-h-[550px] overflow-y-auto pr-1">
            {filteredDocs.map((doc) => {
              const docKey = doc.doc_id || doc.name;
              const isSelected = selectedDocId === docKey;
              const isChecked = selectedDocIds.has(docKey);
              const isOcr = doc.status === 'OCR_REQUIRED';
              const isReq = doc.role === 'requirements';

              return (
                <div
                  key={docKey}
                  onClick={() => setSelectedDocId(docKey)}
                  className={`w-full text-left p-3 rounded-xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-brand-950/40 border-brand-500/60 shadow-lg shadow-brand-950/20'
                      : 'bg-slate-900/60 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-2.5">
                      <button
                        type="button"
                        onClick={(e) => handleToggleSelect(docKey, e)}
                        className="text-slate-400 hover:text-white p-0.5 mt-0.5 rounded focus:outline-none"
                      >
                        {isChecked ? (
                          <CheckSquare className="w-3.5 h-3.5 text-brand-400" />
                        ) : (
                          <Square className="w-3.5 h-3.5 text-slate-600 hover:text-slate-400" />
                        )}
                      </button>

                      <div>
                        <h4 className="text-xs font-bold text-white truncate max-w-[180px]">
                          {doc.name}
                        </h4>
                        {doc.version_number && doc.version_number > 1 && (
                          <span className="inline-block px-1.5 py-0.5 rounded text-[9px] font-mono bg-brand-500/10 text-brand-400 border border-brand-500/20 mt-1">
                            v{doc.version_number}
                          </span>
                        )}
                        {doc.expires_at && (
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] font-mono mt-1 ${
                            (() => {
                              try {
                                const exp = new Date(doc.expires_at);
                                const now = new Date();
                                const diff = exp - now;
                                if (diff <= 0) return 'bg-red-950 text-red-400 border border-red-800';
                                if (diff < 30 * 24 * 60 * 60 * 1000) return 'bg-amber-950 text-amber-400 border border-amber-800';
                                return 'bg-emerald-950 text-emerald-400 border border-emerald-800';
                              } catch {
                                return 'bg-slate-800 text-slate-400 border border-slate-700';
                              }
                            })()
                          }`}>
                            {(() => {
                              try {
                                const exp = new Date(doc.expires_at);
                                const now = new Date();
                                const diff = exp - now;
                                if (diff <= 0) return 'Expired';
                                if (diff < 30 * 24 * 60 * 60 * 1000) return `Expires ${exp.toLocaleDateString()}`;
                                return `Exp: ${exp.toLocaleDateString()}`;
                              } catch {
                                return 'Expires: set';
                              }
                            })()}
                          </span>
                        )}
                        <div className="flex items-center space-x-2 text-[10px] font-mono text-slate-400 mt-1">
                          <span className={`px-1.5 py-0.2 rounded uppercase ${
                            isReq ? 'bg-purple-950 text-purple-300 border border-purple-800' : 'bg-slate-800 text-slate-300'
                          }`}>
                            {doc.role}
                          </span>
                          <span>{doc.total_pages} {doc.total_pages === 1 ? 'pg' : 'pgs'}</span>
                          <span>·</span>
                          <span>{doc.total_chunks} chunks</span>
                        </div>
                      </div>
                    </div>

                    {isOcr && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center space-x-1">
                        <AlertTriangle className="w-2.5 h-2.5" />
                        <span>OCR</span>
                      </span>
                    )}
                  </div>

                  {/* Supported Requirements Badge */}
                  {doc.supported_requirements?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px] font-mono text-emerald-400">
                      <span>✓ Supports {doc.supported_requirements.length} requirement(s)</span>
                      <ChevronRight className="w-3 h-3 text-slate-600" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT COLUMN: DOCUMENT CHUNK & EVIDENCE VIEWER (8 cols) */}
        <div className="lg:col-span-8 bg-slate-900/80 border border-slate-800 rounded-2xl p-6 backdrop-blur-xl space-y-4">
          {loadingDoc ? (
            <div className="p-12 text-center text-slate-400 font-mono text-xs animate-pulse">
              Extracting structured chunks and verified citations...
            </div>
          ) : activeDoc ? (
            <>
              {/* VERSION HISTORY PANEL */}
              {versions.length > 0 && (
                <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-slate-400 uppercase font-bold tracking-wider">
                      Version History ({versions.length} version{versions.length !== 1 ? 's' : ''})
                    </span>
                    {selectedVersion && (
                      <span className="text-[10px] font-mono text-brand-400">
                        Viewing v{selectedVersion.version_number}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {versions.map((v) => (
                      <button
                        key={v.version_id}
                        onClick={async () => {
                          try {
                            const versionDetail = await api.getDocumentVersion(projectId, selectedDocId, v.version_number);
                            setSelectedVersion(versionDetail);
                            if (versionDetail.data_json) {
                              setActiveDoc({
                                ...activeDoc,
                                ...versionDetail.data_json,
                                name: versionDetail.name,
                                version_number: versionDetail.version_number,
                              });
                            }
                          } catch {
                            // Silently handle version load failure
                          }
                        }}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-all cursor-pointer ${
                          selectedVersion?.version_number === v.version_number
                            ? 'bg-brand-600 text-white border border-brand-500'
                            : 'bg-slate-900 text-slate-300 border border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        v{v.version_number}
                        <span className="ml-1 text-[9px] opacity-70">
                          {new Date(v.uploaded_at).toLocaleDateString()}
                        </span>
                        {v.expires_at && (
                          <span className="ml-1 text-[9px] opacity-70">
                            · exp: {new Date(v.expires_at).toLocaleDateString()}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Document Overview Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                <div>
                  <div className="flex items-center space-x-2">
                    <FileText className="w-4 h-4 text-brand-400" />
                    <h3 className="text-sm font-bold text-white">{activeDoc.name}</h3>
                  </div>
                  <p className="text-[11px] font-mono text-slate-400 mt-0.5">
                    {activeDoc.total_characters.toLocaleString()} characters · {activeDoc.total_chunks} chunks · Format: {activeDoc.file_type}
                  </p>
                </div>

                {/* Search in Document */}
                <div className="relative min-w-[200px]">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search in document..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-brand-500 font-mono"
                  />
                </div>
              </div>

              {/* OCR WARNING BANNER IF APPLICABLE */}
              {activeDoc.status === 'OCR_REQUIRED' && (
                <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-700/50 text-xs text-amber-300 flex items-start space-x-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">OCR Required / Scanned Document</span>
                    <p className="text-[11px] text-amber-200/80 mt-0.5">
                      {activeDoc.diagnostics || 'No extractable text was found in this file. The document appears to be scanned or image-only. AI verification requires machine-readable text.'}
                    </p>
                  </div>
                </div>
              )}

              {/* SUPPORTED REQUIREMENTS SECTION */}
              {activeDoc.supported_requirements?.length > 0 && (
                <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                  <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-bold block">
                    Verified Citations In This Document:
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {activeDoc.supported_requirements.map((req) => (
                      <div
                        key={req.requirement_id}
                        className="px-2.5 py-1 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-[11px] flex items-center space-x-1.5"
                      >
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                        <span className="font-mono font-bold text-emerald-300">{req.requirement_id}</span>
                        <span className="text-slate-300 font-medium truncate max-w-[150px]">{req.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* MULTI-PAGE SELECTOR BAR */}
              {activeDoc.total_pages > 1 && !searchQuery && (
                <div className="flex items-center justify-between bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 text-xs font-mono">
                  <span className="text-slate-400">Viewing Page {activePage} of {activeDoc.total_pages}</span>
                  <div className="flex items-center space-x-1">
                    {Array.from({ length: activeDoc.total_pages }, (_, i) => i + 1).map((pg) => (
                      <button
                        key={pg}
                        onClick={() => setActivePage(pg)}
                        className={`px-2.5 py-1 rounded text-xs transition-colors ${
                          activePage === pg
                            ? 'bg-brand-600 text-white font-bold'
                            : 'bg-slate-900 text-slate-400 hover:text-white'
                        }`}
                      >
                        Page {pg}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* CHUNKS STREAM */}
              <div className="space-y-4 max-h-[500px] overflow-y-auto pr-1">
                {filteredChunks.length === 0 ? (
                  <div className="p-8 text-center text-slate-500 font-mono text-xs">
                    No text chunks match your search query.
                  </div>
                ) : (
                  filteredChunks.map((chunk) => {
                    const isHighlighted = highlightQuote && chunk.text.toLowerCase().includes(highlightQuote.toLowerCase().slice(0, 25));

                    return (
                      <div
                        key={chunk.chunk_id}
                        ref={(el) => (chunkRefs.current[chunk.chunk_id] = el)}
                        className={`p-4 rounded-xl border transition-all ${
                          isHighlighted
                            ? 'bg-emerald-950/30 border-emerald-500/70 shadow-lg shadow-emerald-950/30'
                            : 'bg-slate-950/60 border-slate-800/80'
                        }`}
                      >
                        {/* Chunk Header */}
                        <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/60 text-[10px] font-mono text-slate-400">
                          <div className="flex items-center space-x-2">
                            <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 font-bold">
                              Chunk #{chunk.chunk_index + 1}
                            </span>
                            {chunk.page_number && (
                              <span>Page {chunk.page_number}</span>
                            )}
                            {chunk.section && (
                              <span className="text-brand-400 truncate max-w-[200px]">§ {chunk.section}</span>
                            )}
                          </div>
                          <span>~{chunk.token_estimate} tokens</span>
                        </div>

                        {/* Chunk Text Body with Quote Highlighting */}
                        <div className="text-xs text-slate-200 font-mono leading-relaxed whitespace-pre-wrap">
                          {isHighlighted ? (
                            <HighlightedText fullText={chunk.text} targetQuote={highlightQuote} />
                          ) : (
                            chunk.text
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// Helper to highlight matching quote in text
function HighlightedText({ fullText, targetQuote }) {
  if (!targetQuote) return <span>{fullText}</span>;

  const quoteClean = targetQuote.trim();
  const idx = fullText.toLowerCase().indexOf(quoteClean.toLowerCase());

  if (idx === -1) {
    return <span>{fullText}</span>;
  }

  const before = fullText.slice(0, idx);
  const match = fullText.slice(idx, idx + quoteClean.length);
  const after = fullText.slice(idx + quoteClean.length);

  return (
    <span>
      {before}
      <mark className="bg-emerald-500/30 text-emerald-200 border-b-2 border-emerald-400 px-1 py-0.5 rounded">
        {match}
      </mark>
      {after}
    </span>
  );
}
