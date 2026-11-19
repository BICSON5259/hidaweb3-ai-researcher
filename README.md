# Hidaweb3 AI Researcher

A Solana token-monitoring service that receives PumpPortal token events and checks candidates against Hidaweb3's core market filters using the public DEX Screener API.

## Current pipeline

1. Connect to PumpPortal WebSocket.
2. Subscribe to new-token and migration events.
3. Queue each observed `txType=create` mint as a candidate.
4. Every 60 seconds, check queued mints against DEX Screener in batches of up to 30 addresses.
5. Log `HIDA_FILTER_QUALIFIED` only when all core market filters pass.

## Core market filters

| Metric | Rule |
|---|---:|
| Token age | 2 to 48 hours |
| Market cap | $20,000 to $500,000 |
| 24-hour volume | At least $100,000 |
| Liquidity | At least $10,000 |

Token age is measured from the time this service receives the PumpPortal create event. This is a launch-time estimate only when the scanner is connected as the token is created. Tokens created while the service is offline are not backfilled by this in-memory candidate queue.

Market cap, 24-hour volume, and liquidity come from DEX Screener's current pair data. A token remains pending while it is younger than two hours or while DEX Screener has not indexed a pool / required metric. Candidates are removed after 48 hours or after they qualify.

## Logs to watch

- `PumpPortal WebSocket connected`
- `subscriptions sent`
- `Filter engine: new token candidate queued`
- `Filter engine: checking ... pending token candidates`
- `HIDA_FILTER_QUALIFIED`

A qualified log is a market-filter pass, not a buy recommendation or a completed security/fundamental audit.

## Environment variables

- `HIDA_SCANNER_ENABLED=true` — starts the scanner background thread.
- `PUMPPORTAL_API_KEY` — optional PumpPortal API key, if required by the account/subscription.
- `MAKE_WEBHOOK_URL` — Make.com webhook URL used by the protected test endpoint.
- `TEST_WEBHOOK_TOKEN` — required secret for `POST /test-webhook`.
- `LOG_LEVEL=INFO` — set to `DEBUG` for candidate-level filter reasons.

Never commit secret values to GitHub.

## Local tests

Run:

```bash
python -m unittest discover -s tests -v
```

## Current limitations / next stages

- Candidate state is in memory and is reset when the service restarts.
- The filter stage does not yet send Telegram or Make.com alerts.
- Smart-money, whale, holder concentration, dev-wallet, mint/freeze authority, and narrative/community analysis are not implemented yet.
- Do not treat a market-filter pass as proof that a token is safe.
