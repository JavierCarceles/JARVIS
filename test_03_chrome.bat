@echo off
setlocal
rem Ejecuta test_03 (calibracion real de Chrome) oculto y sube la salida a GitHub.
rem Ejecutar desde cualquier sitio: se situa en la raiz del proyecto.
cd /d "%~dp0"

echo === 1/4 git pull ===
git pull
if errorlevel 1 (
    echo git pull ha fallado: revisa el mensaje antes de seguir. No uses push forzado.
    pause
    exit /b 1
)

echo.
echo === 2/4 Cierra TODAS las ventanas de Chrome antes de continuar ===
pause

set JARVIS_TEST_GUI_REAL=1
set TEST=tests/hands/calibration/calibration_pipeline/test_calibracion_aplicaciones_entorno_real.py::TestCalibracionAplicacionesEntornoReal::test_03_calibra_navegador_chromium_entorno_real
set SALIDA=test_03_calibra_chrome_out.txt
set ERRORES=test_03_calibra_chrome_err.txt

echo.
echo === 3/4 test_03 en segundo plano y oculto (no toques raton ni teclado) ===
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process python -ArgumentList '-m','pytest','%TEST%','-v','-s' -RedirectStandardOutput '%SALIDA%' -RedirectStandardError '%ERRORES%' -WindowStyle Hidden -PassThru -Wait; exit $p.ExitCode"
set RESULTADO=%errorlevel%
echo.
type "%SALIDA%"
echo.
echo Codigo de salida de pytest: %RESULTADO% (0 = PASSED)

echo.
echo === 4/4 Subir la salida a GitHub ===
git add "%SALIDA%" "%ERRORES%"
git commit -m "output test_03"
git push
if errorlevel 1 (
    echo git push ha fallado. Haz git pull y vuelve a hacer git push. Nunca push forzado.
)

pause
endlocal
