#!/usr/bin/env bash
# Genera los ficheros de dependencias bloqueadas con hashes SHA-256 (locks/).
#
# Entradas: requirements.txt, requirements-visual.txt y requirements-nlp.txt
# (los que mantiene Dependabot). Salidas: un .lock por cada entrada, con toda
# la cadena de dependencias fijada a una versión exacta y los hashes de todos
# los ficheros publicados de esa versión (Windows, macOS y Linux), más un lock
# para el propio pip.
#
# Se ejecuta en GitHub Actions (workflow «dependencias-bloqueadas»), que tiene
# acceso a PyPI. Requiere uv.
set -euo pipefail
cd "$(dirname "$0")/.."

PY_MIN="3.11"
COMUN=(--universal --python-version "$PY_MIN" --quiet)
mkdir -p locks

# 1) Resolución conjunta, sin hashes: fija una única versión de cada paquete
#    para que los tres locks sean compatibles entre sí al instalarlos uno tras
#    otro (base -> visual -> NLP), como hacen los instaladores.
uv pip compile "${COMUN[@]}" \
  requirements.txt requirements-visual.txt requirements-nlp.txt \
  -o locks/restricciones.txt

# 2) Un lock con hashes por cada fichero de entrada, restringido a (1).
for nombre in requirements requirements-visual requirements-nlp; do
  uv pip compile "${COMUN[@]}" --generate-hashes \
    -c locks/restricciones.txt \
    "${nombre}.txt" -o "locks/${nombre}.lock"
done

# 3) pip, para no actualizarlo sin verificar en los instaladores.
printf 'pip\n' > locks/pip.in
uv pip compile "${COMUN[@]}" --generate-hashes locks/pip.in -o locks/pip.lock
rm -f locks/pip.in

echo "Locks generados con $(uv --version):"
ls -l locks/
