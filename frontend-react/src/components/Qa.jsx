import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

const Qa = ({ onSubmit, isLoading, response, placeholder }) => {
    const [query, setQuery] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (query.trim()) {
            onSubmit(query);
            setQuery(query); 
        }
    };

    return (
        <div>
            <form onSubmit={handleSubmit} className="flex items-center space-x-3">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={placeholder || "e.g., 'Summarize all safety reports from last month'"}
                    className="flex-grow p-4 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none transition-shadow text-slate-700 placeholder-slate-400"
                    disabled={isLoading}
                />
                <button 
                    type="submit" 
                    disabled={isLoading || !query.trim()} 
                    className="bg-slate-900 hover:bg-slate-800 text-white font-bold py-4 px-8 rounded-lg shadow-lg disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
                >
                    {isLoading ? 'Searching...' : 'Ask'}
                </button>
            </form>

            {/* ## CHANGE ##: Updated logic to render the response object */}
            {response && (
                <div className="mt-10 animate-fade-in">
                    <h3 className="text-lg font-bold text-slate-800 mb-4 flex items-center">
                        <span className="bg-emerald-100 text-emerald-600 p-1.5 rounded-md mr-2">
                             💡
                        </span>
                        Answer
                    </h3>
                    <div className="p-6 bg-slate-50 rounded-xl border border-slate-200 shadow-sm">
                        <div className="prose prose-slate max-w-none text-slate-800 leading-relaxed">
                            <ReactMarkdown>{response.answer}</ReactMarkdown>
                        </div>
                    </div>

                    {response.sources && response.sources.length > 0 && (
                        <div className="mt-8">
                             <h4 className="text-sm font-bold text-slate-500 uppercase tracking-wide mb-3">Sources</h4>
                             <div className="space-y-3">
                                {response.sources.map((source, index) => (
                                    <div key={index} className="p-3 bg-white rounded-lg border border-slate-100 shadow-sm flex items-center hover:border-emerald-200 transition-colors">
                                       <svg className="w-5 h-5 mr-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>
                                       <p className="text-sm text-slate-600 font-mono truncate">{source}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default Qa;