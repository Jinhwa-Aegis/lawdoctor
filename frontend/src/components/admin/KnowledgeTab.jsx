import { useEffect, useState } from 'react'
import {
  BookOpen, Database, FileText, Gavel, Landmark, Library, RefreshCw, Upload, X,
} from 'lucide-react'
import {
  getSecurityMetadata, getVectorStats, ingestBuiltinSecurity, ingestLaws, ingestPrecedents,
  uploadLegalPdf, uploadSecurityPdf,
} from '../../api/client'
import FileUpload from '../FileUpload'
import DocumentList from '../DocumentList'
import { Button, Card, Field, Notice, Segmented, inputClass } from './AdminUI'

const COLLECTION_LABELS = {
  consultations: { label: '자문·참고 문서', icon: FileText },
  laws: { label: '법령 조문', icon: Landmark },
  precedents: { label: '판례', icon: Gavel },
  security_guides: { label: '보안 가이드', icon: BookOpen },
  security_incidents: { label: '보안 사고 사례', icon: FileText },
}

const DOMAINS = {
  legal: {
    collections: ['laws', 'consultations', 'precedents'],
    methods: [
      { value: 'upload', label: '문서 업로드', icon: Upload },
      { value: 'laws', label: '법령 가져오기', icon: Landmark },
      { value: 'precedents', label: '판례 가져오기', icon: Gavel },
    ],
  },
  security: {
    collections: ['security_guides', 'security_incidents'],
    methods: [
      { value: 'upload', label: '문서 업로드', icon: Upload },
      { value: 'builtin', label: '내장 지식베이스', icon: Library },
    ],
  },
}

const DEFAULT_LAWS = '개인정보 보호법\n정보통신망 이용촉진 및 정보보호 등에 관한 법률\n민법\n상법\n공동주택관리법\n주택법'
const DEFAULT_PREC_KEYWORDS = '개인정보\n계약 해지\n하자담보\n공동주택 관리비\n정보통신망'
const EMPTY_SECURITY_META = { collection: 'security_guides', guide_name: '', standard: '', section: '', customStandard: '', customSection: '' }

const ACCEPT = '.pdf,.docx,.hwp,.hwpx'
const toLines = (text) => text.split('\n').map((s) => s.trim()).filter(Boolean)

