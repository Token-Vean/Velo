@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Velo
cd /d "%~dp0"
rem Sin caches .pyc: Python no escribe nada en su propia instalacion (la cache
rem de su biblioteca estandar) y Velo no deja restos fuera de esta carpeta.
set "PYTHONDONTWRITEBYTECODE=1"

echo.
echo  ======================================================
echo   Velo - Detector de datos sensibles v0.6.0
echo  ======================================================
echo.

set "PYTHON_CMD="
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=py -3"
    )
)
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    echo   [ERROR] No se ha encontrado Python 3.11+ en este equipo.
    echo.
    goto :fallo
)

echo   [OK] Python detectado: %PYTHON_CMD%

echo   Preparando entorno virtual local .venv ...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo.
        echo   [ERROR] No se pudo crear el entorno virtual .venv.
        echo.
        goto :fallo
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
    goto :fallo
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
    goto :fallo
)

echo.
echo   Intentando instalar dependencias visuales opcionales...
%VENV_PY% %PIP_VERIFICADO% -r locks\requirements-visual.lock
if errorlevel 1 (
    %VENV_PY% -c "import importlib.util as u; import sys; sys.exit(u.find_spec('pymupdf') is None and u.find_spec('fitz') is None)"
    if not errorlevel 1 (
        echo   [ERROR] La capa PDF instalada no pudo actualizarse. Repita la instalacion.
        goto :fallo
    )
    echo   [AVISO] No se pudieron instalar las dependencias visuales.
    echo           Velo arrancara igualmente en modo base.
) else (
    echo   [OK] Dependencias visuales instaladas
)

echo.
set "INSTALL_NLP=S"
%VENV_PY% -m pip show spacy >nul 2>&1
if errorlevel 1 (
    set "INSTALL_NLP="
    set /p "INSTALL_NLP=  Desea instalar la deteccion de nombres? S/N: "
)
if /i "!INSTALL_NLP!"=="S" (
    echo   Sincronizando spaCy y el modelo espanol con las versiones verificadas...
    %VENV_PY% %PIP_VERIFICADO% -r locks\requirements-nlp.lock
    if errorlevel 1 (
        %VENV_PY% -m pip show spacy >nul 2>&1
        if not errorlevel 1 (
            echo   [ERROR] La capa linguistica instalada no pudo actualizarse. Repita la instalacion.
            goto :fallo
        )
        echo   [AVISO] Deteccion de nombres no disponible.
    )
)
%VENV_PY% -m pip check
if errorlevel 1 goto :fallo
if /i "%~1"=="--solo-instalar" exit /b 0

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

exit /b %EXITCODE%

:fallo
if /i not "%~1"=="--solo-instalar" pause
exit /b 1
