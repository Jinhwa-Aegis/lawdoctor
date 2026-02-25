"""IP 제한 미들웨어 — 사내 네트워크만 접근 허용"""

import ipaddress
from typing import List

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import settings

logger = structlog.get_logger()

# 신뢰할 수 있는 프록시 IP 목록 (Docker 내부 네트워크)
TRUSTED_PROXIES = {"127.0.0.1", "172.17.0.1", "172.18.0.1", "10.0.0.1"}


def parse_allowed_networks(allowed_ips_str: str) -> List[ipaddress.IPv4Network]:
    """쉼표로 구분된 IP/CIDR 문자열을 네트워크 목록으로 파싱"""
    networks = []
    for ip_str in allowed_ips_str.split(","):
        ip_str = ip_str.strip()
        if not ip_str:
            continue
        try:
            networks.append(ipaddress.ip_network(ip_str, strict=False))
        except ValueError:
            logger.warning("잘못된 IP 형식 무시", ip=ip_str)
    return networks


class IPFilterMiddleware(BaseHTTPMiddleware):
    """사내 네트워크 IP만 접근 허용하는 미들웨어"""

    def __init__(self, app):
        super().__init__(app)
        self.allowed_networks = parse_allowed_networks(settings.allowed_ips)
        # 개발 환경에서는 IP 필터 비활성화
        self.enabled = settings.app_env != "development"

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # 헬스체크는 항상 허용
        if request.url.path == "/api/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # X-Forwarded-For는 신뢰할 수 있는 프록시에서만 사용
        if client_ip in TRUSTED_PROXIES:
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                client_ip = forwarded_for.split(",")[0].strip()

        if client_ip and self._is_allowed(client_ip):
            return await call_next(request)

        logger.warning("허용되지 않은 IP 접근 차단", client_ip=client_ip)
        return JSONResponse(
            status_code=403,
            content={"detail": "접근이 허용되지 않은 네트워크입니다."},
        )

    def _is_allowed(self, ip_str: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in network for network in self.allowed_networks)
        except ValueError:
            return False
