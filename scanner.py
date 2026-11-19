import asyncio
import json
import logging
import os
from urllib.parse import urlencode

import websockets

logger = logging.getLogger("hidaweb3.scanner")

PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY")
BASE_URL = "wss://pumpportal.fun/api/data"

if PUMPPORTAL_API_KEY:
    URL = f"{BASE_URL}?{urlencode({'api-key': PUMPPORTAL_API_KEY})}"
else:
    URL = BASE_URL


async def start_scanner():
    """Connect to PumpPortal, subscribe to token events, and reconnect safely."""
    reconnect_delay = 5
    max_reconnect_delay = 60

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

                    logger.info(
                        "Scanner: received PumpPortal event: %s",
                        json.dumps(data, separators=(",", ":"))[:4000],
                    )

        except asyncio.CancelledError:
            logger.info("Scanner: shutdown requested")
            raise
        except Exception:
            logger.exception(
                "Scanner: PumpPortal connection failed; retrying in %s seconds",
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(start_scanner())
