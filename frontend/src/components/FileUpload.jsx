import React, { useState, useRef } from 'react';
import { Upload, X } from 'lucide-react';

const FileUpload = ({ onFileSelect, accept = '*', maxSizeMB = 50 }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    const maxSizeBytes = maxSizeMB * 1024 * 1024;

    if (file.size > maxSizeBytes) {
      setError(`파일 크기는 ${maxSizeMB}MB를 초과할 수 없습니다.`);
      return false;
    }

    if (accept !== '*') {
      const acceptedExtensions = accept.split(',').map(ext => ext.trim());
      const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

      if (!acceptedExtensions.includes(fileExtension)) {
        setError(`지원되지 않는 파일 형식입니다. (${accept})`);
        return false;
      }
    }

    setError(null);
    return true;
  };

  const handleFile = (file) => {
    if (validateFile(file)) {
      onFileSelect(file);
    }
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div>
      <div
        onClick={handleClick}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-all ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400 bg-gray-50 hover:bg-gray-100'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          onChange={handleFileInputChange}
          className="hidden"
        />

        <Upload
          size={48}
          className={`mx-auto mb-4 ${
            isDragging ? 'text-blue-600' : 'text-gray-400'
          }`}
        />

        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          파일을 드래그하거나 클릭하여 업로드
        </h3>

        <p className="text-sm text-gray-600 mb-4">
          {accept === '*'
            ? '모든 파일 형식 지원'
            : `지원 형식: ${accept.replace(/\./g, '').toUpperCase()}`}
        </p>

        <p className="text-xs text-gray-500">
          최대 파일 크기: {maxSizeMB}MB
        </p>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-red-600 hover:text-red-800 transition-colors"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
