import logging
import re
from dataclasses import dataclass, asdict
from typing import Callable, Optional
from urllib.parse import quote_plus, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Playwright is optional at runtime and only used as a fallback for Mercado Libre.
try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 20


@dataclass
class SearchResult:
    sku_original: str
    nombre_original: str
    nombre_encontrado: str
    precio: str
    url: str
    tienda: str


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def clean_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_price(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    if "$" in text:
        return text
    digits = re.sub(r"[^\d,\.]", "", text)
    return f"${digits}" if digits else text


def try_query(
    store_name: str,
    search_fn: Callable[[str], Optional[dict]],
    sku: str,
    nombre: str,
) -> Optional[dict]:
    for query in [clean_text(sku), clean_text(nombre)]:
        if not query:
            continue
        logging.info("[%s] buscando: %s", store_name, query)
        try:
            result = search_fn(query)
            if result:
                logging.info("[%s] encontrado: %s", store_name, result.get("nombre", ""))
                return result
        except Exception as exc:
            logging.error("[%s] error con query '%s': %s", store_name, query, exc)
    return None


def search_sodimac(query: str) -> Optional[dict]:
    search_url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    soup = get_soup(search_url)

    card = soup.select_one("a.pod-link") or soup.select_one("a[href*='/sodimac-cl/product/']")
    if not card:
        return None

    link = card.get("href", "")
    full_url = urljoin("https://www.sodimac.cl", link)

    name_node = (
        card.select_one("b.pod-subTitle")
        or card.select_one("span.pod-title")
        or soup.select_one("b.pod-subTitle")
    )
    price_node = (
        card.select_one("span.prices-main-price")
        or card.select_one("span.pod-prices")
        or soup.select_one("span.prices-main-price")
    )

    return {
        "nombre": clean_text(name_node.get_text(" ") if name_node else ""),
        "precio": normalize_price(price_node.get_text(" ") if price_node else ""),
        "url": full_url,
        "tienda": "Sodimac",
    }


def search_easy(query: str) -> Optional[dict]:
    search_url = f"https://www.easy.cl/tienda/s?Ntt={quote_plus(query)}"
    soup = get_soup(search_url)

    card = soup.select_one("article a[href*='/p/']") or soup.select_one("a[href*='/p/']")
    if not card:
        return None

    full_url = urljoin("https://www.easy.cl", card.get("href", ""))

    container = card.parent if card.parent else soup
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
        "nombre": clean_text(name_node.get_text(" ") if name_node else card.get_text(" ")),
        "precio": normalize_price(price_node.get_text(" ") if price_node else ""),
        "url": full_url,
        "tienda": "Easy",
    }


def search_mercadolibre_requests(query: str) -> Optional[dict]:
    search_url = f"https://listado.mercadolibre.cl/{quote_plus(query)}"
    soup = get_soup(search_url)

    item = soup.select_one("li.ui-search-layout__item")
    if not item:
        return None

    link = item.select_one("a.ui-search-item__group__element")
    name = item.select_one("h2.ui-search-item__title")
    fraction = item.select_one("span.andes-money-amount__fraction")
    cents = item.select_one("span.andes-money-amount__cents")

    if not link:
        return None

    precio = ""
    if fraction:
        precio = f"${clean_text(fraction.get_text())}"
        if cents:
            precio += f",{clean_text(cents.get_text())}"

    return {
        "nombre": clean_text(name.get_text(" ") if name else ""),
        "precio": precio,
        "url": link.get("href", ""),
        "tienda": "MercadoLibre",
    }


def search_mercadolibre_playwright(query: str) -> Optional[dict]:
    if sync_playwright is None:
        logging.warning("Playwright no está disponible para fallback de Mercado Libre.")
        return None

    search_url = f"https://listado.mercadolibre.cl/{quote_plus(query)}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)

        title = page.locator("h2.ui-search-item__title").first
        link = page.locator("a.ui-search-item__group__element").first
        fraction = page.locator("span.andes-money-amount__fraction").first

        if title.count() == 0 or link.count() == 0:
            browser.close()
            return None

        result = {
            "nombre": clean_text(title.inner_text()),
            "precio": normalize_price(fraction.inner_text()) if fraction.count() else "",
            "url": link.get_attribute("href") or "",
            "tienda": "MercadoLibre",
        }
        browser.close()
        return result


def search_mercadolibre(query: str) -> Optional[dict]:
    try:
        return search_mercadolibre_requests(query)
    except Exception as exc:
        logging.warning("Mercado Libre por requests falló (%s). Usando Playwright...", exc)
        return search_mercadolibre_playwright(query)


def process_products(input_file: str = "productos.xlsx", output_file: str = "resultados.xlsx") -> None:
    logging.info("Leyendo archivo: %s", input_file)
    df = pd.read_excel(input_file)

    expected_columns = {"SKU", "Nombre"}
    if not expected_columns.issubset(df.columns):
        raise ValueError("El archivo Excel debe contener las columnas SKU y Nombre")

    all_results: list[SearchResult] = []

    for index, row in df.iterrows():
        sku = clean_text(str(row.get("SKU", "")))
        nombre = clean_text(str(row.get("Nombre", "")))

        logging.info("Procesando %s/%s | SKU=%s | Nombre=%s", index + 1, len(df), sku, nombre)

        store_searches = [
            ("Sodimac", search_sodimac),
            ("MercadoLibre", search_mercadolibre),
            ("Easy", search_easy),
        ]

        for store_name, fn in store_searches:
            found = try_query(store_name, fn, sku, nombre)
            if found:
                all_results.append(
                    SearchResult(
                        sku_original=sku,
                        nombre_original=nombre,
                        nombre_encontrado=found.get("nombre", ""),
                        precio=found.get("precio", ""),
                        url=found.get("url", ""),
                        tienda=found.get("tienda", store_name),
                    )
                )
            else:
                all_results.append(
                    SearchResult(
                        sku_original=sku,
                        nombre_original=nombre,
                        nombre_encontrado="No encontrado",
                        precio="",
                        url="",
                        tienda=store_name,
                    )
                )

    output_df = pd.DataFrame([asdict(result) for result in all_results])
    output_df = output_df.rename(
        columns={
            "sku_original": "SKU original",
            "nombre_original": "Nombre original",
            "nombre_encontrado": "Nombre encontrado",
            "precio": "Precio",
            "url": "URL",
            "tienda": "Tienda",
        }
    )

    output_df.to_excel(output_file, index=False)
    logging.info("Proceso finalizado. Resultados guardados en: %s", output_file)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    process_products()
