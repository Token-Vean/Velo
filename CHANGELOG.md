# Changelog

## 0.4.0

- **Seguridad — actualización de pypdf**: se eleva `pypdf` de 6.10.0 a 6.10.1 para corregir la exposición a GHSA-JJ6C-8H6C-HPPX (uncontrolled resource consumption en streams xref/object mal formados). Afectaba al flujo base de lectura de PDF.
- **Refactor del módulo visual**: simplificación de `velo_engine/visual.py` (reducción de ~50 líneas, sin cambios de comportamiento observable).
- **CI endurecida**: los pasos `Pip audit (visual)` y `Pip audit (nlp)` del workflow `security-checks` ahora toleran la ausencia de su fichero de requirements, evitando falsos fallos rojos en perfiles parciales.
- **Alineación de versiones**: unificadas a 0.4.0 las referencias en `README.md`, `README.en.md`, `velo_engine/__init__.py`, `velo_engine/constants.py` e instaladores.

## 0.3.1

- **Extracción PDF mejorada**: el motor primario de lectura de PDF es ahora PyMuPDF (`page.get_text("text")`), que produce texto de alta calidad incluso con capas OCR. PyPDF2 queda como fallback de último recurso.
- **Doble extracción visual**: el módulo visual ahora usa `get_text("text")` como texto canónico para el detector (alta fidelidad), y `get_text("words")` exclusivamente para los bboxes de redacción. La alineación se realiza por búsqueda secuencial de cada palabra en el texto canónico, eliminando los errores de la reconstrucción palabra-por-palabra.
- **Corrección de OCR carácter-por-carácter**: nueva heurística que detecta capas de texto escritas carácter a carácter y fusiona los fragmentos en palabras reales basándose en la proximidad horizontal.
- **Normalización Unicode**: limpieza automática de caracteres Unicode exóticos (NFC, espacios no estándar, caracteres de control) en el texto extraído.
- Logging mejorado en el módulo lector con indicación del motor PDF utilizado.

## 0.3.0

- **Detección de nombres**: los instaladores preguntan si se desea instalar spaCy + modelo español para detectar nombres de personas, organizaciones y lugares. Si ya estaba instalado, se reutiliza.
- **Límites ampliados**: tamaño máximo de fichero subido a 100 MB (antes 16 MB), límite de texto extraído a 2.000.000 caracteres (antes 500.000), límite de páginas PDF a 500 (antes 100).
- **Logging centralizado**: nuevo sistema de logs rotativos en `workspace/logs/velo.log` con registros detallados de cada fichero procesado, errores de extracción, límites alcanzados y estado de las capas de detección.
- **Mejor gestión de errores**: manejador HTTP 413 con mensaje informativo cuando un fichero excede el tamaño máximo; los mensajes de error al usuario incluyen el tipo de excepción para facilitar diagnóstico.
- Nuevo fichero `requirements-nlp.txt` para dependencias de detección NER.

## 0.2.5

- Corrección del desfase de offsets en la alineación visual entre texto reconstruido y cajas proyectadas.
- Mantenimiento del flujo de cinco pasos para PDF: revisión textual, vista original, aplicación sobre el original y exportación.
- Separación entre dependencias base y dependencias visuales opcionales.
- Interfaz en modo claro y sin fuentes remotas.

## 0.2.4

- Arranque robusto aunque no esté disponible `waitress`.
- Instaladores preparados para degradación elegante cuando fallan dependencias visuales.

## 0.2.3

- Activación por defecto del flujo visual PDF cuando las dependencias están disponibles.

## 0.2.2

- Paso explícito de “Aplicación sobre el original” en la interfaz.

## 0.2.1

- Primera integración del flujo visual para PDF y exportación de copia derivada redactada.
