#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
# Sin cachés .pyc: Python no escribe nada en su propia instalación (la caché
# de su biblioteca estándar) y Velo no deja restos fuera de esta carpeta.
export PYTHONDONTWRITEBYTECODE=1

echo
echo "======================================================"
echo " Velo - Detector de datos sensibles v0.6.0"
echo "======================================================"
echo

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  if python3 -c "import sys; assert sys.version_info >= (3, 11)" >/dev/null 2>&1; then
    PYTHON_CMD=python3
  fi
fi
if [[ -z "$PYTHON_CMD" ]] && command -v python >/dev/null 2>&1; then
  if python -c "import sys; assert sys.version_info >= (3, 11)" >/dev/null 2>&1; then
    PYTHON_CMD=python
  fi
fi
if [[ -z "$PYTHON_CMD" ]]; then
  echo "[ERROR] No se encontró Python 3.11+ en el sistema."
  exit 1
fi

echo "[OK] Python detectado: $($PYTHON_CMD -V 2>&1)"
echo

echo "Preparando entorno virtual local .venv ..."
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_CMD" -m venv .venv || exit 1
fi
VENV_PY=".venv/bin/python"

# Instalación verificada: cada paquete se descarga con la versión exacta de
# locks/*.lock y pip rechaza cualquier fichero cuyo SHA-256 no coincida.
# --only-binary impide compilar paquetes fuente (código arbitrario en setup.py).
# --no-cache-dir: pip no deja copias de los paquetes fuera de esta carpeta.
PIP_VERIFICADO=(-m pip install --require-hashes --only-binary=:all: --disable-pip-version-check --no-cache-dir)

echo "Actualizando pip (versión y hash fijados)..."
if ! "$VENV_PY" "${PIP_VERIFICADO[@]}" -r locks/pip.lock; then
  echo "[ERROR] No se pudo actualizar pip dentro de .venv."
  exit 1
fi

echo "Instalando dependencias base (verificadas por hash)..."
if ! "$VENV_PY" "${PIP_VERIFICADO[@]}" -r locks/requirements.lock; then
  echo "[ERROR] No se pudieron instalar las dependencias base."
  echo "        Si pip informa de un hash que no coincide, NO lo fuerce:"
  echo "        puede indicar una descarga manipulada. Avise en el repositorio."
  exit 1
fi

echo
echo "Intentando instalar dependencias visuales opcionales..."
if "$VENV_PY" "${PIP_VERIFICADO[@]}" -r locks/requirements-visual.lock; then
  echo "[OK] Dependencias visuales instaladas"
else
  if "$VENV_PY" -c "import importlib.util as u; import sys; sys.exit(u.find_spec('pymupdf') is None and u.find_spec('fitz') is None)"; then
    echo "[ERROR] La capa PDF instalada no pudo actualizarse. Repita la instalación."
    exit 1
  fi
  echo "[AVISO] No se pudieron instalar las dependencias visuales."
  echo "        Velo arrancará igualmente en modo base."
fi

echo
INSTALL_NLP=S
if ! "$VENV_PY" -m pip show spacy >/dev/null 2>&1; then
  read -r -p "¿Desea instalar la detección de nombres? [S/n]: " INSTALL_NLP
  INSTALL_NLP="${INSTALL_NLP:-S}"
fi
if [[ "$INSTALL_NLP" == S || "$INSTALL_NLP" == s ]]; then
  echo "Sincronizando spaCy y el modelo español con las versiones verificadas..."
  if ! "$VENV_PY" "${PIP_VERIFICADO[@]}" -r locks/requirements-nlp.lock; then
    if "$VENV_PY" -m pip show spacy >/dev/null 2>&1; then
      echo "[ERROR] La capa lingüística instalada no pudo actualizarse. Repita la instalación."
      exit 1
    fi
    echo "[AVISO] Detección de nombres no disponible."
  fi
fi
"$VENV_PY" -m pip check || exit 1
if [[ "${1:-}" == "--solo-instalar" ]]; then exit 0; fi

echo "Velo solo escribe en esta carpeta y en su directorio de datos."
echo "Para eliminarlo por completo: ./desinstalar.sh"
echo
echo "Iniciando Velo dentro de .venv ..."
exec "$VENV_PY" run.py
