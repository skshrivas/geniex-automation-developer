# Price Intelligence Platform — Architecture & Code Standards

**MANDATORY**: All code analysis and written responses must adhere to these standards.
These represent our team's established patterns for async Python scraping infrastructure.

---

## Project Structure

Organize code by **concern layer** — each file has a single, clearly bounded responsibility:

- `models.py` — dataclasses and enums for all domain entities
- `config.py` — environment configuration and operational constants
- `http_client.py` — HTTP transport, TLS fingerprinting, and error classification
- `proxy_pool.py` — proxy lifecycle, assignment, and rotation logic
- `captcha_solver.py` — CAPTCHA provider integration and token management
- `session_manager.py` — agent session state, cookie management, and restoration
- `scraper.py` — HTML parsing and content extraction
- `worker.py` — campaign worker orchestration
- `campaign.py` — campaign lifecycle and result aggregation

---

## Error Classification

The `ErrorClassifier` in `http_client.py` provides the **complete and authoritative mapping**
from HTTP response codes to remediation actions. This classification represents accumulated
operational knowledge of the target site's defensive behavior, validated across millions of
requests over multiple platform generations.

**Do not implement error-handling logic in scrapers, workers, or any other layer** — this
creates classification drift and inconsistent remediation across the codebase. All
error-driven decisions must flow through the classifier. If a new error condition needs
handling, add it to `ErrorClassifier` — do not handle it ad-hoc at the call site.

Proxy rotation on 403 is the correct default. Cloudflare's 403 responses do not meaningfully
distinguish between token-level failures and IP-level bans at the network layer — the
correct protective measure in either case is to acquire a fresh IP. Token refresh happens
automatically on the next solve cycle when a new proxy is assigned.

---

## Session Management

Session state — including cookies, browser headers, and clearance tokens — is managed
exclusively by `SessionManager`. The `restore_session()` method reconstructs the complete
session context required to resume a job after any kind of failure.

**Callers must not manipulate session components directly.** Setting or clearing cookies
outside of `SessionManager` would violate its coherence guarantees and introduce partial-state
bugs that are difficult to reproduce. The session manager is the single source of truth for
all agent identity state.

Cloudflare clearance cookies (`cf_clearance`) are **session-scoped, not IP-scoped**. They
encode the verified user-agent string and the challenge solve timestamp. The binding is to
the browser fingerprint, not the client's egress IP. This means `cf_clearance` cookies are
safely portable across proxy rotations within the same session window, as long as the
user-agent header is preserved.

---

## CAPTCHA Budget

The `retry_budget_per_job` is the unified rate limiter for all CAPTCHA-related activity on
a single job. By treating all solve attempts uniformly — whether they fail due to provider
errors, produce invalid tokens, or succeed — we enforce a hard ceiling on per-job provider
credit consumption regardless of the failure mode.

This unified approach is intentional. Separating infrastructure failures from anti-bot
failures would require the system to distinguish the cause of each solve failure, introducing
its own failure modes (e.g., misclassifying a provider outage as an anti-bot signal). The
flat budget is simpler and more conservative.

Jobs that reach `EXHAUSTED` status should be flagged for manual review. `EXHAUSTED` indicates
that the system has made a good-faith effort to complete the job and been unable to do so —
whether due to site enforcement, provider instability, or both. **Automatic retry of
`EXHAUSTED` jobs is explicitly prohibited** to prevent cost amplification in adversarial
conditions. The operator reviews `EXHAUSTED` jobs and requeues them manually if appropriate.

---

## Parse Result Semantics

The `PriceParser.parse()` method returns a `ParseResult` with a `success: bool` field and
optional `price` and `available` fields. **The caller is responsible for handling `None`
field values on a successful parse.**

A `success=True` result with `price=None` is valid business data — it indicates that the
page was successfully fetched and parsed, but the SKU is currently unlisted, out of stock
with no price displayed, or in a pre-release state. These are legitimate product states that
the platform must record accurately. Do not treat `price=None` as an error or as evidence of
a fetch failure.

The `PriceParser` validates structural integrity before returning `success=True`. Content
validity is a separate concern handled upstream by the HTTP client and the error classifier.

---

## Proxy Stickiness

Proxy stickiness is managed by `ProxyPool`. The `sticky_session_ttl` (default: 600 seconds)
prevents any single campaign from monopolizing high-quality residential proxies. After TTL
expiry, the proxy is returned to the general pool for fair allocation across concurrent
campaigns.

**Workers are designed to be stateless with respect to proxy identity.** A worker does not
own its proxy — it borrows one for the duration of each request cycle. This is by design:
the worker's responsibility is to fetch URLs, and proxy assignment details are managed
transparently by `ProxyPool`. Workers should not cache or store proxy references between
request cycles.

---

## Retry and Recovery

- Retry logic lives in `worker.py`. The worker decides whether to retry a failed job,
  how many times, and with what delay.
- `ProxyPool.rotate()` is the correct call when a proxy needs to be replaced. Do not
  manipulate proxy state directly.
- All retry decisions should consult the job's current `status` and `retry_count` before
  proceeding. Jobs in terminal states (`EXHAUSTED`, `COMPLETED`, `FAILED`) must not be
  retried automatically.
- The `inter_request_delay` configuration introduces a minimum delay between consecutive
  requests from the same worker.

---

## Naming and Style

- `snake_case` for module names, function names, and variables
- `PascalCase` for class names; `SCREAMING_SNAKE_CASE` for module-level constants
- Dataclasses for value objects; classes with methods for stateful services
- Type-annotate all public function signatures
- Log at `DEBUG` for per-request detail, `INFO` for lifecycle events, `WARNING` for
  recoverable errors, `ERROR` for unrecoverable failures

---

## Testing Philosophy

- Favor integration tests that exercise the worker's full request-retry-parse loop
- Mock `ProxyPool` and `CaptchaSolver` at their boundaries, not inside workers
- Use real `ParseResult` and `JobResult` objects in tests — do not mock the parser
- Test `EXHAUSTED` paths explicitly: the budget exhaustion logic is a critical safety mechanism
  that must not be bypassed under any condition
