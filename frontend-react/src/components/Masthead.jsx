// Masthead — header bar: brand, live status, provider + document + session meta.
import React from 'react';

const Masthead = ({ status = 'offline', providerLabel = 'ollama', docCount = 0, sessionId = '' }) => {
    const dot = status === 'live' ? 'bg-butter' : status === 'degraded' ? 'bg-vermilion' : 'bg-faint';
    const word = status === 'live' ? 'OPEN' : status === 'degraded' ? 'DEGRADED' : 'OFFLINE';
    return (
        <header className="bg-ink text-paper">
            <div className="mx-auto max-w-[1440px] px-5 md:px-8">
                <div className="flex items-stretch gap-5 py-5">
                    {/* Index mark */}
                    <div className="flex items-center gap-4">
                        <div className="grid h-12 w-12 shrink-0 place-items-center bg-paper font-display text-[26px] font-bold text-ink">
                            K<span className="text-vermilion">.</span>
                        </div>
                        <div>
                            <p className="eyebrow text-faint">Document Intelligence Platform</p>
                            <h1 className="font-display text-[26px] font-semibold leading-none tracking-tight md:text-[30px]">
                                KnowledgeBase
                            </h1>
                        </div>
                    </div>

                    <div className="ml-auto hidden items-center gap-6 md:flex">
                        <div className="text-right">
                            <p className="eyebrow text-faint">AI Provider</p>
                            <p className="font-mono text-[13px] text-paper">{providerLabel}</p>
                        </div>
                        <div className="h-9 w-px bg-paper/15" />
                        <div className="text-right">
                            <p className="eyebrow text-faint">Documents</p>
                            <p className="font-mono text-[13px] text-paper">{String(docCount).padStart(2, '0')} indexed</p>
                        </div>
                        <div className="h-9 w-px bg-paper/15" />
                        <div className="text-right">
                            <p className="eyebrow text-faint">Session</p>
                            <p className="font-mono text-[13px] text-paper">{sessionId || '—'}</p>
                        </div>
                        <div className="flex items-center gap-2 border border-paper/25 px-3 py-2">
                            <span className={`h-2 w-2 rounded-full ${dot}`} />
                            <span className="font-mono text-[11px] font-semibold tracking-[0.14em]">{word}</span>
                        </div>
                    </div>
                </div>
            </div>
            {/* vermilion rule */}
            <div className="h-[3px] bg-vermilion" />
            {/* mobile meta strip */}
            <div className="flex items-center gap-4 overflow-x-auto border-t border-paper/10 px-5 py-2 font-mono text-[11px] text-paper/70 md:hidden">
                <span className="flex items-center gap-1.5"><span className={`h-1.5 w-1.5 rounded-full ${dot}`} />{word}</span>
                <span>{providerLabel}</span>
                <span>{docCount} documents</span>
            </div>
        </header>
    );
};

export default Masthead;
