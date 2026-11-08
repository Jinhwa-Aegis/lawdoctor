import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown, X } from 'lucide-react';
import { sendFeedback } from '../api/client';

/** compact: 답변 액션 바 안에서 아이콘만 표시 */
const FeedbackButton = ({ messageId, compact = false }) => {
  const [feedbackGiven, setFeedbackGiven] = useState(null);
  const [showReasonModal, setShowReasonModal] = useState(false);
  const [selectedReason, setSelectedReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const reasons = [
    { value: 'inaccurate', label: '부정확한 정보' },
    { value: 'insufficient_evidence', label: '근거 부족' },
    { value: 'irrelevant', label: '관련 없는 답변' },
    { value: 'other', label: '기타' }
  ];

  const handlePositiveFeedback = async () => {
    if (feedbackGiven) return;

    setIsSubmitting(true);
    try {
      await sendFeedback(messageId, 'positive');
      setFeedbackGiven('positive');
    } catch (error) {
      console.error('피드백 전송 실패:', error);
      alert('피드백 전송에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNegativeFeedback = () => {
    if (feedbackGiven) return;
    setShowReasonModal(true);
  };

  const submitNegativeFeedback = async () => {
    if (!selectedReason) {
      alert('사유를 선택해주세요.');
      return;
    }

    setIsSubmitting(true);
    try {
      await sendFeedback(messageId, 'negative', selectedReason);
      setFeedbackGiven('negative');
      setShowReasonModal(false);
    } catch (error) {
      console.error('피드백 전송 실패:', error);
      alert('피드백 전송에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <div className={`flex items-center ${compact ? 'gap-0.5' : 'gap-2'}`}>
        {feedbackGiven ? (
          <p className={compact ? 'text-xs text-green-600 px-2' : 'text-sm text-green-600 font-medium'}>
            피드백 감사합니다!
          </p>
        ) : (
          <>
            {!compact && <span className="text-xs text-gray-500">이 답변이 도움이 되었나요?</span>}
            <button
              onClick={handlePositiveFeedback}
              disabled={isSubmitting}
              className="p-1.5 rounded hover:bg-green-50 text-gray-500 hover:text-green-600 transition-colors disabled:opacity-50"
              title="도움이 됨"
            >
              <ThumbsUp size={16} />
            </button>
            <button
              onClick={handleNegativeFeedback}
              disabled={isSubmitting}
              className="p-1.5 rounded hover:bg-red-50 text-gray-500 hover:text-red-600 transition-colors disabled:opacity-50"
              title="도움이 안 됨"
            >
              <ThumbsDown size={16} />
            </button>
          </>
        )}
      </div>

      {/* 사유 선택 모달 */}
      {showReasonModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-gray-900">
                피드백 사유 선택
              </h3>
              <button
                onClick={() => setShowReasonModal(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <p className="text-sm text-gray-600 mb-4">
              어떤 점이 도움이 되지 않았나요?
            </p>

            <div className="space-y-2 mb-6">
              {reasons.map((reason) => (
                <label
                  key={reason.value}
                  className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <input
                    type="radio"
                    name="reason"
                    value={reason.value}
                    checked={selectedReason === reason.value}
                    onChange={(e) => setSelectedReason(e.target.value)}
                    className="w-4 h-4 text-blue-600"
                  />
                  <span className="text-sm text-gray-900">{reason.label}</span>
                </label>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setShowReasonModal(false)}
                className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              >
                취소
              </button>
              <button
                onClick={submitNegativeFeedback}
                disabled={!selectedReason || isSubmitting}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {isSubmitting ? '전송 중...' : '제출'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default FeedbackButton;
