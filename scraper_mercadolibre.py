import json
import re

from playwright.sync_api import sync_playwright


BASE_URL = "https://listado.mercadolibre.cl"


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


def search_mercadolibre(query: str) -> dict | None:
    resultados = buscar_mercadolibre(query)
    return resultados[0] if resultados else None


if __name__ == "__main__":
    data = scrape_mercadolibre("destornillador")
    print(json.dumps(data, ensure_ascii=False, indent=2))
