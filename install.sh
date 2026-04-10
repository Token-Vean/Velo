#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo
echo "======================================================"
echo " Velo - Detector de datos sensibles v0.2.5"
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

echo
echo "Iniciando Velo..."
$PYTHON_CMD run.py
