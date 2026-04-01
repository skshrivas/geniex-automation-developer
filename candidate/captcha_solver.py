"""
CAPTCHA provider integration for the price intelligence platform.

Wraps the CapSolver API for Cloudflare Turnstile challenges.
All solve attempts — successful or not — are tracked externally by
the worker via job.captcha_solves_used.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from .config import config

logger = logging.getLogger(__name__)

# CapSolver API endpoints
_CAPSOLVER_CREATE_TASK = "https://api.capsolver.com/createTask"
_CAPSOLVER_GET_RESULT = "https://api.capsolver.com/getTaskResult"


class CaptchaProviderError(Exception):
    """Raised when the CAPTCHA provider is unavailable or returns an error."""


class CaptchaTimeoutError(CaptchaProviderError):
    """Raised when a task exceeds the polling timeout."""


@dataclass
class SolveResult:
    token: str
    elapsed_seconds: float
    task_id: str


class CaptchaSolver:
    """
    Solves Cloudflare Turnstile challenges via the CapSolver API.

    Usage:
        solver = CaptchaSolver()
        result = solver.solve_turnstile(page_url, site_key, job_id=job.id)
        # result.token is the cf-turnstile-response value

    Raises CaptchaProviderError on provider failure (503, bad API key, etc.)
    Raises CaptchaTimeoutError if the task takes too long.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or config.captcha.api_key

    def solve_turnstile(
        self,
        page_url: str,
        site_key: str,
        job_id: str = "",
        proxy_url: Optional[str] = None,
    ) -> SolveResult:
        """
        Submit a Turnstile task and poll until resolved.

        Args:
            page_url:  The URL of the page requiring the challenge
            site_key:  The Turnstile site key from the page source
            job_id:    For logging correlation only
            proxy_url: Optional proxy for the solve request (provider-side)

        Returns:
            SolveResult with the token value

        Raises:
            CaptchaProviderError: provider API error (503, auth failure, etc.)
            CaptchaTimeoutError:  task did not resolve within timeout window
        """
        t0 = time.monotonic()
        task_id = self._create_task(page_url, site_key, proxy_url, job_id)
        token = self._poll_result(task_id, job_id)
        elapsed = time.monotonic() - t0
        logger.info(
            "captcha solved: job=%s task=%s elapsed=%.2fs",
            job_id, task_id, elapsed,
        )
        return SolveResult(token=token, elapsed_seconds=elapsed, task_id=task_id)

    def _create_task(
        self,
        page_url: str,
        site_key: str,
        proxy_url: Optional[str],
        job_id: str,
    ) -> str:
        payload: dict = {
            "clientKey": self._api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
        }

        logger.debug("creating captcha task: job=%s url=%s", job_id, page_url)
        try:
            resp = requests.post(
                _CAPSOLVER_CREATE_TASK,
                json=payload,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise CaptchaProviderError(f"network error creating task: {exc}") from exc

        if resp.status_code != 200:
            raise CaptchaProviderError(
                f"provider returned {resp.status_code}: {resp.text[:200]}"
            )

        body = resp.json()
        if body.get("errorId") != 0:
            raise CaptchaProviderError(
                f"provider error: {body.get('errorDescription', 'unknown')}"
            )

        task_id: str = body["taskId"]
        logger.debug("captcha task created: job=%s task_id=%s", job_id, task_id)
        return task_id

    def _poll_result(self, task_id: str, job_id: str) -> str:
        deadline = time.monotonic() + config.captcha.task_timeout_seconds
        payload = {"clientKey": self._api_key, "taskId": task_id}

        while time.monotonic() < deadline:
            time.sleep(config.captcha.poll_interval_seconds)
            try:
                resp = requests.post(
                    _CAPSOLVER_GET_RESULT,
                    json=payload,
                    timeout=10,
                )
            except requests.RequestException as exc:
                raise CaptchaProviderError(
                    f"network error polling task {task_id}: {exc}"
                ) from exc

            if resp.status_code != 200:
                raise CaptchaProviderError(
                    f"provider returned {resp.status_code} while polling"
                )

            body = resp.json()
            if body.get("errorId") != 0:
                raise CaptchaProviderError(
                    f"provider error: {body.get('errorDescription', 'unknown')}"
                )

            status = body.get("status")
            if status == "ready":
                token: str = body["solution"]["token"]
                return token
            if status == "processing":
                logger.debug("task %s still processing (job=%s)", task_id, job_id)
                continue
            raise CaptchaProviderError(f"unexpected task status: {status!r}")

        raise CaptchaTimeoutError(
            f"task {task_id} did not resolve within "
            f"{config.captcha.task_timeout_seconds}s"
        )
