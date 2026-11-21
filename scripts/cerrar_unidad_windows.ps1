# Pruebas pendientes en Windows antes de cerrar la unidad actual.
# Lo lanza cerrar_unidad.bat (raiz del proyecto). Cada paso se ejecuta oculto
# (no roba el foco a las ventanas de prueba) y en serie; la salida queda en
# salidas_windows\ y al final se sube a GitHub (sin push forzado).

$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$out = Join-Path $raiz 'salidas_windows'
New-Item -ItemType Directory -Force $out | Out-Null
$resumenFichero = Join-Path $out '00_resumen.txt'
Set-Content -Path $resumenFichero -Value ("Inicio: " + (Get-Date -Format s)) -Encoding ascii

if (Test-Path (Join-Path $raiz 'venv\Scripts\python.exe')) {
    $py = Join-Path $raiz 'venv\Scripts\python.exe'
} else {
    $py = 'python'
}
$env:PYTHONIOENCODING = 'utf-8'
$env:JARVIS_TEST_GUI_REAL = '1'
Remove-Item Env:JARVIS_AUTORIZAR_ESCANEO_VOLUMEN_GLOBAL -ErrorAction SilentlyContinue
$escaneo = 'tests/hands/inventory/system_inventory/test_escaneo_volumenes_locales_completo_entorno_real.py'

function Paso([string]$nombre, [string]$argumentos) {
    Write-Host ''
    Write-Host ("=== " + $nombre + " (" + (Get-Date -Format T) + ") ===")
    $inicio = Get-Date
    $p = Start-Process -FilePath $py -ArgumentList $argumentos `
        -RedirectStandardOutput (Join-Path $out ($nombre + '.txt')) `
        -RedirectStandardError (Join-Path $out ($nombre + '_err.txt')) `
        -WindowStyle Hidden -PassThru -Wait
    $segundos = [int]((Get-Date) - $inicio).TotalSeconds
    $ultima = ''
    $fichero = Join-Path $out ($nombre + '.txt')
    if (Test-Path $fichero) {
        $ultima = (Get-Content $fichero -Tail 1 -ErrorAction SilentlyContinue)
    }
    $linea = "{0}: codigo {1} en {2} s | {3}" -f $nombre, $p.ExitCode, $segundos, $ultima
    Write-Host $linea
    Add-Content -Path $resumenFichero -Value $linea -Encoding ascii
}

function Esperar([string]$texto) {
    Write-Host ''
    Read-Host ($texto + '. Pulsa Enter cuando este hecho')
}

Write-Host '=== git pull ==='
git pull
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git pull ha fallado: revisalo antes de seguir. Nunca push forzado.'
    Read-Host 'Pulsa Enter para salir'
    exit 1
}

& $py -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ('Falta PySide6 en ' + $py + '. Instala las dependencias en ese Python y vuelve a lanzar cerrar_unidad.bat:')
    Write-Host '  venv\Scripts\activate'
    Write-Host '  docs\requirements\jarvis_requirements.bat'
    Write-Host ('o directamente: ' + $py + ' -m pip install -r docs\requirements\requirements.txt')
    Read-Host 'Pulsa Enter para salir'
    exit 1
}

Esperar 'Cierra Bloc de notas, Calculadora, Chrome, Edge, Configuracion y Discord si los tienes abiertos (VS Code puede quedarse)'

Paso '00_diagnostico' 'scripts/diagnostico_calibracion_windows.py'
Paso '01_py_compile' '-m py_compile src/hands/inventory/system_inventory_storage.py src/hands/apps/launch_windows.py src/hands/apps/platform_launch.py src/hands/calibration/calibration_pipeline.py src/hands/apps/application_discovery.py scripts/diagnostico_calibracion_windows.py'
Paso '02_unitarios_lanzamiento' '-m pytest tests/hands/apps/test_launch_windows_desempate.py tests/hands/apps/test_aplicaciones_integradas_windows.py tests/hands/calibration/calibration_pipeline/test_qwen_robustez.py tests/hands/apps/test_platform_launch_contract.py tests/hands/apps/test_platform_launch_service.py tests/hands/inventory/system_inventory_storage -v -rfEs'
Paso '03_application_discovery' '-m pytest tests/hands/apps/application_discovery/test_application_discovery.py -v -rfEs'
Paso '04_gui_platform_launch' '-m pytest tests/hands/apps/test_platform_launch_entorno_real.py -v -s -rfEs'
Paso '04b_identidad_integradas' '-m pytest tests/hands/apps/test_aplicaciones_integradas_windows.py tests/hands/apps/application_discovery/test_application_discovery.py -k "identidad or Integradas or Variantes or Busqueda" -v -rfEs'
Paso '04c_navegacion_chat' '-m pytest tests/hands/calibration/ui_exploration/test_navegacion_chat_entorno_real.py -v -s -rfEs'
Esperar 'Comprueba que Configuracion de Windows esta cerrada'
Paso '04c_navegacion_ajustes' '-m pytest tests/hands/calibration/ui_exploration/test_navegacion_ajustes_entorno_real.py -v -s -rfEs'
Esperar 'Comprueba que Bloc de notas, Calculadora y Chrome estan cerrados'
Paso '05_calibracion_aplicaciones' '-m pytest tests/hands/calibration/calibration_pipeline/test_calibracion_aplicaciones_entorno_real.py -v -s -rfEs'
Esperar 'No regresion: abrira y cerrara aplicaciones reales y puede tardar mucho. Cierra Bloc de notas, Calculadora, Chrome, Edge, Mapa de caracteres y Discord'
Paso '06a_no_regresion_hands' ("-m pytest tests/hands --ignore=" + $escaneo + " -q -rfEs")
Paso '06b_no_regresion_resto' '-m pytest tests/brain tests/core tests/desktop tests/ear tests/experimental tests/eyes tests/fixtures tests/helpers tests/memory -q -rfEs'

Add-Content -Path $resumenFichero -Value ("Fin: " + (Get-Date -Format s)) -Encoding ascii
Write-Host ''
Get-Content $resumenFichero

Write-Host ''
Write-Host '=== Subir resultados a GitHub ==='
git add salidas_windows data/memory/entities.json
git commit -m "salidas windows cierre unidad"
git push
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git push ha fallado: haz git pull y vuelve a hacer git push. Nunca push forzado.'
}
Read-Host 'Pulsa Enter para cerrar'
