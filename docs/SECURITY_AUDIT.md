# Auditoría de seguridad — Velo v0.2.5

**Fecha:** 13 de abril de 2026  
**Alcance:** Revisión completa del código fuente, endpoints, gestión de sesiones y procesamiento de archivos.

---

## Resumen

Velo tiene una base de seguridad razonable: `secure_filename`, sanitización de session_id con path traversal checks, `MAX_CONTENT_LENGTH`, y binding a 127.0.0.1. Se identificaron 13 vulnerabilidades (2 críticas, 4 altas, 5 medias, 2 bajas). Todas corregidas.

---

## Hallazgos y correcciones

### CRÍTICAS

**C1. Sin protección CSRF**  
Cualquier web que visite el usuario puede ejecutar POST a localhost:7780, disparando análisis, exportaciones o apagando el servidor.  
*Corrección:* Verificación de cabecera `Origin`/`Referer` en todos los POST. Solo se aceptan peticiones del propio Velo.

**C2. ReDoS en regex de tarjeta de crédito**  
El patrón `(?:\d[ -]?){13,19}` causa backtracking catastrófico con entradas largas de dígitos y espacios.  
*Corrección:* Patrón reescrito como `\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}` (estructura fija, sin repetición ambigua).

### ALTAS

**A1. Sin rate limiting**  
Endpoints invocables sin límite.  
*Corrección:* Rate limiter en memoria: 30 peticiones/minuto por IP.

**A2. Mensajes de error exponen excepciones internas**  
Tres endpoints devolvían `f"Error: {exc}"`, filtrando rutas, tipos de excepción y detalles internos.  
*Corrección:* Mensajes genéricos sin detalle de excepción.

**A3. Sin cabeceras de seguridad HTTP**  
No se enviaban X-Frame-Options, CSP, X-Content-Type-Options, etc.  
*Corrección:* `after_request` hook añade todas las cabeceras de seguridad estándar.

**A4. Export filtra ruta de workspace**  
`/api/export` devolvía `"saved_as": filename` que revela la estructura de archivos.  
*Corrección:* Campo eliminado de la respuesta.

### MEDIAS

**M1. Sin límite de páginas en PDF visual**  
Un PDF de cientos de páginas generaría cientos de PNGs de alta resolución, agotando disco y memoria.  
*Corrección:* Límite de 100 páginas. PDFs mayores se rechazan con error.

**M2. Bomba de descompresión en imágenes**  
`PIL.Image.open()` sin límite de píxeles.  
*Corrección:* `Image.MAX_IMAGE_PIXELS = 25_000_000`.

**M3. Sesiones no se limpian al apagar**  
Las sesiones en `workspace/sessions/` con PDFs originales y páginas renderizadas persistían tras cerrar Velo.  
*Corrección:* `/api/shutdown` limpia todas las sesiones antes de cerrar.

**M4. Assets servidos sin validación de tipo**  
`/api/session/{id}/asset/{filename}` servía cualquier archivo del directorio de assets.  
*Corrección:* Solo se permiten archivos `.png`.

**M5. Sin log de auditoría**  
No había registro de qué documentos se procesaban ni qué se exportaba.  
*Corrección:* Log de auditoría en `workspace/velo_audit.log` con rotación (3x5MB). Registra: análisis de texto, análisis de archivo, exportaciones, apagado.

### BAJAS

**B1. Versión inconsistente**  
`__init__.py` decía 0.1.0, `app.py` decía 0.2.5, `build_envelope` decía 0.1.1.  
*Corrección:* Unificada a 0.2.5 en todos los ficheros.

**B2. Dependencias con rangos amplios**  
`flask>=3.0,<4.0` podía instalar versiones vulnerables.  
*Corrección:* Versiones pinadas a releases específicos verificados.

---

## Archivos modificados

| Archivo | Cambios |
|---|---|
| `velo_engine/security.py` | **NUEVO.** Middleware CSRF, rate limiting, cabeceras, auth, auditoría. |
| `velo_engine/app.py` | Integración de seguridad, errores sanitizados, audit logging, limpieza de sesiones, validación de assets. |
| `velo_engine/detector.py` | Fix ReDoS en credit_card, versión unificada. |
| `velo_engine/visual.py` | Límite de páginas PDF, protección Pillow. |
| `velo_engine/__init__.py` | Versión corregida a 0.2.5. |
| `requirements.txt` | Versiones pinadas. |
| `requirements-visual.txt` | Versiones pinadas. |

---

## Recomendaciones futuras

1. **Firma digital SHA-256** de informes exportados para verificar integridad.
2. **Cifrado del workspace** para proteger documentos sensibles en reposo.
3. **Auditoría de dependencias** periódica con `pip-audit`.
4. **Tesseract sandboxing** si se usa OCR en entornos con documentos no confiables.
