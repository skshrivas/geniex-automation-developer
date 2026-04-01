"""
Operational configuration for the price intelligence platform.

All tunable constants are defined here. Modify via environment variables
or by subclassing AppConfig for environment-specific overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class CaptchaConfig:
    provider: str = "capsolver"
    api_key: str = field(
        default_factory=lambda: os.environ.get("CAPSOLVER_API_KEY", "")
    )
    # Maximum number of CAPTCHA solve attempts per job, across all causes.
    # This is the unified budget — see AGENTS.md for rationale.
    retry_budget_per_job: int = 5
    poll_interval_seconds: float = 2.0
    task_timeout_seconds: float = 60.0


@dataclass
class ProxyConfig:
    # How long a proxy remains assigned to a campaign before being returned
    # to the general pool. Prevents proxy hoarding by long-running campaigns.
    sticky_session_ttl: int = 600  # seconds
    # Number of consecutive failures before a proxy is marked COOLING_DOWN
    max_consecutive_failures: int = 3
    # How long a COOLING_DOWN proxy must wait before re-entering the pool
    cooldown_duration: int = 1800  # seconds


@dataclass
class WorkerConfig:
    max_retries_per_job: int = 4
    request_timeout: float = 30.0
    inter_request_delay: float = 1.5  # seconds between consecutive requests


@dataclass
class ScraperConfig:
    price_selector: str = "span.product-price"
    availability_selector: str = "div.stock-status"
    # Minimum page size in bytes; smaller responses are treated as structural failures
    min_page_size_bytes: int = 1000


@dataclass
class AppConfig:
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    base_url: str = "https://www.target-retailer.com"


config = AppConfig()
