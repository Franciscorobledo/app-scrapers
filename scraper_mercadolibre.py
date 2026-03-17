from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://listado.mercadolibre.cl"
TIMEOUT = 20
MAX_RESULTS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es-419;q=0.9,es;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _build_search_url(query: str) -> str:
    return f"{BASE_URL}/{quote_plus(query)}"


def _parse_item(item) -> dict | None:
    title_node = item.select_one(".ui-search-item__title")
    price_node = item.select_one(".andes-money-amount__fraction")
    link_node = item.select_one("a[href]")

    nombre = _clean_text(title_node.get_text(" ") if title_node else "")
    precio = _clean_text(price_node.get_text(" ") if price_node else "")
    url = _clean_text(link_node.get("href", "") if link_node else "")

    if not nombre or not url:
        return None

    return {
        "tienda": "MercadoLibre",
        "nombre": nombre,
        "precio": precio,
        "url": url,
    }


def buscar_mercadolibre(query: str) -> list[dict]:
    if not _clean_text(query):
        print("No se encontraron resultados en Mercado Libre")
        return []

    search_url = _build_search_url(query)
    print(f"[Mercado Libre] URL consultada: {search_url}")

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[Mercado Libre] Error en request: {exc}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select(".ui-search-result")

    results: list[dict] = []
    for item in items:
        parsed = _parse_item(item)
        if parsed:
            results.append(parsed)
        if len(results) >= MAX_RESULTS:
            break

    print(f"[Mercado Libre] Resultados encontrados: {len(results)}")

    if not results:
        print("No se encontraron resultados en Mercado Libre")
        return []

    return results


# BONUS: fallback preparado para Playwright (comentado)
# def buscar_mercadolibre_playwright(query: str) -> list[dict]:
#     from playwright.sync_api import sync_playwright
#
#     url = _build_search_url(query)
#     with sync_playwright() as p:
#         browser = p.chromium.launch(headless=True)
#         page = browser.new_page()
#         page.goto(url, wait_until="domcontentloaded", timeout=45000)
#         page.wait_for_timeout(2000)
#         html = page.content()
#         browser.close()
#
#     soup = BeautifulSoup(html, "html.parser")
#     items = soup.select(".ui-search-result")
#     results = []
#     for item in items[:MAX_RESULTS]:
#         parsed = _parse_item(item)
#         if parsed:
#             results.append(parsed)
#     return results


def search_mercadolibre(query: str) -> dict | None:
    """Compatibilidad con el flujo actual: retorna solo el primer resultado."""
    results = buscar_mercadolibre(query)
    return results[0] if results else None
