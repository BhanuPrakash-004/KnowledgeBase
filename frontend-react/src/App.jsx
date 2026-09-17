import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Masthead from './components/Masthead';
import Shelf from './components/Shelf';
import FileUpload from './components/FileUpload';
import AnalysisResult from './components/AnalysisResult';
import Qa from './components/Qa';
import ProviderToggle, { loadOverride } from './components/ProviderToggle';
import ChatHistory from './components/ChatHistory';

const API_BASE_URL = 'http://localhost:8000';

const App = () => {
    const [sessionId] = useState(() => {
        const saved = localStorage.getItem('kb-session-id');
        if (saved) return saved;
        const fresh = 'session-' + Math.random().toString(36).substr(2, 9);
        try { localStorage.setItem('kb-session-id', fresh); } catch { /* ignore */ }
        return fresh;
    });

    const [analysis, setAnalysis] = useState(null);
    const [documentName, setDocumentName] = useState('');
    const [isUploading, setIsUploading] = useState(false);
    const [fileList, setFileList] = useState([]);
    const [providerOverride, setProviderOverride] = useState(() => loadOverride());

    const [localChatResponse, setLocalChatResponse] = useState(null);
    const [globalChatResponse, setGlobalChatResponse] = useState(null);
    const [isLocalChatLoading, setIsLocalChatLoading] = useState(false);
    const [isGlobalChatLoading, setIsGlobalChatLoading] = useState(false);

    const [localHistory, setLocalHistory] = useState([]);
    const [globalHistory, setGlobalHistory] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    // Page chrome
    const [scope, setScope] = useState('shelf'); // 'doc' | 'shelf'
    const [seed, setSeed] = useState('');
    const [meta, setMeta] = useState({ status: 'offline', chunks: 0, provider: 'ollama' });
    const [error, setError] = useState('');

    const providerLabel = (() => {
        if (providerOverride && providerOverride.mode === 'byok') {
            return `${providerOverride.provider || 'byok'} / ${providerOverride.model || 'custom'}`;
        }
        const m = meta.providerModel ? ` / ${meta.providerModel}` : '';
        return `${meta.provider || 'ollama'}${m}`;
    })();

    const buildChatPayload = useCallback((query, session, filterSource) => {
        const payload = { query, session_id: session, filter_source: filterSource };
        if (providerOverride && providerOverride.mode === 'byok') {
            if (providerOverride.provider) payload.provider = providerOverride.provider;
            if (providerOverride.model) payload.model = providerOverride.model;
            if (providerOverride.apiKey) payload.api_key = providerOverride.apiKey;
            if (providerOverride.base_url) payload.base_url = providerOverride.base_url;
        }
        return payload;
    }, [providerOverride]);

    const fetchHistory = useCallback(async () => {
        setHistoryLoading(true);
        try {
            const [local, global] = await Promise.all([
                axios.get(`${API_BASE_URL}/api/chat/sessions/local-${sessionId}`).catch(() => ({ data: [] })),
                axios.get(`${API_BASE_URL}/api/chat/sessions/global-${sessionId}`).catch(() => ({ data: [] })),
            ]);
            setLocalHistory(local.data || []);
            setGlobalHistory(global.data || []);
        } catch (e) {
            console.error('Failed to fetch history', e);
        } finally {
            setHistoryLoading(false);
        }
    }, [sessionId]);

    const fetchDocuments = useCallback(async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/api/documents`);
            setFileList(response.data);
        } catch (err) {
            console.error('Failed to fetch documents:', err);
        }
    }, []);

    const fetchMeta = useCallback(async () => {
        try {
            const h = await axios.get(`${API_BASE_URL}/api/health`);
            const d = h.data || {};
            setMeta({
                status: d.status === 'ok' ? 'live' : 'degraded',
                chunks: d.chunks ?? 0,
                provider: d.provider?.llm_provider || 'ollama',
                providerModel: d.provider?.llm_model || '',
            });
        } catch {
            setMeta((m) => ({ ...m, status: 'offline' }));
        }
    }, []);

    useEffect(() => {
        fetchDocuments();
        fetchHistory();
        fetchMeta();
    }, [fetchDocuments, fetchHistory, fetchMeta]);

    const handleFileUpload = async (file) => {
        if (!file) return;
        setIsUploading(true);
        setError('');
        setAnalysis(null);
        setDocumentName('');
        setLocalChatResponse(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post(`${API_BASE_URL}/api/upload-and-process`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setAnalysis(response.data);
            setDocumentName(file.name);
            setScope('doc');
            fetchDocuments();
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Error uploading or processing file.';
            setError(errorMsg);
            console.error(err);
        } finally {
            setIsUploading(false);
        }
    };

    const askScoped = async (query, which) => {
        const isDoc = which === 'doc';
        if (isDoc && !documentName) return;
        if (!query) return;
        isDoc ? setIsLocalChatLoading(true) : setIsGlobalChatLoading(true);
        if (isDoc) setLocalChatResponse(null);
        setError('');
        setSeed('');
        try {
            const response = await axios.post(
                `${API_BASE_URL}/api/chat`,
                buildChatPayload(query, `${which === 'doc' ? 'local' : 'global'}-${sessionId}`, isDoc ? documentName : null)
            );
            isDoc ? setLocalChatResponse(response.data) : setGlobalChatResponse(response.data);
            fetchHistory();
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Could not get an answer. Please try again.';
            setError(errorMsg);
            console.error(err);
        } finally {
            isDoc ? setIsLocalChatLoading(false) : setIsGlobalChatLoading(false);
        }
    };

    const handleDeleteDocument = async (filename) => {
        if (!window.confirm(`Delete "${filename}" from the knowledge base?`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/documents/${filename}`);
            fetchDocuments();
            if (documentName === filename) {
                setDocumentName('');
                setAnalysis(null);
                setLocalChatResponse(null);
            }
        } catch (err) {
            console.error('Failed to delete document:', err);
            setError(err.response?.data?.detail || 'Failed to delete document');
        }
    };

    const handleClearSession = async (which) => {
        const sid = `${which}-${sessionId}`;
        if (!window.confirm(`Clear the ${which === 'local' ? 'document' : 'global'} chat history?`)) return;
        try {
            await axios.delete(`${API_BASE_URL}/api/chat/sessions/${sid}`);
            fetchHistory();
            if (which === 'local') setLocalChatResponse(null);
            else setGlobalChatResponse(null);
        } catch (err) {
            setError(err.response?.data?.detail || 'Failed to clear chat history');
        }
    };

    const isDoc = scope === 'doc';
    const activeHistory = isDoc ? localHistory : globalHistory;
    const activeResponse = isDoc ? localChatResponse : globalChatResponse;
    const activeLoading = isDoc ? isLocalChatLoading : isGlobalChatLoading;

    return (
        <div className="min-h-screen font-sans text-ink">
            <Masthead status={meta.status} providerLabel={providerLabel} docCount={fileList.length} sessionId={sessionId} />

            {/* Status strip */}
            <div className="border-b border-line bg-parchment/70">
                <div className="mx-auto flex max-w-[1440px] items-center gap-5 overflow-x-auto px-5 py-2 font-mono text-[11px] tracking-wide text-smoke md:px-8">
                    <span>KnowledgeBase · FastAPI · React · FAISS · Ollama</span>
                    <span className="text-faint">/</span>
                    <span>{fileList.length} documents · {meta.chunks} chunks indexed</span>
                    <span className="text-faint">/</span>
                    <span>Chat history saved across sessions</span>
                    <span className="ml-auto hidden shrink-0 sm:inline">Hybrid search · FAISS + BM25 + Reranker</span>
                </div>
            </div>

            <main className="mx-auto max-w-[1440px] px-5 py-8 md:px-8">
                {error && (
                    <div className="mb-6 flex items-start gap-3 border-2 border-ink bg-butter px-4 py-3 shadow-hard-sm" role="alert">
                        <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center bg-ink font-mono text-[13px] font-bold text-butter">!</span>
                        <div className="min-w-0">
                            <p className="eyebrow text-[11px] text-ink">Error</p>
                            <p className="mt-0.5 text-[14px] font-medium">{error}</p>
                        </div>
                        <button onClick={() => setError('')} className="ml-auto shrink-0 font-mono text-[13px] text-ink/60 hover:text-ink">dismiss ×</button>
                    </div>
                )}

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)_360px]">
                    {/* LEFT — provider + documents */}
                    <div className="space-y-6">
                        <ProviderToggle onOverrideChange={(o) => { setProviderOverride(o); fetchMeta(); }} />
                        <Shelf
                            files={fileList}
                            activeDoc={documentName}
                            onSelect={(f) => { setDocumentName(f); setScope('doc'); setAnalysis(null); }}
                            onDelete={handleDeleteDocument}
                        />
                        <div className="border border-line bg-pine px-4 py-4 text-paper">
                            <p className="eyebrow text-[11px] text-paper/60">How it works</p>
                            <ul className="mt-2 space-y-1.5 font-mono text-[12px] leading-relaxed text-paper/90">
                                <li>I. Upload PDF, TXT, DOCX, CSV or images.</li>
                                <li>II. Get summary, action items & assigned role.</li>
                                <li>III. Ask questions — answers include citations.</li>
                            </ul>
                        </div>
                    </div>

                    {/* CENTER — upload + Q&A */}
                    <div className="min-w-0">
                        <section className="paper-rules border-2 border-ink bg-paper shadow-hard">
                            <div className="flex items-center justify-between border-b-2 border-ink bg-vellum px-5 py-3">
                                <h2 className="font-display text-[22px] font-semibold tracking-tight">Document Q&A</h2>
                                {/* scope tabs */}
                                <div className="flex border border-ink font-mono text-[12px] font-semibold">
                                    <button
                                        onClick={() => setScope('doc')}
                                        className={`px-3.5 py-1.5 transition-colors ${isDoc ? 'bg-ink text-paper' : 'bg-paper text-smoke hover:text-ink'}`}
                                    >
                                        This document
                                    </button>
                                    <button
                                        onClick={() => setScope('shelf')}
                                        className={`border-l border-ink px-3.5 py-1.5 transition-colors ${!isDoc ? 'bg-ink text-paper' : 'bg-paper text-smoke hover:text-ink'}`}
                                    >
                                        All documents
                                    </button>
                                </div>
                            </div>

                            <div className="space-y-6 p-5 md:p-7">
                                <FileUpload onFileUpload={handleFileUpload} isLoading={isUploading} />

                                {isUploading && (
                                    <p className="text-center font-mono text-[12px] text-smoke">
                                        Processing document — summary, action items & role assignment to follow.
                                    </p>
                                )}

                                {isDoc && !documentName && !isUploading && (
                                    <div className="border border-dashed border-ink/30 bg-vellum/70 px-5 py-6 text-center">
                                        <p className="font-display text-[18px] italic text-soot">No document selected.</p>
                                        <p className="mt-1 font-mono text-[11.5px] text-faint">
                                            Upload a file above, or pick one from the list — or search across all documents.
                                        </p>
                                        <button onClick={() => setScope('shelf')} className="mt-3 border border-ink bg-paper px-4 py-2 font-mono text-[12px] font-semibold hover:bg-butter">
                                            Search all documents →
                                        </button>
                                    </div>
                                )}

                                {(!isDoc || documentName) && (
                                    <>
                                        <div className="flex items-center justify-between">
                                            <p className="eyebrow text-smoke">
                                                {isDoc ? (
                                                    <>Searching — <span className="text-vermilion">{documentName}</span></>
                                                ) : (
                                                    <>Searching — <span className="text-vermilion">all documents</span></>
                                                )}
                                            </p>
                                            <button
                                                onClick={() => handleClearSession(isDoc ? 'local' : 'global')}
                                                className="font-mono text-[11px] text-faint underline-offset-2 hover:text-vermilion hover:underline"
                                            >
                                                clear chat
                                            </button>
                                        </div>
                                        <Qa
                                            onSubmit={(q) => askScoped(q, isDoc ? 'doc' : 'global')}
                                            isLoading={activeLoading}
                                            response={activeResponse}
                                            seed={seed}
                                            placeholder={isDoc ? 'Ask about this document…' : 'Ask across all documents…'}
                                        />
                                        <div className="perforation" />
                                        <ChatHistory messages={activeHistory} loading={historyLoading} onSuggest={(s) => setSeed(s)} />
                                    </>
                                )}
                            </div>
                        </section>
                    </div>

                    {/* RIGHT — analysis */}
                    <div className="space-y-6">
                        {analysis ? (
                            <div className="animate-rise">
                                <AnalysisResult analysis={analysis} documentName={documentName} />
                            </div>
                        ) : (
                            <section className="border border-dashed border-ink/30 bg-vellum/50 p-6 text-center">
                                <p className="eyebrow text-faint">Analysis</p>
                                <p className="mt-2 font-display text-[19px] italic leading-snug text-soot">
                                    Upload a document to get its summary, action items and assigned role.
                                </p>
                            </section>
                        )}
                        <section className="border border-line bg-vellum p-5 shadow-card">
                            <p className="eyebrow text-smoke">About</p>
                            <p className="mt-2 text-[13.5px] leading-relaxed text-smoke">
                                AI-powered document intelligence: Python FastAPI backend, React frontend,
                                FAISS vector search with BM25 hybrid retrieval, Ollama LLM + embeddings
                                (or your own cloud API key). Analysis results can trigger n8n workflows.
                            </p>
                            <p className="mt-3 font-mono text-[11px] text-faint">PDF · TXT · MD · CSV · DOCX · PNG · JPG</p>
                        </section>
                    </div>
                </div>

                <footer className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line pt-5 font-mono text-[11px] text-faint">
                    <span>KNOWLEDGEBASE</span>
                    <span> {fileList.length} DOCUMENTS · {meta.chunks} CHUNKS</span>
                    <span className="ml-auto">ANSWERS INCLUDE SOURCE CITATIONS</span>
                </footer>
            </main>
        </div>
    );
};

export default App;
