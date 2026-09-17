// Shelf — document list: searchable indexed documents with numbering.
import React, { useState } from 'react';

const extOf = (name) => (name.split('.').pop() || '').toUpperCase().slice(0, 4);

const Shelf = ({ files = [], activeDoc = '', onSelect, onDelete }) => {
    const [filter, setFilter] = useState('');
    const q = filter.trim().toLowerCase();
    const visible = q ? files.filter((f) => f.toLowerCase().includes(q)) : files;

    return (
        <section className="overflow-hidden border border-line bg-vellum shadow-card">
            <div className="flex items-baseline justify-between border-b border-line px-4 pb-3 pt-4">
                <h2 className="eyebrow text-smoke">Knowledge Base</h2>
                <span className="font-mono text-[11px] text-faint">{String(files.length).padStart(2, '0')} docs</span>
            </div>

            <div className="border-b border-line p-3">
                <input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Search documents…"
                    className="w-full border border-line bg-paper px-3 py-2 font-mono text-[12px] text-ink placeholder:text-faint"
                />
            </div>

            <ul className="slim-scroll max-h-64 overflow-y-auto">
                {visible.length === 0 && (
                    <li className="px-4 py-8 text-center">
                        <p className="font-display text-[17px] italic text-smoke">
                            {files.length === 0 ? 'No documents yet.' : 'No matching document.'}
                        </p>
                        {files.length === 0 && (
                            <p className="mt-1 font-mono text-[11px] text-faint">Upload your first document below.</p>
                        )}
                    </li>
                )}
                {visible.map((file, i) => {
                    const active = file === activeDoc;
                    return (
                        <li key={file}>
                            <div
                                className={`group flex cursor-pointer items-center gap-3 border-b border-line/70 px-4 py-2.5 transition-colors last:border-b-0 ${
                                    active ? 'bg-pine text-paper' : 'hover:bg-parchment/60'
                                }`}
                                onClick={() => onSelect && onSelect(file)}
                                role="button"
                                tabIndex={0}
                                onKeyDown={(e) => e.key === 'Enter' && onSelect && onSelect(file)}
                                title={file}
                            >
                                <span className={`font-mono text-[11px] ${active ? 'text-paper/60' : 'text-faint'}`}>
                                    {String(i + 1).padStart(2, '0')}
                                </span>
                                <span className={`min-w-0 flex-1 truncate font-mono text-[12.5px] ${active ? 'text-paper' : 'text-ink'}`}>
                                    {file}
                                </span>
                                <span className={`shrink-0 border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                                    active ? 'border-paper/40 text-paper/80' : 'border-line bg-paper text-smoke'
                                }`}>
                                    {extOf(file)}
                                </span>
                                <button
                                    onClick={(e) => { e.stopPropagation(); onDelete && onDelete(file); }}
                                    className={`shrink-0 px-1 font-mono text-[13px] leading-none ${
                                        active ? 'text-paper/50 hover:text-paper' : 'text-faint opacity-0 hover:text-vermilion group-hover:opacity-100'
                                    }`}
                                    title={`Delete ${file}`}
                                >
                                    ×
                                </button>
                            </div>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
};

export default Shelf;
