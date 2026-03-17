import re
from urllib.parse import quote_plus, urljoin

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


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in WORD_RE.findall(text or "")}


def _similarity_score(query: str, candidate_name: str) -> int:
    query_tokens = _tokenize(query)
    name_tokens = _tokenize(candidate_name)
    if not query_tokens or not name_tokens:
        return 0

    score = len(query_tokens.intersection(name_tokens)) * 10
    if query.lower() in (candidate_name or "").lower():
        score += 5
    return score


def search_sodimac(query: str, limit: int = 12) -> dict | None:
    url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select("a.pod-link") or soup.select("a[href*='/product/']")
    if not cards:
        return None

    candidates: list[dict] = []
    seen = set()

    for card in cards:
        href = card.get("href", "")
        full_url = urljoin("https://www.sodimac.cl", href)
        if not href or full_url in seen:
            continue
        seen.add(full_url)

        name_node = card.select_one("b.pod-subTitle") or card.select_one("span.pod-title")
        price_node = card.select_one("span.prices-main-price") or card.select_one("span.pod-prices")

        name = _clean_text(name_node.get_text(" ") if name_node else card.get_text(" "))
        price = _clean_text(price_node.get_text(" ") if price_node else "")
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
        return {
            "nombre": candidates[0]["nombre"],
            "precio": candidates[0]["precio"],
            "url": candidates[0]["url"],
        }

    return {
        "nombre": best["nombre"],
        "precio": best["precio"],
        "url": best["url"],
    }
