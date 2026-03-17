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
    )
}
TIMEOUT = 20
PRICE_RE = re.compile(r"\$\s*[\d\.,]+")


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _extract_price(text: str) -> str:
    match = PRICE_RE.search(_clean_text(text))
    return match.group(0) if match else ""


def _extract_name_from_card(card) -> str:
    candidate_selectors = [
        "[data-testid='product-title']",
        "[data-testid*='title']",
        "h2",
        "h3",
        "b",
        "span",
    ]

    for selector in candidate_selectors:
        locator = card.locator(selector).first
        if locator.count() == 0:
            continue
        text = _clean_text(locator.inner_text())
        if text and "$" not in text:
            return text

    raw_text = _clean_text(card.inner_text())
    for line in raw_text.split(" "):
        if line and "$" not in line:
            return line
    return ""


def _extract_price_from_card(card) -> str:
    candidate_selectors = [
        "[data-testid*='price']",
        "span[class*='price']",
        "div[class*='price']",
        "span",
        "div",
    ]

    for selector in candidate_selectors:
        locator = card.locator(selector)
        total = min(locator.count(), 6)
        for idx in range(total):
            text = _clean_text(locator.nth(idx).inner_text())
            price = _extract_price(text)
            if price:
                return price

    return _extract_price(_clean_text(card.inner_text()))


def _buscar_sodimac_requests(query: str, max_resultados: int = 5) -> list[dict]:
    url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("div[data-testid='product-card']") or soup.select("a[href*='/product/']")

    resultados = []
    seen_urls = set()

    for card in cards:
        link = card.select_one("a[href]") if card.name != "a" else card
        if not link:
            continue

        href = link.get("href", "")
        full_url = urljoin("https://www.sodimac.cl", href)
        if not href or full_url in seen_urls:
            continue

        seen_urls.add(full_url)
        name = _clean_text(card.get_text(" "))
        price = _extract_price(card.get_text(" "))

        if not name:
            continue

        resultados.append(
            {
                "tienda": "Sodimac",
                "nombre": name,
                "precio": price,
                "url": full_url,
            }
        )

        if len(resultados) >= max_resultados:
            break

    return resultados


def buscar_sodimac(query: str, max_resultados: int = 5) -> list[dict]:
    print(f"[Sodimac] query: {query}")

    if not query:
        print("[Sodimac] resultados: 0")
        return []

    if sync_playwright is None:
        print("[Sodimac] Playwright no disponible, usando fallback requests")
        try:
            results = _buscar_sodimac_requests(query, max_resultados=max_resultados)
            print(f"[Sodimac] resultados: {len(results)}")
            return results
        except Exception as exc:
            print(f"[Sodimac] error en fallback requests: {exc}")
            return []

    search_url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    browser = None
    resultados: list[dict] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)

            page.wait_for_selector("div[data-testid='product-card']", state="visible", timeout=15000)

            cards = page.locator("div[data-testid='product-card']")
            total_cards = cards.count()
            seen_urls = set()

            for idx in range(min(total_cards, max_resultados)):
                card = cards.nth(idx)

                link = card.locator("a[href]").first
                href = link.get_attribute("href") if link.count() else ""
                full_url = urljoin("https://www.sodimac.cl", href or "")

                if not href or full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                nombre = _extract_name_from_card(card)
                precio = _extract_price_from_card(card)

                if not nombre:
                    continue

                resultados.append(
                    {
                        "tienda": "Sodimac",
                        "nombre": nombre,
                        "precio": precio,
                        "url": full_url,
                    }
                )

    except PlaywrightTimeoutError:
        print("[Sodimac] no se encontraron productos visibles")
        return []
    except Exception as exc:
        print(f"[Sodimac] error con Playwright: {exc}")
        try:
            resultados = _buscar_sodimac_requests(query, max_resultados=max_resultados)
        except Exception as fallback_exc:
            print(f"[Sodimac] fallback requests falló: {fallback_exc}")
            resultados = []
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    print(f"[Sodimac] resultados: {len(resultados)}")
    return resultados


def search_sodimac(query: str) -> Optional[dict]:
    results = buscar_sodimac(query=query, max_resultados=5)
    return results[0] if results else None
