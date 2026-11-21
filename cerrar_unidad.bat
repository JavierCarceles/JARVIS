@echo off
rem Lanza las pruebas pendientes en Windows (scripts\cerrar_unidad_windows.ps1)
rem y sube la salida a GitHub. Ejecutar con doble clic o desde la raiz.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\cerrar_unidad_windows.ps1"
