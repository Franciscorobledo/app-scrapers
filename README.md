# App Scrapers

Script de scraping para comparar productos en tiendas chilenas (Sodimac, Mercado Libre y Easy) usando un Excel de entrada.

## Requisitos

```bash
pip install -r requirements.txt
```

## Uso

1. Crear un archivo `productos.xlsx` con columnas:
   - `SKU`
   - `Nombre`
2. Ejecutar:

```bash
python app.py
```

3. El script generará `resultados.xlsx` con columnas:
   - SKU original
   - Nombre original
   - Nombre encontrado
   - Precio
   - URL
   - Tienda

## Nota de despliegue en Render

Si Render intenta correr `python app.py`, este repositorio ahora incluye ese archivo en la raíz.
