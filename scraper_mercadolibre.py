import json
import logging
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://listado.mercadolibre.cl"
API_URL = "https://api.mercadolibre.com/sites/MLC/search"
TIMEOUT = 25
MAX_RESULTS = 5
WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es-419;q=0.9,es;q=0.8,en;q=0.7",
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

    score = len(q_tokens.intersection(n_tokens)) * 10
    if _normalize(query) in _normalize(nombre):
        score += 5
    return score


def _normalize_price(price: str) -> str:
    price = _clean_text(price)
    if not price:
        return ""
    return price if price.startswith("$") else f"${price}"


def _build_search_url(query: str) -> str:
    slug = "-".join(WORD_RE.findall(_normalize(query)))
    return f"{BASE_URL}/{quote(slug, safe='-')}"


def _extract_from_api(query: str) -> list[dict]:
    logging.info("[Mercado Libre] Intentando API oficial")
    try:
        response = requests.get(
            API_URL,
            params={"q": query, "limit": MAX_RESULTS},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.error("[Mercado Libre] API falló: %s", exc)
        return []

    payload = response.json()
    items = payload.get("results", []) if isinstance(payload, dict) else []

    results = []
    for item in items[:MAX_RESULTS]:
        nombre = _clean_text(item.get("title", ""))
        precio = _normalize_price(str(item.get("price", "")))
        url = _clean_text(item.get("permalink", ""))
        if not nombre or not url:
            continue

        results.append(
            {
                "tienda": "Mercado Libre",
                "nombre": nombre,
                "precio": precio,
                "url": url,
            }
        )

    return results


def _extract_from_html(query: str) -> list[dict]:
    search_url = _build_search_url(query)
    logging.info("[Mercado Libre] Intentando HTML: %s", search_url)

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.error("[Mercado Libre] HTML falló: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("li.ui-search-layout__item")

    results: list[dict] = []
    for item in items:
        title_node = item.select_one("h2.ui-search-item__title")
        price_node = item.select_one("span.andes-money-amount__fraction")
        link_node = item.select_one("a.ui-search-link[href]") or item.select_one("a[href]")

        nombre = _clean_text(title_node.get_text(" ") if title_node else "")
        precio = _normalize_price(price_node.get_text(" ") if price_node else "")
        url = _clean_text(link_node.get("href", "") if link_node else "")

        if not nombre or not url:
            continue

        results.append(
            {
                "tienda": "Mercado Libre",
                "nombre": nombre,
                "precio": precio,
                "url": url,
            }
        )
        if len(results) >= MAX_RESULTS:
            break

    if results:
        return results

    # fallback extra: JSON-LD embebido
    for script in soup.select('script[type="application/ld+json"]'):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        entries = data.get("itemListElement", []) if isinstance(data, dict) else []
        for entry in entries:
            item_data = entry.get("item", {}) if isinstance(entry, dict) else {}
            nombre = _clean_text(item_data.get("name", ""))
            precio = _normalize_price(str(item_data.get("price", "")))
            url = _clean_text(item_data.get("url", ""))
            if not nombre or not url:
                continue
            results.append(
                {
                    "tienda": "Mercado Libre",
                    "nombre": nombre,
                    "precio": precio,
                    "url": url,
                }
            )
            if len(results) >= MAX_RESULTS:
                return results

    return results


def buscar_mercadolibre(query: str) -> list[dict]:
    query = _clean_text(query)
    logging.info("[Mercado Libre] query: %s", query)

    if not query:
        logging.info("[Mercado Libre] resultados: 0 (query vacía)")
        return []

    results = _extract_from_api(query)
    if not results:
        results = _extract_from_html(query)

    results = sorted(results, key=lambda x: _score_result(query, x.get("nombre", "")), reverse=True)[:MAX_RESULTS]
    logging.info("[Mercado Libre] resultados: %s", len(results))
    return results


def search_mercadolibre(query: str) -> dict | None:
    try:
        results = buscar_mercadolibre(query)
        return results[0] if results else None
    except Exception as exc:
        logging.exception("[Mercado Libre] Error inesperado: %s", exc)
        return None
