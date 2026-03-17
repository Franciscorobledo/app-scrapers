import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
    PlaywrightTimeoutError = Exception


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CL,es-419;q=0.9,es;q=0.8,en;q=0.7",
}
TIMEOUT = 25
PRICE_RE = re.compile(r"\$\s*[\d\.,]+")


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _extract_price(text: str) -> str:
    match = PRICE_RE.search(_clean_text(text))
    return match.group(0) if match else ""


def _normalize_result(nombre: str, precio: str, href: str) -> dict:
    return {
        "tienda": "Sodimac",
        "nombre": _clean_text(nombre),
        "precio": _clean_text(precio),
        "url": urljoin("https://www.sodimac.cl", href or ""),
    }


def _extract_from_playwright(query: str, max_resultados: int) -> list[dict]:
    if sync_playwright is None:
        logging.warning("[Sodimac] Playwright no disponible")
        return []

    search_url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector("div[data-testid='product-card']", state="visible", timeout=15000)

            cards = page.locator("div[data-testid='product-card']")
            total = min(cards.count(), max_resultados)
            seen = set()

            for idx in range(total):
                card = cards.nth(idx)
                link = card.locator("a[href]").first
                href = link.get_attribute("href") if link.count() else ""
                full_url = urljoin("https://www.sodimac.cl", href or "")
                if not href or full_url in seen:
                    continue

                seen.add(full_url)
                title_loc = card.locator("[data-testid*='title'], h2, h3, b, span").first
                price_loc = card.locator("[data-testid*='price'], span[class*='price'], div[class*='price'], span, div").first

                nombre = _clean_text(title_loc.inner_text()) if title_loc.count() else _clean_text(card.inner_text())
                precio_raw = _clean_text(price_loc.inner_text()) if price_loc.count() else _clean_text(card.inner_text())
                precio = _extract_price(precio_raw)

                if not nombre:
                    continue

                results.append(_normalize_result(nombre, precio, href))
        finally:
            browser.close()

    return results


def _extract_from_embedded_json(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    for script in soup.select("script"):
        raw = (script.string or script.get_text() or "").strip()
        if "itemListElement" not in raw and "products" not in raw:
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        entries = []
        if isinstance(data, dict) and isinstance(data.get("itemListElement"), list):
            entries = data["itemListElement"]

        for entry in entries:
            item = entry.get("item", {}) if isinstance(entry, dict) else {}
            nombre = _clean_text(item.get("name", ""))
            precio = _clean_text(str(item.get("price", "")))
            precio = _extract_price(precio) if precio else ""
            href = _clean_text(item.get("url", ""))

            if not nombre or not href:
                continue

            results.append(_normalize_result(nombre, precio, href))
            if len(results) >= max_resultados:
                return results

    return results


def _extract_from_html(html: str, max_resultados: int) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div[data-testid='product-card']")
    if not cards:
        cards = soup.select("a[href*='/product/']")

    results: list[dict] = []
    seen = set()

    for card in cards:
        link = card.select_one("a[href]") if card.name != "a" else card
        if not link:
            continue

        href = _clean_text(link.get("href", ""))
        full_url = urljoin("https://www.sodimac.cl", href)
        if not href or full_url in seen:
            continue

        seen.add(full_url)

        name_node = card.select_one("[data-testid*='title']") or card.select_one("h2") or card.select_one("h3")
        price_node = card.select_one("[data-testid*='price']") or card.select_one("span[class*='price']")

        nombre = _clean_text(name_node.get_text(" ") if name_node else card.get_text(" "))
        precio = _extract_price(price_node.get_text(" ") if price_node else card.get_text(" "))

        if not nombre:
            continue

        results.append(_normalize_result(nombre, precio, href))
        if len(results) >= max_resultados:
            break

    return results


def _buscar_sodimac_requests(query: str, max_resultados: int) -> list[dict]:
    search_url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    logging.info("[Sodimac] requests URL: %s", search_url)

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.error("[Sodimac] requests falló: %s", exc)
        return []

    html = response.text
    results = _extract_from_html(html, max_resultados)
    if not results:
        results = _extract_from_embedded_json(html, max_resultados)
    return results


def buscar_sodimac(query: str, max_resultados: int = 5) -> list[dict]:
    query = _clean_text(query)
    logging.info("[Sodimac] query: %s", query)

    if not query:
        logging.info("[Sodimac] resultados: 0 (query vacía)")
        return []

    try:
        results = _extract_from_playwright(query, max_resultados)
        if results:
            logging.info("[Sodimac] resultados Playwright: %s", len(results))
            return results
    except PlaywrightTimeoutError:
        logging.warning("[Sodimac] timeout esperando productos con Playwright")
    except Exception as exc:
        logging.exception("[Sodimac] error Playwright: %s", exc)

    results = _buscar_sodimac_requests(query, max_resultados)
    logging.info("[Sodimac] resultados fallback requests: %s", len(results))
    return results


def search_sodimac(query: str) -> Optional[dict]:
    results = buscar_sodimac(query=query, max_resultados=5)
    return results[0] if results else None
