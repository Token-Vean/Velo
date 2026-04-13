@echo off
title Velo
setlocal EnableDelayedExpansion

echo.
echo  ======================================================
echo   Velo - Detector de datos sensibles v0.3.0
echo  ======================================================
echo.

set "PYTHON_CMD="
set "PYTHON_SOURCE="

if exist "%~dp0python_env\python.exe" (
    set "PYTHON_CMD=%~dp0python_env\python.exe"
    set "PYTHON_SOURCE=embebido local"
    goto :python_found
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=python"
        set "PYTHON_SOURCE=sistema"
        goto :python_found
    )
)

where python3 >nul 2>&1
if %errorlevel% equ 0 (
    python3 -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=python3"
        set "PYTHON_SOURCE=sistema"
        goto :python_found
    )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=py -3"
        set "PYTHON_SOURCE=sistema - py launcher"
        goto :python_found
    )
)

echo   Python 3.9+ no detectado en este equipo.
echo.
echo   Se va a descargar Python embebido desde python.org
echo   No requiere instalación ni permisos de administrador.
echo.
set /p "CONFIRM=  Desea continuar? S/N: "
if /i not "%CONFIRM%"=="S" goto :cancelled

echo.
echo   Descargando Python embebido...

set "PY_VERSION=3.11.9"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-embed-amd64.zip"
set "PY_ZIP=%~dp0python_embed.zip"
set "PY_DIR=%~dp0python_env"

powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%PY_URL%', '%PY_ZIP%') } catch { Write-Host $_.Exception.Message; exit 1 } }"
if %errorlevel% neq 0 goto :download_failed

echo   Descomprimiendo...
powershell -Command "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force" 2>nul
if %errorlevel% neq 0 goto :download_failed
del "%PY_ZIP%" >nul 2>&1

for %%f in ("%PY_DIR%\python*._pth") do (
    powershell -Command "(Get-Content '%%f') -replace '#import site', 'import site' | Set-Content '%%f'"
)

echo   Instalando pip...
powershell -Command "& { try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%PY_DIR%\get-pip.py') } catch { exit 1 } }" 2>nul
"%PY_DIR%\python.exe" "%PY_DIR%\get-pip.py" --no-warn-script-location
if %errorlevel% neq 0 goto :pip_failed
del "%PY_DIR%\get-pip.py" >nul 2>&1

echo   [OK] pip instalado
set "PYTHON_CMD=%PY_DIR%\python.exe"
set "PYTHON_SOURCE=embebido - recién descargado"

:python_found
echo   [OK] Python: %PYTHON_SOURCE%
echo.

echo   Instalando dependencias base...
%PYTHON_CMD% -m pip install -r requirements.txt --no-warn-script-location
if %errorlevel% neq 0 goto :deps_failed
echo   [OK] Dependencias base instaladas

echo.
echo   Intentando instalar dependencias visuales opcionales...
%PYTHON_CMD% -m pip install -r requirements-visual.txt --no-warn-script-location
if %errorlevel% equ 0 (
    echo   [OK] Dependencias visuales instaladas
) else (
    echo   [AVISO] No se pudieron instalar las dependencias visuales.
    echo           Velo arrancará igualmente en modo base.
)

REM === Detección de nombres (spaCy) ===
echo.
%PYTHON_CMD% -c "import spacy" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] spaCy ya instalado
    goto :check_spacy_model
)

echo  ------------------------------------------------------
echo   DETECCION DE NOMBRES Y APELLIDOS (opcional)
echo  ------------------------------------------------------
echo.
echo   Velo puede detectar nombres de personas, organizaciones
echo   y lugares usando inteligencia artificial (spaCy).
echo.
echo   Esto requiere descargar ~50 MB adicionales.
echo   Sin esta opción, Velo solo detecta patrones como
echo   DNI, teléfonos, emails, IBAN, etc.
echo.
set /p "INSTALL_NLP=  Desea instalar la detección de nombres? S/N: "
if /i not "%INSTALL_NLP%"=="S" (
    echo.
    echo   [--] Detección de nombres omitida.
    echo       Puede instalarla después con:
    echo       pip install -r requirements-nlp.txt
    echo       python -m spacy download es_core_news_md
    goto :start_velo
)

echo.
echo   Instalando spaCy...
%PYTHON_CMD% -m pip install -r requirements-nlp.txt --no-warn-script-location
if %errorlevel% neq 0 (
    echo   [AVISO] No se pudo instalar spaCy.
    goto :start_velo
)
echo   [OK] spaCy instalado

:check_spacy_model
echo   Comprobando modelo de idioma español...
%PYTHON_CMD% -c "import spacy; spacy.load('es_core_news_md')" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Modelo es_core_news_md disponible
    goto :start_velo
)
%PYTHON_CMD% -c "import spacy; spacy.load('es_core_news_sm')" >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] Modelo es_core_news_sm disponible
    goto :start_velo
)

echo   Descargando modelo español (es_core_news_md)...
%PYTHON_CMD% -m spacy download es_core_news_md --no-warn-script-location
if %errorlevel% equ 0 (
    echo   [OK] Modelo es_core_news_md instalado
) else (
    echo   Intentando modelo ligero (es_core_news_sm)...
    %PYTHON_CMD% -m spacy download es_core_news_sm --no-warn-script-location
    if %errorlevel% equ 0 (
        echo   [OK] Modelo es_core_news_sm instalado
    ) else (
        echo   [AVISO] No se pudo descargar el modelo español.
        echo           La detección de nombres no estará disponible.
    )
)

:start_velo
echo.
echo   Iniciando Velo...
echo   Use el botón Apagar en la interfaz para detener
echo.

cd /d "%~dp0"
%PYTHON_CMD% run.py

echo.
echo   Velo se ha detenido.
echo.
pause
goto :eof

:cancelled
echo.
echo   Instalación cancelada.
echo.
pause
goto :eof

:download_failed
echo.
echo   [ERROR] No se pudo descargar o descomprimir Python.
echo   Compruebe su conexión a internet.
echo.
pause
goto :eof

:pip_failed
echo.
echo   [ERROR] No se pudo instalar pip.
echo.
pause
goto :eof

:deps_failed
echo.
echo   [ERROR] No se pudieron instalar las dependencias base.
echo.
pause
goto :eof
