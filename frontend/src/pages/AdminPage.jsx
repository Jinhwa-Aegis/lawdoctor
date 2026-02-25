import React, { useState, useEffect } from 'react';
import {
  Settings, User, TrendingUp, MessageSquare, ThumbsUp, Users, Plus, X,
  Database, Upload, FileText, Shield, Scale, Loader2, CheckCircle, AlertCircle,
} from 'lucide-react';
import {
  getDashboard, getUsers, createUser,
  uploadLegalPdf, uploadSecurityPdf, getVectorStats, getSecurityMetadata,
  ingestLaws, ingestPrecedents,
} from '../api/client';
import FileUpload from '../components/FileUpload';
import DocumentList from '../components/DocumentList';

const TABS = [
  { id: 'dashboard', label: '대시보드', icon: TrendingUp },
  { id: 'legal', label: '법률 자료 관리', icon: Scale },
  { id: 'security', label: '보안 자료 관리', icon: Shield },
];

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-gray-600 mb-1">{label}</p>
        <p className="text-3xl font-bold text-gray-900">{value}</p>
      </div>
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon size={24} className="text-white" />
      </div>
    </div>
  </div>
);

const CollectionStatsCard = ({ collections, statsLoading, vectorStats, onRefresh }) => (
  <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
    <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
      <Database size={20} className="text-blue-600" />
      벡터 DB 컬렉션 통계
    </h3>
    {statsLoading ? (
      <div className="flex items-center justify-center py-4">
        <Loader2 size={24} className="animate-spin text-blue-600" />
        <span className="ml-2 text-gray-600">로딩 중...</span>
      </div>
    ) : vectorStats ? (
      <div className="grid grid-cols-2 gap-4">
        {collections.map((name) => {
          const stat = vectorStats[name];
          return (
            <div key={name} className="bg-gray-50 rounded-lg p-4">
              <p className="text-sm text-gray-500 mb-1">{name}</p>
              <p className="text-2xl font-bold text-gray-900">
                {stat?.count ?? 0}
              </p>
              <p className="text-xs text-gray-400">문서 수</p>
            </div>
          );
        })}
      </div>
    ) : (
      <p className="text-gray-500 text-sm">통계를 불러올 수 없습니다.</p>
    )}
    <button
      onClick={onRefresh}
      disabled={statsLoading}
      className="mt-4 w-full px-4 py-2 text-sm border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
    >
      새로고침
    </button>
  </div>
);

