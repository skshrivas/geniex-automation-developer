"""
Seed data representing the current state of the price intelligence platform.

This module defines the proxy pool, account registry, and campaign history
that the system had at the time of this assessment snapshot (2025-02-06 09:15 UTC).

Use this as ground truth when answering the assessment questions.
"""

from __future__ import annotations

from .models import (
    Account,
    AccountStatus,
    Campaign,
    CampaignStatus,
    Job,
    JobResult,
    JobStatus,
    ParseResult,
    Proxy,
    ProxyStatus,
    ProxyType,
)

# ---------------------------------------------------------------------------
# Proxies
# ---------------------------------------------------------------------------

PROXIES = [
    Proxy(
        id="P-001",
        host="us-res-1.proxyvendor.net",
        port=10000,
        username="geniex_res",
        password="pass-p001",
        proxy_type=ProxyType.RESIDENTIAL,
        country="US",
        status=ProxyStatus.HEALTHY,
        # Sticky session assigned to C-001, but TTL expired 10 minutes ago.
        # The proxy is HEALTHY in the pool and will be reallocated to the next
        # campaign that calls acquire().
        sticky_until="2025-02-06T09:05:00+00:00",
        assigned_campaign_id="C-001",
        last_used_at="2025-02-06T09:04:50+00:00",
        ban_count=0,
        success_count=312,
    ),
    Proxy(
        id="P-002",
        host="us-res-2.proxyvendor.net",
        port=10001,
        username="geniex_res",
        password="pass-p002",
        proxy_type=ProxyType.RESIDENTIAL,
        country="US",
        status=ProxyStatus.HEALTHY,
        sticky_until="2025-02-06T09:25:00+00:00",
        assigned_campaign_id="C-001",
        last_used_at="2025-02-06T09:14:00+00:00",
        ban_count=0,
        success_count=287,
    ),
    Proxy(
        id="P-003",
        host="us-dc-1.proxyvendor.net",
        port=20000,
        username="geniex_dc",
        password="pass-p003",
        proxy_type=ProxyType.DATACENTER,
        country="US",
        # Status reflects last database write. During the C-002 run, this proxy
        # received a 403 SESSION_FINGERPRINT_MISMATCH response. The ErrorClassifier
        # classified it as PROXY_BANNED and rotate() was called, setting it to
        # COOLING_DOWN in memory. However, a process restart occurred before the
        # status was flushed to the database. The database still shows HEALTHY.
        status=ProxyStatus.HEALTHY,
        sticky_until=None,
        assigned_campaign_id=None,
        last_used_at="2025-02-06T08:47:00+00:00",
        ban_count=2,
        success_count=94,
    ),
    Proxy(
        id="P-004",
        host="uk-mob-1.proxyvendor.net",
        port=30000,
        username="geniex_mob",
        password="pass-p004",
        proxy_type=ProxyType.MOBILE,
        country="UK",
        # P-004 entered COOLING_DOWN after an account-sharing detection event
        # during C-002. At the time, P-001's sticky session had expired and both
        # P-001 and P-004 were serving requests for the same campaign concurrently,
        # leading the target site to flag same-IP session conflicts.
        status=ProxyStatus.COOLING_DOWN,
        sticky_until=None,
        assigned_campaign_id=None,
        last_used_at="2025-02-06T08:51:00+00:00",
        ban_count=1,
        success_count=55,
    ),
]

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

ACCOUNTS = [
    Account(
        id="ACC-001",
        username="price_scraper_01@geniex.io",
        password="s3cur3-p@ss-001",
        status=AccountStatus.ACTIVE,
        cookies={
            # This cf_clearance token was solved by P-003 during the C-003 campaign run.
            # It encodes the Cloudflare verification context for P-003's IP address.
            # P-003 is the proxy that obtained this clearance; subsequent requests using
            # this cookie must originate from the same IP for Cloudflare to honour it.
            "cf_clearance": (
                "6Yz3mP8nRkXvQ1sL-1707210000-0-AY3zxNBP9wK7jT2qSm"
                "Hc5dLpV6bF8eC4oUr0nIg2vtXw1aJu9hElkMsD3fPyRz"
            ),
            "session_id": "sess_acc001_cf_legacy",
            "_cf_bm": "xK9pLmN2qRvS4tUw6yZa8bCd0eF",
        },
        last_login_at="2025-02-05T14:22:00+00:00",
        campaign_id=None,
    ),
    Account(
        id="ACC-002",
        username="price_scraper_02@geniex.io",
        password="s3cur3-p@ss-002",
        status=AccountStatus.ACTIVE,
        cookies={},
        last_login_at=None,
        campaign_id=None,
    ),
]

# ---------------------------------------------------------------------------
# Campaign C-001: pending, never run
# ---------------------------------------------------------------------------

C001_JOBS = [
    Job(
        id=f"J-{str(i).zfill(3)}",
        campaign_id="C-001",
        url=f"https://www.target-retailer.com/products/sku-{str(i).zfill(4)}",
        status=JobStatus.PENDING,
        retry_count=0,
        captcha_solves_used=0,
        assigned_proxy_id=None,
        assigned_account_id="ACC-001",
        result=None,
        created_at="2025-02-06T09:10:00+00:00",
        updated_at="2025-02-06T09:10:00+00:00",
    )
    for i in range(1, 6)
]

