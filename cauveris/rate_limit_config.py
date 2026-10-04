"""
Rate limit configuration parsing and policy building.
Loads policies from environment variables via Settings.
"""

from typing import Dict, List, Optional
from cauveris.config import get_settings
from cauveris.rate_limit import RateLimitPolicy, RateLimitConfig, RateLimitAlgorithm


def parse_rate_limit_string(rate_limit_str: str) -> List[RateLimitConfig]:
    """
    Parse a rate limit string like "100/60,1000/3600" into list of RateLimitConfig.
    Format: "limit/window_seconds,limit/window_seconds,..."
    """
    configs = []
    for part in rate_limit_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            limit_str, window_str = part.split("/")
            configs.append(RateLimitConfig(
                limit=int(limit_str),
                window_seconds=int(window_str),
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW_LOG
            ))
        except ValueError:
            continue
    return configs


def build_policies_from_settings() -> Dict[str, RateLimitPolicy]:
    """Build cost class policies from environment configuration."""
    settings = get_settings()

    return {
        "LOW_COST": RateLimitPolicy(
            name="low_cost",
            windows=parse_rate_limit_string(settings.rate_limit_low_cost),
        ),
        "NORMAL_READ": RateLimitPolicy(
            name="normal_read",
            windows=parse_rate_limit_string(settings.rate_limit_normal_read),
        ),
        "PUBLIC_READ": RateLimitPolicy(
            name="public_read",
            windows=parse_rate_limit_string(settings.rate_limit_public_read),
        ),
        "MUTATION": RateLimitPolicy(
            name="mutation",
            windows=parse_rate_limit_string(settings.rate_limit_mutation),
            cost=1,
        ),
        "UPLOAD": RateLimitPolicy(
            name="upload",
            windows=parse_rate_limit_string(settings.rate_limit_upload),
            cost=5,
        ),
        "COMPUTE": RateLimitPolicy(
            name="compute",
            windows=parse_rate_limit_string(settings.rate_limit_compute),
            cost=10,
        ),
        "EXPERIMENT": RateLimitPolicy(
            name="experiment",
            windows=parse_rate_limit_string(settings.rate_limit_experiment),
            cost=20,
        ),
        "PATCH": RateLimitPolicy(
            name="patch",
            windows=parse_rate_limit_string(settings.rate_limit_patch),
            cost=15,
        ),
        "DOWNLOAD": RateLimitPolicy(
            name="download",
            windows=parse_rate_limit_string(settings.rate_limit_download),
            cost=2,
        ),
        "STREAM": RateLimitPolicy(
            name="stream",
            windows=parse_rate_limit_string(settings.rate_limit_stream),
            cost=1,
        ),
        "MODEL": RateLimitPolicy(
            name="model",
            windows=parse_rate_limit_string(settings.rate_limit_model),
            cost=50,
        ),
        "CRITICAL_COST": RateLimitPolicy(
            name="critical_cost",
            windows=parse_rate_limit_string(settings.rate_limit_critical_cost),
            cost=100,
        ),
    }


def get_cost_class_for_endpoint(method: str, path: str) -> str:
    """
    Map endpoint to cost class.
    This should match the classification in ABUSE_RESISTANCE_AUDIT.md
    """
    # Normalize path
    path = path.rstrip("/")

    # Health and status - public read
    if path in ["/", "/health", "/api/v1/health", "/api/v1/model-health", "/status-center", "/api/v1/status-center"]:
        return "PUBLIC_READ"

    # List incidents - normal read
    if path == "/api/v1/incidents" and method == "GET":
        return "NORMAL_READ"

    # Create incident - mutation
    if path == "/api/v1/incidents" and method == "POST":
        return "MUTATION"

    # Upload - upload
    if "/upload" in path and method == "POST":
        return "UPLOAD"

    # Validate, temporal analysis, visualization - compute
    if any(x in path for x in ["/validate", "/temporal-analysis", "/temporal-visualization", "/simulate-custom"]):
        if method == "POST":
            return "COMPUTE"
        return "NORMAL_READ"

    # Reconstruct, experiments run - critical cost
    if any(x in path for x in ["/reconstruct", "/experiments/run"]) and method == "POST":
        return "CRITICAL_COST"

    # Cancel, reset, apply-patch - mutation
    if any(x in path for x in ["/cancel", "/reset", "/apply-patch"]) and method == "POST":
        return "MUTATION"

    # Hypothesis test - experiment
    if "/hypotheses/" in path and "/test" in path and method == "POST":
        return "EXPERIMENT"

    # Patch verification - patch
    if "/patches" in path:
        if method == "POST":
            return "PATCH"
        return "NORMAL_READ"

    # Report export, download - download
    if any(x in path for x in ["/report", "/reports", "/download-patch", "/export-patch"]):
        if method == "DELETE":
            return "MUTATION"
        return "DOWNLOAD"

    # Events, timeline, hypotheses, experiments list - normal read
    if any(x in path for x in ["/events", "/timeline", "/hypotheses", "/experiments"]) and method == "GET":
        return "NORMAL_READ"

    # SSE stream - stream
    if "/stream" in path:
        return "STREAM"

    # Default
    return "NORMAL_READ"