const UploadHistory = ({ history }) => {
  if (history.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
        <FileText size={20} className="text-green-600" />
        업로드 이력
      </h3>
      <div className="space-y-3">
        {history.map((item, index) => (
          <div key={index} className="flex items-center gap-3 p-3 bg-green-50 rounded-lg">
            <CheckCircle size={20} className="text-green-600 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">
                {item.filename}
              </p>
              <p className="text-xs text-gray-500">
                {item.collection} | {item.chunks}개 청크 | {item.timestamp}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const AdminPage = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [users, setUsers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [newUser, setNewUser] = useState({
    username: '',
    display_name: '',
    role: 'staff',
  });

  // 벡터 DB 통계
  const [vectorStats, setVectorStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // 법률 PDF 업로드
  const [legalFile, setLegalFile] = useState(null);
  const [legalUploading, setLegalUploading] = useState(false);
  const [legalHistory, setLegalHistory] = useState([]);

  // 보안 PDF 업로드
  const [securityFile, setSecurityFile] = useState(null);
  const [securityUploading, setSecurityUploading] = useState(false);
  const [securityHistory, setSecurityHistory] = useState([]);
  const [securityMeta, setSecurityMeta] = useState({
    collection: 'security_guides',
    guide_name: '',
    standard: '',
    section: '',
    customStandard: '',
    customSection: '',
  });

  // 보안 메타데이터 (표준/섹션 목록)
  const [securityMetadataMap, setSecurityMetadataMap] = useState({});

  // 문서 목록 갱신 키
  const [legalRefreshKey, setLegalRefreshKey] = useState(0);
  const [securityRefreshKey, setSecurityRefreshKey] = useState(0);

  // 법령 API 적재
  const [lawIngestLoading, setLawIngestLoading] = useState(false);
  const [lawIngestResult, setLawIngestResult] = useState(null);
  const [lawNamesText, setLawNamesText] = useState(
    '개인정보 보호법\n정보통신망 이용촉진 및 정보보호 등에 관한 법률\n민법\n상법\n공동주택관리법\n주택법'
  );

  // 판례 API 적재
  const [precIngestLoading, setPrecIngestLoading] = useState(false);
  const [precIngestResult, setPrecIngestResult] = useState(null);
  const [precKeywordsText, setPrecKeywordsText] = useState(
    '개인정보\n계약 해지\n하자담보\n공동주택 관리비\n정보통신망'
  );
  const [precMaxPerKeyword, setPrecMaxPerKeyword] = useState(10);

  // 내장 지식베이스 적재
  const [builtinLoading, setBuiltinLoading] = useState(false);
  const [builtinResult, setBuiltinResult] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (activeTab === 'legal' || activeTab === 'security') {
      loadVectorStats();
    }
    if (activeTab === 'security') {
      loadSecurityMetadata();
    }
  }, [activeTab]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [dashboardData, usersData] = await Promise.all([
        getDashboard(),
        getUsers()
      ]);
      setDashboard(dashboardData);
      setUsers(usersData);
    } catch (error) {
      console.error('데이터 로드 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadVectorStats = async () => {
    setStatsLoading(true);
    try {
      const stats = await getVectorStats();
      setVectorStats(stats);
    } catch (error) {
      console.error('벡터 통계 로드 실패:', error);
    } finally {
      setStatsLoading(false);
    }
  };

  const loadSecurityMetadata = async () => {
    try {
      const data = await getSecurityMetadata();
      setSecurityMetadataMap(data);
    } catch (error) {
      console.error('보안 메타데이터 로드 실패:', error);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();

    if (!newUser.username || !newUser.display_name) {
      alert('모든 필드를 입력해주세요.');
      return;
    }

    try {
      await createUser(newUser);
      setShowAddUserModal(false);
      setNewUser({ username: '', display_name: '', role: 'staff' });
      loadData();
    } catch (error) {
      console.error('사용자 생성 실패:', error);
      alert('사용자 생성에 실패했습니다.');
    }
  };

  const handleLegalUpload = async () => {
    if (!legalFile) return;

    setLegalUploading(true);
    try {
      const result = await uploadLegalPdf(legalFile);
      setLegalHistory((prev) => [
        { ...result, timestamp: new Date().toLocaleTimeString('ko-KR') },
        ...prev,
      ]);
      setLegalFile(null);
      setLegalRefreshKey((k) => k + 1);
      loadVectorStats();
    } catch (error) {
      console.error('법률 PDF 업로드 실패:', error);
      alert(error.message || '업로드에 실패했습니다.');
    } finally {
      setLegalUploading(false);
    }
  };

  const handleSecurityUpload = async () => {
    if (!securityFile) return;

    // "기타" 선택 시 커스텀 값 사용
    const resolvedMeta = {
      collection: securityMeta.collection,
      guide_name: securityMeta.guide_name,
      standard: securityMeta.standard === '__custom__'
        ? securityMeta.customStandard
        : securityMeta.standard,
      section: securityMeta.section === '__custom__'
        ? securityMeta.customSection
        : securityMeta.section,
    };

    setSecurityUploading(true);
    try {
      const result = await uploadSecurityPdf(securityFile, resolvedMeta);
      setSecurityHistory((prev) => [
        { ...result, timestamp: new Date().toLocaleTimeString('ko-KR') },
        ...prev,
      ]);
      setSecurityFile(null);
      setSecurityMeta({
        collection: 'security_guides',
        guide_name: '',
        standard: '',
        section: '',
        customStandard: '',
        customSection: '',
      });
      // 새 표준/섹션이 추가되었을 수 있으므로 메타데이터 갱신
      setSecurityRefreshKey((k) => k + 1);
      loadVectorStats();
      loadSecurityMetadata();
    } catch (error) {
      console.error('보안 문서 업로드 실패:', error);
      alert(error.message || '업로드에 실패했습니다.');
    } finally {
      setSecurityUploading(false);
    }
  };

  const handleLawIngest = async () => {
    setLawIngestLoading(true);
    setLawIngestResult(null);
    try {
      const lawNames = lawNamesText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await ingestLaws(lawNames.length > 0 ? lawNames : null);
      setLawIngestResult(result);
      loadVectorStats();
    } catch (error) {
      console.error('법령 적재 실패:', error);
      alert(error.message || '법령 적재에 실패했습니다.');
    } finally {
      setLawIngestLoading(false);
    }
  };

  const handlePrecedentIngest = async () => {
    setPrecIngestLoading(true);
    setPrecIngestResult(null);
    try {
      const keywords = precKeywordsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await ingestPrecedents(
        keywords.length > 0 ? keywords : null,
        precMaxPerKeyword
      );
      setPrecIngestResult(result);
      loadVectorStats();
    } catch (error) {
      console.error('판례 적재 실패:', error);
      alert(error.message || '판례 적재에 실패했습니다.');
    } finally {
      setPrecIngestLoading(false);
    }
  };

  const handleBuiltinIngest = async () => {
    setBuiltinLoading(true);
    setBuiltinResult(null);
    try {
      const response = await fetch('/api/admin/ingest/security', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-ID': localStorage.getItem('userId') || '1',
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '내장 지식베이스 적재 실패');
      }

      const result = await response.json();
      setBuiltinResult(result);
      loadVectorStats();
    } catch (error) {
      console.error('내장 지식베이스 적재 실패:', error);
      alert(error.message || '적재에 실패했습니다.');
    } finally {
      setBuiltinLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <Settings size={48} className="animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">데이터 로드 중...</p>
        </div>
      </div>
    );
  }

  // === 탭 내용 렌더링 ===

  const renderDashboardTab = () => (
    <>
      {/* 통계 카드 */}
      {dashboard && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            icon={Users}
            label="총 사용자"
            value={dashboard.total_users || 0}
            color="bg-blue-600"
          />
          <StatCard
            icon={MessageSquare}
            label="총 세션"
            value={dashboard.total_sessions || 0}
            color="bg-green-600"
          />
          <StatCard
            icon={TrendingUp}
            label="총 메시지"
            value={dashboard.total_messages || 0}
            color="bg-purple-600"
          />
          <StatCard
            icon={ThumbsUp}
            label="피드백 긍정률"
            value={`${dashboard.positive_feedback_ratio || 0}%`}
            color="bg-orange-600"
          />
        </div>
      )}

      {/* 사용자 관리 */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <User size={24} className="text-blue-600" />
              사용자 관리
            </h2>
            <button
              onClick={() => setShowAddUserModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Plus size={20} />
              새 사용자 추가
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  이름
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  사용자명
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  역할
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  상태
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  생성일
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.length === 0 ? (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center text-gray-500">
                    등록된 사용자가 없습니다.
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                          <User size={16} className="text-blue-600" />
                        </div>
                        <span className="text-sm font-medium text-gray-900">
                          {user.display_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-gray-600">{user.username}</span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                          user.role === 'executive'
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {user.role === 'executive' ? '경영진' : '직원'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                          user.is_active
                            ? 'bg-green-100 text-green-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {user.is_active ? '활성' : '비활성'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {new Date(user.created_at).toLocaleDateString('ko-KR')}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );

  const renderLegalTab = () => (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* 업로드 영역 */}
      <div className="lg:col-span-2 space-y-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
            <Scale size={20} className="text-blue-600" />
            법률 문서 업로드
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            변호사 자문 이력이나 법률 참고 자료(PDF, DOCX, HWP)를 업로드하면 자동으로 파싱, 임베딩 후
            벡터 DB(consultations 컬렉션)에 적재됩니다.
          </p>

          {!legalFile ? (
            <FileUpload
              onFileSelect={(file) => setLegalFile(file)}
              accept=".pdf,.docx,.hwp,.hwpx"
              maxSizeMB={50}
            />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <FileText size={24} className="text-blue-600 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {legalFile.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {(legalFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <button
                  onClick={() => setLegalFile(null)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              <button
                onClick={handleLegalUpload}
                disabled={legalUploading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {legalUploading ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    적재 중...
                  </>
                ) : (
                  <>
                    <Upload size={20} />
                    업로드 및 적재
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* 법령 API 적재 */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-2">
            <Database size={20} className="text-green-600" />
            법령 API 적재
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            국가법령정보센터 Open API에서 법령 조문을 가져와 벡터 DB(laws 컬렉션)에 적재합니다.
          </p>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              법령명 (줄바꿈으로 구분)
            </label>
            <textarea
              value={lawNamesText}
              onChange={(e) => setLawNamesText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 text-sm font-mono"
            />
          </div>

          <button
            onClick={handleLawIngest}
            disabled={lawIngestLoading}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {lawIngestLoading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                법령 적재 중... (시간이 소요됩니다)
              </>
            ) : (
              <>
                <Database size={20} />
                법령 적재
              </>
            )}
          </button>

          {lawIngestResult && (
            <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={16} className="text-green-600" />
                <span className="text-sm font-medium text-green-800">
                  법령 적재 완료 (총 {lawIngestResult.total_chunks}개 청크)
                </span>
              </div>
              <div className="text-xs text-green-700 space-y-1">
                {Object.entries(lawIngestResult.results).map(([name, count]) => (
                  <p key={name}>{name}: {count}개 청크</p>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 판례 API 적재 */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-2">
            <Scale size={20} className="text-indigo-600" />
            판례 API 적재
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            국가법령정보센터 Open API에서 판례를 검색·수집하여 벡터 DB(precedents 컬렉션)에 적재합니다.
          </p>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              검색 키워드 (줄바꿈으로 구분)
            </label>
            <textarea
              value={precKeywordsText}
              onChange={(e) => setPrecKeywordsText(e.target.value)}
              rows={5}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm font-mono"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              키워드당 최대 판례 수
            </label>
            <input
              type="number"
              value={precMaxPerKeyword}
              onChange={(e) => setPrecMaxPerKeyword(Math.max(1, parseInt(e.target.value) || 1))}
              min={1}
              max={100}
              className="w-32 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm"
            />
          </div>

          <button
            onClick={handlePrecedentIngest}
            disabled={precIngestLoading}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {precIngestLoading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                판례 적재 중... (시간이 소요됩니다)
              </>
            ) : (
              <>
                <Scale size={20} />
                판례 적재
              </>
            )}
          </button>

          {precIngestResult && (
            <div className="mt-4 p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={16} className="text-indigo-600" />
                <span className="text-sm font-medium text-indigo-800">
                  판례 적재 완료 (총 {precIngestResult.total_chunks}개 청크)
                </span>
              </div>
              <div className="text-xs text-indigo-700 space-y-1">
                {Object.entries(precIngestResult.results).map(([keyword, count]) => (
                  <p key={keyword}>{keyword}: {count}개 청크</p>
                ))}
              </div>
            </div>
          )}
        </div>

        <UploadHistory history={legalHistory} />

        <DocumentList
          documentType="legal"
          refreshKey={legalRefreshKey}
          onDocumentsChanged={loadVectorStats}
        />
      </div>

      {/* 사이드바: 통계 */}
      <div>
        <CollectionStatsCard
          collections={['consultations', 'laws', 'precedents']}
          statsLoading={statsLoading}
          vectorStats={vectorStats}
          onRefresh={loadVectorStats}
        />
      </div>
    </div>
  );

  const renderSecurityTab = () => (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* 업로드 영역 */}
      <div className="lg:col-span-2 space-y-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
            <Shield size={20} className="text-purple-600" />
            보안 문서 업로드
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            보안 가이드나 보안 사고 사례 문서(PDF, DOCX, HWP)를 업로드합니다. 컬렉션과 메타데이터를 지정할 수 있습니다.
          </p>

          {/* 메타데이터 입력 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* 컬렉션 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                컬렉션
              </label>
              <select
                value={securityMeta.collection}
                onChange={(e) =>
                  setSecurityMeta({ ...securityMeta, collection: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="security_guides">보안 가이드</option>
                <option value="security_incidents">보안 사고 사례</option>
              </select>
            </div>

            {/* 가이드명 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                가이드명
              </label>
              <input
                type="text"
                value={securityMeta.guide_name}
                onChange={(e) =>
                  setSecurityMeta({ ...securityMeta, guide_name: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="예: ISMS-P 인증기준 해설서"
              />
            </div>

            {/* 표준 선택 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                표준
              </label>
              <select
                value={securityMeta.standard}
                onChange={(e) => {
                  const val = e.target.value;
                  setSecurityMeta({
                    ...securityMeta,
                    standard: val,
                    // 표준 변경 시 섹션 초기화
                    section: '',
                    customStandard: val === '__custom__' ? securityMeta.customStandard : '',
                    customSection: '',
                  });
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
              >
                <option value="">-- 선택 --</option>
                {Object.keys(securityMetadataMap).map((std) => (
                  <option key={std} value={std}>{std}</option>
                ))}
                <option value="__custom__">기타 (직접 입력)</option>
              </select>
              {securityMeta.standard === '__custom__' && (
                <input
                  type="text"
                  value={securityMeta.customStandard}
                  onChange={(e) =>
                    setSecurityMeta({ ...securityMeta, customStandard: e.target.value })
                  }
                  className="w-full mt-2 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="새 표준명 입력"
                />
              )}
            </div>

            {/* 섹션 선택 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                섹션
              </label>
              {(() => {
                const selectedStd = securityMeta.standard;
                const sections = (selectedStd && selectedStd !== '__custom__')
                  ? (securityMetadataMap[selectedStd] || [])
                  : [];

                return (
                  <>
                    <select
                      value={securityMeta.section}
                      onChange={(e) =>
                        setSecurityMeta({
                          ...securityMeta,
                          section: e.target.value,
                          customSection: e.target.value === '__custom__' ? securityMeta.customSection : '',
                        })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                      disabled={!selectedStd}
                    >
                      <option value="">-- 선택 --</option>
                      {sections.map((sec) => (
                        <option key={sec} value={sec}>{sec}</option>
                      ))}
                      <option value="__custom__">기타 (직접 입력)</option>
                    </select>
                    {securityMeta.section === '__custom__' && (
                      <input
                        type="text"
                        value={securityMeta.customSection}
                        onChange={(e) =>
                          setSecurityMeta({ ...securityMeta, customSection: e.target.value })
                        }
                        className="w-full mt-2 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
                        placeholder="새 섹션명 입력"
                      />
                    )}
                  </>
                );
              })()}
            </div>
          </div>

          {!securityFile ? (
            <FileUpload
              onFileSelect={(file) => setSecurityFile(file)}
              accept=".pdf,.docx,.hwp,.hwpx"
              maxSizeMB={50}
            />
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                <FileText size={24} className="text-purple-600 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {securityFile.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {(securityFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <button
                  onClick={() => setSecurityFile(null)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X size={20} />
                </button>
              </div>

              <button
                onClick={handleSecurityUpload}
                disabled={securityUploading}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {securityUploading ? (
                  <>
                    <Loader2 size={20} className="animate-spin" />
                    적재 중...
                  </>
                ) : (
                  <>
                    <Upload size={20} />
                    업로드 및 적재
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* 내장 지식베이스 적재 */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-2">
            <Database size={20} className="text-green-600" />
            내장 지식베이스 적재
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            ISMS-P, OWASP Top 10, KISA 가이드 등 내장된 보안 지식베이스를 벡터 DB에 적재합니다.
          </p>

          <button
            onClick={handleBuiltinIngest}
            disabled={builtinLoading}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {builtinLoading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                적재 중...
              </>
            ) : (
              <>
                <Database size={20} />
                내장 지식베이스 적재
              </>
            )}
          </button>

          {builtinResult && (
            <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle size={16} className="text-green-600" />
                <span className="text-sm font-medium text-green-800">적재 완료</span>
              </div>
              <div className="text-xs text-green-700 space-y-1">
                <p>보안 가이드: {builtinResult.builtin?.security_guides ?? 0}건</p>
                <p>보안 사고 사례: {builtinResult.builtin?.security_incidents ?? 0}건</p>
              </div>
            </div>
          )}
        </div>

        <UploadHistory history={securityHistory} />

        <DocumentList
          documentType="security"
          refreshKey={securityRefreshKey}
          onDocumentsChanged={() => {
            loadVectorStats();
            loadSecurityMetadata();
          }}
        />
      </div>

      {/* 사이드바: 통계 */}
      <div>
        <CollectionStatsCard
          collections={['security_guides', 'security_incidents']}
          statsLoading={statsLoading}
          vectorStats={vectorStats}
          onRefresh={loadVectorStats}
        />
      </div>
    </div>
  );

  return (
    <div className="bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* 헤더 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Settings size={32} className="text-blue-600" />
            <h1 className="text-3xl font-bold text-gray-900">관리자 대시보드</h1>
          </div>
          <p className="text-gray-600">시스템 통계, 사용자 관리, 자료 관리</p>
        </div>

        {/* 탭 네비게이션 */}
        <div className="flex gap-1 mb-8 bg-white rounded-lg shadow-sm border border-gray-200 p-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <Icon size={18} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* 탭 내용 */}
        {activeTab === 'dashboard' && renderDashboardTab()}
        {activeTab === 'legal' && renderLegalTab()}
        {activeTab === 'security' && renderSecurityTab()}
      </div>

      {/* 사용자 추가 모달 */}
      {showAddUserModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-gray-900">새 사용자 추가</h3>
              <button
                onClick={() => setShowAddUserModal(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  사용자명
                </label>
                <input
                  type="text"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="hong.gildong"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  표시 이름
                </label>
                <input
                  type="text"
                  value={newUser.display_name}
                  onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="홍길동"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  역할
                </label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="staff">직원</option>
                  <option value="executive">경영진</option>
                </select>
              </div>

              <div className="flex gap-2 mt-6">
                <button
                  type="button"
                  onClick={() => setShowAddUserModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  추가
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPage;
