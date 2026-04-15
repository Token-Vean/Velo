#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"

echo
echo "======================================================"
echo " Velo - Detector de datos sensibles v0.3.0"
echo "======================================================"
echo

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=python
else
  echo "[ERROR] No se encontró Python 3.9+ en el sistema."
  exit 1
fi

echo "[OK] Python detectado: $($PYTHON_CMD -V 2>&1)"
echo

echo "Instalando dependencias base..."
if ! "$PYTHON_CMD" -m pip install -r requirements.txt; then
  echo "[ERROR] No se pudieron instalar las dependencias base."
  exit 1
fi

echo
echo "Intentando instalar dependencias visuales opcionales..."
if "$PYTHON_CMD" -m pip install -r requirements-visual.txt; then
  echo "[OK] Dependencias visuales instaladas"
else
  echo "[AVISO] No se pudieron instalar las dependencias visuales."
  echo "        Velo arrancará igualmente en modo base."
fi

echo
if ! "$PYTHON_CMD" -c "import spacy" >/dev/null 2>&1; then
  echo "------------------------------------------------------"
  echo " DETECCIÓN DE NOMBRES Y APELLIDOS (opcional)"
  echo "------------------------------------------------------"
  echo
  read -r -p "¿Desea instalar la detección de nombres? [S/n]: " INSTALL_NLP
  INSTALL_NLP="${INSTALL_NLP:-S}"

  if [[ "${INSTALL_NLP^^}" == "S" ]]; then
    echo
    echo "Instalando spaCy..."
    if "$PYTHON_CMD" -m pip install -r requirements-nlp.txt; then
      echo "[OK] spaCy instalado"
      if ! "$PYTHON_CMD" -c "import spacy; spacy.load('es_core_news_md')" >/dev/null 2>&1; then
        if ! "$PYTHON_CMD" -c "import spacy; spacy.load('es_core_news_sm')" >/dev/null 2>&1; then
          echo "Descargando modelo español (es_core_news_md)..."
          if "$PYTHON_CMD" -m spacy download es_core_news_md; then
            echo "[OK] Modelo es_core_news_md instalado"
          else
            echo "Intentando modelo ligero (es_core_news_sm)..."
            if "$PYTHON_CMD" -m spacy download es_core_news_sm; then
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
echo "Iniciando Velo..."
echo "Si spaCy falla, Velo debe arrancar igualmente en modo regex."
exec "$PYTHON_CMD" run.py
