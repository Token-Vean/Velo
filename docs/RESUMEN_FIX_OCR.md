# Velo — Fix OCR Text Extraction (v0.3.1)

## Problema reportado

Un usuario reporta que un PDF con capa OCR correcta produce texto con muchos errores al ser procesado por Velo.

## Causa raíz

### Problema 1: `reader.py` usa PyPDF2 (baja calidad con OCR)

El flujo en `app.py` (línea 152) se bifurca:

- **Con fitz+Pillow instalados** → ruta visual (`visual.py`, PyMuPDF) — buena calidad
- **Sin ellos** → fallback (`reader.py`, PyPDF2) — calidad muy pobre

`PyPDF2.PdfReader.extract_text()` es conocido por producir texto defectuoso con PDFs que tienen capa OCR: caracteres perdidos, palabras fusionadas, codificaciones rotas, reordenación errónea de glifos.

Como `requirements-visual.txt` es **opcional**, cualquier usuario que instale solo las dependencias base está en la ruta de baja calidad.

### Problema 2: `visual.py` no detecta capas OCR carácter-por-carácter

Ciertos motores OCR (ABBYY, Tesseract antiguo, herramientas propietarias) escriben la capa de texto **un carácter por posición**. `page.get_text("words")` de PyMuPDF devuelve cada carácter como una "palabra" independiente. La reconstrucción con `_page_text_and_map()` los une con espacios, produciendo texto tipo:

```
E s t e   e s   u n   t e x t o   d e   e j e m p l o
```

## Cambios aplicados

### `reader.py`

- **Motor primario**: ahora usa `fitz.open()` + `page.get_text("text")` de PyMuPDF, que preserva el flujo natural del texto incluyendo saltos de línea y espaciado originales.
- **Fallback**: PyPDF2 solo se activa si PyMuPDF no está instalado, con un warning en log indicando la calidad limitada.
- **`supported_extensions()`**: informa al usuario qué motor PDF está activo y su nivel de calidad.
- Se añade logging con `velo.reader`.

### `visual.py`

- **`_is_char_level_ocr()`**: heurística que detecta capas de texto carácter-por-carácter (>40% de tokens son de un solo carácter).
- **`_merge_char_level_words()`**: fusiona caracteres consecutivos de la misma línea cuando la distancia horizontal entre ellos es menor que el 40% de la altura media del carácter. Un hueco mayor se interpreta como espacio entre palabras. Los bboxes se expanden para cubrir la palabra completa.
- Se integra automáticamente al final de `_words_from_text_layer()`.

## Cómo aplicar

### Opción A: patch

```bash
cd /ruta/a/Velo
patch -p0 < velo_ocr_fix.patch
```

### Opción B: reemplazo directo

Copiar los dos ficheros de `velo_engine/` al repositorio, reemplazando los existentes.

## Entrada para CHANGELOG.md

```markdown
## 0.3.1

- **Extracción PDF mejorada**: el motor primario de lectura de PDF es ahora PyMuPDF (`page.get_text("text")`), que produce texto de alta calidad incluso con capas OCR. PyPDF2 queda como fallback de último recurso.
- **Corrección de OCR carácter-por-carácter**: nueva heurística en el módulo visual que detecta capas de texto escritas carácter a carácter y fusiona los fragmentos en palabras reales basándose en la proximidad horizontal.
- Logging mejorado en el módulo lector con indicación del motor PDF utilizado.
```

## Tests recomendados

1. **PDF con OCR bueno** (Tesseract reciente, ABBYY): verificar que el texto se extrae correctamente en ambas rutas (visual y no visual).
2. **PDF con OCR carácter-por-carácter**: verificar que la heurística de fusión reconstruye las palabras correctamente y que los bboxes de las redacciones siguen cubriendo las zonas correctas.
3. **PDF sin capa de texto**: verificar que el mensaje de error sigue siendo correcto.
4. **Instalación solo con requirements.txt** (sin visual): verificar que ahora falla gracefully indicando que instale PyMuPDF.
