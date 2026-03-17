from urllib.parse import quote_plus, urljoin

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


def search_sodimac(query: str) -> dict | None:
    url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    card = soup.select_one("a.pod-link") or soup.select_one("a[href*='/product/']")
    if not card:
        return None

    link = urljoin("https://www.sodimac.cl", card.get("href", ""))
    name_node = card.select_one("b.pod-subTitle") or card.select_one("span.pod-title")
    if not name_node:
        name_node = soup.select_one("b.pod-subTitle")

    price_node = card.select_one("span.prices-main-price") or soup.select_one(
        "span.prices-main-price"
    )

    return {
        "nombre": _clean_text(name_node.get_text(" ") if name_node else ""),
        "precio": _clean_text(price_node.get_text(" ") if price_node else ""),
        "url": link,
    }
