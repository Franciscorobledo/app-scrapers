from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 20


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _search_mercadolibre_requests(query: str) -> dict | None:
    url = f"https://listado.mercadolibre.cl/{quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    item = soup.select_one("li.ui-search-layout__item")
    if not item:
        return None

    link = item.select_one("a.ui-search-item__group__element")
    if not link:
        return None

    title = item.select_one("h2.ui-search-item__title")
    fraction = item.select_one("span.andes-money-amount__fraction")
    cents = item.select_one("span.andes-money-amount__cents")

    price = ""
    if fraction:
        price = f"${_clean_text(fraction.get_text())}"
        if cents:
            price = f"{price},{_clean_text(cents.get_text())}"

    return {
        "nombre": _clean_text(title.get_text(" ") if title else ""),
        "precio": price,
        "url": link.get("href", ""),
    }


def _search_mercadolibre_playwright(query: str) -> dict | None:
    """Prepared fallback for dynamic pages if needed in the future.

    This keeps architecture ready without forcing playwright dependency.
    """
    return None


def search_mercadolibre(query: str) -> dict | None:
    try:
        return _search_mercadolibre_requests(query)
    except Exception as exc:
        print(f"[Mercado Libre] requests falló ({exc}), intentando fallback preparado")
        return _search_mercadolibre_playwright(query)
