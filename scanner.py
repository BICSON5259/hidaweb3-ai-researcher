import asyncio
import json
import logging
import os
import time
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


async def monitor_candidates(candidates):
    """Poll market data in batches and log tokens that pass all core filters."""
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
                    candidates.pop(address, None)
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

                        # PumpPortal sends a create event with the token mint address.
                        if data.get("txType") == "create":
                            mint = data.get("mint")
                            if isinstance(mint, str) and mint:
                                if mint not in candidates and len(candidates) < MAX_CANDIDATES:
                                    candidates[mint] = {"observed_at": time.time()}
                                    logger.info(
                                        "Filter engine: new token candidate queued: %s "
                                        "(%s/%s)",
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
