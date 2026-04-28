# Checklist de seguridad antes de publicar una beta de Velo

## 1. Repositorio

- [ ] `workspace/`, `.venv/`, `dist/`, `build/`, `*.log`, `__pycache__/` y `*.pyc` están en `.gitignore`.
- [ ] No hay documentos reales ni informes de prueba con datos personales.
- [ ] No hay logs subidos al historial.
- [ ] `SECURITY.md` explica alcance, límites y canal de reporte.
- [ ] La licencia y el aviso de uso local están claros.

## 2. Validación de ficheros

- [ ] Solo se aceptan TXT, DOCX y PDF.
- [ ] Se valida extensión y firma real.
- [ ] DOCX pasa preflight ZIP.
- [ ] PDF se rechaza si la firma no es válida.
- [ ] Hay límite de tamaño.
- [ ] Hay límite de páginas.
- [ ] Hay timeout real de OCR.
- [ ] Hay mensajes de error seguros para el usuario.

## 3. Datos locales

- [ ] El usuario puede purgar sesiones.
- [ ] El usuario puede purgar derivados.
- [ ] El usuario recibe aviso si el workspace está en OneDrive, Dropbox, Google Drive u otra carpeta sincronizada.
- [ ] Los logs no guardan nombres reales de ficheros por defecto.
- [ ] Los informes seguros no guardan valores sensibles completos salvo decisión expresa.

## 4. Aplicación web local

- [ ] Bind exclusivo a `127.0.0.1`.
- [ ] CSRF activo.
- [ ] Same-origin activo.
- [ ] Cabeceras de seguridad activas.
- [ ] Rate limit ajustado por endpoint.
- [ ] Apagado desde interfaz limpia sesiones temporales.
- [ ] No hay modo debug en release.

## 5. Redacción visual

- [ ] La redacción se aplica sobre copia derivada, nunca sobre el original fuera de sesión.
- [ ] El PDF derivado no mantiene capa textual recuperable con datos confirmados.
- [ ] Se informa al usuario de que debe revisar visualmente el resultado.
- [ ] Se conserva traza de decisiones humanas.

## 6. CI/CD

- [ ] GitHub Actions tiene permisos mínimos.
- [ ] Hay timeout de job.
- [ ] Hay `compileall`.
- [ ] Hay `ruff`.
- [ ] Hay `pytest`.
- [ ] Hay `bandit`.
- [ ] Hay `pip-audit`.
- [ ] Hay escaneo de secretos.
- [ ] Dependabot revisa `pip` y `github-actions`.

## 7. Release fácil

- [ ] La release no es simplemente el repo comprimido.
- [ ] Scripts visibles: instalar, iniciar, apagar, desinstalar, diagnóstico.
- [ ] Código fuente y dependencias quedan bajo `app/`.
- [ ] El usuario no técnico no ve carpetas internas en primer plano.
- [ ] Se incluye `SHA256SUMS.txt`.
- [ ] Se incluye advertencia sobre uso con datos sensibles.
- [ ] Se documenta cómo borrar completamente sesiones y logs.
