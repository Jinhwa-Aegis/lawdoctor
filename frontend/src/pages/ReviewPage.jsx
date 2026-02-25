import React, { useState } from 'react';
import { FileSearch, Loader } from 'lucide-react';
import { uploadContract } from '../api/client';
import FileUpload from '../components/FileUpload';
import RiskReport from '../components/RiskReport';

const ReviewPage = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelect = (file) => {
    setSelectedFile(file);
    setAnalysisResult(null);
    setError(null);
  };

  const handleAnalyze = async () => {
    if (!selectedFile) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      const result = await uploadContract(selectedFile);
      setAnalysisResult(result);
    } catch (err) {
      console.error('분석 실패:', err);
      setError(err.message || '계약서 분석 중 오류가 발생했습니다.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setAnalysisResult(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-5xl mx-auto">
        {/* 헤더 */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <FileSearch size={40} className="text-blue-600" />
            <h1 className="text-3xl font-bold text-gray-900">계약서 리뷰</h1>
          </div>
          <p className="text-gray-600">
            계약서를 업로드하면 AI가 법률적 리스크를 분석하고 검토 의견을 제공합니다
          </p>
        </div>

        {/* 업로드 영역 */}
        {!analysisResult && !isAnalyzing && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
            <FileUpload
              onFileSelect={handleFileSelect}
              accept=".pdf,.docx,.hwp"
              maxSizeMB={50}
            />

            {selectedFile && (
              <div className="mt-6">
                <div className="flex items-center justify-between p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-900">{selectedFile.name}</p>
                    <p className="text-sm text-gray-600">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                  <button
                    onClick={handleReset}
                    className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
                  >
                    취소
                  </button>
                </div>

                <button
                  onClick={handleAnalyze}
                  disabled={isAnalyzing}
                  className="w-full mt-4 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isAnalyzing ? (
                    <>
                      <Loader size={20} className="animate-spin" />
                      분석 중...
                    </>
                  ) : (
                    <>
                      <FileSearch size={20} />
                      계약서 분석 시작
                    </>
                  )}
                </button>
              </div>
            )}

            {error && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}
          </div>
        )}

        {/* 로딩 애니메이션 */}
        {isAnalyzing && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12">
            <div className="text-center">
              <Loader size={48} className="animate-spin text-blue-600 mx-auto mb-4" />
              <h2 className="text-xl font-bold text-gray-900 mb-2">
                계약서 분석 중...
              </h2>
              <p className="text-gray-600">
                AI가 계약서를 검토하고 법률적 리스크를 분석하고 있습니다.
              </p>
              <div className="mt-8 space-y-2">
                <div className="flex items-center justify-center gap-2 text-sm text-gray-600">
                  <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
                  문서 내용 분석 중
                </div>
                <div className="flex items-center justify-center gap-2 text-sm text-gray-600">
                  <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                  법률 조항 검토 중
                </div>
                <div className="flex items-center justify-center gap-2 text-sm text-gray-600">
                  <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                  리스크 평가 중
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 분석 결과 */}
        {analysisResult && (
          <div>
            <RiskReport result={analysisResult} />
            <div className="mt-6 text-center">
              <button
                onClick={handleReset}
                className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              >
                새 계약서 분석
              </button>
            </div>
          </div>
        )}

        {/* 지원 형식 안내 */}
        <div className="mt-8 text-center">
          <p className="text-sm text-gray-500">
            지원 형식: PDF, DOCX, HWP | 최대 파일 크기: 50MB
          </p>
        </div>
      </div>
    </div>
  );
};

export default ReviewPage;