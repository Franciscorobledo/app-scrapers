import os
from typing import Any

import pandas as pd
from flask import Flask, jsonify, request

from scraper_easy import search_easy
from scraper_mercadolibre import search_mercadolibre
from scraper_sodimac import search_sodimac

app = Flask(__name__)


STORE_SEARCHERS = [
    ("Sodimac", search_sodimac),
    ("Mercado Libre", search_mercadolibre),
    ("Easy", search_easy),
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def run_store_search(search_fn, sku: str, nombre: str, tienda: str) -> dict[str, str]:
    """Try SKU first, fallback to product name. Return a normalized result."""
    queries = [sku, nombre]
    last_error = None

    for query in queries:
        query = clean_text(query)
        if not query:
            continue
        try:
            print(f"[{tienda}] buscando con query: {query}")
            found = search_fn(query)
            if found:
                return {
                    "tienda": tienda,
                    "nombre": clean_text(found.get("nombre", "")),
                    "precio": clean_text(found.get("precio", "")),
                    "url": clean_text(found.get("url", "")),
                }
        except Exception as exc:  # Keep process alive per store
            last_error = str(exc)
            print(f"[{tienda}] error buscando '{query}': {exc}")

    if last_error:
        return {
            "tienda": tienda,
            "nombre": "",
            "precio": "",
            "url": "",
            "error": f"No se pudo completar la búsqueda: {last_error}",
        }

    return {
        "tienda": tienda,
        "nombre": "",
        "precio": "",
        "url": "",
    }


def process_product_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        sku = clean_text(row.get("SKU") or row.get("sku"))
        nombre = clean_text(row.get("Nombre") or row.get("nombre"))

        print(f"Procesando producto {idx}/{total} | SKU: {sku}")

        resultados = []
        for tienda, search_fn in STORE_SEARCHERS:
            result = run_store_search(search_fn, sku, nombre, tienda)
            resultados.append(result)

        output.append(
            {
                "sku": sku,
                "nombre_original": nombre,
                "resultados": resultados,
            }
        )

    return output




@app.get("/")
def root():
    producto = clean_text(request.args.get("producto"))

    if not producto:
        return (
            jsonify(
                {
                    "message": "API de scraping activa",
                    "como_probar": {
                        "ejemplo": "/?producto=destornillador",
                        "alternativa": "/buscar?producto=destornillador",
                    },
                }
            ),
            200,
        )

    result = process_product_rows([{"sku": "", "nombre": producto}])
    return jsonify(result[0]), 200


@app.get("/buscar")
def buscar_producto():
    producto = clean_text(request.args.get("producto"))
    if not producto:
        return jsonify({"error": "Debes enviar el parámetro 'producto'"}), 400

    result = process_product_rows([{"sku": "", "nombre": producto}])
    return jsonify(result[0]), 200

@app.get("/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


@app.get("/test")
def test() -> tuple[dict[str, str], int]:
    return {"message": "API funcionando correctamente"}, 200


@app.post("/scrape")
def scrape_excel():
    if "file" not in request.files:
        return jsonify({"error": "Debes enviar un archivo en el campo 'file'"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "Archivo inválido"}), 400

    try:
        df = pd.read_excel(file)
    except Exception as exc:
        return jsonify({"error": f"No se pudo leer el Excel: {exc}"}), 400

    required_columns = {"SKU", "Nombre"}
    if not required_columns.issubset(df.columns):
        return (
            jsonify({"error": "El Excel debe contener columnas 'SKU' y 'Nombre'"}),
            400,
        )

    rows = df[["SKU", "Nombre"]].to_dict(orient="records")
    result = process_product_rows(rows)
    return jsonify(result), 200


@app.post("/scrape-json")
def scrape_json():
    payload = request.get_json(silent=True) or {}
    productos = payload.get("productos")

    if not isinstance(productos, list):
        return jsonify({"error": "El JSON debe contener una lista en 'productos'"}), 400

    result = process_product_rows(productos)
    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
