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
            print("Hidaweb3 Scanner connecting to PumpPortal...")

            async with websockets.connect(URL) as ws:

                await ws.send(json.dumps({
                    "method": "subscribeNewToken"
                }))

                await ws.send(json.dumps({
                    "method": "subscribeMigration"
                }))

                print("Hidaweb3 Scanner is now LIVE!")

                async for message in ws:
                    data = json.loads(message)

                    print(
                        "NEW TOKEN EVENT:",
                        json.dumps(data)
                    )

        except Exception as error:
            print("Scanner connection error:", error)
            print("Reconnecting in 10 seconds...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(start_scanner())
