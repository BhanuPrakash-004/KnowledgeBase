//frontend-react/src/components/FileUpload.jsx
import React, { useState, useRef } from 'react';

const FileUpload = ({ onFileUpload, isLoading }) => {
    const [isDragging, setIsDragging] = useState(false);
    const inputRef = useRef(null);

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            onFileUpload(file);
        }
        // Reset file input to allow re-uploading the same file.
        e.target.value = null;
    };

    const handleDragOver = (e) => {
        e.preventDefault(); // Necessary to allow dropping.
        if (!isLoading) {
            setIsDragging(true);
        }
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        if (isLoading) {
            return;
        }
        const file = e.dataTransfer.files[0];
        if (file) {
            onFileUpload(file);
        }
        // If a user selected a file with the input, then drops another,
        // the input still holds a reference. It's better to clear it.
        if (inputRef.current) {
            inputRef.current.value = null;
        }
    };

    const labelClasses = `flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-xl cursor-pointer transition-all duration-300 ${
        isLoading 
            ? 'cursor-not-allowed opacity-60 border-slate-200 bg-slate-50' 
            : 'border-slate-300 bg-slate-50 hover:bg-white hover:border-emerald-500 hover:shadow-md'
    } ${isDragging ? 'bg-emerald-50 border-emerald-500' : ''}`;

    return (
        <div className="flex flex-col items-center justify-center w-full">
            <label 
                htmlFor="dropzone-file" 
                className={labelClasses}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                    <svg className={`w-12 h-12 mb-4 ${isDragging ? 'text-emerald-500' : 'text-slate-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-4-4V7a4 4 0 014-4h1.586a1 1 0 01.707.293l1.414 1.414a1 1 0 00.707.293H12a4 4 0 014 4v1m-6 4h6m-3-3v6"></path></svg>
                    <p className="mb-2 text-sm text-slate-600"><span className="font-semibold text-emerald-600">Click to upload</span> or drag and drop</p>
                    <p className="text-xs text-slate-500">PDF, TXT, PNG, JPG, or JPEG</p>
                </div>
                <input 
                    id="dropzone-file" 
                    type="file" 
                    className="hidden" 
                    onChange={handleFileChange} 
                    disabled={isLoading} 
                    accept=".pdf,.txt,.png,.jpg,.jpeg"
                    ref={inputRef}
                />
            </label>
            {isLoading && <p className="mt-4 text-emerald-600 font-medium animate-pulse">Processing document...</p>}
        </div>
    );
};

export default FileUpload;