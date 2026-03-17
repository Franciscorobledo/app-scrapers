import unittest
from unittest.mock import patch

import scraper_mercadolibre as ml


class DummyResponse:
    def __init__(self, json_data=None, text="", status_code=200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class MercadoLibreSearchTests(unittest.TestCase):
    def test_api_path_returns_best_similarity(self):
        payload = {
            "results": [
                {
                    "title": "Taladro percutor 650w",
                    "price": 25990,
                    "permalink": "https://ml.example/taladro",
                },
                {
                    "title": "Set destornilladores 22 piezas",
                    "price": 13990,
                    "permalink": "https://ml.example/destornilladores",
                },
            ]
        }
        with patch("scraper_mercadolibre.requests.get", return_value=DummyResponse(json_data=payload)):
            result = ml.search_mercadolibre("destornillador")

        self.assertIsNotNone(result)
        self.assertIn("destornill", result["nombre"].lower())
        self.assertEqual(result["url"], "https://ml.example/destornilladores")

    def test_fallback_to_html_when_api_fails(self):
        html = """
        <ul>
          <li class='ui-search-layout__item'>
            <a class='ui-search-item__group__element' href='https://ml.example/item1'></a>
            <h2 class='ui-search-item__title'>Destornillador Philips</h2>
            <span class='andes-money-amount__fraction'>9.990</span>
          </li>
        </ul>
        """

        def fake_get(url, headers=None, timeout=0):
            if "api.mercadolibre.com" in url:
                raise RuntimeError("api down")
            return DummyResponse(text=html)

        with patch("scraper_mercadolibre.requests.get", side_effect=fake_get):
            result = ml.search_mercadolibre("destornillador")

        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://ml.example/item1")
        self.assertIn("Destornillador", result["nombre"])

    def test_returns_none_when_all_sources_fail(self):
        with patch("scraper_mercadolibre.requests.get", side_effect=RuntimeError("network error")):
            result = ml.search_mercadolibre("destornillador")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
