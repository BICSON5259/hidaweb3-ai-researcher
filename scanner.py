import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import websockets

from scanner_filters import evaluate_candidate, find_best_pair

logger = logging.getLogger("hidaweb3.scanner")

PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY")
BASE_URL = "wss://pumpportal.fun/api/data"

if PUMPPORTAL_API_KEY:
    URL = f"{BASE_URL}?{urlencode({'api-key': PUMPPORTAL_API_KEY})}"
else:
    URL = BASE_URL

DEXSCREENER_BATCH_URL = "https://api.dexscreener.com/tokens/v1/solana/"
POLL_INTERVAL_SECONDS = 60
MAX_CANDIDATES = 600
BATCH_SIZE = 30


def fetch_dex_pairs(token_addresses):
    """Fetch current Solana pools for up to 30 token addresses."""
    if not token_addresses:
        return []
    url = DEXSCREENER_BATCH_URL + ",".join(token_addresses)
    response = requests.get(
        url,
        headers={"Accept": "application/json", "User-Agent": "Hidaweb3/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def build_qualified_payload(result, pair, token_address):
    """Build a stable, Make.com-friendly event payload for a qualified token."""
    base_token = pair.get("baseToken") or {}
    quote_token = pair.get("quoteToken") or {}
    if str(base_token.get("address", "")).lower() == token_address.lower():
        token = base_token
    elif str(quote_token.get("address", "")).lower() == token_address.lower():
        token = quote_token
    else:
        token = {}

    return {
        "source": "Hidaweb3 AI Researcher",
        "event": "token_qualified",
        "event_id": f"solana:{token_address}:{result.get('pair_address') or 'no-pair'}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chain": "solana",
        "token_name": token.get("name"),
        "token_symbol": token.get("symbol"),
        "token_address": token_address,
        "market_cap_usd": result.get("market_cap_usd"),
        "volume_24h_usd": result.get("volume_24h_usd"),
        "liquidity_usd": result.get("liquidity_usd"),
        "token_age_hours": result.get("age_hours"),
        "pair_address": result.get("pair_address"),
        "dex_id": result.get("dex_id"),
        "dexscreener_url": result.get("pair_url"),
        "filter_status": result.get("status"),
        "filter_reason": result.get("reason"),
    }


def send_make_webhook(payload):
    """Send a qualified-token event to the configured Make.com custom webhook."""
    webhook_url = os.getenv("MAKE_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Make.com delivery skipped: MAKE_WEBHOOK_URL is not configured")
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": str(payload.get("event_id", "")),
            },
            timeout=20,
        )
        response.raise_for_status()
        logger.info(
            "Make.com webhook delivered: event_id=%s status_code=%s",
            payload.get("event_id"),
            response.status_code,
        )
        return True
    except requests.RequestException:
        logger.exception(
            "Make.com webhook delivery failed; qualified token will be retried: %s",
            payload.get("token_address"),
        )
        return False


async def monitor_candidates(candidates):
    """Poll market data and forward tokens that pass all core filters to Make.com."""
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        now = time.time()
        addresses = list(candidates.keys())

        if not addresses:
            continue

        logger.info("Filter engine: checking %s pending token candidates", len(addresses))
        for offset in range(0, len(addresses), BATCH_SIZE):
            batch = addresses[offset:offset + BATCH_SIZE]
            try:
                pairs = await asyncio.to_thread(fetch_dex_pairs, batch)
            except requests.RequestException:
                logger.exception("Filter engine: DEX Screener request failed")
                continue
            except Exception:
                logger.exception("Filter engine: unexpected market-data error")
                continue

            pairs_by_token = {address: [] for address in batch}
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                base = (pair.get("baseToken") or {}).get("address", "").lower()
                quote = (pair.get("quoteToken") or {}).get("address", "").lower()
                for address in batch:
                    if address.lower() in {base, quote}:
                        pairs_by_token[address].append(pair)

            for address in batch:
                candidate = candidates.get(address)
                if not candidate:
                    continue
                best_pair = find_best_pair(pairs_by_token.get(address), address)
                result = evaluate_candidate(
                    best_pair,
                    address,
                    candidate["observed_at"],
                    now,
                )

                if result["status"] == "qualified":
                    logger.info(
                        "HIDA_FILTER_QUALIFIED %s",
                        json.dumps(result, separators=(",", ":")),
                    )
                    payload = build_qualified_payload(result, best_pair, address)
                    delivered = await asyncio.to_thread(send_make_webhook, payload)
                    if delivered:
                        candidates.pop(address, None)
                    else:
                        logger.warning(
                            "Filter engine: qualified token remains queued for webhook retry: %s",
                            address,
                        )
                elif result["status"] == "expired":
                    logger.info("Filter engine: candidate expired: %s", address)
                    candidates.pop(address, None)
                else:
                    logger.debug(
                        "Filter engine: %s status=%s reason=%s",
                        address,
                        result["status"],
                        result["reason"],
                    )


async def start_scanner():
    """Connect to PumpPortal, collect new tokens, and run market filters."""
    reconnect_delay = 5
    max_reconnect_delay = 60
    candidates = {}
    monitor_task = asyncio.create_task(monitor_candidates(candidates))

    try:
        while True:
            try:
                logger.info("Scanner: opening PumpPortal WebSocket connection")

                async with websockets.connect(
                    URL,
                    open_timeout=20,
                    close_timeout=10,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=2**20,
                ) as ws:
                    reconnect_delay = 5
                    logger.info("Scanner: PumpPortal WebSocket connected")

                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    logger.info("Scanner: subscribeNewToken request sent")

                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    logger.info("Scanner: subscribeMigration request sent")
                    logger.info("Scanner: subscriptions sent; waiting for PumpPortal events")

                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except (json.JSONDecodeError, TypeError):
                            logger.warning("Scanner: received a non-JSON WebSocket message")
                            continue

                        if not isinstance(data, dict):
                            continue

                        if data.get("txType") == "create":
                            mint = data.get("mint")
                            if isinstance(mint, str) and mint:
                                if mint not in candidates and len(candidates) < MAX_CANDIDATES:
                                    candidates[mint] = {"observed_at": time.time()}
                                    logger.info(
                                        "Filter engine: new token candidate queued: %s (%s/%s)",
                                        mint,
                                        len(candidates),
                                        MAX_CANDIDATES,
                                    )
                                elif mint not in candidates:
                                    logger.warning(
                                        "Filter engine: candidate queue full; skipped %s",
                                        mint,
                                    )

                        logger.debug(
                            "Scanner: PumpPortal event: %s",
                            json.dumps(data, separators=(",", ":"))[:2000],
                        )

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Scanner: PumpPortal connection failed; retrying in %s seconds",
                    reconnect_delay,
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    finally:
        monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(start_scanner())
