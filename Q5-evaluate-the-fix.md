# Q5 — Evaluate the Fix

Two engineers have reviewed the cascade described in Q4 and proposed fixes.

---

## Fix A — Response Body Inspection in `ErrorClassifier`

Engineer A says: *"The problem is that we're not reading the response body. If we inspect the error field, we can distinguish IP bans from token failures and apply the right remediation."*

```python
# In http_client.py, ErrorClassifier.classify():
def classify(self, response: Response, job_id: str) -> ErrorEvent:
    if response.status_code == 403:
        body = response.json_body or {}
        error_code = body.get("error", "")
        if error_code in ("TOKEN_INVALID", "TOKEN_EXPIRED", "CAPTCHA_REQUIRED"):
            return ErrorEvent(
                job_id=job_id,
                error_type=ErrorType.CAPTCHA_INVALID,
                http_status=403,
                remediation=RemediationAction.RESOLVE_CAPTCHA,
                occurred_at=_now(),
                detail=error_code,
            )
        # Default for IP_BLOCKED, ACCESS_DENIED, etc.
        return ErrorEvent(
            job_id=job_id,
            error_type=ErrorType.PROXY_BANNED,
            http_status=403,
            remediation=RemediationAction.ROTATE_PROXY,
            occurred_at=_now(),
            detail=error_code,
        )
    # ... rest of method unchanged
```

**(a)** Does Fix A address the root cause of the cascade in Q4? Fully, partially, or not at all? Explain.

**(b)** Fix A introduces a new dependency: it assumes the target site always returns a parseable JSON body with a consistent `error` field on 403 responses. What happens if the site returns a 403 with an HTML body (e.g., a WAF block page)? Trace through the code.

---

## Fix B — Invalidate Session on Proxy Rotation

Engineer B says: *"The real problem is that we're reusing session state — including the `cf_clearance` cookie — after rotating to a new proxy. We should invalidate the session whenever a proxy rotation happens."*

```python
# In proxy_pool.py, ProxyPool.rotate():
def rotate(self, proxy_id: str, campaign_id: str) -> Optional[Proxy]:
    self._mark_cooling_down(proxy_id)
    new_proxy = self._get_next_available(campaign_id)
    if new_proxy:
        self._session_manager.invalidate_session(campaign_id)  # clears cf_clearance
        self._assignments[campaign_id] = new_proxy.id
    return new_proxy
```

**(a)** Does Fix B address the root cause of the cascade in Q4? Fully, partially, or not at all? Explain.

**(b)** After Fix B is deployed, what happens to a job that rotates proxies? Walk through the consequences for `captcha_solves_used` across a job that needs 3 proxy rotations before it succeeds.

**(c)** Fix B places session invalidation logic inside `ProxyPool`. Read `candidate/AGENTS.md` — specifically the section on Session Management. What does it say about where session state should be managed? Does Fix B comply with this standard? Does that matter?

---

## The Correct Fix

**(d)** Neither fix fully addresses the system. Describe the correct approach:

- What is the actual root cause — in one sentence?
- Which layer(s) need to change, and what specifically needs to change in each?
- What would the fixed `ErrorClassifier` look like at a conceptual level (you don't need to write code — describe the decision logic)?
- What would the fixed session restoration flow look like on a retry with a new proxy?
