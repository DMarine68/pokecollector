import unittest
from unittest.mock import MagicMock, patch

from services.pricecharting import (
    clean_card_number,
    build_pricecharting_urls,
    estimate_graded_prices,
    get_card_pricecharting_data,
)


class TestPriceCharting(unittest.TestCase):
    def test_clean_card_number(self):
        self.assertEqual(clean_card_number("111/197"), "111")
        self.assertEqual(clean_card_number("025/165"), "25")
        self.assertEqual(clean_card_number("GG01/GG70"), "GG01")
        self.assertEqual(clean_card_number(" 42 "), "42")
        self.assertEqual(clean_card_number(""), "")
        self.assertEqual(clean_card_number(None), "")

    def test_build_pricecharting_urls(self):
        search_url, direct_url = build_pricecharting_urls("Misty's Vitality", "111/197", "Pitch Black")
        self.assertIn("search-products?type=prices&q=Misty%27s+Vitality+111", search_url)
        self.assertEqual(direct_url, "https://www.pricecharting.com/game/pokemon-pitch-black/mistys-vitality-111")

        search_url2, direct_url2 = build_pricecharting_urls("Charizard", "4", "Base Set")
        self.assertIn("Charizard+4", search_url2)
        self.assertEqual(direct_url2, "https://www.pricecharting.com/game/pokemon-base-set/charizard-4")

    def test_estimate_graded_prices(self):
        est = estimate_graded_prices(10.0)
        self.assertEqual(est["ungraded"], 10.0)
        self.assertEqual(est["grade_7"], 10.5)
        self.assertEqual(est["grade_8"], 13.5)
        self.assertEqual(est["grade_9"], 28.0)
        self.assertEqual(est["grade_9_5"], 38.0)
        self.assertEqual(est["psa_10"], 85.0)
        self.assertTrue(est["is_estimate"])
        self.assertFalse(est["has_live_data"])

        empty_est = estimate_graded_prices(None)
        self.assertIsNone(empty_est["ungraded"])
        self.assertIsNone(empty_est["psa_10"])

    def test_get_card_pricecharting_data(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        current_user = MagicMock()
        current_user.id = 1

        card = MagicMock()
        card.id = "test-card-1"
        card.name = "Pikachu"
        card.number = "25/102"
        card.set_ref = MagicMock()
        card.set_ref.name = "Base Set"
        card.is_custom = False
        card.price_tcg_normal_market = 15.0
        card.price_tcg_holo_market = None
        card.price_market = 14.0
        card.price_trend = 14.5

        data = get_card_pricecharting_data(db, current_user, card)
        self.assertEqual(data["card_id"], "test-card-1")
        self.assertEqual(data["card_name"], "Pikachu")
        self.assertEqual(data["ungraded"], 15.0)
        self.assertEqual(len(data["grades"]), 6)
        # Verify PSA 10 entry
        psa10 = next(g for g in data["grades"] if g["id"] == "psa_10")
        self.assertTrue(psa10["is_psa10"])
        self.assertGreater(psa10["price"], 15.0)
        self.assertEqual(psa10["multiplier"], 8.5)


if __name__ == "__main__":
    unittest.main()