CAMPAIGN_C001 = Campaign(
    id="C-001",
    name="Daily SKU price check — batch 1",
    status=CampaignStatus.PENDING,
    target_urls=[j.url for j in C001_JOBS],
    jobs=C001_JOBS,
    created_at="2025-02-06T09:10:00+00:00",
    completed_at=None,
)

# ---------------------------------------------------------------------------
# Campaign C-002: failed — all jobs exhausted during provider outage
# ---------------------------------------------------------------------------
#
# C-002 ran at 14:00 UTC on 2025-02-05. The CapSolver API went down shortly
# after the campaign started. Every CAPTCHA solve attempt raised
# CaptchaProviderError. Each attempt incremented captcha_solves_used.
# All 50 jobs reached captcha_solves_used=5 and were marked EXHAUSTED.
# The proxies and accounts involved remain healthy — the exhaustion was
# caused entirely by provider unavailability, not by the target site.
# ---------------------------------------------------------------------------

C002_JOBS = [
    Job(
        id=f"J-{str(i).zfill(3)}",
        campaign_id="C-002",
        url=f"https://www.target-retailer.com/products/sku-{str(i).zfill(4)}",
        status=JobStatus.EXHAUSTED,
        retry_count=4,
        captcha_solves_used=5,
        assigned_proxy_id="P-003",
        assigned_account_id="ACC-002",
        result=None,
        created_at="2025-02-05T14:00:00+00:00",
        updated_at="2025-02-05T14:12:00+00:00",
    )
    for i in range(11, 61)
]

CAMPAIGN_C002 = Campaign(
    id="C-002",
    name="Competitor price sweep — 50 SKUs",
    status=CampaignStatus.FAILED,
    target_urls=[j.url for j in C002_JOBS],
    jobs=C002_JOBS,
    created_at="2025-02-05T14:00:00+00:00",
    completed_at="2025-02-05T14:12:00+00:00",
)

# ---------------------------------------------------------------------------
# Campaign C-003: completed — 10/10 jobs, but 7 have null price data
# ---------------------------------------------------------------------------
#
# C-003 ran successfully in the sense that all 10 jobs reached COMPLETED.
# However, 7 of the 10 responses were Cloudflare JS challenge pages
# (HTTP 200, ~14KB of valid HTML, no product content). PriceParser.parse()
# returned success=True with price=None and available=None for each.
# The campaign reports a 100% success rate and a 30% price coverage rate.
# ---------------------------------------------------------------------------

def _make_c003_job(job_num: int, price: float | None, available: bool | None) -> Job:
    parse_result = ParseResult(
        success=True,
        price=price,
        available=available,
        currency="USD" if price else None,
        raw_html_size=14200 if price is None else 9800,
        parse_duration_ms=12.4 if price is None else 8.1,
    )
    job_result = JobResult(
        job_id=f"J-{str(job_num).zfill(3)}",
        status=JobStatus.COMPLETED,
        parse_result=parse_result,
        error_type=None,
        proxy_id="P-001",
        completed_at="2025-02-06T08:55:00+00:00",
    )
    return Job(
        id=f"J-{str(job_num).zfill(3)}",
        campaign_id="C-003",
        url=f"https://www.target-retailer.com/products/sku-{str(job_num).zfill(4)}",
        status=JobStatus.COMPLETED,
        retry_count=0,
        captcha_solves_used=1,
        assigned_proxy_id="P-001",
        assigned_account_id="ACC-001",
        result=job_result,
        created_at="2025-02-06T08:50:00+00:00",
        updated_at="2025-02-06T08:55:00+00:00",
    )


# Jobs 101-103: genuine product pages — have price and availability
# Jobs 104-110: Cloudflare challenge pages — parse succeeded, data is null
C003_JOBS = [
    _make_c003_job(101, price=49.99, available=True),
    _make_c003_job(102, price=129.00, available=True),
    _make_c003_job(103, price=24.95, available=False),
    _make_c003_job(104, price=None, available=None),   # challenge page
    _make_c003_job(105, price=None, available=None),   # challenge page
    _make_c003_job(106, price=None, available=None),   # challenge page
    _make_c003_job(107, price=None, available=None),   # challenge page
    _make_c003_job(108, price=None, available=None),   # challenge page
    _make_c003_job(109, price=None, available=None),   # challenge page
    _make_c003_job(110, price=None, available=None),   # challenge page
]

CAMPAIGN_C003 = Campaign(
    id="C-003",
    name="New product launch monitoring",
    status=CampaignStatus.COMPLETED,
    target_urls=[j.url for j in C003_JOBS],
    jobs=C003_JOBS,
    created_at="2025-02-06T08:50:00+00:00",
    completed_at="2025-02-06T08:55:00+00:00",
)

# ---------------------------------------------------------------------------
# Convenience exports
# ---------------------------------------------------------------------------

ALL_PROXIES = PROXIES
ALL_ACCOUNTS = ACCOUNTS
ALL_CAMPAIGNS = [CAMPAIGN_C001, CAMPAIGN_C002, CAMPAIGN_C003]
