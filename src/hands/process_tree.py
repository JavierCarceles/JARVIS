# -*- coding: utf-8 -*-
"""
Utilidades para gestionar el ciclo de vida de procesos GUI en el SO real.

En Windows 11 algunas aplicaciones (por ejemplo notepad.exe) son "stubs":
el ejecutable que se invoca lanza un proceso independiente y el proceso
inicial termina rapidamente. Como consecuencia:

* subprocess.Popen([exe]).pid devuelve el PID del stub, no el del proceso
  real que muestra la ventana.
* proc.terminate() / proc.kill() sobre el PID del stub no afectan al
  proceso real, que permanece vivo tras el cierre aparente.
* taskkill /PID <pid_stub> /T /F no alcanza al proceso real porque ya no
  es hijo del stub en el momento de invocarlo.

Este modulo ofrece funciones genericas para:

* obtener_pids_por_nombre(nombre): set de PIDs de una imagen en tasklist.
* esperar_pid_nuevo(nombre, pids_referencia, timeout): espera a que aparezca
  un PID que no estaba en pids_referencia y lo devuelve (es el PID real de
  la instancia lanzada por la prueba).
* cerrar_proceso_por_pid(pid): mata un proceso concreto por PID.
* cerrar_procesos_nuevos(nombre, pids_referencia): mata todos los PIDs
  de esa imagen que no estaban en la referencia.

Todas las operaciones se hacen contra el SO real (tasklist / taskkill),
sin mocks, y sin cerrar procesos que ya existieran antes de la prueba
(para no tocar procesos ajenos del usuario).
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional, Set


def obtener_pids_por_nombre(nombre_ejecutable: str) -> Set[int]:
    """Devuelve el conjunto de PIDs activos de una imagen de tasklist."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {nombre_ejecutable}"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: Set[int] = set()
    token = nombre_ejecutable.lower()
    for linea in (resultado.stdout or "").splitlines():
        if token not in linea.lower():
            continue
        partes = linea.split()
        if len(partes) >= 2:
            try:
                pids.add(int(partes[1]))
            except ValueError:
                continue
    return pids


def esperar_pid_nuevo(
    nombre_ejecutable: str,
    pids_referencia: Set[int],
    timeout_segundos: float = 10.0,
    poll_interval: float = 0.25,
) -> Optional[int]:
    """
    Espera a que aparezca un PID de ``nombre_ejecutable`` que no estuviera
    en ``pids_referencia`` y lo devuelve.

    Es util para obtener el PID real del proceso lanzado por una prueba
    cuando el ejecutable es un stub (ej. notepad.exe en Windows 11).

    Retorna None si no aparece ningun PID nuevo dentro del timeout.
    """
    fin = time.time() + timeout_segundos
    while time.time() < fin:
        pids_actuales = obtener_pids_por_nombre(nombre_ejecutable)
        nuevos = pids_actuales - pids_referencia
        if nuevos:
            # Devolver el PID mas pequeno (el mas antiguo de los nuevos,
            # mas probablemente el propio de la prueba).
            return min(nuevos)
        time.sleep(poll_interval)
    return None


def cerrar_proceso_por_pid(pid: int, timeout_segundos: float = 10.0) -> bool:
    """
    Mata un proceso concreto por PID usando taskkill /PID /F.

    Espera hasta ``timeout_segundos`` a que el proceso desaparezca de
    tasklist. Retorna True si el proceso ya no esta vivo, False en caso
    contrario.
    """
    subprocess.run(
        ["taskkill", "/PID", str(int(pid)), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    fin = time.time() + timeout_segundos
    while time.time() < fin:
        if not _pid_esta_vivo(int(pid)):
            return True
        time.sleep(0.25)
    return not _pid_esta_vivo(int(pid))


def cerrar_procesos_nuevos(
    nombre_ejecutable: str,
    pids_referencia: Set[int],
    timeout_segundos: float = 10.0,
) -> Set[int]:
    """
    Mata todos los PIDs de ``nombre_ejecutable`` que no estaban en
    ``pids_referencia`` y devuelve el conjunto de PIDs cerrados.

    Solo cierra procesos que aparecieron despues de la referencia, por lo
    que nunca toca procesos preexistentes del usuario.
    """
    pids_actuales = obtener_pids_por_nombre(nombre_ejecutable)
    nuevos = pids_actuales - pids_referencia
    cerrados: Set[int] = set()
    for pid in nuevos:
        if cerrar_proceso_por_pid(pid, timeout_segundos=timeout_segundos):
            cerrados.add(pid)
    return cerrados


def _pid_esta_vivo(pid: int) -> bool:
    """Devuelve True si el PID sigue apareciendo en tasklist."""
    resultado = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return str(pid) in resultado.stdout
