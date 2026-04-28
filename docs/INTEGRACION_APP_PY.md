# Integración de `file_guard.py` en `velo_engine/app.py`

No he podido escribir directamente en el repositorio desde el conector actual porque GitHub ha devuelto `Resource not accessible by integration` para operaciones de escritura. Por eso este kit incluye los archivos completos nuevos y las instrucciones de integración.

## 1. Importar el validador

En `velo_engine/app.py`, junto al resto de imports internos, añadir:

```python
from velo_engine.file_guard import FileValidationError, validate_uploaded_file
```

## 2. Validar PDF visual

Localizar este bloque:

```python
pdf_path = os.path.join(session_dir, "original.pdf")
file.save(pdf_path)

try:
    text, fmt, error, visual_meta = read_pdf_for_visual_review(pdf_path, session_dir, session_id)
```

Sustituir por:

```python
pdf_path = os.path.join(session_dir, "original.pdf")
file.save(pdf_path)

try:
    validation = validate_uploaded_file(
        pdf_path,
        original_name,
        max_bytes=app.config.get("MAX_CONTENT_LENGTH"),
    )
    for warning in validation.warnings:
        logger.warning("Advertencia de entorno local: %s", warning)
except FileValidationError as exc:
    logger.warning("Fichero rechazado por validación previa: %s", exc.safe_message)
    _cleanup_session(session_id)
    return jsonify({"error": exc.safe_message}), 400

try:
    text, fmt, error, visual_meta = read_pdf_for_visual_review(pdf_path, session_dir, session_id)
```

## 3. Validar flujo no visual

Localizar este bloque:

```python
filepath = os.path.join(workspace, safe_name)
file.save(filepath)

try:
    text, fmt, error = read_file(filepath)
finally:
```

Sustituir por:

```python
filepath = os.path.join(workspace, safe_name)
file.save(filepath)

try:
    validation = validate_uploaded_file(
        filepath,
        original_name,
        max_bytes=app.config.get("MAX_CONTENT_LENGTH"),
    )
    for warning in validation.warnings:
        logger.warning("Advertencia de entorno local: %s", warning)
except FileValidationError as exc:
    logger.warning("Fichero rechazado por validación previa: %s", exc.safe_message)
    try:
        os.remove(filepath)
    except OSError:
        pass
    return jsonify({"error": exc.safe_message}), 400

try:
    text, fmt, error = read_file(filepath)
finally:
```

## 4. Prueba local

Después de integrar:

```powershell
python -m pip install pytest ruff bandit pip-audit
python -m compileall .
ruff check .
pytest -q
bandit -r . -x .venv,build,dist,workspace,tests
pip-audit -r requirements.txt
```

## 5. Resultado esperado

- Un `.pdf` falso debe ser rechazado antes de abrir PyMuPDF.
- Un `.docx` que no sea ZIP debe ser rechazado antes de `python-docx`.
- Un `.exe` renombrado debe ser rechazado.
- El flujo normal TXT/DOCX/PDF válido debe seguir funcionando.
