"""업로드 파일 자동 삭제 스케줄러"""

import os
import time

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from config import settings

logger = structlog.get_logger()

scheduler = BackgroundScheduler()


def cleanup_uploads():
    """만료된 업로드 파일 삭제 (기본 24시간)"""
    upload_dir = settings.upload_dir
    if not os.path.exists(upload_dir):
        return

    cutoff = time.time() - (settings.upload_cleanup_hours * 3600)
    removed = 0

    for filename in os.listdir(upload_dir):
        if filename == ".gitkeep":
            continue
        filepath = os.path.join(upload_dir, filename)
        if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff:
            try:
                os.remove(filepath)
                removed += 1
            except OSError as e:
                logger.error("파일 삭제 실패", filepath=filepath, error=str(e))

    if removed > 0:
        logger.info("만료 파일 정리 완료", removed_count=removed)


def start_scheduler():
    """스케줄러 시작"""
    scheduler.add_job(cleanup_uploads, "interval", hours=1, id="cleanup_uploads", replace_existing=True)
    scheduler.start()
    logger.info("파일 정리 스케줄러 시작")


def shutdown_scheduler():
    """스케줄러 종료"""
    scheduler.shutdown(wait=False)
    logger.info("파일 정리 스케줄러 종료")
