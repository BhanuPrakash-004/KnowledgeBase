// AnalysisResult — AI analysis of the current document. Props: { analysis, documentName }.
import React from 'react';
import ReactMarkdown from 'react-markdown';

const Dossier = ({ analysis, documentName }) => {
    if (!analysis) return null;
    const { summary, action_items, assigned_role } = analysis;

    return (
        <section className="relative overflow-hidden border-2 border-ink bg-vellum shadow-hard">
            <div className="flex items-center justify-between bg-ink px-4 py-2.5 text-paper">
                <span className="eyebrow text-[11px] text-paper/70">Document Analysis</span>
                <span className="max-w-[60%] truncate font-mono text-[11px] text-butter">{documentName || 'current document'}</span>
            </div>

            <div className="p-5">
                {/* Assigned role */}
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <p className="eyebrow text-smoke">Assigned Role</p>
                        <p className="mt-1 font-display text-[22px] font-semibold leading-tight">{assigned_role}</p>
                    </div>
                    <div className="animate-stamp shrink-0 -rotate-3 border-2 border-vermilion px-3 py-1.5 text-center">
                        <p className="font-mono text-[10px] font-semibold tracking-[0.18em] text-vermilion">ANALYZED</p>
                        <p className="font-mono text-[10px] text-vermilion/70">via n8n webhook</p>
                    </div>
                </div>

                <div className="perforation my-4" />

                <p className="eyebrow text-smoke">Summary</p>
                <div className="prose-desk mt-2 font-display text-[15.5px] leading-[1.65] text-soot">
                    <ReactMarkdown>{summary}</ReactMarkdown>
                </div>

                <div className="perforation my-4" />

                <p className="eyebrow text-smoke">Action Items ({(action_items || []).length})</p>
                {(action_items || []).length === 0 ? (
                    <p className="mt-2 font-mono text-[12px] text-faint">No action items found in this document.</p>
                ) : (
                    <ol className="mt-2 space-y-2.5">
                        {action_items.map((item, i) => (
                            <li key={i} className="flex gap-3 border border-line bg-paper px-3 py-2.5">
                                <span className="font-display text-[16px] font-bold text-vermilion">
                                    {String(i + 1).padStart(2, '0')}
                                </span>
                                <div className="prose-desk min-w-0 flex-1 text-[13.5px] leading-relaxed text-soot">
                                    <ReactMarkdown>{item}</ReactMarkdown>
                                </div>
                            </li>
                        ))}
                    </ol>
                )}
            </div>
        </section>
    );
};

export default Dossier;
