// FileUpload — document upload ticket. Same contract: { onFileUpload, isLoading }.
import React, { useState, useRef } from 'react';

const FORMATS = 'PDF · TXT · MD · CSV · DOCX · PNG · JPG';

const FileUpload = ({ onFileUpload, isLoading }) => {
    const [isDragging, setIsDragging] = useState(false);
    const inputRef = useRef(null);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) onFileUpload(file);
        e.target.value = null;
    };
    const handleDragOver = (e) => { e.preventDefault(); if (!isLoading) setIsDragging(true); };
    const handleDragLeave = (e) => { e.preventDefault(); setIsDragging(false); };
    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        if (isLoading) return;
        const file = e.dataTransfer.files[0];
        if (file) onFileUpload(file);
        if (inputRef.current) inputRef.current.value = null;
    };

    return (
        <div className="w-full">
            <label
                htmlFor="dropzone-file"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative block cursor-pointer overflow-hidden border-2 border-dashed transition-colors ${
                    isLoading ? 'cursor-wait border-line bg-parchment/50' : isDragging ? 'border-vermilion bg-[#F8E9DC]' : 'border-ink/40 bg-vellum hover:border-vermilion hover:bg-[#FAF3E3]'
                }`}
            >
                <div className="flex">
                    {/* stub */}
                    <div className="flex w-[86px] shrink-0 flex-col items-center justify-center gap-1 border-r-2 border-dashed border-ink/25 bg-ink py-6 text-paper">
                        <span className="font-mono text-[10px] tracking-[0.2em] text-paper/60">UPLOAD</span>
                        <span className="font-display text-[22px] font-bold leading-none">Doc</span>
                        <span className="font-mono text-[10px] tracking-[0.2em] text-butter">FILE</span>
                    </div>
                    {/* body */}
                    <div className="flex min-h-[128px] flex-1 flex-col items-center justify-center px-6 py-6 text-center">
                        {isLoading ? (
                            <>
                                <div className="relative h-1 w-40 overflow-hidden bg-line">
                                    <div className="absolute inset-y-0 w-1/2 animate-[shimmer_1.1s_linear_infinite] bg-vermilion" />
                                </div>
                                <p className="mt-3 font-mono text-[12px] text-smoke">
                                    Extracting text, analyzing, indexing…
                                </p>
                            </>
                        ) : (
                            <>
                                <svg className={`mb-2 h-8 w-8 ${isDragging ? 'text-vermilion' : 'text-ink'}`} fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16" />
                                </svg>
                                <p className="font-display text-[19px] font-medium">
                                    {isDragging ? 'Release to upload & analyze.' : 'Drop a document, or browse.'}
                                </p>
                                <p className="mt-1.5 font-mono text-[11px] tracking-wide text-smoke">{FORMATS}</p>
                                <p className="font-mono text-[11px] text-faint">25 MB max · text is extracted & indexed into FAISS</p>
                            </>
                        )}
                    </div>
                </div>
            </label>
            <input
                id="dropzone-file"
                type="file"
                className="hidden"
                onChange={handleFileChange}
                disabled={isLoading}
                accept=".pdf,.txt,.md,.csv,.docx,.png,.jpg,.jpeg"
                ref={inputRef}
            />
        </div>
    );
};

export default FileUpload;
