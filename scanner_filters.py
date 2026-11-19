"""Market-data filtering for Hidaweb3's Solana token candidates.

Token age is measured from the PumpPortal create event observed by this
scanner. This is a close launch-time estimate only when the scanner is
already connected as the token is created.
"""
from __future__ import annotations

from typing import Any

MIN_TOKEN_AGE_HOURS = 2.0
MAX_TOKEN_AGE_HOURS = 48.0
MIN_MARKET_CAP_USD = 20_000.0
MAX_MARKET_CAP_USD = 500_000.0
MIN_VOLUME_24H_USD = 100_000.0
MIN_LIQUIDITY_USD = 10_000.0


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def find_best_pair(pairs: Any, token_address: str) -> dict | None:
    """Choose the most liquid pair that actually contains the target token."""
    if not isinstance(pairs, list):
        return None

    matches = []
    target = token_address.lower()
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        base = pair.get("baseToken") or {}
        quote = pair.get("quoteToken") or {}
        addresses = {
            str(base.get("address", "")).lower(),
            str(quote.get("address", "")).lower(),
        }
        if target not in addresses:
            continue
        liquidity = _number((pair.get("liquidity") or {}).get("usd")) or 0.0
        matches.append((liquidity, pair))

    return max(matches, key=lambda item: item[0])[1] if matches else None


def evaluate_candidate(
    pair: dict | None,
    token_address: str,
    observed_at: float,
    now: float,
) -> dict:
    """Return pending, expired, watching, or qualified with transparent metrics."""
    age_hours = max(0.0, (now - observed_at) / 3600.0)
    result = {
        "token_address": token_address,
        "age_hours": round(age_hours, 2),
        "market_cap_usd": None,
        "volume_24h_usd": None,
        "liquidity_usd": None,
        "status": "pending",
        "reason": "",
        "pair_address": None,
        "dex_id": None,
        "pair_url": None,
    }

    if age_hours > MAX_TOKEN_AGE_HOURS:
        result.update(status="expired", reason="older than 48-hour limit")
        return result

    if age_hours < MIN_TOKEN_AGE_HOURS:
        result.update(status="pending", reason="waiting until token reaches 2 hours")
        return result

    if not pair:
        result.update(status="pending", reason="DEX Screener has no indexed pool yet")
        return result

    result["pair_address"] = pair.get("pairAddress")
    result["dex_id"] = pair.get("dexId")
    result["pair_url"] = pair.get("url")
    result["market_cap_usd"] = _number(pair.get("marketCap"))
    result["volume_24h_usd"] = _number((pair.get("volume") or {}).get("h24"))
    result["liquidity_usd"] = _number((pair.get("liquidity") or {}).get("usd"))

    missing = [
        label for label, value in (
            ("market cap", result["market_cap_usd"]),
            ("24h volume", result["volume_24h_usd"]),
            ("liquidity", result["liquidity_usd"]),
        ) if value is None
    ]
    if missing:
        result.update(status="pending", reason="missing DEX data: " + ", ".join(missing))
        return result

    checks = [
        (MIN_MARKET_CAP_USD <= result["market_cap_usd"] <= MAX_MARKET_CAP_USD,
         "market cap outside $20K-$500K"),
        (result["volume_24h_usd"] >= MIN_VOLUME_24H_USD,
         "24h volume below $100K"),
        (result["liquidity_usd"] >= MIN_LIQUIDITY_USD,
         "liquidity below $10K"),
    ]
    failed = [reason for passed, reason in checks if not passed]
    if failed:
        result.update(status="watching", reason="; ".join(failed))
        return result

    result.update(status="qualified", reason="all market filters passed")
    return result
