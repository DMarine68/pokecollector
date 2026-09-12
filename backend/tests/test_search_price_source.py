import unittest

from services.search_price_source import (
    DEFAULT_SEARCH_PRICE_SOURCE,
    normalize_search_price_source,
    parse_search_price_source,
)


class TestSearchPriceSource(unittest.TestCase):
    def test_normalize_defaults_unknown_values(self):
        self.assertEqual(normalize_search_price_source(None), DEFAULT_SEARCH_PRICE_SOURCE)
        self.assertEqual(normalize_search_price_source("PriceCharting"), "pricecharting")
        self.assertEqual(normalize_search_price_source("nope"), DEFAULT_SEARCH_PRICE_SOURCE)

    def test_parse_rejects_invalid_values(self):
        self.assertEqual(parse_search_price_source("tcgplayer"), "tcgplayer")
        with self.assertRaises(ValueError):
            parse_search_price_source("ebay")


if __name__ == "__main__":
    unittest.main()
