import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText, Search, Trash2, Edit3, Check, X, Loader2, AlertCircle, Lock,
} from 'lucide-react';
import { getDocuments, updateDocument, deleteDocument } from '../api/client';

const DocumentList = ({ documentType, refreshKey, onDocumentsChanged }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editData, setEditData] = useState({});
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { document_type: documentType };
      if (search.trim()) params.search = search.trim();
      const data = await getDocuments(params);
      setDocuments(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [documentType, search]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments, refreshKey]);

  const handleEdit = (doc) => {
    setEditingId(doc.id);
    setEditData({
      guide_name: doc.guide_name || '',
      standard: doc.standard || '',
      section: doc.section || '',
    });
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditData({});
  };

  const handleEditSave = async (id) => {
    try {
      await updateDocument(id, editData);
      setEditingId(null);
      setEditData({});
      loadDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      setDeletingId(id);
      await deleteDocument(id);
      loadDocuments();
      onDocumentsChanged?.();
    } catch (err) {
      alert(err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const confirmDelete = (doc) => {
    if (window.confirm(`"${doc.original_filename}" 문서를 삭제하시겠습니까?\n벡터 DB의 청크도 함께 삭제됩니다.`)) {
      handleDelete(doc.id);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  const isBuiltin = (doc) => doc.source === 'builtin';
  const isSecurity = documentType === 'security';

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
        <FileText size={20} className="text-indigo-600" />
        업로드 문서 관리
      </h3>

      {/* 검색 */}
      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="파일명으로 검색..."
          className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div className="flex items-center gap-2 p-3 mb-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* 로딩 */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={24} className="animate-spin text-indigo-600" />
          <span className="ml-2 text-gray-600 text-sm">로딩 중...</span>
        </div>
      ) : documents.length === 0 ? (
        <p className="text-center text-gray-500 text-sm py-8">
          등록된 문서가 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">파일명</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">컬렉션</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">청크</th>
                {isSecurity && (
                  <>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">표준</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">섹션</th>
                  </>
                )}
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">크기</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">등록일</th>
                <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  {/* 파일명 */}
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2 max-w-[200px]">
                      <span className="truncate text-gray-900" title={doc.original_filename}>
                        {doc.original_filename}
                      </span>
                      {isBuiltin(doc) && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-gray-200 text-gray-600 rounded">
                          <Lock size={10} />
                          내장
                        </span>
                      )}
                    </div>
                  </td>

                  {/* 컬렉션 */}
                  <td className="px-3 py-2.5 text-gray-600">{doc.collection_name}</td>

                  {/* 청크 수 */}
                  <td className="px-3 py-2.5 text-right text-gray-600">{doc.chunk_count}</td>

                  {/* 보안 자료 메타데이터 (인라인 편집) */}
                  {isSecurity && (
                    <>
                      <td className="px-3 py-2.5">
                        {editingId === doc.id ? (
                          <input
                            type="text"
                            value={editData.standard}
                            onChange={(e) => setEditData({ ...editData, standard: e.target.value })}
                            className="w-full px-2 py-1 border border-indigo-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                        ) : (
                          <span className="text-gray-600">{doc.standard || '-'}</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5">
                        {editingId === doc.id ? (
                          <input
                            type="text"
                            value={editData.section}
                            onChange={(e) => setEditData({ ...editData, section: e.target.value })}
                            className="w-full px-2 py-1 border border-indigo-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                        ) : (
                          <span className="text-gray-600">{doc.section || '-'}</span>
                        )}
                      </td>
                    </>
                  )}

                  {/* 파일 크기 */}
                  <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">
                    {formatFileSize(doc.file_size_bytes)}
                  </td>

                  {/* 등록일 */}
                  <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">
                    {new Date(doc.created_at).toLocaleDateString('ko-KR')}
                  </td>

                  {/* 액션 */}
                  <td className="px-3 py-2.5">
                    <div className="flex items-center justify-center gap-1">
                      {isBuiltin(doc) ? (
                        <span className="text-gray-300 text-xs">-</span>
                      ) : editingId === doc.id ? (
                        <>
                          <button
                            onClick={() => handleEditSave(doc.id)}
                            className="p-1 text-green-600 hover:bg-green-50 rounded transition-colors"
                            title="저장"
                          >
                            <Check size={16} />
                          </button>
                          <button
                            onClick={handleEditCancel}
                            className="p-1 text-gray-400 hover:bg-gray-100 rounded transition-colors"
                            title="취소"
                          >
                            <X size={16} />
                          </button>
                        </>
                      ) : (
                        <>
                          {isSecurity && (
                            <button
                              onClick={() => handleEdit(doc)}
                              className="p-1 text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                              title="메타데이터 편집"
                            >
                              <Edit3 size={16} />
                            </button>
                          )}
                          <button
                            onClick={() => confirmDelete(doc)}
                            disabled={deletingId === doc.id}
                            className="p-1 text-red-500 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                            title="삭제"
                          >
                            {deletingId === doc.id ? (
                              <Loader2 size={16} className="animate-spin" />
                            ) : (
                              <Trash2 size={16} />
                            )}
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DocumentList;
