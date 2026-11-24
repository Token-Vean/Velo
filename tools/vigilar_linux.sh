#!/usr/bin/env bash
# Vigilancia completa de Velo en Linux (CI): instalar, usar sin y con red,
# y desinstalar, comprobando qué toca en el sistema.
#
#  1. Instalación desde los locks bajo strace: solo puede escribir en la
#     carpeta de Velo (y temporales que desaparecen).
#  2. Auditoría del entorno instalado y revisión del modelo spaCy.
#  3. Uso con red disponible bajo strace (prueba de humo completa): ninguna
#     conexión salvo a la propia interfaz de Velo en 127.0.0.1, ni siquiera
#     DNS; solo escribe en su carpeta y en su directorio de datos.
#  4. Uso en un espacio de red aislado (sin interfaz externa): todo funciona.
#  5. Desinstalación: no queda directorio de datos y la carpeta vuelve a
#     estar exactamente como en el repositorio.
# Requiere: strace, sudo sin contraseña (unshare) y git.
set -euo pipefail
cd "$(dirname "$0")/.."
CARPETA="$(pwd)"
PYTHON_BASE="${PYTHON_BASE:-python3}"
TRAZAS="${RUNNER_TEMP:-/tmp}/trazas-velo"
DATOS="${XDG_STATE_HOME:-$HOME/.local/state}/velo"
mkdir -p "$TRAZAS"
STRACE=(strace -f -y -qq -s 512 -e trace=%network,%file)
FLAGS=(--require-hashes --only-binary=:all: --disable-pip-version-check --no-cache-dir)
export BROWSER=true   # no abrir navegador en CI

if [[ -e .venv || -e "$DATOS" ]]; then
  echo "[ERROR] Ya existe .venv o $DATOS: la vigilancia debe partir de cero."
  exit 1
fi

echo "::group::1. Instalación vigilada"
"${STRACE[@]}" -o "$TRAZAS/instalacion.txt" bash -c "
  set -e
  '$PYTHON_BASE' -m venv .venv
  for lock in pip requirements requirements-visual requirements-nlp; do
    .venv/bin/python -m pip install ${FLAGS[*]} -r locks/\$lock.lock
  done"
echo "::endgroup::"
python3 tools/analizar_traza.py "$TRAZAS/instalacion.txt" --sin-red --permitida "$CARPETA"

echo "::group::2. Auditoría del entorno y del modelo"
.venv/bin/python tools/auditar_entorno.py
.venv/bin/python tools/revisar_modelo_spacy.py
echo "::endgroup::"

echo "::group::3. Uso vigilado con red disponible"
"${STRACE[@]}" -o "$TRAZAS/uso.txt" .venv/bin/python run.py > "$TRAZAS/servidor.txt" 2>&1 &
SERVIDOR=$!
.venv/bin/python tools/prueba_humo.py
wait "$SERVIDOR"
echo "::endgroup::"
python3 tools/analizar_traza.py "$TRAZAS/uso.txt" --permitida "$CARPETA" --permitida "$DATOS"

echo "::group::4. Uso sin red"
cat > "$TRAZAS/sin_red.sh" <<INTERIOR
set -e
cd "$CARPETA"
if .venv/bin/python -c 'import socket; socket.create_connection(("1.1.1.1", 443), 3)' 2>/dev/null; then
  echo "[ERROR] El espacio aislado tiene salida a internet"; exit 1
fi
echo "[OK] Sin salida a internet en el espacio aislado"
.venv/bin/python run.py > "$TRAZAS/servidor-sin-red.txt" 2>&1 &
SERVIDOR=\$!
.venv/bin/python tools/prueba_humo.py
wait \$SERVIDOR
INTERIOR
sudo unshare --net -- bash -c "ip link set lo up && exec sudo -u '$(id -un)' env PATH='$PATH' HOME='$HOME' BROWSER=true XDG_STATE_HOME='${XDG_STATE_HOME:-$HOME/.local/state}' bash '$TRAZAS/sin_red.sh'"
echo "::endgroup::"

echo "::group::5. Desinstalación"
bash desinstalar.sh --si
echo "::endgroup::"
FALLOS=0
if [[ -e .venv ]]; then echo "[ERROR] Queda .venv"; FALLOS=1; fi
if [[ -e "$DATOS" ]]; then echo "[ERROR] Queda $DATOS"; FALLOS=1; fi
RESTOS="$(git status --porcelain --ignored --untracked-files=all)"
if [[ -n "$RESTOS" ]]; then
  echo "[ERROR] La carpeta de Velo no ha quedado como en el repositorio:"
  echo "$RESTOS" | head -50
  FALLOS=1
fi
if [[ $FALLOS -ne 0 ]]; then exit 1; fi
echo "[OK] Desinstalación completa: sin directorio de datos y la carpeta idéntica al repositorio"
