# -*- coding: ascii -*-
"""
Aplicaciones que trae Windows, identificadas sin depender del idioma.

El menu Inicio, los titulos de ventana y los recursos de version de las
aplicaciones de Windows estan traducidos: en un Windows en ingles la
Calculadora es "Calculator" y en uno en espanol "Calculadora". El usuario puede
pedirla en cualquiera de los dos idiomas sea cual sea el idioma del sistema.

Esta tabla da, para cada aplicacion integrada, sus nombres habituales en
espanol e ingles y los identificadores que NO cambian con el idioma:

- familia de paquete (``Microsoft.WindowsCalculator_8wekyb3d8bbwe``): prefijo
  del AUMID ``Familia!App`` que devuelve Get-StartApps;
- AUMID completos que no siguen ese formato (Explorador de archivos);
- nombre del ejecutable clasico (``calc.exe``, ``notepad.exe``).

Solo amplia la busqueda: no lanza nada ni salta el preflight. No incluye
herramientas que `CalibrationManager` trata como riesgo de elevacion o de
accesibilidad (Administrador de tareas, Lupa, Escritorio remoto...): hacerlas
localizables por nombre ampliaria lo que JARVIS puede abrir. Una aplicacion
de terceros (Chrome, Spotify, Discord...) tiene el mismo nombre en todos los
idiomas y no necesita entrada aqui.

Los nombres se escriben sin tildes (regla ASCII del proyecto) y se comparan
sin tildes ni mayusculas.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


def normalizar_nombre_aplicacion(texto: str) -> str:
    """Minusculas, sin tildes, ``&`` como ``y`` y espacios simples."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto or ""))
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    limpio = sin_tildes.casefold().replace("&", " y ").replace("\u00ae", " ").replace("\u2122", " ")
    return " ".join(limpio.split())


@dataclass(frozen=True)
class AplicacionIntegrada:
    clave: str
    nombres: Tuple[str, ...]
    familias_paquete: Tuple[str, ...] = ()
    aumids: Tuple[str, ...] = ()
    ejecutables: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VariantesBusqueda:
    """Formas equivalentes de una aplicacion integrada para buscarla."""

    clave: str
    nombres: frozenset
    familias_paquete: frozenset
    aumids: frozenset
    ejecutables: frozenset

    def coincide_nombre(self, nombre: str) -> bool:
        return normalizar_nombre_aplicacion(nombre) in self.nombres

    def coincide_app_id(self, app_id: Optional[str]) -> bool:
        valor = str(app_id or "").strip().casefold()
        if not valor:
            return False
        if valor in self.aumids:
            return True
        familia, separador, _app = valor.partition("!")
        return bool(separador) and familia in self.familias_paquete

    def coincide_ejecutable(self, nombre_fichero: str) -> bool:
        return str(nombre_fichero or "").strip().casefold() in self.ejecutables


