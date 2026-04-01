"""
Agent session state management for the price intelligence platform.

Maintains the complete identity context for each scraping job:
cookies (including Cloudflare clearance), user-agent, and account
assignment. Provides session persistence and restoration across retries.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import Account, AccountStatus, Job, Session

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Single source of truth for all agent session state.

    Callers should use get_session_cookies() for initial requests and
    restore_session() for retries. Direct manipulation of cookies or
    account state outside this class violates its coherence guarantees.
    """

    def __init__(self, accounts: List[Account]) -> None:
        self._accounts: Dict[str, Account] = {a.id: a for a in accounts}
        # job_id → Session snapshot (persisted after each successful request)
        self._sessions: Dict[str, Session] = {}
        # account_id → campaign_id (tracks which campaign has which account)
        self._account_assignments: Dict[str, str] = {}

    def get_available_account(self, campaign_id: str) -> Optional[Account]:
        """Return an available active account and assign it to this campaign."""
        for account in self._accounts.values():
            if account.status != AccountStatus.ACTIVE:
                continue
            if account.campaign_id and account.campaign_id != campaign_id:
                continue
            account.campaign_id = campaign_id
            return account
        return None

    def get_session_cookies(self, job: Job) -> dict:
        """
        Return the current cookie jar for the account assigned to this job.

        Used for the first attempt on a fresh or previously-completed job.
        Returns a copy of the account's stored cookies, which may include
        a cf_clearance token from a prior session.
        """
        account = self._accounts.get(job.assigned_account_id or "")
        if not account:
            return {}
        return deepcopy(account.cookies)

    def restore_session(self, job: Job) -> dict:
        """
        Restore the full session context for a job being retried.

        Returns the persisted session cookies including cf_clearance.
        cf_clearance cookies are session-scoped, not IP-scoped — they
        encode the verified user-agent fingerprint and solve timestamp.
        This makes them safely portable across proxy rotations within
        the same session window as long as the user-agent is preserved.

        If no persisted session exists, falls back to get_session_cookies().
        """
        session = self._sessions.get(job.id)
        if session:
            logger.debug(
                "restoring session for job %s (account=%s proxy=%s)",
                job.id, session.account_id, session.proxy_id,
            )
            return deepcopy(session.cookies)

        logger.debug(
            "no persisted session for job %s — using account cookies", job.id
        )
        return self.get_session_cookies(job)

    def store_session(
        self,
        job: Job,
        cookies: dict,
        proxy_id: str,
        user_agent: str,
    ) -> None:
        """
        Persist the session state after a successful request.
        Called by the worker after each successful response for future restore_session calls.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._sessions[job.id] = Session(
            id=job.id,
            account_id=job.assigned_account_id or "",
            proxy_id=proxy_id,
            campaign_id=job.campaign_id,
            cookies=deepcopy(cookies),
            user_agent=user_agent,
            created_at=now,
            last_active_at=now,
        )
        # Also update the account's cookie jar for future get_session_cookies calls
        account = self._accounts.get(job.assigned_account_id or "")
        if account:
            account.cookies.update(cookies)

    def invalidate_session(self, job_id: str) -> None:
        """Remove the persisted session snapshot for a job."""
        removed = self._sessions.pop(job_id, None)
        if removed:
            logger.debug("session invalidated for job %s", job_id)

    def lock_account(self, account_id: str, reason: str = "") -> None:
        """Mark an account as suspended."""
        account = self._accounts.get(account_id)
        if account:
            account.status = AccountStatus.SUSPENDED
            logger.warning("account %s suspended: %s", account_id, reason)

    def get_user_agent(self, job: Job) -> str:
        session = self._sessions.get(job.id)
        if session:
            return session.user_agent
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
