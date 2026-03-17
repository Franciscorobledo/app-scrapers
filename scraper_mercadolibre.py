import json
import re
import unicodedata
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://listado.mercadolibre.cl"
API_URL = "https://api.mercadolibre.com/sites/MLC/search"
TIMEOUT = 20
MAX_RESULTS = 5
WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)

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


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _tokenize(value: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(_normalize(value))}


def _score_result(query: str, nombre: str) -> int:
    q_tokens = _tokenize(query)
    n_tokens = _tokenize(nombre)
    if not q_tokens or not n_tokens:
        return 0

    overlap = len(q_tokens.intersection(n_tokens))
    score = overlap * 10

    q_normalized = _normalize(query)
    n_normalized = _normalize(nombre)
    if q_normalized in n_normalized:
        score += 5

    return score


def _build_search_url(query: str) -> str:
    return f"{BASE_URL}/{quote_plus(query)}"


def _normalize_price(price: str) -> str:
    price = _clean_text(price)
    if not price:
        return ""
    return price if price.startswith("$") else f"${price}"


def _parse_item(item) -> dict | None:
    title_node = item.select_one(".ui-search-item__title")
    price_node = item.select_one(".andes-money-amount__fraction")
    link_node = item.select_one("a.ui-search-link[href]") or item.select_one("a[href]")

    nombre = _clean_text(title_node.get_text(" ") if title_node else "")
    precio = _normalize_price(price_node.get_text(" ") if price_node else "")
    url = _clean_text(link_node.get("href", "") if link_node else "")

    if not nombre or not url:
        return None

    return {
        "tienda": "MercadoLibre",
        "nombre": nombre,
        "precio": precio,
        "url": url,
    }


def _extract_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(".ui-search-result")
    if not items:
        items = soup.select("li.ui-search-layout__item")

    results: list[dict] = []
    for item in items:
        parsed = _parse_item(item)
        if parsed:
            results.append(parsed)
            if len(results) >= MAX_RESULTS:
                break

    return results


def _extract_from_jsonld(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        entries = []
        if isinstance(data, dict) and isinstance(data.get("itemListElement"), list):
            entries = data["itemListElement"]
        elif isinstance(data, list):
            for element in data:
                if isinstance(element, dict) and isinstance(element.get("itemListElement"), list):
                    entries.extend(element["itemListElement"])

        for entry in entries:
            item_data = entry.get("item", {}) if isinstance(entry, dict) else {}
            nombre = _clean_text(item_data.get("name", ""))
            precio = _normalize_price(str(item_data.get("price", "")))
            url = _clean_text(item_data.get("url", ""))
            if not nombre or not url:
                continue
            results.append(
                {
                    "tienda": "MercadoLibre",
                    "nombre": nombre,
                    "precio": precio,
                    "url": url,
                }
            )
            if len(results) >= MAX_RESULTS:
                return results

    return results


def _fallback_api(query: str) -> list[dict]:
    try:
        response = requests.get(API_URL, params={"q": query, "limit": MAX_RESULTS}, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[Mercado Libre] Fallback API falló: {exc}")
        return []

    payload = response.json()
    api_results = payload.get("results", []) if isinstance(payload, dict) else []

    results: list[dict] = []
    for item in api_results[:MAX_RESULTS]:
        nombre = _clean_text(item.get("title", ""))
        precio = _normalize_price(str(item.get("price", "")))
        url = _clean_text(item.get("permalink", ""))

        if not nombre or not url:
            continue

        results.append(
            {
                "tienda": "MercadoLibre",
                "nombre": nombre,
                "precio": precio,
                "url": url,
            }
        )

    return results


def _sort_by_relevance(results: list[dict], query: str) -> list[dict]:
    return sorted(results, key=lambda x: _score_result(query, x.get("nombre", "")), reverse=True)


def buscar_mercadolibre(query: str) -> list[dict]:
    query = _clean_text(query)
    if not query:
        print("No se encontraron resultados en Mercado Libre")
        return []

    search_url = _build_search_url(query)
    print(f"[Mercado Libre] URL consultada: {search_url}")

    html = ""
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        html = response.text
    except requests.RequestException as exc:
        print(f"[Mercado Libre] Error en request HTML: {exc}")

    results = _extract_from_html(html) if html else []
    if not results and html:
        results = _extract_from_jsonld(html)
    if not results:
        results = _fallback_api(query)

    results = _sort_by_relevance(results, query)[:MAX_RESULTS]
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
#     results = _extract_from_html(html) or _extract_from_jsonld(html)
#     return _sort_by_relevance(results, query)[:MAX_RESULTS]


def search_mercadolibre(query: str) -> dict | None:
    """Compatibilidad con el flujo actual: retorna el mejor resultado por relevancia."""
    results = buscar_mercadolibre(query)
    return results[0] if results else None
