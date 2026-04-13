#!/usr/bin/env bash
set -e
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
$PYTHON_CMD -m pip install -r requirements.txt

echo
echo "Intentando instalar dependencias visuales opcionales..."
if $PYTHON_CMD -m pip install -r requirements-visual.txt; then
  echo "[OK] Dependencias visuales instaladas"
else
  echo "[AVISO] No se pudieron instalar las dependencias visuales."
  echo "        Velo arrancará igualmente en modo base."
fi

# === Detección de nombres (spaCy) ===
echo
if $PYTHON_CMD -c "import spacy" 2>/dev/null; then
  echo "[OK] spaCy ya instalado"
else
  echo "------------------------------------------------------"
  echo " DETECCIÓN DE NOMBRES Y APELLIDOS (opcional)"
  echo "------------------------------------------------------"
  echo
  echo "Velo puede detectar nombres de personas, organizaciones"
  echo "y lugares usando inteligencia artificial (spaCy)."
  echo
  echo "Esto requiere descargar ~50 MB adicionales."
  echo "Sin esta opción, Velo solo detecta patrones como"
  echo "DNI, teléfonos, emails, IBAN, etc."
  echo
  read -rp "¿Desea instalar la detección de nombres? [S/n]: " INSTALL_NLP
  INSTALL_NLP="${INSTALL_NLP:-S}"

  if [[ "${INSTALL_NLP^^}" != "S" ]]; then
    echo
    echo "[--] Detección de nombres omitida."
    echo "     Puede instalarla después con:"
    echo "     pip install -r requirements-nlp.txt"
    echo "     python -m spacy download es_core_news_md"
  else
    echo
    echo "Instalando spaCy..."
    if $PYTHON_CMD -m pip install -r requirements-nlp.txt; then
      echo "[OK] spaCy instalado"
    else
      echo "[AVISO] No se pudo instalar spaCy."
    fi
  fi
fi

# Comprobar modelo español
if $PYTHON_CMD -c "import spacy" 2>/dev/null; then
  if $PYTHON_CMD -c "import spacy; spacy.load('es_core_news_md')" 2>/dev/null; then
    echo "[OK] Modelo es_core_news_md disponible"
  elif $PYTHON_CMD -c "import spacy; spacy.load('es_core_news_sm')" 2>/dev/null; then
    echo "[OK] Modelo es_core_news_sm disponible"
  else
    echo "Descargando modelo español (es_core_news_md)..."
    if $PYTHON_CMD -m spacy download es_core_news_md; then
      echo "[OK] Modelo es_core_news_md instalado"
    else
      echo "Intentando modelo ligero (es_core_news_sm)..."
      if $PYTHON_CMD -m spacy download es_core_news_sm; then
        echo "[OK] Modelo es_core_news_sm instalado"
      else
        echo "[AVISO] No se pudo descargar el modelo español."
        echo "        La detección de nombres no estará disponible."
      fi
    fi
  fi
fi

echo
echo "Iniciando Velo..."
$PYTHON_CMD run.py
