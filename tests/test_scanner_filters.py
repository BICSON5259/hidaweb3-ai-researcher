import unittest

from scanner_filters import evaluate_candidate, find_best_pair


class ScannerFilterTests(unittest.TestCase):
    def setUp(self):
        self.mint = "TokenMint111"
        self.now = 2_000_000.0
        self.observed_at = self.now - (3 * 3600)

    def pair(self, market_cap=100_000, volume=150_000, liquidity=20_000):
        return {
            "pairAddress": "Pool111",
            "dexId": "raydium",
            "url": "https://dexscreener.com/solana/Pool111",
            "baseToken": {"address": self.mint},
            "quoteToken": {"address": "So111"},
            "marketCap": market_cap,
            "volume": {"h24": volume},
            "liquidity": {"usd": liquidity},
        }

    def test_all_filters_pass(self):
        result = evaluate_candidate(self.pair(), self.mint, self.observed_at, self.now)
        self.assertEqual(result["status"], "qualified")

    def test_under_two_hours_waits(self):
        result = evaluate_candidate(
            self.pair(), self.mint, self.now - 3600, self.now
        )
        self.assertEqual(result["status"], "pending")

    def test_over_48_hours_expires(self):
        result = evaluate_candidate(
            self.pair(), self.mint, self.now - (49 * 3600), self.now
        )
        self.assertEqual(result["status"], "expired")

    def test_low_volume_does_not_pass(self):
        result = evaluate_candidate(
            self.pair(volume=99_999), self.mint, self.observed_at, self.now
        )
        self.assertEqual(result["status"], "watching")

    def test_low_liquidity_does_not_pass(self):
        result = evaluate_candidate(
            self.pair(liquidity=9_999), self.mint, self.observed_at, self.now
        )
        self.assertEqual(result["status"], "watching")

    def test_wrong_token_pair_is_ignored(self):
        wrong = self.pair()
        wrong["baseToken"]["address"] = "DifferentMint"
        self.assertIsNone(find_best_pair([wrong], self.mint))


if __name__ == "__main__":
    unittest.main()
