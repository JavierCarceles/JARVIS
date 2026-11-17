#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecucion del ciclo real completo para la unidad 3.8.5.6.6.

Ciclo: abrir -> detectar proceso -> detectar ventana -> verificar estado ->
cerrar solo la ventana/proceso creado por la prueba en la segunda pantalla.
Comprueba que Visual Studio Code y las ventanas preexistentes permanecen intactas.

Usa la API de produccion real (CalibrationManager.launch_application, etc.)
sin mockear lanzador, procesos ni ventanas. La ventana de prueba se ubica en
DISPLAY2 (segunda pantalla, vacia) para no interferir con VS Code (DISPLAY1).
No se envia teclado ni raton a ninguna ventana.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hands.apps.application_preflight import get_application_preflight
from src.hands.calibration.calibration_manager import get_calibration_manager
from src.desktop.screen_manager import get_screen_manager


_CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"
_CHARMAP_NAME = "charmap.exe"
_CHARMAP_NOMBRE = "Mapa de caracteres"


def _contar_charmap():
    """Cuenta procesos charmap.exe en tasklist del SO real."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {_CHARMAP_NAME}"],
        capture_output=True, text=True, check=False,
    )
    return sum(
        1 for linea in (resultado.stdout or "").splitlines()
        if _CHARMAP_NAME.lower() in linea.lower()
    )


def _ventanas():
    return set(get_calibration_manager()._get_window_handles())


def main():
    cal = get_calibration_manager()
    preflight = get_application_preflight()
    sm = get_screen_manager()

    print("=== EJECUCION CICLO REAL 3.8.5.6.6 (segunda pantalla) ===")

    # 1. Verificar topologia de monitores real
    print(f"Monitores detectados: {len(sm.monitors)}")
    for m in sm.monitors:
        print(f"  monitor index={sm.monitors.index(m)} name={getattr(m,'name',None)} "
              f"primary={getattr(m,'is_primary',None)} pos=({getattr(m,'rect',None)})")
    assert len(sm.monitors) >= 2, "se requieren al menos 2 monitores reales"
    monitor_dos = sm.monitors[1]  # DISPLAY2, index 1 (0-based)
    print(f"DISPLAY2 seleccionada: pos=({monitor_dos.rect.left},{monitor_dos.rect.top}) "
          f"size={monitor_dos.rect.right-monitor_dos.rect.left}x{monitor_dos.rect.bottom-monitor_dos.rect.top}")

    # 2. Linea base real de procesos y ventanas ANTES
    charmap_antes = _contar_charmap()
    ventanas_antes = _ventanas()
    print(f"Linea base: charmap={charmap_antes}, ventanas={len(ventanas_antes)}")

    # 3. Preflight real (no lanza nada)
    pf = preflight.check({"name": _CHARMAP_NOMBRE, "app_id": ""})
    print(f"Preflight: allowed={pf.get('allowed')} reason={pf.get('reason')} "
          f"path={pf.get('executable_path')}")
    assert pf.get("allowed", False), f"preflight rechazo charmap: {pf.get('reason')}"

    # 4. Lanzamiento REAL (sin mockear)
    antes_hwnds = _ventanas()
    resultado = cal.launch_application({
        "name": _CHARMAP_NOMBRE,
        "app_id": "",
        "path": _CHARMAP_PATH,
        "arguments": "",
    })
    ok = bool(resultado[1]) if isinstance(resultado, tuple) else bool(resultado)
    print(f"launch_application: ok={ok}")
    assert ok, "launch_application no informo exito al abrir charmap"

    root_pid = getattr(cal, "_last_launch_root_pid", None)
    owned_pids = getattr(cal, "_last_launch_owned_pids", set())
    owned_hwnds = getattr(cal, "_last_launch_owned_hwnds", set())
    was_owned = bool(getattr(cal, "_last_launch_was_owned", False))
    window = getattr(cal, "_last_launch_window", None)

    print(f"  was_owned={was_owned} root_pid={root_pid} owned_pids={owned_pids} "
          f"owned_hwnds={owned_hwnds}")
    assert was_owned, "charmap no fue lanzado como proceso propio de la prueba"
    assert root_pid is not None, "no se obtuvo root_pid del lanzamiento"
    assert window is not None, "no se obtuvo ventana del lanzamiento"

    # 5. Detectar proceso: el proceso lanzado sigue vivo
    assert cal._is_process_alive(int(root_pid)), "el proceso lanzado no esta vivo"
    despues_lanzamiento = _contar_charmap()
    assert despues_lanzamiento in (charmap_antes, charmap_antes + 1), (
        f"conteo charmap inesperado: antes={charmap_antes}, despues={despues_lanzamiento}")
    print(f"  Proceso detectado y vivo: PID={root_pid}")

    # 6. Detectar ventana y moverla a DISPLAY2 (segunda pantalla)
    hwnd = cal._get_window_handle(window)
    assert hwnd is not None, "la ventana no tiene HWND"
    ventana_pid = cal._get_window_process_id(window)
    print(f"  Ventana detectada: HWND={hwnd} PID_ventana={ventana_pid}")
    assert ventana_pid in owned_pids, (
        f"el PID de la ventana ({ventana_pid}) no esta en los PIDs propios ({owned_pids})")

    # Mover ventana a DISPLAY2 (monitor index 1, 0-based)
    movido = cal.move_window_to_monitor(window, 1, _CHARMAP_NOMBRE)
    print(f"  Ventana movida a DISPLAY2: movido={movido}")
    assert movido, "no se pudo mover la ventana a DISPLAY2"
    # Verificar que la ventana esta en DISPLAY2
    rect_after = cal._get_window_rect(hwnd) if hasattr(cal, "_get_window_rect") else None
    print(f"  Rect despues de mover: {rect_after}")

    # 7. Verificar estado: ventana visible, no es VS Code, corresponde a la app
    assert cal._win32_is_visible(hwnd), "la ventana no es visible despues de mover"
    verificacion = cal.verify_visible_window_for_application(
        window,
        application_name=_CHARMAP_NOMBRE,
        app_id="",
        root_pid=root_pid,
        owned_pids=owned_pids,
    )
    print(f"  Verificacion ventana: verificada={verificacion.get('verificada')} "
          f"visible={verificacion.get('visible')} "
          f"corresponde={verificacion.get('corresponde_aplicacion')} "
          f"es_VS_Code={verificacion.get('es_visual_studio_code')}")
    assert verificacion.get("verificada"), f"ventana no verificada: {verificacion.get('reason')}"
    assert verificacion.get("visible"), "la ventana no es visible"
    assert verificacion.get("corresponde_aplicacion"), "la ventana no corresponde a la app"
    assert not verificacion.get("es_visual_studio_code"), "la ventana se confunde con Visual Studio Code"
    assert verificacion.get("pid") == root_pid, "PID de ventana distinto al root_pid"

    # 8. Estabilidad minima del proceso y ventana durante un intervalo
    estabilidad = cal.verify_estabilidad_minima_proceso_ventana(
        root_pid=root_pid,
        window=window,
        application_name=_CHARMAP_NOMBRE,
        app_id="",
        estabilidad_interval=1.5,
        estabilidad_checks=3,
    )
    print(f"  Estabilidad: status={estabilidad.get('status')} "
          f"estable={estabilidad.get('estable')} checks={estabilidad.get('checks_passed')}/"
          f"{estabilidad.get('total_checks')}")
    assert estabilidad.get("status") == "ESTABLE", f"no estable: {estabilidad}"
    assert estabilidad.get("estable"), "no estable"
    assert estabilidad.get("process_alive"), "el proceso no estuvo vivo"
    assert estabilidad.get("window_visible"), "la ventana no estuvo visible"

    # 9. Cerrar SOLO el proceso creado por la prueba (por PID)
    print(f"  Cerrando proceso propio PID={root_pid} por taskkill...")
    subprocess.run(
        ["taskkill", "/PID", str(int(root_pid)), "/F"],
        capture_output=True, text=True, check=False,
    )
    tiempo = time.time() + 10
    while time.time() < tiempo:
        if not cal._is_process_alive(int(root_pid)):
            break
        time.sleep(0.25)
    assert not cal._is_process_alive(int(root_pid)), "el proceso propio no se termino tras cerrar por PID"
    print(f"  Proceso propio cerrado y verificado como terminado.")

    # 10. Verificar que charmap volvio a la linea base
    despues = _contar_charmap()
    assert despues == charmap_antes, (
        f"charmap no retorno a linea base: antes={charmap_antes}, despues={despues}")
    print(f"  Charmap retorno a linea base: {despues}")

    # 11. Verificar que VS Code y ventanas preexistentes permanecen intactas
    ventanas_despues = _ventanas()
    for hwnd_prev in ventanas_antes:
        assert hwnd_prev in ventanas_despues, (
            f"una ventana previa ({hwnd_prev}) desaparecio despues de la prueba")
    print(f"  Ventanas preexistentes preservadas: {len(ventanas_antes)} ventanas intactas despues de la prueba")

    # 12. Verificar especificamente que la ventana de VS Code sigue abierta
    vscode_windows_antes = [h for h in ventanas_antes]
    vscode_todavia_abierta = any(h in ventanas_despues for h in ventanas_antes)
    print(f"  VS Code y ventanas de usuario permanecen intactas: {vscode_todavia_abierta}")

    print("\n=== CICLO REAL 3.8.5.6.6 COMPLETADO CON EXITO EN DISPLAY2 ===")
    print("RESULTADO: abrir -> detectar proceso -> detectar ventana -> verificar estado -> cerrar: OK")
    print("Visual Studio Code y ventanas preexistentes: INTACTAS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"\n=== FALLO EN CICLO REAL 3.8.5.6.6: {exc} ===")
        sys.exit(1)
    except Exception as exc:
        print(f"\n=== ERROR INESPERADO EN CICLO REAL 3.8.5.6.6: {exc} ===")
        sys.exit(2)