function CollectionStats({ collections, stats, loading, onRefresh }) {
  const cols = { 2: 'md:grid-cols-2', 3: 'md:grid-cols-3' }[collections.length] || 'md:grid-cols-4'
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[12.5px] font-medium text-slate-600">벡터 DB 적재 현황</p>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-slate-500 hover:bg-white hover:text-slate-800 disabled:opacity-60"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          새로고침
        </button>
      </div>
      <div className={`grid grid-cols-2 ${cols} gap-3`}>
        {collections.map((name) => {
          const meta = COLLECTION_LABELS[name]
          const stat = stats?.[name]
          return (
            <div key={name} className="rounded-2xl border border-slate-200 bg-white px-4 py-3.5">
              <p className="flex items-center gap-1.5 text-[12px] text-slate-500">
                <meta.icon className="w-3.5 h-3.5" />
                {meta.label}
              </p>
              <p className="mt-1 text-[24px] font-bold leading-tight text-slate-900 tabular-nums">
                {loading && !stats ? '—' : (stat?.count ?? 0).toLocaleString('ko-KR')}
                <span className="ml-1 text-[12px] font-normal text-slate-400">청크</span>
              </p>
              <p className={`mt-0.5 text-[11.5px] ${stat?.error ? 'text-amber-600' : 'text-slate-400'}`}>
                {stat?.error || name}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SelectedFile({ file, onClear }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <FileText className="w-5 h-5 text-slate-500 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-slate-900 truncate">{file.name}</p>
        <p className="text-[11.5px] text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
      </div>
      <button type="button" onClick={onClear} className="text-slate-400 hover:text-slate-700" aria-label="파일 선택 취소">
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

function CountList({ results, unit = '청크' }) {
  return (
    <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5">
      {Object.entries(results).map(([name, count]) => (
        <li key={name} className="flex justify-between gap-2">
          <span className="truncate">{name}</span>
          <span className={`tabular-nums ${count === 0 ? 'text-amber-700' : ''}`}>{count === 0 ? '찾지 못함' : `${count}${unit}`}</span>
        </li>
      ))}
    </ul>
  )
}

function SecurityMetaFields({ meta, setMeta, metadataMap }) {
  const sections = meta.standard && meta.standard !== '__custom__' ? metadataMap[meta.standard] || [] : []
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <Field label="자료 유형">
        <select className={inputClass} value={meta.collection} onChange={(e) => setMeta({ ...meta, collection: e.target.value })}>
          <option value="security_guides">보안 가이드</option>
          <option value="security_incidents">보안 사고 사례</option>
        </select>
      </Field>
      <Field label="가이드명">
        <input className={inputClass} value={meta.guide_name} placeholder="예: ISMS-P 인증기준 해설서"
          onChange={(e) => setMeta({ ...meta, guide_name: e.target.value })} />
      </Field>
      <Field label="표준">
        <select
          className={inputClass}
          value={meta.standard}
          onChange={(e) => setMeta({ ...meta, standard: e.target.value, section: '', customSection: '' })}
        >
          <option value="">선택 안 함</option>
          {Object.keys(metadataMap).map((s) => <option key={s} value={s}>{s}</option>)}
          <option value="__custom__">직접 입력</option>
        </select>
        {meta.standard === '__custom__' && (
          <input className={`${inputClass} mt-2`} value={meta.customStandard} placeholder="새 표준명"
            onChange={(e) => setMeta({ ...meta, customStandard: e.target.value })} />
        )}
      </Field>
      <Field label="섹션">
        <select
          className={inputClass}
          value={meta.section}
          disabled={!meta.standard}
          onChange={(e) => setMeta({ ...meta, section: e.target.value })}
        >
          <option value="">선택 안 함</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          <option value="__custom__">직접 입력</option>
        </select>
        {meta.section === '__custom__' && (
          <input className={`${inputClass} mt-2`} value={meta.customSection} placeholder="새 섹션명"
            onChange={(e) => setMeta({ ...meta, customSection: e.target.value })} />
        )}
      </Field>
    </div>
  )
}

export default function KnowledgeTab({ domain }) {
  const config = DOMAINS[domain]
  const [method, setMethod] = useState('upload')
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const [file, setFile] = useState(null)
  const [securityMeta, setSecurityMeta] = useState(EMPTY_SECURITY_META)
  const [metadataMap, setMetadataMap] = useState({})
  const [lawNames, setLawNames] = useState(DEFAULT_LAWS)
  const [precKeywords, setPrecKeywords] = useState(DEFAULT_PREC_KEYWORDS)
  const [precMax, setPrecMax] = useState(10)

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null) // { tone, title, body }

  const loadStats = async () => {
    setStatsLoading(true)
    try {
      setStats(await getVectorStats())
    } catch (e) {
      setResult({ tone: 'error', title: '벡터 DB 통계를 불러오지 못했습니다', body: e.message })
    } finally {
      setStatsLoading(false)
    }
  }

  const loadMetadata = () => {
    if (domain !== 'security') return
    getSecurityMetadata().then(setMetadataMap).catch(() => setMetadataMap({}))
  }

  useEffect(() => {
    setMethod('upload')
    setFile(null)
    setResult(null)
    loadStats()
    loadMetadata()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain])

  /** 적재 작업 공통 처리 — 실행 중 표시, 결과 알림, 통계 갱신 */
  const run = async (task, onSuccess) => {
    setRunning(true)
    setResult(null)
    try {
      const data = await task()
      setResult({ tone: 'success', ...onSuccess(data) })
      loadStats()
    } catch (e) {
      setResult({ tone: 'error', title: '작업에 실패했습니다', body: e.message })
    } finally {
      setRunning(false)
    }
  }

  const handleUpload = () => {
    if (domain === 'legal') {
      return run(() => uploadLegalPdf(file), (r) => {
        setFile(null)
        setRefreshKey((k) => k + 1)
        return { title: `${r.filename} 적재 완료`, body: `${COLLECTION_LABELS[r.collection]?.label || r.collection}에 ${r.chunks}개 청크를 넣었습니다.` }
      })
    }
    const meta = {
      collection: securityMeta.collection,
      guide_name: securityMeta.guide_name,
      standard: securityMeta.standard === '__custom__' ? securityMeta.customStandard : securityMeta.standard,
      section: securityMeta.section === '__custom__' ? securityMeta.customSection : securityMeta.section,
    }
    return run(() => uploadSecurityPdf(file, meta), (r) => {
      setFile(null)
      setSecurityMeta(EMPTY_SECURITY_META)
      setRefreshKey((k) => k + 1)
      loadMetadata()
      return { title: `${r.filename} 적재 완료`, body: `${COLLECTION_LABELS[r.collection]?.label || r.collection}에 ${r.chunks}개 청크를 넣었습니다.` }
    })
  }

  const busyLabel = running ? '처리 중… 법령·판례는 몇 분 걸릴 수 있습니다' : null

  return (
    <div className="space-y-5">
      <CollectionStats collections={config.collections} stats={stats} loading={statsLoading} onRefresh={loadStats} />

      <Card
        title="자료 추가"
        description="추가한 자료는 바로 검색 근거로 쓰입니다."
        icon={Database}
        action={<Segmented options={config.methods} value={method} onChange={(m) => { setMethod(m); setResult(null) }} />}
      >
        <div className="space-y-4">
          {method === 'upload' && (
            <>
              <p className="text-[12.5px] text-slate-500">
                {domain === 'legal'
                  ? '변호사 자문 이력이나 사내 법률 참고 자료를 올리면 파싱·임베딩해 자문·참고 문서로 적재합니다.'
                  : '보안 가이드나 사고 사례 문서를 올립니다. 표준·섹션을 지정하면 답변에 출처로 함께 표시됩니다.'}
              </p>
              {domain === 'security' && (
                <SecurityMetaFields meta={securityMeta} setMeta={setSecurityMeta} metadataMap={metadataMap} />
              )}
              {file ? (
                <SelectedFile file={file} onClear={() => setFile(null)} />
              ) : (
                <FileUpload onFileSelect={setFile} accept={ACCEPT} maxSizeMB={50} />
              )}
              <div className="flex justify-end">
                <Button icon={Upload} loading={running} disabled={!file} onClick={handleUpload}>업로드하고 적재</Button>
              </div>
            </>
          )}

          {method === 'laws' && (
            <>
              <p className="text-[12.5px] text-slate-500">
                국가법령정보센터에서 현행 법령 조문을 가져옵니다. 법령명이 정확히 일치해야 하며, 같은 법령은 최신 조문으로 덮어씁니다.
              </p>
              <Field label="법령명" hint="한 줄에 하나씩 입력">
                <textarea rows={6} className={`${inputClass} leading-relaxed`} value={lawNames} onChange={(e) => setLawNames(e.target.value)} />
              </Field>
              <div className="flex items-center justify-end gap-3">
                {busyLabel && <span className="text-[12px] text-slate-500">{busyLabel}</span>}
                <Button
                  icon={Landmark}
                  loading={running}
                  disabled={toLines(lawNames).length === 0}
                  onClick={() => run(() => ingestLaws(toLines(lawNames)), (r) => ({
                    title: `법령 ${Object.keys(r.results).length}건 · ${r.total_chunks}개 청크 적재`,
                    body: <CountList results={r.results} />,
                  }))}
                >
                  법령 가져오기
                </Button>
              </div>
            </>
          )}

          {method === 'precedents' && (
            <>
              <p className="text-[12.5px] text-slate-500">키워드로 판례를 검색해 판례 컬렉션에 적재합니다.</p>
              <div className="grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3">
                <Field label="검색 키워드" hint="한 줄에 하나씩 입력">
                  <textarea rows={5} className={`${inputClass} leading-relaxed`} value={precKeywords} onChange={(e) => setPrecKeywords(e.target.value)} />
                </Field>
                <Field label="키워드당 최대 판례 수" hint="1~100">
                  <input
                    type="number" min={1} max={100} className={inputClass} value={precMax}
                    onChange={(e) => setPrecMax(Math.min(100, Math.max(1, parseInt(e.target.value, 10) || 1)))}
                  />
                </Field>
              </div>
              <div className="flex items-center justify-end gap-3">
                {busyLabel && <span className="text-[12px] text-slate-500">{busyLabel}</span>}
                <Button
                  icon={Gavel}
                  loading={running}
                  disabled={toLines(precKeywords).length === 0}
                  onClick={() => run(() => ingestPrecedents(toLines(precKeywords), precMax), (r) => ({
                    title: `판례 ${r.total_chunks}개 청크 적재`,
                    body: <CountList results={r.results} />,
                  }))}
                >
                  판례 가져오기
                </Button>
              </div>
            </>
          )}

          {method === 'builtin' && (
            <>
              <p className="text-[12.5px] text-slate-500">
                ISMS-P, OWASP Top 10, KISA 가이드 등 서비스에 내장된 보안 지식베이스를 적재합니다. 다시 실행해도 중복되지 않습니다.
              </p>
              <div className="flex justify-end">
                <Button
                  icon={Library}
                  loading={running}
                  onClick={() => run(ingestBuiltinSecurity, (r) => ({
                    title: '내장 지식베이스 적재 완료',
                    body: `보안 가이드 ${r.builtin?.security_guides ?? 0}건 · 보안 사고 사례 ${r.builtin?.security_incidents ?? 0}건`,
                  }))}
                >
                  내장 지식베이스 적재
                </Button>
              </div>
            </>
          )}

          {result && (
            <Notice tone={result.tone} title={result.title} onClose={() => setResult(null)}>{result.body}</Notice>
          )}
        </div>
      </Card>

      <DocumentList
        documentType={domain}
        refreshKey={refreshKey}
        onDocumentsChanged={() => {
          loadStats()
          loadMetadata()
        }}
      />
    </div>
  )
}
