# Changelog

## Sin publicar

### Auditoría de seguridad y privacidad (noviembre de 2026)

- **Dependencias**: `pypdf` 6.21.4 → 7.1.0 (correcciones de seguridad de 7.0.0
  y 7.0.1: límites de imagen, object streams, XFA, búferes de imagen).
  `PyMuPDF` 1.28.0 → 2.1 (MuPDF 1.28.6: CVE-2026-7233, desbordamiento de pila
  #5112, cuelgues de `get_pixmap`/`get_text` #5082 y #5125, y #5152:
  `apply_redactions()` dejaba texto mostrado con el operador `'`, regresión de
  1.28 que afectaba al expurgo nativo). `spacy` ≥ 3.8.18. Mínimos explícitos
  para transitivas con avisos recientes: `Werkzeug` ≥ 3.1.6, `Jinja2` ≥ 3.1.6,
  `lxml` ≥ 6.1.0. El código usa `import pymupdf` (el módulo `fitz` queda
  obsoleto en PyMuPDF 2.x).
- **Expurgo nativo — saneado completo**: además de metadatos, la copia derivada
  elimina anotaciones y comentarios, adjuntos e incrustados, índice/marcadores,
  JavaScript, enlaces, miniaturas y valores de formulario (`Document.scrub`).
  Antes una nota adhesiva o un adjunto con datos personales sobrevivían al
  expurgo. La capa OCR invisible se conserva.
- **Hallazgos sin proyectar**: si un hallazgo confirmado no tiene coordenadas en
  el PDF (palabra sin mapear, OCR deficiente) no puede tacharse. Antes ocurría
  en silencio; ahora la aplicación sobre el original y las descargas PDF avisan
  de los hallazgos no tachados o tachados solo en parte.
- **DOCX completo**: se analizan tablas, encabezados, pies, notas al pie y al
  final, comentarios y cuadros de texto; antes solo los párrafos del cuerpo.
  Se avisa si el documento tiene control de cambios, comentarios o imágenes.
- **ReDoS en el patrón de correo**: con cuantificadores sin límite, un texto
  tipo `a.a.a.…` tardaba horas (cuadrático). Ahora es lineal.
- **Solapes en O(log n)**: la comprobación de solapes entre hallazgos era
  cuadrática; un listado con decenas de miles de correos bloqueaba un hilo
  durante horas. Por encima de 20 000 hallazgos se pide dividir el documento.
- **Validación de hallazgos**: los endpoints de exportación y redacción
  rechazan con 400 estructuras mal formadas en lugar de fallar con 500.
- **Log de auditoría**: se escribía en la carpeta de instalación (a menudo
  sincronizada con la nube) porque se abría antes de fijar el workspace; ahora
  va a `<workspace>/logs`. El hash de los textos pasa a HMAC con clave local:
  el SHA-256 truncado de un DNI se invertía por fuerza bruta en segundos.
- **Logs sin contenido**: el registro DEBUG de palabras no mapeadas incluía el
  texto de la palabra; ahora solo su longitud.
- **Subidas huérfanas**: los TXT/DOCX/PDF temporales que sobrevivían a una
  caída del proceso se purgan al arrancar y cada 15 minutos.
- **Páginas gigantes**: la escala de render se reduce por página para no
  superar 20 Mpx (un PDF con páginas de 14 400 pt pedía ~2,5 GB por página).
- **OCR**: la imagen se cierra tras Tesseract; en Windows el fichero abierto
  impedía borrar la sesión.
- **Same-origin**: `Sec-Fetch-Site: same-site` ya no basta (otro puerto de
  localhost es same-site); se admite el origen `http://[::1]:puerto`.
- **Nombres no ASCII**: la extensión se toma del nombre original; `数据.pdf`
  se rechazaba porque `secure_filename` lo dejaba en `pdf`.
- **Riesgo orientativo**: con hallazgos pendientes de revisión el indicador
  marca ALTO; antes podía marcar BAJO con decenas de pendientes.
- **spaCy**: el modelo se carga una vez por proceso, no en cada análisis ni en
  cada consulta a `/api/status`.

- **Instalación verificada por hash**: los instaladores instalan desde
  `locks/*.lock` con `--require-hashes --only-binary=:all:` (versión exacta y
  SHA-256 de cada fichero, sin compilar paquetes fuente), incluidos pip y el
  modelo `es_core_news_md` 3.8.0, que pasa a fijarse por URL y hash en lugar
  de descargarse con `spacy download`. El contenido del modelo se contrasta en
  CI con los paquetes independientes de conda-forge y Anaconda (26 de 26
  ficheros idénticos). Nuevo workflow `dependencias-bloqueadas`: coherencia de
  los locks, instalación real en Windows/macOS/Linux con Python 3.11 y 3.13, y
  regeneración bajo demanda.
- **install.bat**: la pregunta de instalar spaCy no funcionaba (la respuesta
  se leía con expansión `%…%` dentro del bloque y siempre quedaba vacía); la
  ruta de logs indicada al salir era la anterior a #19.

### Anteriores

- **Privacidad — curso 2026 (#19)**: detección de DNI con guion o puntos, NIE
  con guiones, IBAN con espacios y fijos con espacios o guiones; los registros
  dejan de guardar el nombre original del fichero; el espacio de trabajo pasa a
  `%LOCALAPPDATA%\Velo`, `~/Library/Application Support/Velo` o
  `~/.local/state/velo`, fuera de la carpeta de la aplicación, y la purga de sesiones e informes se repite cada 15 minutos.
  `pypdf` 6.21.4.
- **Privacidad — nombre de fichero en formatos rechazados**: el aviso de formato
  no permitido registraba aún el nombre original; ahora solo la extensión.
- **Servidor**: si falta `waitress`, Velo se detiene con un mensaje en lugar de
  arrancar con el servidor de desarrollo de Flask. Para pruebas puede forzarse
  con `VELO_PERMITIR_SERVIDOR_FLASK=1`.
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
- **Licencia**: `LICENSE` contiene ahora el texto íntegro de la AGPL-3.0; antes
  solo tenía el aviso abreviado y un enlace, por lo que GitHub no la reconocía.
  El aviso de copyright pasa a los README.

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
