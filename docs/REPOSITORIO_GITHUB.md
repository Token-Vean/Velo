# Preparación del repositorio para GitHub

Este paquete está saneado para publicación en GitHub.

Incluye:
- limpieza de `__pycache__`, `workspace/` y artefactos de sesión;
- documentación normalizada;
- `CHANGELOG.md` y `CONTRIBUTING.md`;
- flujo de CI básico en `.github/workflows/python-smoke.yml`;
- separación entre dependencias base y opcionales (`requirements-visual.txt`).

Antes de publicar una release, conviene revisar:
1. Nombre definitivo del repositorio.
2. Texto del autor y contacto en `README.md` y `SECURITY.md`.
3. Política de soporte a Windows/macOS/Linux.
4. Ejemplos o capturas sin datos reales.
