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


def search_easy(query: str) -> dict | None:
    url = f"https://www.easy.cl/tienda/s?Ntt={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    link_node = soup.select_one("article a[href*='/p/']") or soup.select_one("a[href*='/p/']")
    if not link_node:
        return None

    link = urljoin("https://www.easy.cl", link_node.get("href", ""))
    container = link_node.parent if link_node.parent else soup

    name_node = (
        container.select_one("h2")
        or container.select_one("h3")
        or container.select_one("span[class*='product']")
    )
    price_node = (
        container.select_one("span[class*='price']")
        or container.select_one("div[class*='price']")
    )

    return {
        "nombre": _clean_text(name_node.get_text(" ") if name_node else link_node.get_text(" ")),
        "precio": _clean_text(price_node.get_text(" ") if price_node else ""),
        "url": link,
    }
