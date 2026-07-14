#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

echo
echo "======================================================"
echo " Velo - Detector de datos sensibles v0.5.0"
echo "======================================================"
echo

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  if python3 -c "import sys; assert sys.version_info >= (3, 10)" >/dev/null 2>&1; then
    PYTHON_CMD=python3
  fi
fi
if [[ -z "$PYTHON_CMD" ]] && command -v python >/dev/null 2>&1; then
  if python -c "import sys; assert sys.version_info >= (3, 10)" >/dev/null 2>&1; then
    PYTHON_CMD=python
  fi
fi
if [[ -z "$PYTHON_CMD" ]]; then
  echo "[ERROR] No se encontró Python 3.10+ en el sistema."
  exit 1
fi

echo "[OK] Python detectado: $($PYTHON_CMD -V 2>&1)"
echo

echo "Preparando entorno virtual local .venv ..."
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON_CMD" -m venv .venv
fi
VENV_PY=".venv/bin/python"

"$VENV_PY" -m pip install --upgrade pip setuptools wheel

echo "Instalando dependencias base..."
if ! "$VENV_PY" -m pip install -r requirements.txt; then
  echo "[ERROR] No se pudieron instalar las dependencias base."
  exit 1
fi

echo
echo "Intentando instalar dependencias visuales opcionales..."
if "$VENV_PY" -m pip install -r requirements-visual.txt; then
  echo "[OK] Dependencias visuales instaladas"
else
  echo "[AVISO] No se pudieron instalar las dependencias visuales."
  echo "        Velo arrancará igualmente en modo base."
fi

echo
if ! "$VENV_PY" -c "import spacy" >/dev/null 2>&1; then
  echo "------------------------------------------------------"
  echo " DETECCIÓN DE NOMBRES Y APELLIDOS (opcional)"
  echo "------------------------------------------------------"
  echo
  read -r -p "¿Desea instalar la detección de nombres? [S/n]: " INSTALL_NLP
  INSTALL_NLP="${INSTALL_NLP:-S}"

  if [[ "${INSTALL_NLP^^}" == "S" ]]; then
    echo
    echo "Instalando spaCy..."
    if "$VENV_PY" -m pip install -r requirements-nlp.txt; then
      echo "[OK] spaCy instalado"
      if ! "$VENV_PY" -c "import spacy; spacy.load('es_core_news_md')" >/dev/null 2>&1; then
        if ! "$VENV_PY" -c "import spacy; spacy.load('es_core_news_sm')" >/dev/null 2>&1; then
          echo "Descargando modelo español (es_core_news_md)..."
          if "$VENV_PY" -m spacy download es_core_news_md; then
            echo "[OK] Modelo es_core_news_md instalado"
          else
            echo "Intentando modelo ligero (es_core_news_sm)..."
            if "$VENV_PY" -m spacy download es_core_news_sm; then
              echo "[OK] Modelo es_core_news_sm instalado"
            else
              echo "[AVISO] No se pudo descargar el modelo español."
              echo "        Velo arrancará igualmente en modo regex."
            fi
          fi
        fi
      fi
    else
      echo "[AVISO] No se pudo instalar spaCy."
      echo "        Velo arrancará igualmente en modo regex."
    fi
  else
    echo "[--] Detección de nombres omitida."
  fi
else
  echo "[OK] spaCy ya instalado"
fi

echo
echo "Iniciando Velo dentro de .venv ..."
exec "$VENV_PY" run.py
