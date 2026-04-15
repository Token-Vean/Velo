@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Velo
cd /d "%~dp0"

echo.
echo  ======================================================
echo   Velo - Detector de datos sensibles v0.3.0
echo  ======================================================
echo.

set "PYTHON_CMD="
where python >nul 2>&1
if %errorlevel% equ 0 (
    python -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    where py >nul 2>&1
    if %errorlevel% equ 0 (
        py -3 -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=py -3"
    )
)
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if %errorlevel% equ 0 (
        python3 -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    echo   [ERROR] No se ha encontrado Python 3.9+ en este equipo.
    echo.
    pause
    goto :eof
)

echo   [OK] Python detectado: %PYTHON_CMD%
echo.
echo   Instalando dependencias base...
%PYTHON_CMD% -m pip install -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo.
    echo   [ERROR] No se pudieron instalar las dependencias base.
    echo.
    pause
    goto :eof
)

echo.
echo   Intentando instalar dependencias visuales opcionales...
%PYTHON_CMD% -m pip install -r requirements-visual.txt --no-warn-script-location
if errorlevel 1 (
    echo   [AVISO] No se pudieron instalar las dependencias visuales.
    echo           Velo arrancara igualmente en modo base.
) else (
    echo   [OK] Dependencias visuales instaladas
)

echo.
%PYTHON_CMD% -c "import spacy" >nul 2>&1
if %errorlevel% neq 0 (
    echo  ------------------------------------------------------
    echo   DETECCION DE NOMBRES Y APELLIDOS (opcional)
    echo  ------------------------------------------------------
    echo.
    set /p "INSTALL_NLP=  Desea instalar la deteccion de nombres? S/N: "
    if /i "%INSTALL_NLP%"=="S" (
        echo.
        echo   Instalando spaCy...
        %PYTHON_CMD% -m pip install -r requirements-nlp.txt --no-warn-script-location
        if errorlevel 1 (
            echo   [AVISO] No se pudo instalar spaCy.
            echo           Velo arrancara igualmente en modo regex.
        ) else (
            echo   [OK] spaCy instalado
            %PYTHON_CMD% -c "import spacy; spacy.load('es_core_news_md')" >nul 2>&1
            if errorlevel 1 (
                %PYTHON_CMD% -c "import spacy; spacy.load('es_core_news_sm')" >nul 2>&1
                if errorlevel 1 (
                    echo   Descargando modelo es_core_news_md...
                    %PYTHON_CMD% -m spacy download es_core_news_md --no-warn-script-location
                    if errorlevel 1 (
                        echo   Intentando modelo ligero es_core_news_sm...
                        %PYTHON_CMD% -m spacy download es_core_news_sm --no-warn-script-location
                        if errorlevel 1 (
                            echo   [AVISO] No se pudo instalar ningun modelo de spaCy.
                            echo           Velo arrancara igualmente en modo regex.
                        ) else (
                            echo   [OK] Modelo es_core_news_sm instalado
                        )
                    ) else (
                        echo   [OK] Modelo es_core_news_md instalado
                    )
                ) else (
                    echo   [OK] Modelo es_core_news_sm ya disponible
                )
            ) else (
                echo   [OK] Modelo es_core_news_md ya disponible
            )
        )
    ) else (
        echo   [--] Deteccion de nombres omitida.
    )
) else (
    echo   [OK] spaCy ya esta instalado
)

echo.
echo   Iniciando Velo...
echo   Si spaCy falla, la aplicacion debe arrancar igualmente en modo regex.
echo.
%PYTHON_CMD% run.py
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo   [AVISO] Velo termino con codigo %EXITCODE%.
    echo   Revise workspace\logs\velo.log
) else (
    echo   Velo se ha detenido.
)
echo.
pause
