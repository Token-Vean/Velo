# Changelog

## Sin publicar

- **Seguridad — actualización de dependencias**: `Pillow` 12.3.0 → 13.0.0
  (4 avisos críticos y 23 altos: desbordamientos de heap en los decodificadores
  TIFF y JPEG y en FreeType, inyección de argumentos en la llamada a
  Ghostscript, lecturas fuera de límites). `pypdf` 6.14.2 → 6.21.2 (8 avisos
  altos y 13 moderados de consumo de memoria o CPU con PDF malformados; afectan
  al motor fallback de Velo).
- **Seguridad — CSP sin scripts inline**: el JavaScript de la interfaz pasa de
  un bloque `<script>` en `index.html` a `velo_engine/static/app.js`, y los 27
  manejadores `onclick`/`onchange`/`onerror` se sustituyen por atributos
  `data-action` / `data-change` resueltos con una lista blanca. La CSP queda en
  `script-src 'self'`: un fallo de escapado futuro ya no permitiría ejecutar
  código. Se añade `escapeAttr` para valores en atributos (`escapeHtml` no
  escapa comillas).
- **Seguridad — validación de la cabecera Host**: las peticiones cuyo `Host` no
  sea `127.0.0.1`, `localhost` o `::1` reciben 421, lo que bloquea el DNS
  rebinding. Se pueden añadir nombres con `app.config["ALLOWED_HOSTS"]`.
- **Python 3.11 o superior**: Pillow 13 ya no admite Python 3.10, que llegó a
  fin de soporte en octubre de 2026. Los instaladores (`install.sh`,
  `install.bat`), `MIN_PYTHON` y los README pasan a exigir 3.11. Quien tenga
  3.10 debe actualizar Python antes de reinstalar.

## 0.5.0

- **Seguridad — actualización de dependencias**: `pypdf` 6.12.0 → 6.14.2 (corrige
  CVE-2026-48735, CVE-2026-49460, CVE-2026-49461, CVE-2026-54530, CVE-2026-54531 y
  CVE-2026-54651, todas de denegación de servicio con PDF manipulados; las de
  extracción de texto afectaban al motor fallback de Velo). `Pillow` 12.2.0 → 12.3.0
  (bypass de la protección anti-bomba de descompresión: CVE-2026-54060,
  CVE-2026-55379, CVE-2026-55380). `PyMuPDF` 1.27.2 → 1.28.0 (MuPDF 1.28 con
  correcciones de endurecimiento de seguridad).
- **Expurgo nativo de PDF (nuevo)**: nuevo modo `redaction_mode: "native"` en
  `/api/export/redacted-pdf`, basado en `add_redact_annot` + `apply_redactions`
  de PyMuPDF. A diferencia del modo imagen, el texto subyacente se **elimina**
  del fichero (no solo se tapa), el PDF conserva su capa de texto y naturaleza
  vectorial, y se purgan los metadatos del documento (autor, software, XMP) en
  la copia derivada. El modo imagen sigue siendo el predeterminado. Los modos
  disponibles se anuncian en `/api/status` → `visual_redaction.modes`.
- **OCR con timeout efectivo**: la constante `OCR_TIMEOUT_SECONDS` (25 s) ahora
  se aplica realmente a la llamada a Tesseract. Antes una página escaneada
  hostil o degenerada podía bloquear un hilo del servidor indefinidamente; ahora
  la página se trata como sin texto y se registra el aborto.
- **Rate limiting corregido**: los GET de assets de sesión (una imagen por
  página) quedan exentos del limitador; un PDF legítimo de más de ~30 páginas
  disparaba un 429 al cargar la revisión visual.
- **Comprobaciones de ruta robustas**: las validaciones de contención de rutas
  (`_session_dir`, limpieza de sesiones, exportación) usan `os.path.commonpath`
  en lugar de `startswith`, eliminando el problema clásico de prefijo.
- **Purga de informes exportados**: los `*_pii_report.json` del workspace se
  purgan con el mismo TTL que las sesiones (`EXPORT_REPORT_TTL_HOURS`); hasta
  ahora se acumulaban indefinidamente.
- **Detector — validación NSS**: los números de la Seguridad Social con formato
  canónico de 12 dígitos se validan por dígitos de control (módulo 97),
  reduciendo falsos positivos con numeraciones de expediente.
- **Corrección**: en la ruta de error "PDF sin texto extraíble" se accedía a
  `document.page_count` después de `document.close()`, lo que provocaba una
  excepción secundaria en PyMuPDF.
- **CI endurecida**: `actions/checkout` v5 → v7 y nuevo paso `pip-audit` sobre
  el entorno resuelto para auditar también dependencias transitivas.
- **Corrección CI**: se actualiza `setuptools` a la rama corregida 83.x antes de
  auditar el entorno resuelto, evitando la exposición PYSEC-2026-3447.
- **Interfaz de expurgo nativo**: la exportación nativa deja de estar limitada a
  la API y se ofrece como descarga directa para los PDF revisados.
- **Corrección de límite de páginas**: los PDF que superan el máximo configurado
  devuelven un error controlado sin consultar el documento después de cerrarlo.
- **Pruebas de regresión**: se verifican el límite de páginas y la eliminación
  efectiva de texto y metadatos en el expurgo nativo.
- **Deuda conocida (documentada, no resuelta)**: la CSP mantiene
  `script-src 'unsafe-inline'` porque la interfaz usa 26 manejadores de eventos
  inline, varios generados dinámicamente. La migración a delegación de eventos
  + nonce queda planificada para 0.5.x.

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
