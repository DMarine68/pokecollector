import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

from services.pricecharting import (
    _payload_from_pricecharting_product,
    _pick_pricecharting_product,
    _product_page_url,
    build_pricecharting_urls,
    clean_card_number,
    enrich_pricecharting_ungraded,
    estimate_graded_prices,
    fetch_pricecharting_api,
    get_card_pricecharting_data,
    persist_live_ungraded_price,
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
        self.assertEqual(direct_url, "https://www.pricecharting.com/game/pokemon-pitch-black/misty's-vitality-111")

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

    def test_payload_from_pricecharting_product_converts_cents(self):
        payload = _payload_from_pricecharting_product({
            "loose-price": 740,
            "manual-only-price": 8500,
            "sales-volume": 12,
        })
        self.assertEqual(payload["ungraded"], 7.4)
        self.assertEqual(payload["psa_10"], 85.0)
        self.assertEqual(payload["sales_volume_year"], 12)
        self.assertTrue(payload["has_live_data"])
        self.assertIsNone(_payload_from_pricecharting_product({"loose-price": 0}))

    def test_payload_maps_card_grades_from_video_game_fields(self):
        payload = _payload_from_pricecharting_product({
            "id": "13644131",
            "product-name": "Misty's Vitality #111",
            "console-name": "Pokemon Pitch Black",
            "loose-price": 1847,
            "cib-price": 0,
            "new-price": 0,
            "graded-price": 6250,
            "box-only-price": 6900,
            "manual-only-price": 18434,
            "sales-volume": 365,
        })
        self.assertEqual(payload["ungraded"], 18.47)
        self.assertIsNone(payload["grade_7"])
        self.assertIsNone(payload["grade_8"])
        self.assertEqual(payload["grade_9"], 62.50)
        self.assertEqual(payload["grade_9_5"], 69.00)
        self.assertEqual(payload["psa_10"], 184.34)
        self.assertEqual(payload["sales_volume_year"], 365)
        self.assertEqual(
            payload["product_url"],
            "https://www.pricecharting.com/game/pokemon-pitch-black/misty's-vitality-111",
        )

    def test_payload_accepts_underscore_price_keys(self):
        payload = _payload_from_pricecharting_product({
            "loose_price": 1847,
            "graded_price": 6250,
            "manual_only_price": 18434,
        })
        self.assertEqual(payload["ungraded"], 18.47)
        self.assertEqual(payload["grade_9"], 62.50)
        self.assertEqual(payload["psa_10"], 184.34)

    def test_persist_live_ungraded_price_ignores_estimates(self):
        db = MagicMock()
        card = MagicMock()
        self.assertFalse(persist_live_ungraded_price(db, card, None, commit=False))
        self.assertTrue(persist_live_ungraded_price(db, card, 7.4, commit=True))
        self.assertEqual(card.price_pc_ungraded, 7.4)
        self.assertIsNotNone(card.price_pc_synced_at)
        db.commit.assert_called_once()

    def test_enrich_pricecharting_ungraded_persists_live_api_prices(self):
        db = MagicMock()
        current_user = MagicMock()
        current_user.id = 1
        card = MagicMock()
        card.id = "sv1-1_en"
        card.name = "Pikachu"
        card.number = "25"
        card.is_custom = False
        card.price_pc_ungraded = None
        card.price_pc_synced_at = None

        live = {
            "source": "pricecharting_api",
            "has_live_data": True,
            "ungraded": 6.5,
        }
        with patch("services.pricecharting.resolve_pricecharting_api_token", return_value="token"), \
             patch("services.pricecharting.fetch_pricecharting_api", return_value=live):
            enrich_pricecharting_ungraded(db, current_user, [card], max_fetches=1)

        self.assertEqual(card.price_pc_ungraded, 6.5)
        db.commit.assert_called_once()

    def test_enrich_pricecharting_ungraded_skips_fresh_cache(self):
        db = MagicMock()
        current_user = MagicMock()
        card = MagicMock()
        card.id = "sv1-2_en"
        card.is_custom = False
        card.price_pc_ungraded = 11.0
        card.price_pc_synced_at = datetime.datetime.utcnow()

        with patch("services.pricecharting.resolve_pricecharting_api_token", return_value="token") as token_mock, \
             patch("services.pricecharting.fetch_pricecharting_api") as fetch_mock:
            enrich_pricecharting_ungraded(db, current_user, [card], max_fetches=1)

        fetch_mock.assert_not_called()
        token_mock.assert_called_once()
        db.commit.assert_not_called()

    def test_enrich_pricecharting_ungraded_skips_live_fetches_by_default(self):
        db = MagicMock()
        current_user = MagicMock()
        card = MagicMock()
        card.is_custom = False
        card.price_pc_ungraded = None
        card.price_pc_synced_at = None

        with patch("services.pricecharting.resolve_pricecharting_api_token") as token_mock, \
             patch("services.pricecharting.fetch_pricecharting_api") as fetch_mock:
            enrich_pricecharting_ungraded(db, current_user, [card])

        token_mock.assert_not_called()
        fetch_mock.assert_not_called()

    def test_pick_pricecharting_product_prefers_matching_number(self):
        products = [
            {"id": "1", "product-name": "Pikachu #001", "console-name": "Pokemon Base"},
            {"id": "2", "product-name": "Pikachu #25", "console-name": "Pokemon Base Set"},
        ]
        picked = _pick_pricecharting_product(products, "Pikachu", "025/102")
        self.assertEqual(picked["id"], "2")
        self.assertEqual(
            _product_page_url(picked),
            "https://www.pricecharting.com/game/pokemon-base-set/pikachu-25",
        )

    def test_fetch_pricecharting_api_loads_full_product_when_search_omits_grades(self):
        calls = []

        def fake_http_get(url, headers, timeout):
            calls.append(url)
            if "/api/products?" in url:
                return json.dumps({
                    "status": "success",
                    "products": [{
                        "id": "13644131",
                        "product-name": "Misty's Vitality #111",
                        "console-name": "Pokemon Pitch Black",
                        "loose-price": 1847,
                    }],
                })
            if "/api/product?" in url and "id=13644131" in url:
                return json.dumps({
                    "status": "success",
                    "id": "13644131",
                    "product-name": "Misty's Vitality #111",
                    "console-name": "Pokemon Pitch Black",
                    "loose-price": 1847,
                    "cib-price": 0,
                    "new-price": 0,
                    "graded-price": 6250,
                    "box-only-price": 6900,
                    "manual-only-price": 18434,
                    "sales-volume": 365,
                })
            raise AssertionError(url)

        with patch("services.pricecharting._http_get", side_effect=fake_http_get):
            payload = fetch_pricecharting_api(
                "token",
                "Misty's Vitality",
                "111",
                set_name="Pitch Black",
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(payload["ungraded"], 18.47)
        self.assertEqual(payload["grade_9"], 62.50)
        self.assertEqual(payload["grade_9_5"], 69.00)
        self.assertEqual(payload["psa_10"], 184.34)
        self.assertEqual(payload["sales_volume_year"], 365)

    def test_fetch_pricecharting_api_skips_product_lookup_when_grades_present(self):
        calls = []

        def fake_http_get(url, headers, timeout):
            calls.append(url)
            return json.dumps({
                "status": "success",
                "products": [{
                    "id": "13644131",
                    "product-name": "Misty's Vitality #111",
                    "console-name": "Pokemon Pitch Black",
                    "loose-price": 1847,
                    "cib-price": 0,
                    "new-price": 0,
                    "graded-price": 6250,
                    "box-only-price": 6900,
                    "manual-only-price": 18434,
                }],
            })

        with patch("services.pricecharting._http_get", side_effect=fake_http_get):
            payload = fetch_pricecharting_api("token", "Misty's Vitality", "111")

        self.assertEqual(len(calls), 1)
        self.assertIn("/api/products?", calls[0])
        self.assertEqual(payload["psa_10"], 184.34)

    def test_fetch_pricecharting_api_ungraded_only_skips_second_request(self):
        calls = []

        def fake_http_get(url, headers, timeout):
            calls.append(url)
            return json.dumps({
                "status": "success",
                "products": [{
                    "id": "13644131",
                    "product-name": "Misty's Vitality #111",
                    "console-name": "Pokemon Pitch Black",
                    "loose-price": 1847,
                }],
            })

        with patch("services.pricecharting._http_get", side_effect=fake_http_get):
            payload = fetch_pricecharting_api(
                "token",
                "Misty's Vitality",
                "111",
                ungraded_only=True,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(payload["ungraded"], 18.47)
        self.assertIsNone(payload["psa_10"])


if __name__ == "__main__":
    unittest.main()
