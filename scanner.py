import asyncio
import json
import os
import websockets

PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY")

URL = "wss://pumpportal.fun/api/data"

if PUMPPORTAL_API_KEY:
    URL += f"?api-key={PUMPPORTAL_API_KEY}"


async def start_scanner():
    while True:
        try:
            print("Hidaweb3 connecting to PumpPortal...")

            async with websockets.connect(
                URL,
                open_timeout=20,
                close_timeout=10,
                ping_interval=20,
                ping_timeout=20
            ) as ws:

                print("Hidaweb3 Scanner is now LIVE!")

                await ws.send(json.dumps({
                    "method": "subscribeNewToken"
                }))

                await ws.send(json.dumps({
                    "method": "subscribeMigration"
                }))

                print("Subscriptions sent successfully.")

                async for message in ws:
                    data = json.loads(message)
                    print("PUMPPORTAL EVENT:")
                    print(json.dumps(data, indent=2))

        except Exception as error:
            print("SCANNER CONNECTION ERROR:", repr(error))
            print("Reconnecting in 10 seconds...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(start_scanner())
