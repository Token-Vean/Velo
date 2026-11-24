#!/usr/bin/env bash
# Velo - desinstalación completa (Linux y macOS).
#
# Velo no instala nada fuera de su carpeta salvo su directorio de datos
# (documentos en revisión, informes, logs y la clave del log de auditoría).
# Este script borra:
#   - el entorno virtual .venv y las cachés __pycache__ de la carpeta de Velo;
#   - la carpeta workspace/ dentro de la carpeta de Velo (versiones antiguas);
#   - el directorio de datos:
#       macOS: ~/Library/Application Support/Velo
#       Linux: ${XDG_STATE_HOME:-~/.local/state}/velo
# Después basta con borrar la propia carpeta de Velo.
# Uso: ./desinstalar.sh        (pide confirmación)
#      ./desinstalar.sh --si   (sin preguntar)
set -u
cd "$(dirname "$0")"
CARPETA="$(pwd)"

if [[ "$(uname -s)" == "Darwin" ]]; then
  DATOS="$HOME/Library/Application Support/Velo"
else
  DATOS="${XDG_STATE_HOME:-$HOME/.local/state}/velo"
fi

OBJETIVOS=()
[[ -d "$CARPETA/.venv" ]] && OBJETIVOS+=("$CARPETA/.venv")
[[ -d "$CARPETA/workspace" ]] && OBJETIVOS+=("$CARPETA/workspace")
[[ -d "$DATOS" ]] && OBJETIVOS+=("$DATOS")
while IFS= read -r -d '' cache; do
  OBJETIVOS+=("$cache")
done < <(find "$CARPETA" -type d -name __pycache__ -not -path "$CARPETA/.venv/*" -print0 2>/dev/null)

echo
echo "======================================================"
echo " Velo - Desinstalación"
echo "======================================================"
echo
if [[ ${#OBJETIVOS[@]} -eq 0 ]]; then
  echo "No queda nada de Velo que borrar fuera de esta carpeta."
else
  echo "Se borrará:"
  for objetivo in "${OBJETIVOS[@]}"; do
    echo "  - $objetivo"
  done
  echo
  echo "Incluye documentos en revisión, informes y registros de Velo."
  if [[ "${1:-}" != "--si" ]]; then
    read -r -p "¿Continuar? [s/N]: " RESPUESTA
    case "$RESPUESTA" in
      [sS]|[sS][iI]|[sS][íÍ]) ;;
      *) echo "Cancelado. No se ha borrado nada."; exit 0 ;;
    esac
  fi
  if pgrep -f "$CARPETA/run.py" >/dev/null 2>&1 || pgrep -f "\.venv/bin/python run.py" >/dev/null 2>&1; then
    echo "[AVISO] Parece que Velo sigue abierto. Apáguelo desde la interfaz y repita."
    exit 1
  fi
  for objetivo in "${OBJETIVOS[@]}"; do
    rm -rf -- "$objetivo"
  done
  RESTOS=0
  for objetivo in "${OBJETIVOS[@]}"; do
    if [[ -e "$objetivo" ]]; then
      echo "[ERROR] No se pudo borrar: $objetivo"
      RESTOS=1
    fi
  done
  [[ $RESTOS -ne 0 ]] && exit 1
  echo "[OK] Datos y entorno de Velo eliminados."
fi
echo
echo "Para terminar, borre la carpeta de Velo:"
echo "  $CARPETA"
echo "Si instaló Tesseract aparte para el OCR, se desinstala desde su propio"
echo "gestor de paquetes; Velo no lo instala."
