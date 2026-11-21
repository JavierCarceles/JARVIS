@echo off
setlocal
title Instalador de Dependencias - JARVIS (Windows)
color 0A
chcp 65001 >nul

echo ============================================================
echo      INSTALADOR DE DEPENDENCIAS DE JARVIS - WINDOWS
echo ============================================================
echo.

rem Este .bat solo localiza Python y lanza docs\requirements\install_jarvis.py,
rem que instala todo lo necesario segun el sistema operativo.
rem En macOS usar docs/requirements/jarvis_requirements.command

set "SCRIPT=%~dp0install_jarvis.py"
set "PYCMD="

rem 1) python del PATH (el que se usa para ejecutar main.py)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto python_ok

rem 2) lanzador py de python.org
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"

:python_ok
if not defined PYCMD (
    echo ERROR: no se encontro Python 3.14 o superior.
    echo Descargalo de https://www.python.org/downloads/ y marca "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo Usando: %PYCMD%
echo.
%PYCMD% "%SCRIPT%" %*
set "RESULTADO=%errorlevel%"

echo.
if "%RESULTADO%"=="0" (
    echo ============================================================
    echo               INSTALACION COMPLETADA
    echo ============================================================
) else (
    echo ============================================================
    echo     INSTALACION TERMINADA CON ERRORES - revisa el resumen
    echo ============================================================
)
echo Ya puedes cerrar esta ventana.
pause
exit /b %RESULTADO%
