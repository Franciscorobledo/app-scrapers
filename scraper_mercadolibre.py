import json
import re

from playwright.sync_api import sync_playwright


BASE_URL = "https://listado.mercadolibre.cl"
try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

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


def _slugify_query(query: str) -> str:
    words = WORD_RE.findall(_normalize(query))
    return "-".join(words)


def _build_search_url(query: str) -> str:
    slug = _slugify_query(query)
    return f"{BASE_URL}/{quote(slug, safe='-')}"


def _normalize_price(price: str) -> str:
    cleaned = _clean_text(price)
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("$") else f"${cleaned}"


def _extract_sku_from_url(url: str) -> str:
    sku_match = re.search(r"MLC-?(\d+)", url or "", re.IGNORECASE)
    return f"MLC{sku_match.group(1)}" if sku_match else ""


def scrape_mercadolibre(producto: str) -> dict:
    """Scraper Playwright de Mercado Libre.

    Retorna estructura completa con todos los resultados detectados.
    """
    producto = _clean_text(producto)
    query = producto.replace(" ", "-")
    url = f"{BASE_URL}/{query}"
    resultados: list[dict] = []

    if sync_playwright is None:
        print("[Mercado Libre] Playwright no está disponible")
        return {"nombre_original": producto, "total": 0, "resultados": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
        )
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

        print(f"[Mercado Libre] Abriendo: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("li.ui-search-layout__item", timeout=15000)
        except Exception:
            print("[Mercado Libre] Timeout esperando resultados")
            browser.close()
            return {"nombre_original": producto, "total": 0, "resultados": []}

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        items = page.query_selector_all("li.ui-search-layout__item")
        print(f"[Mercado Libre] Items encontrados: {len(items)}")

        for item in items:
            if len(resultados) >= MAX_RESULTS:
                break
            try:
                nombre = ""
                for selector in [
                    "h2.ui-search-item__title",
                    "h2",
                    "a.ui-search-link__title-card",
                    "[class*='title']",
                    "a[class*='link']",
                ]:
                    el = item.query_selector(selector)
                    if el:
                        texto = _clean_text(el.inner_text())
                        if len(texto) > 3:
                            nombre = texto
                            break

                url_producto = ""
                for sel_link in ["a.ui-search-link", "a[href*='mercadolibre']", "a"]:
                    link_el = item.query_selector(sel_link)
                    if link_el:
                        href = _clean_text(link_el.get_attribute("href") or "")
                        if href.startswith("http"):
                            url_producto = href.split("#")[0]
                            break

                precio = ""
                for sel_precio in [
                    "span.andes-money-amount__fraction",
                    "[class*='price'] [class*='fraction']",
                    "[class*='amount__fraction']",
                    "[class*='price']",
                ]:
                    fraccion_el = item.query_selector(sel_precio)
                    if fraccion_el:
                        monto = _clean_text(fraccion_el.inner_text())
                        if monto:
                            precio = f"$ {monto}"
                            centavos_el = item.query_selector(
                                "span.andes-money-amount__cents, [class*='amount__cents']"
                            )
                            if centavos_el:
                                precio += f",{_clean_text(centavos_el.inner_text())}"
                            break

                tienda = "MercadoLibre"
                for sel_tienda in [
                    "p.ui-search-official-store-label",
                    "[class*='official-store']",
                    "[class*='store-label']",
                ]:
                    tienda_el = item.query_selector(sel_tienda)
                    if tienda_el:
                        texto_tienda = _clean_text(tienda_el.inner_text())
                        tienda = re.sub(r"^(por|by)\s+", "", texto_tienda, flags=re.IGNORECASE).strip()
                        break

                sku = _extract_sku_from_url(url_producto)

                if not nombre and url_producto:
                    full_text = _clean_text(item.inner_text())
                    for linea in full_text.splitlines():
                        linea = _clean_text(linea)
                        if len(linea) > 5:
                            nombre = linea
                            break

                if nombre or url_producto:
                    resultados.append(
                        {
                            "nombre": nombre,
                            "precio": precio,
                            "tienda": tienda,
                            "url": url_producto,
                            "sku": sku,
                        }
                    )
            except Exception as exc:
                print(f"[Mercado Libre] Error parseando item: {exc}")

        browser.close()

    output = {
        "nombre_original": producto,
        "total": len(resultados),
        "resultados": resultados,
    }
    return output


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


def scrape_mercadolibre(producto: str) -> dict:
    query = producto.replace(" ", "-")
    url = f"{BASE_URL}/{query}"
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
        )
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

        print(f"Abriendo: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("li.ui-search-layout__item", timeout=15000)
        except Exception:
            print("Timeout esperando resultados.")
            browser.close()
            return {"nombre_original": producto, "resultados": [], "sku": ""}

        # Scroll completo para cargar todos los items
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        items = page.query_selector_all("li.ui-search-layout__item")
        print(f"Items encontrados: {len(items)}")

        for i, item in enumerate(items):
            try:
                # Intentar múltiples selectores posibles para el nombre
                nombre = ""
                for selector in [
                    "h2.ui-search-item__title",
                    "h2",
                    "a.ui-search-link__title-card",
                    "[class*='title']",
                    "a[class*='link']",
                ]:
                    el = item.query_selector(selector)
                    if el:
                        texto = el.inner_text().strip()
                        if texto and len(texto) > 3:
                            nombre = texto
                            break

                # URL
                url_producto = ""
                for sel_link in ["a.ui-search-link", "a[href*='mercadolibre']", "a"]:
                    link_el = item.query_selector(sel_link)
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                        if href.startswith("http"):
                            url_producto = href.split("#")[0]
                            break

                # Precio
                precio = ""
                for sel_precio in [
                    "span.andes-money-amount__fraction",
                    "[class*='price'] [class*='fraction']",
                    "[class*='amount__fraction']",
                    "[class*='price']",
                ]:
                    fraccion_el = item.query_selector(sel_precio)
                    if fraccion_el:
                        monto = fraccion_el.inner_text().strip()
                        if monto:
                            precio = f"$ {monto}"
                            # Intentar centavos
                            centavos_el = item.query_selector(
                                "span.andes-money-amount__cents, [class*='amount__cents']"
                            )
                            if centavos_el:
                                precio += f",{centavos_el.inner_text().strip()}"
                            break

                # Tienda
                tienda = "Mercado Libre"
                for sel_tienda in [
                    "p.ui-search-official-store-label",
                    "[class*='official-store']",
                    "[class*='store-label']",
                ]:
                    tienda_el = item.query_selector(sel_tienda)
                    if tienda_el:
                        texto = tienda_el.inner_text().strip()
                        tienda = re.sub(r"^(por|by)\s+", "", texto, flags=re.IGNORECASE).strip()
                        break

                # SKU desde URL (MLC-XXXXXXX)
                sku = ""
                if url_producto:
                    sku_match = re.search(r"MLC-?(\d+)", url_producto, re.IGNORECASE)
                    if sku_match:
                        sku = f"MLC{sku_match.group(1)}"

                # Si aún no hay nombre, usar inner_text del item completo
                if not nombre and url_producto:
                    full_text = item.inner_text().strip()
                    for linea in full_text.splitlines():
                        linea = linea.strip()
                        if len(linea) > 5:
                            nombre = linea
                            break

                if nombre or url_producto:
                    resultados.append(
                        {
                            "nombre": nombre,
                            "precio": precio,
                            "tienda": tienda,
                            "url": url_producto,
                            "sku": sku,
                        }
                    )

            except Exception as e:
                print(f"Error en item {i}: {e}")
                continue

        browser.close()

    output = {
        "nombre_original": producto,
        "total": len(resultados),
        "resultados": resultados,
    }

    return output


def buscar_mercadolibre(query: str) -> list[dict]:
    data = scrape_mercadolibre(query)
    return data.get("resultados", [])

    # Estrategia principal: Playwright para capturar contenido dinámico.
    scraped = scrape_mercadolibre(query)
    results = scraped.get("resultados", []) if isinstance(scraped, dict) else []

    # Fallback: API pública (rápida) si Playwright no entrega resultados.
    if not results:
        results = _search_api(query)

def search_mercadolibre(query: str) -> dict | None:
    resultados = buscar_mercadolibre(query)
    return resultados[0] if resultados else None


if __name__ == "__main__":
    data = scrape_mercadolibre("destornillador")
    print(json.dumps(data, ensure_ascii=False, indent=2))
