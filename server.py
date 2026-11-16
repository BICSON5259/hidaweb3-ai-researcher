import os
import json
import asyncio
import threading
import urllib.request
from flask import Flask, jsonify
from scanner import start_scanner

app = Flask(__name__)


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "bot": "Hidaweb3 AI Researcher"
    })


@app.route("/health")
def health():
    return "OK", 200


@app.route("/test-webhook")
def test_webhook():
    webhook_url = os.getenv("MAKE_WEBHOOK_URL")

    if not webhook_url:
        return jsonify({
            "error": "MAKE_WEBHOOK_URL is not configured"
        }), 500

    data = {
        "project": "Hidaweb3 AI Researcher",
        "event": "webhook_test",
        "token_name": "Hidaweb3 Test",
        "message": "Render is successfully sending data to Make.com."
    }

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return jsonify({
                "status": "sent",
                "make_response": response.read().decode("utf-8")
            }), 200

    except Exception as error:
        return jsonify({
            "status": "failed",
            "error": str(error)
        }), 500


def run_scanner():
    asyncio.run(start_scanner())


if __name__ == "__main__":
    scanner_thread = threading.Thread(
        target=run_scanner,
        daemon=True
    )
    scanner_thread.start()

    app.run(host="0.0.0.0", port=10000)
