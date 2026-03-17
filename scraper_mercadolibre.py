import re
from urllib.parse import quote_plus

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
WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _normalize_token(token: str) -> str:
    token = token.lower().strip()
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokenize(text: str) -> set[str]:
    return {_normalize_token(t) for t in WORD_RE.findall(text or "")}


def _similarity_score(query: str, candidate_name: str) -> int:
    query_tokens = _tokenize(query)
    name_tokens = _tokenize(candidate_name)
    if not query_tokens or not name_tokens:
        return 0

    score = len(query_tokens.intersection(name_tokens)) * 10

    # Bonus por prefijo similar (destornillador ~ destornilladores)
    for q in query_tokens:
        for n in name_tokens:
            if q.startswith(n) or n.startswith(q):
                score += 2

    if query.lower() in (candidate_name or "").lower():
        score += 5
    return score


def _search_mercadolibre_api(query: str, limit: int = 12) -> dict | None:
    # API oficial de Mercado Libre para Chile (MLC)
    url = f"https://api.mercadolibre.com/sites/MLC/search?q={quote_plus(query)}&limit={limit}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    data = response.json()
    results = data.get("results") or []
    if not results:
        return None

    candidates: list[dict] = []
    for item in results:
        name = _clean_text(item.get("title", ""))
        if not name:
            continue

        price_value = item.get("price")
        if isinstance(price_value, (int, float)):
            price = f"${int(price_value):,}".replace(",", ".")
        else:
            price = ""

        permalink = _clean_text(item.get("permalink", ""))

        candidates.append(
            {
                "nombre": name,
                "precio": price,
                "url": permalink,
                "score": _similarity_score(query, name),
            }
        )

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["score"])
    if best["score"] == 0:
        best = candidates[0]

    return {
        "nombre": best["nombre"],
        "precio": best["precio"],
        "url": best["url"],
    }


def _search_mercadolibre_requests(query: str, limit: int = 12) -> dict | None:
    url = f"https://listado.mercadolibre.cl/{quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("li.ui-search-layout__item")
    if not items:
        return None

    candidates: list[dict] = []
    for item in items[:limit]:
        link = item.select_one("a.ui-search-item__group__element")
        if not link:
            continue

        title = item.select_one("h2.ui-search-item__title")
        name = _clean_text(title.get_text(" ") if title else "")
        if not name:
            continue

        fraction = item.select_one("span.andes-money-amount__fraction")
        cents = item.select_one("span.andes-money-amount__cents")

        price = ""
        if fraction:
            price = f"${_clean_text(fraction.get_text())}"
            if cents:
                price = f"{price},{_clean_text(cents.get_text())}"

        candidates.append(
            {
                "nombre": name,
                "precio": price,
                "url": link.get("href", ""),
                "score": _similarity_score(query, name),
            }
        )

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["score"])
    if best["score"] == 0:
        best = candidates[0]

    return {
        "nombre": best["nombre"],
        "precio": best["precio"],
        "url": best["url"],
    }


def _search_mercadolibre_playwright(query: str) -> dict | None:
    """Prepared fallback for dynamic pages if needed in the future.

    This keeps architecture ready without forcing playwright dependency.
    """
    return None


def search_mercadolibre(query: str) -> dict | None:
    # 1) API oficial (más estable). 2) HTML scraping. 3) fallback preparado.
    try:
        api_result = _search_mercadolibre_api(query)
        if api_result:
            return api_result
    except Exception as exc:
        print(f"[Mercado Libre] API falló ({exc}), probando scraping HTML")

    try:
        return _search_mercadolibre_requests(query)
    except Exception as exc:
        print(f"[Mercado Libre] requests falló ({exc}), intentando fallback preparado")
        return _search_mercadolibre_playwright(query)
