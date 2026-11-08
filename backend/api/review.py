"""계약서 리뷰 API 엔드포인트"""

import os
import uuid

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import settings
from middleware.auth import get_current_user
from models.user import User
from core.contract_reviewer import review_contract, ContractReviewResult
from core.contract_checklists import AUTO_DETECT, CONTRACT_TYPES, list_contract_types

logger = structlog.get_logger()

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".hwp", ".hwpx", ".txt"}


@router.get("/contract-types")
async def get_contract_types(user: User = Depends(get_current_user)) -> list[dict]:
    """계약 유형별 점검표 목록 (유형 선택 UI용)"""
    return list_contract_types()


@router.post("", response_model=ContractReviewResult)
async def upload_and_review(
    file: UploadFile = File(...),
    contract_type: str = Form(AUTO_DETECT),
    user: User = Depends(get_current_user),
):
    """계약서 업로드 및 리스크 분석

    contract_type: 점검표 유형 키 (auto면 자동 감지)
    """
    if contract_type != AUTO_DETECT and contract_type not in CONTRACT_TYPES:
        raise HTTPException(status_code=400, detail="지원하지 않는 계약 유형입니다.")

    # 파일 확장자 검증
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 파일 크기 제한
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_upload_size_mb}MB를 초과합니다.",
        )

    # 임시 파일 저장
    os.makedirs(settings.upload_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    logger.info(
        "계약서 업로드 완료",
        user_id=user.id,
        filename=file.filename,
        size=len(content),
    )

    try:
        result = await review_contract(filepath, contract_type=contract_type)
        result.file_name = file.filename or ""
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("계약서 리뷰 실패", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="계약서 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        )
    finally:
        # 분석 완료 후 즉시 파일 삭제 (스케줄러는 24시간 후 미삭제 파일 정리)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info("임시 파일 삭제 완료", filepath=filepath)
        except OSError as cleanup_err:
            logger.warning("임시 파일 삭제 실패", filepath=filepath, error=str(cleanup_err))
