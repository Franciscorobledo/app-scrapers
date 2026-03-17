import re
from random import choice
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]

HEADERS_BASE = {
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
TIMEOUT = 20
PRICE_RE = re.compile(r"\$\s*[\d\.\,]+")
WORD_RE = re.compile(r"[a-z0-9áéíóúñ]+", re.IGNORECASE)


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _clean_price(text: str) -> str:
    m = PRICE_RE.search(text or "")
    return _clean_text(m.group(0)) if m else ""


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in WORD_RE.findall(text or "")}


def _similarity_score(query: str, candidate_name: str) -> int:
    query_tokens = _tokenize(query)
    name_tokens = _tokenize(candidate_name)
    if not query_tokens or not name_tokens:
        return 0

    intersection = query_tokens.intersection(name_tokens)
    score = len(intersection) * 10
    if candidate_name and query.lower() in candidate_name.lower():
        score += 5
    return score


def search_easy(query: str, limit: int = 12) -> dict | None:
    url = f"https://www.easy.cl/search/{quote_plus(query)}"
    headers = HEADERS_BASE.copy()
    headers["User-Agent"] = choice(USER_AGENTS)

    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    products = soup.select("a[href*='/p/']")
    seen = set()

    candidates: list[dict] = []
    for p in products:
        href = p.get("href")
        if not href:
            continue

        full_url = urljoin("https://www.easy.cl", href)
        if full_url in seen:
            continue
        seen.add(full_url)

        name = _clean_text(p.get_text(" ", strip=True))
        price = ""

        container = p
        for _ in range(6):
            if container is None:
                break
            txt = _clean_text(container.get_text(" ", strip=True))
            if "$" in txt:
                price = _clean_price(txt)
                if price:
                    break
            container = container.parent

        if not name:
            continue

        candidates.append(
            {
                "nombre": name,
                "precio": price,
                "url": full_url,
                "score": _similarity_score(query, name),
            }
        )

        if len(candidates) >= limit:
            break

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["score"])
    if best["score"] == 0:
        return candidates[0]  # fallback to first parsed product

    return {
        "nombre": best["nombre"],
        "precio": best["precio"],
        "url": best["url"],
    }
