# App Scrapers API (Flask)

API en Flask para scraping de productos en Chile, pensada para consumo desde n8n.

## Endpoints

- `GET /` → estado API + prueba rápida con `?producto=destornillador`
- `GET /buscar?producto=destornillador` → búsqueda rápida en tiendas
- `GET /health` → `{"status": "ok"}`
- `GET /test` → `{"message": "API funcionando correctamente"}`
- `POST /scrape` (multipart/form-data)
  - campo `file` con Excel y columnas `SKU` y `Nombre`
- `POST /scrape-json`
  - body:
    ```json
    {
      "productos": [
        {"sku": "ABC123", "nombre": "Taladro"}
      ]
    }
    ```

## Estructura

- `main.py` → Flask app + endpoints
- `scraper_sodimac.py` → scraping Sodimac
- `scraper_mercadolibre.py` → scraping Mercado Libre
- `scraper_easy.py` → scraping Easy

## Ejecutar local

```bash
pip install -r requirements.txt
python main.py
```

## Deploy en Render

La app usa:

- `host="0.0.0.0"`
- `port = int(os.environ.get("PORT", 5000))`

Comando recomendado de inicio:

```bash
python main.py
```


Prueba rápida en Render:

```
https://app-scraper-29uy.onrender.com/?producto=destornillador
```

