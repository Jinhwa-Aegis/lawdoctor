import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText, Search, Trash2, Pencil, Check, X, Loader2, Lock,
} from 'lucide-react';
import { getDocuments, updateDocument, deleteDocument } from '../api/client';
import { Card, EmptyState, Notice, inputClass } from './admin/AdminUI';

const COLLECTION_NAMES = {
  consultations: '자문·참고 문서',
  laws: '법령 조문',
  precedents: '판례',
  security_guides: '보안 가이드',
  security_incidents: '보안 사고 사례',
};

const formatFileSize = (bytes) => {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
};

/** 업로드 문서 목록 — 검색, (보안 자료) 메타데이터 편집, 삭제 */
const DocumentList = ({ documentType, refreshKey, onDocumentsChanged }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editData, setEditData] = useState({});
  const [confirmId, setConfirmId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [notice, setNotice] = useState(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const params = { document_type: documentType };
      if (search.trim()) params.search = search.trim();
      setDocuments(await getDocuments(params));
    } catch (err) {
      setNotice({ tone: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  }, [documentType, search]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments, refreshKey]);

  const handleEditSave = async (id) => {
    try {
      await updateDocument(id, editData);
      setEditingId(null);
      setNotice({ tone: 'success', text: '메타데이터를 저장했습니다.' });
      loadDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      setNotice({ tone: 'error', text: err.message });
    }
  };

  const handleDelete = async (doc) => {
    setDeletingId(doc.id);
    try {
      const res = await deleteDocument(doc.id);
      setNotice(
        res?.chromadb_warning
          ? { tone: 'error', text: `문서 기록은 지웠지만 벡터 DB 정리에 실패했습니다: ${res.chromadb_warning}` }
          : { tone: 'success', text: `"${doc.original_filename}"과 검색용 청크를 삭제했습니다.` },
      );
      loadDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      setNotice({ tone: 'error', text: err.message });
    } finally {
      setDeletingId(null);
      setConfirmId(null);
    }
  };

  const isSecurity = documentType === 'security';
  const cellInput = `${inputClass} !py-1 !text-[12px]`;

  return (
    <Card
      title="등록 문서"
      description={loading ? '불러오는 중…' : `${documents.length}건`}
      icon={FileText}
      action={
        <div className="relative w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            className={`${inputClass} pl-9`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="파일명 검색"
          />
        </div>
      }
    >
      {notice && (
        <div className="mb-4">
          <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>
        </div>
      )}

      {loading && documents.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-slate-500">
          <Loader2 className="w-4 h-4 animate-spin" />
          불러오는 중…
        </div>
      ) : documents.length === 0 ? (
        <EmptyState icon={FileText} title={search ? '검색 결과가 없습니다' : '등록된 문서가 없습니다'}>
          {!search && '위의 자료 추가에서 문서를 올려보세요.'}
        </EmptyState>
      ) : (
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-y border-slate-100 bg-slate-50 text-left text-[12px] text-slate-500">
                <th className="px-5 py-2 font-medium">파일명</th>
                <th className="px-3 py-2 font-medium">구분</th>
                <th className="px-3 py-2 font-medium text-right">청크</th>
                {isSecurity && (
                  <>
                    <th className="px-3 py-2 font-medium">표준</th>
                    <th className="px-3 py-2 font-medium">섹션</th>
                  </>
                )}
                <th className="px-3 py-2 font-medium text-right">크기</th>
                <th className="px-3 py-2 font-medium text-right">등록일</th>
                <th className="px-5 py-2 font-medium text-right w-[190px]"><span className="sr-only">작업</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {documents.map((doc) => {
                const builtin = doc.source === 'builtin';
                const editing = editingId === doc.id;
                return (
                  <tr key={doc.id} className="hover:bg-slate-50/60">
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-2 max-w-[280px]">
                        <span className="truncate text-slate-900" title={doc.original_filename}>{doc.original_filename}</span>
                        {builtin && (
                          <span className="inline-flex items-center gap-0.5 rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] text-slate-500 flex-shrink-0">
                            <Lock size={10} />
                            내장
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">{COLLECTION_NAMES[doc.collection_name] || doc.collection_name}</td>
                    <td className="px-3 py-2.5 text-right text-slate-600 tabular-nums">{doc.chunk_count}</td>
                    {isSecurity && (
                      <>
                        <td className="px-3 py-2.5 text-slate-600">
                          {editing ? (
                            <input className={cellInput} value={editData.standard} onChange={(e) => setEditData({ ...editData, standard: e.target.value })} />
                          ) : (doc.standard || '-')}
                        </td>
                        <td className="px-3 py-2.5 text-slate-600">
                          {editing ? (
                            <input className={cellInput} value={editData.section} onChange={(e) => setEditData({ ...editData, section: e.target.value })} />
                          ) : (doc.section || '-')}
                        </td>
                      </>
                    )}
                    <td className="px-3 py-2.5 text-right text-slate-500 whitespace-nowrap tabular-nums">{formatFileSize(doc.file_size_bytes)}</td>
                    <td className="px-3 py-2.5 text-right text-slate-500 whitespace-nowrap tabular-nums">
                      {new Date(doc.created_at).toLocaleDateString('ko-KR')}
                    </td>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        {builtin ? null : editing ? (
                          <>
                            <button type="button" onClick={() => handleEditSave(doc.id)} className="p-1.5 rounded-md text-primary-600 hover:bg-primary-50" title="저장">
                              <Check size={15} />
                            </button>
                            <button type="button" onClick={() => setEditingId(null)} className="p-1.5 rounded-md text-slate-400 hover:bg-slate-100" title="취소">
                              <X size={15} />
                            </button>
                          </>
                        ) : confirmId === doc.id ? (
                          // 두 번 눌러 삭제 (브라우저 확인창 대신)
                          <>
                            <span className="text-[11.5px] text-slate-500 mr-1 whitespace-nowrap">청크도 삭제할까요?</span>
                            <button
                              type="button"
                              onClick={() => handleDelete(doc)}
                              disabled={deletingId === doc.id}
                              className="inline-flex items-center gap-1 rounded-md bg-red-600 px-2 py-1 text-[12px] font-medium text-white hover:bg-red-700 disabled:opacity-60"
                            >
                              {deletingId === doc.id && <Loader2 size={12} className="animate-spin" />}
                              삭제
                            </button>
                            <button type="button" onClick={() => setConfirmId(null)} className="rounded-md px-2 py-1 text-[12px] text-slate-500 hover:bg-slate-100">
                              취소
                            </button>
                          </>
                        ) : (
                          <>
                            {isSecurity && (
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingId(doc.id);
                                  setEditData({ guide_name: doc.guide_name || '', standard: doc.standard || '', section: doc.section || '' });
                                }}
                                className="p-1.5 rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                                title="메타데이터 편집"
                              >
                                <Pencil size={15} />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => setConfirmId(doc.id)}
                              className="p-1.5 rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600"
                              title="삭제"
                            >
                              <Trash2 size={15} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};

export default DocumentList;
