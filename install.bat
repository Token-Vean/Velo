@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Velo
cd /d "%~dp0"

echo.
echo  ======================================================
echo   Velo - Detector de datos sensibles v0.5.0
echo  ======================================================
echo.

set "PYTHON_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 (
        py -3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=py -3"
    )
)
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if %errorlevel% equ 0 (
        python3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    echo   [ERROR] No se ha encontrado Python 3.11+ en este equipo.
    echo.
    pause
    goto :eof
)

echo   [OK] Python detectado: %PYTHON_CMD%

echo   Preparando entorno virtual local .venv ...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo.
        echo   [ERROR] No se pudo crear el entorno virtual .venv.
        echo.
        pause
        goto :eof
    )
)

set "VENV_PY=.venv\Scripts\python.exe"
rem Instalacion verificada: version exacta de locks\*.lock y comprobacion del
rem SHA-256 de cada fichero. --only-binary impide compilar paquetes fuente.
rem --no-cache-dir: pip no deja copias de los paquetes fuera de esta carpeta.
set "PIP_VERIFICADO=-m pip install --require-hashes --only-binary=:all: --disable-pip-version-check --no-cache-dir --no-warn-script-location"

echo   Actualizando pip (version y hash fijados)...
%VENV_PY% %PIP_VERIFICADO% -r locks\pip.lock
if errorlevel 1 (
    echo.
    echo   [ERROR] No se pudo actualizar pip dentro de .venv.
    echo.
    pause
    goto :eof
)

echo.
echo   Instalando dependencias base (verificadas por hash)...
%VENV_PY% %PIP_VERIFICADO% -r locks\requirements.lock
if errorlevel 1 (
    echo.
    echo   [ERROR] No se pudieron instalar las dependencias base.
    echo           Si pip informa de un hash que no coincide, NO lo fuerce:
    echo           puede indicar una descarga manipulada. Avise en el repositorio.
    echo.
    pause
    goto :eof
)

echo.
echo   Intentando instalar dependencias visuales opcionales...
%VENV_PY% %PIP_VERIFICADO% -r locks\requirements-visual.lock
if errorlevel 1 (
    echo   [AVISO] No se pudieron instalar las dependencias visuales.
    echo           Velo arrancara igualmente en modo base.
) else (
    echo   [OK] Dependencias visuales instaladas
)

echo.
%VENV_PY% -c "import spacy; spacy.load('es_core_news_md')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  ------------------------------------------------------
    echo   DETECCION DE NOMBRES Y APELLIDOS (opcional)
    echo  ------------------------------------------------------
    echo.
    set "INSTALL_NLP="
    set /p "INSTALL_NLP=  Desea instalar la deteccion de nombres? S/N: "
    if /i "!INSTALL_NLP!"=="S" (
        echo.
        echo   Instalando spaCy y el modelo es_core_news_md ^(verificados por hash^)...
        %VENV_PY% %PIP_VERIFICADO% -r locks\requirements-nlp.lock
        if errorlevel 1 (
            echo   [AVISO] No se pudo instalar spaCy o su modelo.
            echo           Velo arrancara igualmente en modo regex.
        ) else (
            echo   [OK] spaCy y modelo espanol instalados
        )
    ) else (
        echo   [--] Deteccion de nombres omitida.
    )
) else (
    echo   [OK] spaCy y modelo es_core_news_md ya instalados
)

echo.
echo   Velo solo escribe en esta carpeta y en %LOCALAPPDATA%\Velo.
echo   Para eliminarlo por completo: desinstalar.bat
echo.
echo   Iniciando Velo dentro de .venv ...
echo.
%VENV_PY% run.py
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo   [AVISO] Velo termino con codigo %EXITCODE%.
    echo   Revise los logs en %LOCALAPPDATA%\Velo\workspace\logs
) else (
    echo   Velo se ha detenido.
)
echo.
pause
