import React, { useState, useEffect } from 'react';
import axios from 'axios';
import FileUpload from './components/FileUpload';
import AnalysisResult from './components/AnalysisResult';
import Qa from './components/Qa';

// Set the correct base URL for your FastAPI backend
const API_BASE_URL = 'http://localhost:8000';

const App = () => {
    // Session State
    const [sessionId] = useState(() => 'session-' + Math.random().toString(36).substr(2, 9));

    // Upload & Analysis State
    const [analysis, setAnalysis] = useState(null);
    const [documentName, setDocumentName] = useState('');
    const [isUploading, setIsUploading] = useState(false);
    
    // Data State
    const [fileList, setFileList] = useState([]);

    // Chat State (Split into Local and Global)
    const [localChatResponse, setLocalChatResponse] = useState(null);
    const [globalChatResponse, setGlobalChatResponse] = useState(null);
    
    const [isLocalChatLoading, setIsLocalChatLoading] = useState(false);
    const [isGlobalChatLoading, setIsGlobalChatLoading] = useState(false);
    
    const [error, setError] = useState('');

    // Fetch document list on mount
    useEffect(() => {
        fetchDocuments();
    }, []);

    const fetchDocuments = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/api/documents`);
            setFileList(response.data);
        } catch (err) {
            console.error("Failed to fetch documents:", err);
        }
    };

    const handleFileUpload = async (file) => {
        if (!file) return;
        setIsUploading(true);
        setError('');
        setAnalysis(null);
        setDocumentName('');
        setLocalChatResponse(null); // Clear previous local chat results

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post(`${API_BASE_URL}/api/upload-and-process`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            setAnalysis(response.data);
            setDocumentName(file.name);
            fetchDocuments(); // Refresh the list of files
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Error uploading or processing file.';
            setError(errorMsg);
            console.error(err);
        } finally {
            setIsUploading(false);
        }
    };

    const handleLocalQaSubmit = async (query) => {
        if (!query || !documentName) return;
        setIsLocalChatLoading(true);
        setError('');
        try {
            const response = await axios.post(`${API_BASE_URL}/api/chat`, { 
                query,
                session_id: `local-${sessionId}`,
                filter_source: documentName // Filter by the current document
            });
            setLocalChatResponse(response.data);
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Error in local chat.';
            setError(errorMsg);
            console.error(err);
        } finally {
            setIsLocalChatLoading(false);
        }
    };

    const handleGlobalQaSubmit = async (query) => {
        if (!query) return;
        setIsGlobalChatLoading(true);
        setError('');
        try {
            const response = await axios.post(`${API_BASE_URL}/api/chat`, { 
                query,
                session_id: `global-${sessionId}`,
                filter_source: null // Search everything
            });
            setGlobalChatResponse(response.data);
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Error in global chat.';
            setError(errorMsg);
            console.error(err);
        } finally {
            setIsGlobalChatLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
            <header className="bg-slate-900 text-white shadow-lg border-b border-slate-800">
                <div className="container mx-auto px-6 py-8">
                    <h1 className="text-4xl font-bold tracking-tight text-white">KnowledgeBase</h1>
                    <p className="mt-2 text-lg text-emerald-400 font-medium">Your organization's centralized knowledge base, powered by AI.</p>
                </div>
            </header>

            <main className="container mx-auto px-6 py-12">
                {error && (
                    <div className="bg-rose-50 border-l-4 border-rose-500 text-rose-700 p-4 mb-8 rounded-md shadow-sm" role="alert">
                        <p className="font-bold">Error</p>
                        <p>{error}</p>
                    </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
                    {/* Left Column: Current Interaction (Upload + Local Chat) */}
                    <div className="space-y-8">
                        <section className="bg-white p-8 rounded-xl shadow-xl shadow-slate-200/60 border border-slate-100">
                             <div className="flex items-center mb-6">
                                 <div className="bg-emerald-600 text-white rounded-full h-10 w-10 flex items-center justify-center text-xl font-bold shadow-md">1</div>
                                 <h2 className="text-2xl font-bold ml-4 text-slate-800">Current Session</h2>
                             </div>
                            <FileUpload onFileUpload={handleFileUpload} isLoading={isUploading} />
                            
                            {documentName && !isUploading && (
                                <div className="mt-6">
                                     <p className="text-emerald-700 font-medium bg-emerald-50 p-4 rounded-lg border border-emerald-100 flex items-center mb-6">
                                        <span className="mr-2">✅</span> Successfully processed: {documentName}
                                    </p>
                                    
                                    {/* Local Chat Widget */}
                                    <div className="bg-slate-50 rounded-xl p-6 border border-slate-200">
                                        <h3 className="text-lg font-bold text-slate-700 mb-4 flex items-center">
                                            <span className="bg-slate-200 text-slate-600 p-1 rounded mr-2 text-sm">DOC</span>
                                            Chat with "{documentName}"
                                        </h3>
                                        <Qa 
                                            onSubmit={handleLocalQaSubmit} 
                                            isLoading={isLocalChatLoading} 
                                            response={localChatResponse}
                                            placeholder="Ask about this specific document..."
                                        />
                                    </div>
                                </div>
                            )}
                        </section>
                        
                        {isUploading && !analysis && (
                            <div className="flex flex-col items-center justify-center p-12 text-slate-500 space-y-4">
                                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
                                <p>Analyzing document, please wait...</p>
                            </div>
                        )}
                        {analysis && <AnalysisResult analysis={analysis} />}
                    </div>

                    {/* Right Column: Knowledge Base (File List + Global Chat) */}
                    <div className="space-y-8">
                        <section className="bg-white p-8 rounded-xl shadow-xl shadow-slate-200/60 border border-slate-100 h-fit">
                            <div className="flex items-center mb-6">
                                <div className="bg-emerald-600 text-white rounded-full h-10 w-10 flex items-center justify-center text-xl font-bold shadow-md">2</div>
                                <h2 className="text-2xl font-bold ml-4 text-slate-800">Knowledge Base</h2>
                            </div>
                            
                            {/* Available Documents List */}
                            <div className="mb-8">
                                <h3 className="text-sm font-bold text-slate-500 uppercase tracking-wide mb-3">Available Documents ({fileList.length})</h3>
                                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 max-h-48 overflow-y-auto">
                                    {fileList.length > 0 ? (
                                        <ul className="space-y-2">
                                            {fileList.map((file, idx) => (
                                                <li key={idx} className="text-sm text-slate-600 flex items-center">
                                                    <svg className="w-4 h-4 mr-2 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                                                    <span className="truncate">{file}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <p className="text-sm text-slate-400 italic">No documents indexed yet.</p>
                                    )}
                                </div>
                            </div>

                            <p className="text-slate-600 mb-6 leading-relaxed">
                                Search across your entire organization's knowledge base.
                            </p>
                            
                            {/* Global Chat Widget */}
                            <div className="bg-emerald-50/50 rounded-xl p-6 border border-emerald-100">
                                <h3 className="text-lg font-bold text-emerald-800 mb-4 flex items-center">
                                    <span className="bg-emerald-200 text-emerald-700 p-1 rounded mr-2 text-sm">ALL</span>
                                    Global Search
                                </h3>
                                <Qa 
                                    onSubmit={handleGlobalQaSubmit} 
                                    isLoading={isGlobalChatLoading} 
                                    response={globalChatResponse}
                                    placeholder="Ask a question across all documents..."
                                />
                            </div>
                        </section>
                    </div>
                </div>
            </main>
        </div>
    );
};

export default App;