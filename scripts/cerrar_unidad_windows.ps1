# Pruebas pendientes en Windows antes de cerrar la unidad actual.
# Lo lanza cerrar_unidad.bat (raiz del proyecto). No pide nada: cada paso se ejecuta oculto
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
# Sin PROMPT, scripts\registrar_candidatos_inventario.py cree que se abrio con
# doble clic y espera un Enter al terminar.
if (-not $env:PROMPT) { $env:PROMPT = '$P$G' }
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

Write-Host '=== git pull ==='
git pull
if ($LASTEXITCODE -ne 0) {
    Write-Host 'git pull ha fallado: revisalo antes de seguir. Nunca push forzado.'
    Read-Host 'Pulsa Enter para salir'
    exit 1
}

& $py -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ('=== Falta PySide6: instalando docs\requirements\requirements.txt en ' + $py + ' ===')
    & $py -m pip install -r docs\requirements\requirements.txt
    & $py -c "import PySide6" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Add-Content -Path $resumenFichero -Value 'AVISO: PySide6 sigue sin poder importarse tras pip install' -Encoding ascii
    }
}

Paso '00_diagnostico' 'scripts/diagnostico_calibracion_windows.py'
# Candidatos de aplicacion del ultimo escaneo completo real (sin reescanear el
# disco; idempotente). Los tests de la SQLite real los necesitan.
Paso '00b_registrar_candidatos' 'scripts/registrar_candidatos_inventario.py --volumen C:'
Paso '01_py_compile' '-m py_compile src/hands/inventory/system_inventory_storage.py src/hands/apps/launch_windows.py src/hands/apps/platform_launch.py src/hands/calibration/calibration_pipeline.py src/hands/apps/application_discovery.py src/hands/apps/applications_core.py src/hands/inventory/system_inventory_storage.py src/memory/storage.py src/eyes/capture/screen_capture.py src/hands/apps/launch_macos.py src/hands/calibration/ui_exploration.py scripts/diagnostico_calibracion_windows.py'
Paso '02_unitarios_lanzamiento' '-m pytest tests/hands/apps/test_launch_windows_desempate.py tests/hands/apps/test_aplicaciones_integradas_windows.py tests/hands/calibration/calibration_pipeline/test_qwen_robustez.py tests/hands/apps/test_platform_launch_contract.py tests/hands/apps/test_platform_launch_service.py tests/hands/inventory/system_inventory_storage -v -rfEs'
Paso '03_application_discovery' '-m pytest tests/hands/apps/application_discovery/test_application_discovery.py -v -rfEs'
Paso '04_gui_platform_launch' '-m pytest tests/hands/apps/test_platform_launch_entorno_real.py -v -s -rfEs'
Paso '04b_identidad_integradas' '-m pytest tests/hands/apps/test_aplicaciones_integradas_windows.py tests/hands/apps/application_discovery/test_application_discovery.py -k "identidad or Integradas or Variantes or Busqueda" -v -rfEs'
Paso '04c_navegacion_chat' '-m pytest tests/hands/calibration/ui_exploration/test_navegacion_chat_entorno_real.py -v -s -rfEs'
Paso '04c_navegacion_ajustes' '-m pytest tests/hands/calibration/ui_exploration/test_navegacion_ajustes_entorno_real.py -v -s -rfEs'
Paso '05_calibracion_aplicaciones' '-m pytest tests/hands/calibration/calibration_pipeline/test_calibracion_aplicaciones_entorno_real.py -v -s -rfEs'
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
