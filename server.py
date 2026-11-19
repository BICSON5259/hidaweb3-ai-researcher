import asyncio
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request

from flask import Flask, jsonify, request

from scanner import start_scanner

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("hidaweb3")

app = Flask(__name__)

_scanner_lock = threading.Lock()
_scanner_thread = None


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "bot": "Hidaweb3 AI Researcher",
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/test-webhook", methods=["POST"])
def test_webhook():
    # Fail closed: this endpoint must never be publicly callable without a secret.
    expected_token = os.getenv("TEST_WEBHOOK_TOKEN")
    supplied_token = request.headers.get("X-Webhook-Token", "")

    if not expected_token:
        logger.error("TEST_WEBHOOK_TOKEN is not configured")
        return jsonify({"error": "Webhook test authentication is not configured"}), 503

    if not supplied_token or not hmac.compare_digest(supplied_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401

    webhook_url = os.getenv("MAKE_WEBHOOK_URL")
    if not webhook_url:
        return jsonify({"error": "MAKE_WEBHOOK_URL is not configured"}), 503

    data = {
        "project": "Hidaweb3 AI Researcher",
        "event": "webhook_test",
        "token_name": "Hidaweb3 Test",
        "message": "Render is successfully sending data to Make.com.",
    }

    outgoing_request = urllib.request.Request(
        webhook_url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(outgoing_request, timeout=20) as response:
            return jsonify({
                "status": "sent",
                "make_status_code": response.status,
                "make_response": response.read().decode("utf-8", errors="replace"),
            }), 200
    except (urllib.error.URLError, TimeoutError) as error:
        logger.exception("Make.com webhook delivery failed")
        return jsonify({
            "status": "failed",
            "error": str(error),
        }), 502


def run_scanner():
    try:
        asyncio.run(start_scanner())
    except Exception:
        # Keep the web process alive if the scanner exits unexpectedly.
        logger.exception("Scanner background task stopped unexpectedly")


def start_scanner_background():
    """Start one scanner thread in this web worker when the WSGI app loads."""
    global _scanner_thread

    if os.getenv("HIDA_SCANNER_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        logger.info("Scanner startup disabled by HIDA_SCANNER_ENABLED")
        return

    with _scanner_lock:
        if _scanner_thread and _scanner_thread.is_alive():
            return

        _scanner_thread = threading.Thread(
            target=run_scanner,
            name="hidaweb3-scanner",
            daemon=True,
        )
        _scanner_thread.start()
        logger.info("Hidaweb3 scanner background thread started")


# Gunicorn imports this module; __main__ is not executed under a WSGI server.
# Render is configured with one Gunicorn worker to avoid duplicate scanner loops.
start_scanner_background()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
    )
