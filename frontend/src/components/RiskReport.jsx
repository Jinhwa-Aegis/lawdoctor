import React from 'react';
import { AlertTriangle, Shield, FileText, CheckCircle } from 'lucide-react';

const RiskReport = ({ result }) => {
  if (!result) return null;

  const getRiskBadge = (level) => {
    const configs = {
      high: { label: '높음', color: 'bg-red-100 text-red-800 border-red-200' },
      medium: { label: '보통', color: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
      low: { label: '낮음', color: 'bg-green-100 text-green-800 border-green-200' }
    };

    const config = configs[level] || configs.medium;

    return (
      <span className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border ${config.color}`}>
        <Shield size={14} />
        {config.label}
      </span>
    );
  };

  const getRiskIcon = (level) => {
    const configs = {
      high: { icon: AlertTriangle, color: 'text-red-600' },
      medium: { icon: AlertTriangle, color: 'text-yellow-600' },
      low: { icon: CheckCircle, color: 'text-green-600' }
    };

    const config = configs[level] || configs.medium;
    const Icon = config.icon;

    return <Icon size={20} className={config.color} />;
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* 헤더 */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">계약서 분석 결과</h2>
            <p className="text-sm text-gray-600 mt-1">
              {result.contract_type || '일반 계약서'}
            </p>
          </div>
          {getRiskBadge(result.overall_risk_level || result.overall_risk)}
        </div>
      </div>

      {/* 요약 */}
      {result.summary && (
        <div className="p-6 border-b border-gray-200 bg-blue-50">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">요약</h3>
          <p className="text-gray-700 whitespace-pre-wrap">{result.summary}</p>
        </div>
      )}

      {/* 리스크 항목 */}
      {((result.risks && result.risks.length > 0) || (result.risk_items && result.risk_items.length > 0)) && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <AlertTriangle size={20} className="text-red-600" />
            발견된 리스크 ({(result.risks || result.risk_items).length}건)
          </h3>
          <div className="space-y-4">
            {(result.risks || result.risk_items).map((risk, index) => (
              <div
                key={index}
                className="p-4 border border-gray-200 rounded-lg hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-3">
                  {getRiskIcon(risk.severity || risk.risk_level)}
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-semibold text-gray-900">{risk.clause}</h4>
                      {getRiskBadge(risk.severity || risk.risk_level)}
                    </div>

                    <p className="text-sm text-gray-700 mb-3">{risk.description}</p>

                    {((risk.legal_basis && risk.legal_basis.length > 0) || (typeof risk.legal_basis === 'string')) && (
                      <div className="mb-3 p-3 bg-gray-50 rounded">
                        <p className="text-xs font-medium text-gray-700 mb-1">
                          근거 법령
                        </p>
                        {Array.isArray(risk.legal_basis) ? (
                          <ul className="space-y-1">
                            {risk.legal_basis.map((basis, idx) => (
                              <li key={idx} className="text-xs text-gray-600">
                                {basis}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-gray-600">{risk.legal_basis}</p>
                        )}
                      </div>
                    )}

                    {(risk.recommendation || risk.suggestion) && (
                      <div className="p-3 bg-blue-50 rounded border border-blue-200">
                        <p className="text-xs font-medium text-blue-900 mb-1">
                          수정 제안
                        </p>
                        <p className="text-sm text-blue-800">{risk.recommendation || risk.suggestion}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 누락 조항 */}
      {result.missing_clauses && result.missing_clauses.length > 0 && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FileText size={20} className="text-orange-600" />
            누락된 조항 ({result.missing_clauses.length}건)
          </h3>
          <div className="space-y-3">
            {result.missing_clauses.map((clause, index) => (
              <div
                key={index}
                className="p-4 border border-orange-200 bg-orange-50 rounded-lg"
              >
                <h4 className="font-semibold text-gray-900 mb-1">{clause.name || clause.clause_name}</h4>
                <p className="text-sm text-gray-700">{clause.description}</p>
                {clause.importance && (
                  <p className="text-xs text-gray-600 mt-2">
                    중요도: {clause.importance}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 종합 의견 */}
      {(result.overall_opinion || result.recommendation) && (
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">종합 의견</h3>
          <p className="text-gray-700 whitespace-pre-wrap">{result.overall_opinion || result.recommendation}</p>
        </div>
      )}

      {/* 면책 문구 */}
      <div className="p-6 bg-gray-50">
        <div className="flex items-start gap-3">
          <AlertTriangle size={20} className="text-gray-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-gray-900 mb-2">법률 자문 면책</p>
            <p className="text-xs text-gray-600 leading-relaxed">
              본 분석 결과는 AI 기반 자동 검토 시스템에 의한 것으로, 참고용 정보 제공을 목적으로 합니다.
              실제 계약서 체결 전에는 반드시 전문 변호사의 법률 자문을 받으시기 바랍니다.
              본 분석 결과를 신뢰하여 발생한 손해에 대해 당사는 책임을 지지 않습니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskReport;
