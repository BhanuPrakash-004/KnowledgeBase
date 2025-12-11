import React from 'react';
import ReactMarkdown from 'react-markdown';

const AnalysisResult = ({ analysis }) => {
    if (!analysis) return null;

    const { summary, action_items, assigned_role } = analysis;

    return (
        <section className="bg-white p-8 rounded-xl shadow-xl shadow-slate-200/60 border border-slate-100 space-y-8">
            <h2 className="text-2xl font-bold text-slate-800 border-b border-slate-100 pb-4">Document Analysis</h2>

            {/* Assigned Role */}
            <div>
                <h3 className="text-sm uppercase tracking-wide text-slate-500 font-bold mb-3">👤 Suggested Assignee</h3>
                <div className="p-4 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-100 font-semibold shadow-sm inline-block">
                    {assigned_role}
                </div>
                <p className="text-xs text-slate-400 mt-2">This task can be automatically routed via n8n.</p>
            </div>

            {/* Summary */}
            <div>
                <h3 className="text-sm uppercase tracking-wide text-slate-500 font-bold mb-3">📄 Executive Summary</h3>
                <div className="p-6 bg-slate-50 rounded-lg border border-slate-200 shadow-sm">
                    <div className="prose prose-slate max-w-none text-slate-700 leading-relaxed">
                        <ReactMarkdown>{summary}</ReactMarkdown>
                    </div>
                </div>
            </div>

            {/* Action Items */}
            <div>
                <h3 className="text-sm uppercase tracking-wide text-slate-500 font-bold mb-3">📌 Action Items</h3>
                <div className="p-6 bg-white rounded-lg border border-slate-200 shadow-sm">
                    <ul className="space-y-3">
                        {action_items.map((item, index) => (
                            <li key={index} className="flex items-start text-slate-700">
                                <span className="mr-3 text-emerald-500 mt-1">•</span>
                                <div className="prose prose-slate max-w-none">
                                    <ReactMarkdown>{item}</ReactMarkdown>
                                </div>
                            </li>
                        ))}
                    </ul>
                </div>
            </div>
        </section>
    );
};

export default AnalysisResult;