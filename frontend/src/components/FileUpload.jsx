import React, { useState, useRef } from 'react';
import { UploadCloud, X } from 'lucide-react';

/** 파일 선택 영역 — 드래그 앤 드롭 또는 클릭 (형식·크기 검사) */
const FileUpload = ({ onFileSelect, accept = '*', maxSizeMB = 50 }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    if (file.size > maxSizeMB * 1024 * 1024) {
      setError(`파일 크기는 ${maxSizeMB}MB를 넘을 수 없습니다.`);
      return false;
    }
    if (accept !== '*') {
      const accepted = accept.split(',').map((ext) => ext.trim());
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!accepted.includes(ext)) {
        setError(`지원하지 않는 형식입니다. (${accept})`);
        return false;
      }
    }
    setError(null);
    return true;
  };

  const handleFile = (file) => {
    if (file && validateFile(file)) onFileSelect(file);
  };

  const stop = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputRef.current?.click()}
        onDragEnter={(e) => { stop(e); setIsDragging(true); }}
        onDragOver={stop}
        onDragLeave={(e) => { stop(e); setIsDragging(false); }}
        onDrop={(e) => { stop(e); setIsDragging(false); handleFile(e.dataTransfer.files?.[0]); }}
        className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-primary-100 ${
          isDragging
            ? 'border-primary-400 bg-primary-50'
            : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-slate-100/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          onChange={(e) => { handleFile(e.target.files?.[0]); e.target.value = ''; }}
          className="hidden"
        />
        <UploadCloud className={`w-8 h-8 mb-2 ${isDragging ? 'text-primary-600' : 'text-slate-400'}`} />
        <p className="text-[13.5px] font-medium text-slate-800">파일을 끌어다 놓거나 클릭해서 선택</p>
        <p className="mt-1 text-[12px] text-slate-500">
          {accept === '*' ? '모든 형식' : accept.replace(/\./g, '').toUpperCase().split(',').join(' · ')} · 최대 {maxSizeMB}MB
        </p>
      </div>

      {error && (
        <div role="alert" className="mt-3 flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-3 py-2">
          <p className="text-[12.5px] text-red-800">{error}</p>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-700" aria-label="오류 닫기">
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
