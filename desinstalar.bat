@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Velo - Desinstalacion
cd /d "%~dp0"
rem Velo - desinstalacion completa (Windows).
rem Velo no instala nada fuera de su carpeta salvo su directorio de datos
rem %LOCALAPPDATA%\Velo (documentos en revision, informes, logs y la clave del
rem log de auditoria). Este script borra ese directorio, el entorno .venv, la
rem carpeta workspace de versiones antiguas y las caches __pycache__.
rem Despues basta con borrar la propia carpeta de Velo.
rem Uso: desinstalar.bat        (pide confirmacion)
rem      desinstalar.bat /S     (sin preguntar)

set "CARPETA=%CD%"
set "DATOS=%LOCALAPPDATA%\Velo"
if not defined LOCALAPPDATA set "DATOS=%USERPROFILE%\Velo"

echo.
echo  ======================================================
echo   Velo - Desinstalacion
echo  ======================================================
echo.
echo   Se borrara, si existe:
echo     - %CARPETA%\.venv
echo     - %CARPETA%\workspace
echo     - %DATOS%
echo     - carpetas __pycache__ dentro de %CARPETA%
echo.
echo   Incluye documentos en revision, informes y registros de Velo.

if /i not "%~1"=="/S" (
    set "RESPUESTA="
    set /p "RESPUESTA=  Continuar? S/N: "
    if /i not "!RESPUESTA!"=="S" (
        echo   Cancelado. No se ha borrado nada.
        if /i not "%~1"=="/S" pause
        goto :eof
    )
)

tasklist /FI "IMAGENAME eq python.exe" /V 2>nul | find /i "Velo" >nul
if not errorlevel 1 (
    echo   [AVISO] Parece que Velo sigue abierto. Apaguelo desde la interfaz y repita.
    if /i not "%~1"=="/S" pause
    exit /b 1
)

if exist "%CARPETA%\.venv" rd /s /q "%CARPETA%\.venv"
if exist "%CARPETA%\workspace" rd /s /q "%CARPETA%\workspace"
if exist "%DATOS%" rd /s /q "%DATOS%"
for /d /r "%CARPETA%" %%D in (__pycache__) do if exist "%%D" rd /s /q "%%D"

set "RESTOS=0"
if exist "%CARPETA%\.venv" (echo   [ERROR] No se pudo borrar %CARPETA%\.venv & set "RESTOS=1")
if exist "%CARPETA%\workspace" (echo   [ERROR] No se pudo borrar %CARPETA%\workspace & set "RESTOS=1")
if exist "%DATOS%" (echo   [ERROR] No se pudo borrar %DATOS% & set "RESTOS=1")
if "%RESTOS%"=="1" (
    echo   Cierre Velo y cualquier ventana que use esos ficheros y repita.
    if /i not "%~1"=="/S" pause
    exit /b 1
)

echo   [OK] Datos y entorno de Velo eliminados.
echo.
echo   Para terminar, borre la carpeta de Velo:
echo     %CARPETA%
echo   Si instalo Tesseract aparte para el OCR, se desinstala desde
echo   "Aplicaciones instaladas" de Windows; Velo no lo instala.
echo.
if /i not "%~1"=="/S" pause
exit /b 0
