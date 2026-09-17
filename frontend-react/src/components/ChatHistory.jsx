// ChatHistory — conversation thread. Props: { messages, loading, onSuggest }.
import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

const SUGGESTIONS = [
    'Summarize the key points in these documents.',
    'What action items are mentioned?',
    'What important details might need follow-up?',
];

const Thread = ({ messages = [], loading, onSuggest }) => {
    const boxRef = useRef(null);

    useEffect(() => {
        const el = boxRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [messages.length, loading]);

    if (loading) {
        return (
            <div className="space-y-3 py-2">
                {[0, 1].map((i) => (
                    <div key={i} className="border border-line bg-vellum p-4">
                        <div className="h-2.5 w-24 bg-line" />
                        <div className="mt-2 h-2.5 w-full bg-parchment" />
                        <div className="mt-1.5 h-2.5 w-2/3 bg-parchment" />
                    </div>
                ))}
            </div>
        );
    }

    if (!messages.length) {
        return (
            <div className="border border-dashed border-ink/30 bg-vellum/60 px-5 py-7 text-center">
                <p className="font-display text-[18px] italic text-soot">No conversation yet.</p>
                <p className="mt-1 font-mono text-[11px] text-faint">Ask a question — chat history is saved across reloads.</p>
                {onSuggest && (
                    <div className="mt-4 flex flex-col gap-2">
                        {SUGGESTIONS.map((s) => (
                            <button key={s} onClick={() => onSuggest(s)}
                                className="border border-line bg-paper px-3 py-2 text-left font-mono text-[12px] text-soot hover:border-vermilion hover:text-vermilion">
                                “{s}”
                            </button>
                        ))}
                    </div>
                )}
            </div>
        );
    }

    return (
        <div ref={boxRef} className="slim-scroll max-h-[520px] space-y-5 overflow-y-auto pr-1">
            {messages.map((m, idx) => {
                const human = m.role === 'human';
                if (human) {
                    return (
                        <div key={m.id ?? idx} className="ml-10 animate-rise md:ml-16">
                            <p className="eyebrow mb-1 text-right text-[10px] text-faint">You · {m.created_at ? m.created_at.slice(11, 16) : ''}</p>
                            <div className="border-2 border-ink bg-ink px-4 py-3 text-[14.5px] leading-relaxed text-paper shadow-hard-sm">
                                <div className="prose-desk"><ReactMarkdown>{m.content}</ReactMarkdown></div>
                            </div>
                        </div>
                    );
                }
                return (
                    <div key={m.id ?? idx} className="mr-4 animate-rise md:mr-10">
                        <p className="eyebrow mb-1 text-[10px] text-vermilion">
                            AI Assistant{m.model ? ` · ${m.model}` : ''}
                        </p>
                        <div className="border border-line border-l-4 border-l-pine bg-vellum px-4 py-3.5 text-[14.5px] leading-relaxed text-ink shadow-card">
                            <div className="prose-desk"><ReactMarkdown>{m.content}</ReactMarkdown></div>
                            {m.sources?.length > 0 && (
                                <div className="mt-3 border-t border-line pt-2.5">
                                    <p className="eyebrow text-[10px] text-faint">Sources</p>
                                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                                        {m.sources.map((s, i) => (
                                            <span key={i} className="border border-line bg-paper px-2 py-1 font-mono text-[11px] text-soot">
                                                <span className="mr-1 font-semibold text-vermilion">{i + 1}</span>{s}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

export default Thread;
