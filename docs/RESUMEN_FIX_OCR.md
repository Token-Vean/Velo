# Velo — Fix OCR + Doble Extracción (v0.3.1)

## Problema reportado

Un usuario reporta que un PDF con capa OCR correcta produce texto con muchos errores al ser procesado por Velo.

## Cambios aplicados

### 1. `reader.py` — PyMuPDF como motor primario

**Antes**: usaba `PyPDF2.PdfReader.extract_text()`, que con PDFs OCR produce texto defectuoso.

**Ahora**: usa `fitz.open()` + `page.get_text("text")` de PyMuPDF, que preserva el flujo natural del texto. PyPDF2 solo se activa como fallback si PyMuPDF no está instalado.

### 2. `visual.py` — Doble extracción (cambio principal)

**Antes**: una sola fuente — `page.get_text("words")` devolvía palabras individuales con bboxes, y el texto se reconstruía uniéndolas con espacios. Esa reconstrucción perdía formato, partía palabras por guiones, fusionaba tokens, etc.

**Ahora**: dos fuentes independientes para páginas con capa de texto:

- `page.get_text("text")` → **texto canónico** de alta fidelidad que va al detector
- `page.get_text("words")` → **bboxes** para la redacción visual

La función `_map_words_to_canonical()` alinea los bboxes contra el texto canónico mediante búsqueda secuencial: recorre las palabras en orden y localiza cada una en el texto canónico avanzando un cursor. Si una palabra no se encuentra exactamente, intenta búsqueda case-insensitive. Si sigue sin encontrarla, la descarta del mapa (sin cobertura de redacción, pero es más seguro que un mapeo erróneo).

Para páginas procesadas con OCR propio (sin capa de texto nativa), se mantiene la reconstrucción palabra-por-palabra porque las palabras OCR son la única fuente.

### 3. `visual.py` — Corrección de capas OCR carácter-por-carácter

`_is_char_level_ocr()` detecta si >40% de los tokens son de un solo carácter. `_merge_char_level_words()` fusiona caracteres consecutivos de la misma línea cuando la distancia horizontal es menor que el 40% de la altura media.

### 4. `visual.py` — Normalización Unicode

`_clean_extracted_text()` aplica NFC, reemplaza espacios Unicode exóticos y elimina caracteres de control.

## Ficheros a copiar

| Fichero | Destino en el repo |
|---|---|
| `reader.py` | `Velo/velo_engine/reader.py` |
| `visual.py` | `Velo/velo_engine/visual.py` |
| `CHANGELOG.md` | `Velo/CHANGELOG.md` |
| `RESUMEN_FIX_OCR.md` | `Velo/docs/RESUMEN_FIX_OCR.md` |
| `velo_v031_full.patch` | `Velo/velo_v031_full.patch` |

## Tests recomendados

1. **PDF con capa OCR buena** (Tesseract reciente, ABBYY): verificar que el texto extraído es fiel al original.
2. **PDF con OCR carácter-por-carácter**: verificar que la heurística de fusión reconstruye las palabras.
3. **Redacción visual**: confirmar que los rectángulos negros cubren las zonas correctas tras el cambio de alineación.
4. **PDF sin capa de texto + Tesseract**: verificar que la ruta OCR sigue funcionando (usa `_page_text_and_map`, no la nueva función).
5. **Instalación solo con `requirements.txt`**: verificar que el fallback PyPDF2 funciona y muestra warning.
