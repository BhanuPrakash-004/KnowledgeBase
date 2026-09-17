// Qa — question input. Props: { onSubmit, isLoading, response, placeholder, seed }.
// `seed` lets suggestion cards elsewhere fill the input.
import React, { useEffect, useState } from 'react';

const Qa = ({ onSubmit, isLoading, response, placeholder, seed }) => {
    const [query, setQuery] = useState('');

    useEffect(() => {
        if (seed) setQuery(seed);
    }, [seed]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (query.trim() && !isLoading) onSubmit(query.trim());
    };

    return (
        <div>
            <form onSubmit={handleSubmit}>
                <label className="eyebrow text-smoke" htmlFor="desk-query">Ask a question</label>
                <div className="mt-2 flex border-2 border-ink bg-vellum shadow-hard-sm focus-within:shadow-hard">
                    <span className="grid w-10 shrink-0 place-items-center border-r-2 border-ink bg-butter font-display text-[18px] font-bold text-ink">?</span>
                    <input
                        id="desk-query"
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder={placeholder || 'Ask about your documents…'}
                        className="min-w-0 flex-1 bg-transparent px-4 py-3.5 text-[15px] text-ink placeholder:text-faint focus:outline-none"
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={isLoading || !query.trim()}
                        className="m-1 shrink-0 bg-vermilion px-5 font-mono text-[13px] font-semibold text-paper hover:bg-ember disabled:cursor-not-allowed disabled:bg-faint"
                    >
                        {isLoading ? (
                            <span className="flex items-center gap-1">
                                Searching
                                {[0, 1, 2].map((i) => (
                                    <span key={i} className="h-1 w-1 animate-[dots_1s_infinite] rounded-full bg-paper" style={{ animationDelay: `${i * 0.18}s` }} />
                                ))}
                            </span>
                        ) : 'Ask →'}
                    </button>
                </div>
            </form>

            {response && (
                <p className="mt-2 animate-rise font-mono text-[11.5px] text-smoke">
                    <span className="font-semibold text-pine">{response.model || 'AI model'}</span>
                    {typeof response.latency_ms === 'number' && ` · ${response.latency_ms} ms`}
                    {response.sources?.length > 0 && ` · ${response.sources.length} citation${response.sources.length > 1 ? 's' : ''}`}
                </p>
            )}
        </div>
    );
};

export default Qa;