# Nombres en espanol e ingles (incluidos los nombres anteriores de la misma
# aplicacion en versiones de Windows 10/11). Las familias de paquete y los AUMID
# son los publicados por Microsoft para las aplicaciones de la bandeja de
# entrada de Windows.
APLICACIONES_INTEGRADAS: Tuple[AplicacionIntegrada, ...] = (
    AplicacionIntegrada(
        "notepad", ("bloc de notas", "notepad"),
        familias_paquete=("Microsoft.WindowsNotepad_8wekyb3d8bbwe",),
        ejecutables=("notepad.exe",),
    ),
    AplicacionIntegrada(
        "calculator", ("calculadora", "calculator"),
        familias_paquete=("Microsoft.WindowsCalculator_8wekyb3d8bbwe",),
        ejecutables=("calc.exe",),
    ),
    AplicacionIntegrada(
        "paint", ("paint", "microsoft paint"),
        familias_paquete=("Microsoft.Paint_8wekyb3d8bbwe",),
        ejecutables=("mspaint.exe",),
    ),
    AplicacionIntegrada(
        "explorer", ("explorador de archivos", "explorador", "file explorer", "explorer"),
        aumids=("Microsoft.Windows.Explorer",),
        ejecutables=("explorer.exe",),
    ),
    AplicacionIntegrada(
        "settings", ("configuracion", "settings"),
        familias_paquete=("windows.immersivecontrolpanel_cw5n1h2txyewy",),
    ),
    AplicacionIntegrada(
        "photos", ("fotos", "photos", "microsoft fotos", "microsoft photos"),
        familias_paquete=("Microsoft.Windows.Photos_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "camera", ("camara", "camera"),
        familias_paquete=("Microsoft.WindowsCamera_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "clock", ("reloj", "alarmas y reloj", "clock", "alarms y clock", "alarms and clock"),
        familias_paquete=("Microsoft.WindowsAlarms_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "snipping_tool",
        ("recortes", "herramienta recortes", "recorte y anotacion",
         "snipping tool", "snip y sketch", "snip and sketch"),
        familias_paquete=("Microsoft.ScreenSketch_8wekyb3d8bbwe",),
        ejecutables=("snippingtool.exe",),
    ),
    AplicacionIntegrada(
        "sound_recorder",
        ("grabadora de sonido", "grabadora de voz", "sound recorder", "voice recorder"),
        familias_paquete=("Microsoft.WindowsSoundRecorder_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "store", ("microsoft store", "tienda de microsoft", "store"),
        familias_paquete=("Microsoft.WindowsStore_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "terminal", ("terminal", "terminal de windows", "windows terminal"),
        familias_paquete=("Microsoft.WindowsTerminal_8wekyb3d8bbwe",),
        ejecutables=("wt.exe",),
    ),
    AplicacionIntegrada(
        "sticky_notes", ("notas rapidas", "notas adhesivas", "sticky notes"),
        familias_paquete=("Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "media_player", ("reproductor multimedia", "media player"),
        familias_paquete=("Microsoft.ZuneMusic_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "movies_tv", ("peliculas y tv", "movies y tv", "movies and tv", "films y tv"),
        familias_paquete=("Microsoft.ZuneVideo_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "weather", ("el tiempo", "weather"),
        familias_paquete=("Microsoft.BingWeather_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "maps", ("mapas", "maps"),
        familias_paquete=("Microsoft.WindowsMaps_8wekyb3d8bbwe",),
    ),
    AplicacionIntegrada(
        "control_panel", ("panel de control", "control panel"),
        ejecutables=("control.exe",),
    ),
    AplicacionIntegrada(
        "character_map", ("mapa de caracteres", "character map"),
        ejecutables=("charmap.exe",),
    ),
    AplicacionIntegrada("wordpad", ("wordpad",), ejecutables=("wordpad.exe",)),
    AplicacionIntegrada(
        "windows_media_player",
        ("reproductor de windows media", "windows media player", "windows media player legacy"),
        ejecutables=("wmplayer.exe",),
    ),
    AplicacionIntegrada("edge", ("microsoft edge", "edge"), ejecutables=("msedge.exe",)),
)


def _ejecutables_y_raices(ejecutables: Iterable[str]) -> Tuple[set, set]:
    con_ext = {e.casefold() for e in ejecutables}
    raices = {e[:-4] for e in con_ext if e.endswith(".exe")}
    return con_ext, raices


def variantes_para(nombre: str) -> Optional[VariantesBusqueda]:
    """Variantes de busqueda si ``nombre`` es una aplicacion integrada de Windows.

    Coincide por nombre exacto (sin tildes ni mayusculas) en espanol o ingles,
    o por nombre del ejecutable con o sin ``.exe``. No hay coincidencia
    parcial: "explorer" no debe arrastrar "Internet Explorer".
    """
    buscado = normalizar_nombre_aplicacion(nombre)
    if not buscado:
        return None
    for app in APLICACIONES_INTEGRADAS:
        nombres = {normalizar_nombre_aplicacion(n) for n in app.nombres}
        con_ext, raices = _ejecutables_y_raices(app.ejecutables)
        if buscado in nombres or buscado in con_ext or buscado in raices:
            return VariantesBusqueda(
                clave=app.clave,
                nombres=frozenset(nombres | raices),
                familias_paquete=frozenset(f.casefold() for f in app.familias_paquete),
                aumids=frozenset(a.casefold() for a in app.aumids),
                ejecutables=frozenset(con_ext),
            )
    return None


def familia_de_aumid(aumid: Optional[str]) -> str:
    """Familia de paquete de un AUMID ``Familia!App`` (vacio si no lo es)."""
    valor = str(aumid or "").strip()
    familia, separador, _app = valor.partition("!")
    return familia if separador else ""


def ruta_windows_normalizada(ruta: str) -> str:
    """Ruta en minusculas con separadores ``\\`` (comparacion sin depender del SO).

    Expande variables ``%VAR%`` (el registro App Paths guarda valores como
    ``%windir%\\system32\\notepad.exe``).
    """
    import ntpath

    texto = ntpath.expandvars(str(ruta or "").strip().strip('"'))
    return ntpath.normcase(ntpath.normpath(texto)) if texto else ""


def es_ruta_del_sistema_windows(ruta: str, system_root: Optional[str] = None) -> bool:
    """True si ``ruta`` esta dentro de ``%SystemRoot%`` (``C:\\Windows``)."""
    import os

    normal = ruta_windows_normalizada(ruta)
    if not normal:
        return False
    raiz = ruta_windows_normalizada(system_root or os.environ.get("SystemRoot") or "C:\\Windows")
    return bool(raiz) and normal.startswith(raiz.rstrip("\\") + "\\")
