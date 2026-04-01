"""
HTTP transport and error classification for the price intelligence platform.

HttpClient executes requests through a specified proxy with Cloudflare-compatible
headers. ErrorClassifier maps HTTP responses to ErrorType + RemediationAction.

All error classification flows through ErrorClassifier — do not handle
error conditions in workers or scrapers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ConnectionError, ReadTimeout

from .models import ErrorEvent, ErrorType, RemediationAction

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Request / Response types
# ---------------------------------------------------------------------------


@dataclass
class RequestConfig:
    url: str
    proxy_url: str
    cookies: dict
    user_agent: str
    headers: dict
    timeout: float = 30.0


@dataclass
class Response:
    status_code: int
    body: str
    headers: Dict[str, str]
    proxy_id: str = ""
    json_body: Optional[Dict[str, Any]] = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------


class ErrorClassifier:
    """
    Maps HTTP responses to ErrorType and RemediationAction.

    This is the authoritative classification layer — all remediation
    decisions for non-200 responses must flow through this class.
    """

    def classify(self, response: Response, job_id: str = "") -> ErrorEvent:
        """
        Classify a non-200 response and return the appropriate remediation.

        403 responses indicate that the request was rejected at the identity
        or network layer. The correct remediation is proxy rotation: acquiring
        a fresh IP resolves both IP-level bans and token-level failures, since
        a new proxy triggers a fresh solve cycle on the next request.
        """
        status = response.status_code

        if status == 403:
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.PROXY_BANNED,
                http_status=403,
                remediation=RemediationAction.ROTATE_PROXY,
                occurred_at=_now(),
                detail="forbidden — proxy or identity rejected",
            )

        if status == 401:
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.PROXY_BANNED,
                http_status=401,
                remediation=RemediationAction.ABORT,
                occurred_at=_now(),
                detail="unauthorized — account or session rejected",
            )

        if status == 429:
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.RATE_LIMITED,
                http_status=429,
                remediation=RemediationAction.BACKOFF,
                occurred_at=_now(),
                detail="rate limited",
            )

        if status == 404:
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.NOT_FOUND,
                http_status=404,
                remediation=RemediationAction.SKIP,
                occurred_at=_now(),
                detail="url not found",
            )

        if status >= 500:
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.SERVER_ERROR,
                http_status=status,
                remediation=RemediationAction.RETRY,
                occurred_at=_now(),
                detail=f"server error {status}",
            )

        return ErrorEvent(
            job_id=job_id,
            error_type=ErrorType.UNKNOWN,
            http_status=status,
            remediation=RemediationAction.RETRY,
            occurred_at=_now(),
            detail=f"unexpected status {status}",
        )


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class NetworkError(Exception):
    """Raised for connection-level failures (timeout, DNS, etc.)"""


class HttpClient:
    """
    Executes HTTP requests with proxy support and Cloudflare-compatible
    header configuration.
    """

    # Headers that mimic a real Chrome browser on Windows
    _BASE_HEADERS: Dict[str, str] = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    def execute(self, req: RequestConfig) -> Response:
        """
        Execute a GET request and return the response.

        Raises NetworkError on connection-level failures.
        Does not raise on non-200 status codes — callers use ErrorClassifier.
        """
        headers = {
            **self._BASE_HEADERS,
            "User-Agent": req.user_agent,
            **req.headers,
        }

        self._log_request("GET", req.url, headers, req.cookies)

        proxies = {"http": req.proxy_url, "https": req.proxy_url}
        try:
            raw = requests.get(
                req.url,
                headers=headers,
                cookies=req.cookies,
                proxies=proxies,
                timeout=req.timeout,
                allow_redirects=True,
            )
        except ReadTimeout as exc:
            raise NetworkError(f"timeout fetching {req.url}") from exc
        except ConnectionError as exc:
            raise NetworkError(f"connection error fetching {req.url}") from exc

        json_body: Optional[Dict[str, Any]] = None
        content_type = raw.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                json_body = raw.json()
            except Exception:
                pass

        resp = Response(
            status_code=raw.status_code,
            body=raw.text,
            headers=dict(raw.headers),
            json_body=json_body,
            elapsed_ms=raw.elapsed.total_seconds() * 1000,
        )

        logger.debug(
            "response: %d %s (%.0fms)", raw.status_code, req.url, resp.elapsed_ms
        )
        return resp

    def _log_request(
        self,
        method: str,
        url: str,
        headers: dict,
        cookies: dict,
    ) -> None:
        logger.debug(
            "request: %s %s headers=%s cookies=%s",
            method,
            url,
            headers,
            cookies,
        )
