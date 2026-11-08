import React, { useEffect, useRef, useState } from 'react';
import { FileSearch, UploadCloud, FileText, X, Check, Loader2, ShieldCheck, Sparkles } from 'lucide-react';
import { uploadContract, getContractTypes } from '../api/client';
import ReviewWorkspace from '../components/review/ReviewWorkspace';

const ACCEPT = ['.pdf', '.docx', '.hwp', '.hwpx', '.txt'];
const MAX_SIZE_MB = 50;

// 분석 진행 단계 (요청 1건이라 서버 진행률은 알 수 없음 — 경과 시간 기준 안내)
const ANALYSIS_STEPS = [
  { label: '계약서 텍스트 추출', at: 0 },
  { label: '계약 유형 판별·점검표 선택', at: 3 },
  { label: '조항별 리스크 분석', at: 7 },
  { label: '근거 법령 검증·원문 위치 표시', at: 22 },
];

function formatSize(bytes) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function DropZone({ file, onFile, error }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const pick = (f) => f && onFile(f);

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-primary-200 bg-primary-50/50 px-5 py-4">
        <span className="w-10 h-10 rounded-xl bg-white border border-primary-100 flex items-center justify-center">
          <FileText className="w-5 h-5 text-primary-600" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-semibold text-slate-900 truncate">{file.name}</p>
          <p className="text-[12px] text-slate-500">{formatSize(file.size)}</p>
        </div>
        <button
          type="button"
          onClick={() => onFile(null)}
          className="p-2 rounded-lg text-slate-400 hover:bg-white hover:text-slate-700"
          title="파일 바꾸기"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files?.[0]); }}
        className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 cursor-pointer transition-colors ${
          dragging ? 'border-primary-400 bg-primary-50' : 'border-slate-300 bg-white hover:border-primary-300 hover:bg-slate-50'
        }`}
      >
        <span className="w-12 h-12 rounded-2xl bg-primary-50 text-primary-600 flex items-center justify-center mb-3">
          <UploadCloud className="w-6 h-6" />
        </span>
        <p className="text-[15px] font-semibold text-slate-800">계약서 파일을 끌어다 놓거나 클릭해서 선택하세요</p>
        <p className="mt-1 text-[12.5px] text-slate-500">PDF · DOCX · HWP · HWPX · TXT, 최대 {MAX_SIZE_MB}MB · 스캔 이미지 PDF는 지원하지 않습니다</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT.join(',')}
          className="hidden"
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }}
        />
      </div>
      {error && <p className="mt-2 text-[12.5px] text-red-600">{error}</p>}
    </div>
  );
}

function AnalysisProgress({ fileName }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const current = ANALYSIS_STEPS.reduce((idx, step, i) => (elapsed >= step.at ? i : idx), 0);

  return (
    <div className="max-w-xl mx-auto pt-[14vh] px-6">
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-8">
        <div className="flex items-center gap-3 mb-6">
          <Loader2 className="w-6 h-6 text-primary-600 animate-spin" />
          <div className="min-w-0">
            <p className="text-[16px] font-bold text-slate-900">계약서를 검토하고 있습니다</p>
            <p className="text-[12.5px] text-slate-500 truncate">{fileName} · {elapsed}초 경과 (보통 20~40초)</p>
          </div>
        </div>
        <ol className="space-y-3">
          {ANALYSIS_STEPS.map((step, i) => (
            <li key={step.label} className="flex items-center gap-3 text-[13.5px]">
              {i < current ? (
                <span className="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center"><Check className="w-3 h-3" /></span>
              ) : i === current ? (
                <span className="w-5 h-5 rounded-full border-2 border-primary-500 flex items-center justify-center"><span className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" /></span>
              ) : (
                <span className="w-5 h-5 rounded-full border-2 border-slate-200" />
              )}
              <span className={i <= current ? 'text-slate-800 font-medium' : 'text-slate-400'}>{step.label}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

const ReviewPage = () => {
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [error, setError] = useState(null);
  const [contractTypes, setContractTypes] = useState([]);
  const [contractType, setContractType] = useState('auto');

  useEffect(() => {
    getContractTypes()
      .then(setContractTypes)
      .catch((err) => console.error('계약 유형 목록 로드 실패:', err));
  }, []);

  const handleFile = (file) => {
    setError(null);
    setFileError('');
    if (!file) { setSelectedFile(null); return; }
    const ext = `.${file.name.split('.').pop().toLowerCase()}`;
    if (!ACCEPT.includes(ext)) { setFileError(`지원하지 않는 파일 형식입니다 (${ext}).`); return; }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) { setFileError(`파일 크기가 ${MAX_SIZE_MB}MB를 초과합니다.`); return; }
    setSelectedFile(file);
  };

  const handleAnalyze = async () => {
    if (!selectedFile) return;
    setIsAnalyzing(true);
    setError(null);
    try {
      setAnalysisResult(await uploadContract(selectedFile, contractType));
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

  if (analysisResult) return <ReviewWorkspace result={analysisResult} onReset={handleReset} />;
  if (isAnalyzing) return <AnalysisProgress fileName={selectedFile?.name} />;

  const typeOptions = [{ key: 'auto', label: '자동 감지', description: 'AI가 계약 유형을 판별합니다' }, ...contractTypes];

  return (
    <div className="max-w-3xl mx-auto px-6 pt-[8vh] pb-16">
      <div className="text-center mb-8">
        <span className="inline-flex w-12 h-12 rounded-2xl bg-primary-50 text-primary-600 items-center justify-center mb-4">
          <FileSearch className="w-6 h-6" />
        </span>
        <h1 className="text-[26px] font-bold tracking-tight text-slate-900">계약서 리뷰</h1>
        <p className="mt-2 text-[15px] text-slate-500">
          이지스엔터프라이즈 입장에서 불리한 조항과 빠진 조항을 찾고, 바로 쓸 수 있는 수정 조문을 제안합니다.
        </p>
      </div>

      <DropZone file={selectedFile} onFile={handleFile} error={fileError} />

      <div className="mt-8">
        <div className="flex items-baseline justify-between mb-3">
          <p className="text-[14px] font-semibold text-slate-900">계약 유형</p>
          <p className="text-[12px] text-slate-400">유형별 필수 점검표로 빠진 조항까지 확인합니다</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {typeOptions.map((t) => {
            const active = contractType === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setContractType(t.key)}
                className={`text-left p-3 rounded-xl border transition-all ${
                  active ? 'border-primary-500 bg-primary-50/70 ring-1 ring-primary-500' : 'border-slate-200 bg-white hover:border-primary-300'
                }`}
              >
                <p className={`text-[13px] font-semibold flex items-center gap-1 ${active ? 'text-primary-800' : 'text-slate-800'}`}>
                  {t.key === 'auto' && <Sparkles className="w-3.5 h-3.5 text-amber-500" />}
                  {t.label}
                </p>
                <p className="text-[11.5px] text-slate-500 mt-0.5 line-clamp-2">
                  {t.description}
                  {t.item_count ? ` · ${t.item_count}개 항목` : ''}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-800">{error}</div>
      )}

      <button
        type="button"
        onClick={handleAnalyze}
        disabled={!selectedFile}
        className="mt-8 w-full h-12 rounded-xl bg-primary-600 text-white text-[15px] font-semibold hover:bg-primary-700 disabled:bg-slate-200 disabled:text-slate-400 transition-colors flex items-center justify-center gap-2"
      >
        <FileSearch className="w-5 h-5" />
        계약서 검토 시작
      </button>

      <p className="mt-4 flex items-center justify-center gap-1.5 text-[12px] text-slate-400">
        <ShieldCheck className="w-3.5 h-3.5" />
        업로드한 파일은 분석 직후 서버에서 삭제됩니다 · 분석 결과는 참고용입니다
      </p>
    </div>
  );
};

export default ReviewPage;
