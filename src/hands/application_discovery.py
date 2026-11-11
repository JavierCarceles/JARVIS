"""
Descubrimiento de aplicaciones reutilizando primero las fuentes existentes del SO.

Unidad 3.8.5.1.4.7.2: localiza destinos de aplicaciones consultando, en orden,
(1) las fuentes de descubrimiento ya existentes (menu de aplicaciones/Get-StartApps,
accesos directos .lnk del menu Inicio, paquetes AppX, registro de desinstaladores,
rutas PATH y App Paths del registro de Windows) y (2), solo para destinos faltantes,
el inventario persistente del sistema de archivos como fuente complementaria.

Este modulo NO lanza aplicaciones, no modifica `data/knowledge/entities.json` ni el
catalogo conocido, y no persiste capacidades inferidas. Toda validacion de destino
se delega en `ApplicationPreflight.validate_launch_destination` (sin lanzar). Es de
lectura sola sobre el equipo.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.hands.application_launch_classifier import (
    CONFIANZA_NINGUNA,
    LaunchClassification,
    LaunchClassifier,
    LaunchType,
)
from src.hands.application_preflight import ApplicationPreflight
from src.hands.calibration_manager import CalibrationManager
from src.hands.system_inventory import EntryType, generate_machine_id
from src.hands.system_inventory_storage import (
    SCAN_MODE_FULL,
    SCAN_RESULT_INTERRUPTED,
    SCAN_RESULT_OK,
    SystemInventoryStorage,
)


def _ahora_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Identificadores de fuente de descubrimiento (reutilizados, no se duplican)
# ---------------------------------------------------------------------------

FUENTE_START_MENU = "start_menu"
FUENTE_APPX = "appx"
FUENTE_UNINSTALL_REGISTRY = "uninstall_registry"
FUENTE_PATH = "path"
FUENTE_APP_PATHS = "app_paths"
FUENTE_INVENTARIO = "inventario"

# Fuentes primarias (se consultan primero, en este orden de prioridad).
FUENTES_PRIMARIAS = (
    FUENTE_START_MENU,
    FUENTE_APPX,
    FUENTE_UNINSTALL_REGISTRY,
    FUENTE_PATH,
    FUENTE_APP_PATHS,
)

# Índice de prioridad: menor número = mayor prioridad al dedupar por destino.
_PRIORIDAD_FUENTE = {fuente: i for i, fuente in enumerate(FUENTES_PRIMARIAS)}
_PRIORIDAD_FUENTE[FUENTE_INVENTARIO] = len(FUENTES_PRIMARIAS)

# Extensiones tratadas como candidatos de lanzamiento al consultar el inventario.
_EXTENSIONS_CANDIDATOS = (".exe", ".lnk")


@dataclass
class DiscoveredCandidate:
    """
    Candidato de aplicación descubierto y clasificado.

    Combina la clasificación de lanzamiento (`LaunchClassification`) con los
    metadatos de descubrimiento propios de esta unidad: de qué fuente provino,
    si estuvo ya en el inventario y la decisión del preflight (sin lanzar).
    """

    candidate_id: str
    name: str
    nombre_comercial: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    absolute_path: Optional[str] = None
    destination: Optional[str] = None
    volume: Optional[str] = None
    launch_type: Optional[str] = None
    launch_subtype: str = "desconocido"
    es_lanzable: bool = False
    evidencia: list[str] = field(default_factory=list)
    confianza: str = CONFIANZA_NINGUNA
    version: Optional[str] = None
    producto: Optional[str] = None
    fuente: str = FUENTE_INVENTARIO
    ultima_comprobacion: str = ""
    razon: str = ""
    requiere_preflight: bool = True
    advertencias: list[str] = field(default_factory=list)

    # Metadatos de descubrimiento (3.8.5.1.4.7.2).
    destino_original: Optional[str] = None
    fuentes_consultadas: list[str] = field(default_factory=list)
    esta_en_inventario: bool = False
    preflight_decision: Optional[dict] = None

    @classmethod
    def from_classification(
        cls,
        clasificacion: LaunchClassification,
        fuente: str,
        destino_original: Optional[str] = None,
        preflight_decision: Optional[dict] = None,
        fuentes_consultadas: Optional[list[str]] = None,
        esta_en_inventario: bool = False,
    ) -> "DiscoveredCandidate":
        return cls(
            candidate_id=clasificacion.candidate_id,
            name=clasificacion.name,
            nombre_comercial=clasificacion.nombre_comercial,
            aliases=list(clasificacion.aliases),
            absolute_path=clasificacion.absolute_path,
            destination=clasificacion.destination,
            volume=clasificacion.volume,
            launch_type=clasificacion.launch_type,
            launch_subtype=clasificacion.launch_subtype.value,
            es_lanzable=clasificacion.es_lanzable,
            evidencia=list(clasificacion.evidencia),
            confianza=clasificacion.confianza,
            version=clasificacion.version,
            producto=clasificacion.producto,
            fuente=fuente,
            ultima_comprobacion=clasificacion.ultima_comprobacion,
            razon=clasificacion.razon,
            requiere_preflight=clasificacion.requiere_preflight,
            advertencias=list(clasificacion.advertencias),
            destino_original=destino_original,
            fuentes_consultadas=list(fuentes_consultadas or []),
            esta_en_inventario=esta_en_inventario,
            preflight_decision=dict(preflight_decision) if preflight_decision else None,
        )

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "nombre_comercial": self.nombre_comercial,
            "aliases": list(self.aliases),
            "absolute_path": self.absolute_path,
            "destination": self.destination,
            "volume": self.volume,
            "launch_type": self.launch_type,
            "launch_subtype": self.launch_subtype,
            "es_lanzable": self.es_lanzable,
            "evidencia": list(self.evidencia),
            "confianza": self.confianza,
            "version": self.version,
            "producto": self.producto,
            "fuente": self.fuente,
            "ultima_comprobacion": self.ultima_comprobacion,
            "razon": self.razon,
            "requiere_preflight": self.requiere_preflight,
            "advertencias": list(self.advertencias),
            "destino_original": self.destino_original,
            "fuentes_consultadas": list(self.fuentes_consultadas),
            "esta_en_inventario": self.esta_en_inventario,
            "preflight_decision": self.preflight_decision,
        }


# ---------------------------------------------------------------------------
# Orquestador de descubrimiento
# ---------------------------------------------------------------------------

class ApplicationDiscovery:
    """
    Descubre aplicaciones reutilizando primero las fuentes existentes del SO.

    El inventario persistente solo se consulta como fuente complementaria para
    localizar destinos que no aparecieron en las fuentes primarias. Nada se
    lanza, nada se modifica en el catalogo conocido y nada se infiere como
    capacidad confirmada.
    """

    def __init__(
        self,
        preflight: Optional[ApplicationPreflight] = None,
        clasificador: Optional[LaunchClassifier] = None,
        storage: Optional[SystemInventoryStorage] = None,
        calibration: Optional[CalibrationManager] = None,
        machine_id: Optional[str] = None,
    ) -> None:
        self.preflight = preflight or ApplicationPreflight()
        # El clasificador ya valida con preflight internamente (.7.10).
        self.clasificador = clasificador or LaunchClassifier(preflight=self.preflight)
        self.storage = storage or SystemInventoryStorage()
        self.calibration = calibration or CalibrationManager()
        self.machine_id = machine_id or generate_machine_id()

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def descubrir_todos(
        self,
        limite_por_fuente: int = 50,
        incluir_inventario: bool = True,
    ) -> list[DiscoveredCandidate]:
        """
        Devuelve candidatos de aplicaciones descubiertos.

        Orden de consulta: primero las fuentes primarias existentes del SO
        (menu de aplicaciones, paquetes, registro, accesos directos, PATH,
        App Paths) y, solo para destinos faltantes, el inventario persistente.

        Parametros:
        - limite_por_fuente: tope de candidatos leidos de cada fuente
          (evita lecturas ilimitadas del equipo).
        - incluir_inventario: si True, complementa con el inventario los
          destinos no cubiertos por las fuentes primarias.

        No lanza aplicaciones, no modifica entities.json ni el catalogo conocido.
        """
        fuentes_consultadas: list[str] = []

        # 1) Fuentes primarias existentes (reutilizadas, no se duplican).
        primarios = self._fuentes_primarias(limite_por_fuente)
        for fuente in FUENTES_PRIMARIAS:
            if any(str(p.get("source", "")).casefold() == fuente for p in primarios):
                fuentes_consultadas.append(fuente)

        # Dedup por destino real antes de clasificar (evita trabajo duplicado y
        # conserva la fuente de mayor prioridad para cada destino).
        primarios_unicos = self._dedup_por_destino(primarios)

        descubiertos = self._clasificar_y_validar(
            primarios_unicos, fuentes_consultadas=list(fuentes_consultadas)
        )

        # 2) Complemento de inventario solo para destinos faltantes.
        if incluir_inventario:
            nombres_cubiertos = {
                str(c.name or "").casefold() for c in descubiertos if c.name
            }
            destinos_cubiertos = {
                str(c.destination or "").casefold() for c in descubiertos if c.destination
            }
            complemento = self._complemento_inventario(
                nombres_cubiertos,
                destinos_cubiertos,
                limite_por_fuente,
                fuentes_consultadas=list(fuentes_consultadas),
            )
            descubiertos.extend(complemento)

        descubiertos.sort(
            key=lambda c: (
                {"alta": 3, "media": 2, "baja": 1, "ninguna": 0}.get(c.confianza, 0),
                len(c.evidencia),
            ),
            reverse=True,
        )
        return descubiertos

    def buscar_por_nombre(
        self,
        nombre: str,
        incluir_inventario: bool = True,
        limite_por_fuente: int = 50,
    ) -> list[DiscoveredCandidate]:
        """
        Busca candidatos por nombre. Consulta primero las fuentes primarias y,
        solo si no hay coincidencias, el inventario como fuente complementaria
        para localizar destinos faltantes (.7.2).
        """
        if not nombre or not isinstance(nombre, str):
            return []
        nombre = nombre.strip()
        if not nombre:
            return []

        nombre_lower = nombre.casefold()
        fuentes_consultadas: list[str] = []

        primarios = self._fuentes_primarias(limite_por_fuente)
        for fuente in FUENTES_PRIMARIAS:
            if any(str(p.get("source", "")).casefold() == fuente for p in primarios):
                fuentes_consultadas.append(fuente)

        coincidencias = [
            p
            for p in primarios
            if nombre_lower in str(p.get("name", "")).casefold()
        ]
        if coincidencias:
            coincidencias_unicas = self._dedup_por_destino(coincidencias)
            return self._clasificar_y_validar(
                coincidencias_unicas, fuentes_consultadas=fuentes_consultadas
            )

        if not incluir_inventario:
            return []

        # Fuentes primarias sin coincidencia: el inventario es la fuente
        # complementaria para localizar el destino faltante.
        try:
            self.storage.connect()
            entradas = self.storage.search(
                machine_id=self.machine_id,
                name=nombre,
                extension=".exe",
                tipo=EntryType.FILE.value,
                disponible=True,
                limit=limite_por_fuente,
                solo_volumes_montados=True,
            )
        except (OSError, PermissionError, sqlite3.Error):
            return []
        except Exception:
            return []
        finally:
            try:
                self.storage.close()
            except Exception:
                pass

        if not entradas:
            return []

        candidatos = [
            {
                "candidate_id": str(e.get("absolute_path", "")),
                "name": str(e.get("name", "")),
                "absolute_path": str(e.get("absolute_path", "")),
                "source": FUENTE_INVENTARIO,
                "volume": str(e.get("volume", "")) or None,
                "last_checked_at": str(e.get("last_checked_at", "")),
            }
            for e in entradas
        ]
        return self._clasificar_y_validar(
            candidatos,
            fuente_defecto=FUENTE_INVENTARIO,
            fuentes_consultadas=list(fuentes_consultadas) + [FUENTE_INVENTARIO],
            esta_en_inventario=True,
        )

    def candidatos_lanzables(
        self,
        limite_por_fuente: int = 50,
        incluir_inventario: bool = True,
    ) -> list[DiscoveredCandidate]:
        """
        Devuelve solo los candidatos clasificados como lanzables
        (`es_lanzable == True`), tras validar el destino con preflight
        (sin lanzar nada).
        """
        return [
            c
            for c in self.descubrir_todos(
                limite_por_fuente=limite_por_fuente,
                incluir_inventario=incluir_inventario,
            )
            if c.es_lanzable
        ]

    def registrar_candidatos(
        self,
        candidatos: list[DiscoveredCandidate],
        volume: str,
        scan_id: Optional[str] = None,
    ) -> int:
        """Persiste una lista de candidatos clasificados en `application_candidates`.

        Registra de forma duradera, por cada candidato: fuente, ruta/destino,
        tipo de lanzamiento, version/producto si existe, ultima comprobacion,
        evidencia y nivel de confianza (unidad 3.8.5.1.4.7.6).

        Gestiona el ciclo de vida del escaneo (begin_scan_run / end_scan_run)
        para que la insercion sea atomica y el bloqueo de concurrencia se
        libere al finalizar.

        Parametros:
        - candidatos: lista de `DiscoveredCandidate` a registrar.
        - volume: volumen de destino para el escaneo de registro.
        - scan_id: identificador de escaneo opcional; si no se proporciona,
          se genera uno nuevo.

        Retorna:
        Numero de candidatos insertados.
        """
        if not candidatos:
            return 0
        self.storage.connect()
        self.storage.record_machine(self.machine_id)
        scan = scan_id or f"registro-{uuid.uuid4()}"
        ahora = _ahora_iso()
        try:
            self.storage.begin_scan_run(
                scan_id=scan,
                machine_id=self.machine_id,
                volume=volume,
                mode=SCAN_MODE_FULL,
                started_at=ahora,
            )
            filas = [
                {
                    "candidate_id": c.candidate_id,
                    "name": c.name,
                    "absolute_path": c.absolute_path,
                    "launch_type": c.launch_type,
                    "confidence": c.confianza,
                    "version": c.version,
                    "producto": c.producto,
                    "evidencia": c.evidencia,
                    "source": c.fuente,
                    "last_checked_at": c.ultima_comprobacion,
                }
                for c in candidatos
            ]
            insertados = self.storage.insert_application_candidates(
                scan_id=scan,
                machine_id=self.machine_id,
                volume=volume,
                candidates=filas,
            )
            self.storage.end_scan_run(
                scan_id=scan,
                finished_at=ahora,
                result=SCAN_RESULT_OK,
                entries_count=insertados,
            )
            return insertados
        except Exception:
            try:
                self.storage.end_scan_run(
                    scan_id=scan,
                    finished_at=_ahora_iso(),
                    result=SCAN_RESULT_INTERRUPTED,
                    entries_count=0,
                )
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------ #
    # Fuentes primarias existentes (reutilizadas)
    # ------------------------------------------------------------------ #

    def _fuentes_primarias(self, limite_por_fuente: int) -> list[dict[str, Any]]:
        """
        Recolecta candidatos de las fuentes de descubrimiento existentes del SO,
        en orden: menu de aplicaciones (Get-StartApps, .lnk, AppX, registro de
        desinstaladores), rutas PATH y App Paths del registro.

        Cada fuente se lee de forma independiente y resiliente: el fallo de una
        no interrumpe las demas.
        """
        recolectados: list[dict[str, Any]] = []

        # 1) CalibrationManager: menu de aplicaciones, .lnk menu Inicio,
        #    paquetes AppX y registro de desinstaladores (fuente existente).
        try:
            apps = self.calibration.discover_applications() or []
            for app in apps[:limite_por_fuente]:
                nombre = str(app.get("name", "")).strip()
                path = str(app.get("path", "")).strip()
                fuente_app = str(app.get("source", "")).strip().casefold()
                if fuente_app in ("start_menu", "menu_inicio"):
                    fuente = FUENTE_START_MENU
                elif fuente_app == "appx":
                    fuente = FUENTE_APPX
                elif fuente_app == "uninstall_registry":
                    fuente = FUENTE_UNINSTALL_REGISTRY
                else:
                    fuente = fuente_app or FUENTE_START_MENU
                if nombre:
                    recolectados.append(
                        {
                            "candidate_id": path or nombre,
                            "name": nombre,
                            "absolute_path": path or None,
                            "destination": path or None,
                            "source": fuente,
                            "app_id": str(app.get("app_id", "")).strip() or None,
                            "arguments": str(app.get("arguments", "")).strip() or None,
                            "volume": self._volumen_de(path) if path else None,
                        }
                    )
        except Exception:
            # La fuente de menu de aplicaciones no esta disponible; se sigue
            # con PATH y App Paths.
            pass

        # 2) Rutas registradas en PATH (primera capa de cada carpeta, sin
        #    busqueda recursiva por el disco, segun diseno 3.8.1.4).
        try:
            raw_path = os.environ.get("PATH", "")
            dirs = [d for d in raw_path.split(os.pathsep) if d]
            vistos_exe: set[str] = set()
            for directory in dirs:
                if not os.path.isdir(directory):
                    continue
                try:
                    for entry in os.listdir(directory):
                        if not entry.lower().endswith(".exe"):
                            continue
                        ruta = os.path.join(directory, entry)
                        clave = os.path.normcase(os.path.abspath(ruta))
                        if clave in vistos_exe:
                            continue
                        vistos_exe.add(clave)
                        if len(recolectados) >= limite_por_fuente * 2:
                            break
                        recolectados.append(
                            {
                                "candidate_id": ruta,
                                "name": entry,
                                "absolute_path": ruta,
                                "destination": ruta,
                                "source": FUENTE_PATH,
                                "volume": self._volumen_de(ruta),
                            }
                        )
                except (OSError, PermissionError):
                    continue
                if len(recolectados) >= limite_por_fuente * 2:
                    break
        except Exception:
            pass

        # 3) App Paths del registro de Windows (HKCU y HKLM).
        if os.name == "nt":
            try:
                import winreg  # type: ignore

                raices = [
                    (0x80000001, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),  # HKEY_CURRENT_USER
                    (0x80000002, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),  # HKEY_LOCAL_MACHINE
                ]
                for hive, root in raices:
                    try:
                        with winreg.OpenKey(hive, root) as key:
                            index = 0
                            while True:
                                try:
                                    exe_name = winreg.EnumKey(key, index)
                                except OSError:
                                    break
                                index += 1
                                try:
                                    with winreg.OpenKey(key, exe_name) as subkey:
                                        path, _ = winreg.QueryValueEx(subkey, "")
                                except OSError:
                                    path = ""
                                if path and len(recolectados) < limite_por_fuente * 2:
                                    recolectados.append(
                                        {
                                            "candidate_id": path,
                                            "name": exe_name,
                                            "absolute_path": path,
                                            "destination": path,
                                            "source": FUENTE_APP_PATHS,
                                            "volume": self._volumen_de(path),
                                        }
                                    )
                    except OSError:
                        continue
            except Exception:
                pass

        return recolectados

    @staticmethod
    def _dedup_por_destino(
        candidatos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Deduplica candidatos por destino real (ruta normalizada o URI), no solo
        por nombre. Para cada destino conserva la fuente de mayor prioridad.
        Las instalaciones distintas con rutas distintas se conservan todas.
        """
        mejores: dict[str, dict[str, Any]] = {}
        sueltos: list[dict[str, Any]] = []
        for c in candidatos:
            destino = c.get("destination") or c.get("absolute_path")
            fuente = str(c.get("source", "")).strip()
            clave = _clave_destino(destino)
            if clave is None:
                sueltos.append(c)
                continue
            existente = mejores.get(clave)
            if existente is None:
                mejores[clave] = c
            else:
                prioridad_nueva = _PRIORIDAD_FUENTE.get(fuente, 99)
                prioridad_vieja = _PRIORIDAD_FUENTE.get(
                    str(existente.get("source", "")).strip(), 99
                )
                if prioridad_nueva < prioridad_vieja:
                    mejores[clave] = c
        return list(mejores.values()) + sueltos

    # ------------------------------------------------------------------ #
    # Complemento de inventario (fuente complementaria, solo faltantes)
    # ------------------------------------------------------------------ #

    def _complemento_inventario(
        self,
        nombres_cubiertos: set[str],
        destinos_cubiertos: set[str],
        limite_por_fuente: int,
        fuentes_consultadas: list[str],
    ) -> list[DiscoveredCandidate]:
        """
        Consulta el inventario persistente como fuente complementaria para
        localizar destinos faltantes: candidatos .exe/.lnk cuyo nombre o destino
        no fue cubierto por las fuentes primarias.

        Lectura sola; no modifica la base de datos del inventario.
        """
        try:
            self.storage.connect()
        except Exception:
            return []

        try:
            candidatos_raw: list[dict[str, Any]] = []
            for ext in _EXTENSIONS_CANDIDATOS:
                try:
                    entradas = self.storage.search(
                        machine_id=self.machine_id,
                        extension=ext,
                        tipo=EntryType.FILE.value,
                        disponible=True,
                        limit=limite_por_fuente,
                        solo_volumes_montados=True,
                    )
                except Exception:
                    continue
                for e in entradas:
                    nombre = str(e.get("name", "")).casefold()
                    destino = str(e.get("absolute_path", "")).casefold()
                    if nombre in nombres_cubiertos or destino in destinos_cubiertos:
                        continue
                    candidatos_raw.append(
                        {
                            "candidate_id": str(e.get("absolute_path", "")),
                            "name": str(e.get("name", "")),
                            "absolute_path": str(e.get("absolute_path", "")),
                            "destination": str(e.get("absolute_path", "")),
                            "source": FUENTE_INVENTARIO,
                            "volume": str(e.get("volume", "")) or None,
                            "last_checked_at": str(e.get("last_checked_at", "")),
                        }
                    )
                    if len(candidatos_raw) >= limite_por_fuente:
                        break
                if len(candidatos_raw) >= limite_por_fuente:
                    break
        finally:
            try:
                self.storage.close()
            except Exception:
                pass

        if not candidatos_raw:
            return []

        return self._clasificar_y_validar(
            candidatos_raw,
            fuente_defecto=FUENTE_INVENTARIO,
            fuentes_consultadas=list(fuentes_consultadas) + [FUENTE_INVENTARIO],
            esta_en_inventario=True,
        )

    # ------------------------------------------------------------------ #
    # Clasificacion y validacion (sin lanzar)
    # ------------------------------------------------------------------ #

    def _clasificar_y_validar(
        self,
        candidatos: list[dict[str, Any]],
        fuente_defecto: Optional[str] = None,
        fuentes_consultadas: Optional[list[str]] = None,
        esta_en_inventario: bool = False,
    ) -> list[DiscoveredCandidate]:
        """
        Clasifica cada candidato con `LaunchClassifier` y valida su destino con
        `ApplicationPreflight.validate_launch_destination` (sin lanzar).

        `fuente_defecto` se usa cuando el candidato no trae fuente propia.
        """
        descubiertos: list[DiscoveredCandidate] = []
        fuentes = list(fuentes_consultadas or [])
        for c in candidatos:
            destino = c.get("absolute_path") or c.get("destination")
            fuente = str(c.get("source", "") or fuente_defecto or FUENTE_INVENTARIO).strip()

            clasificacion = self.clasificador.classify_candidate(c)

            # Validacion de destino con preflight (solo lectura, no lanza).
            preflight_decision: Optional[dict] = None
            if clasificacion.destination:
                try:
                    preflight_decision = self.clasificador.validar_destino_antes_de_lanzar(
                        clasificacion.destination
                    )
                except Exception:
                    preflight_decision = {
                        "valid": False,
                        "launch_type": None,
                        "destination": clasificacion.destination,
                        "reason": "Error al validar destino con preflight",
                    }

            descubiertos.append(
                DiscoveredCandidate.from_classification(
                    clasificacion,
                    fuente=fuente,
                    destino_original=destino,
                    preflight_decision=preflight_decision,
                    fuentes_consultadas=list(fuentes),
                    esta_en_inventario=esta_en_inventario,
                )
            )
        return descubiertos

    # ------------------------------------------------------------------ #
    # Deduplicacion por identidad y destino real (.7.7)
    # ------------------------------------------------------------------ #

    def _clave_destino_candidato(self, c: DiscoveredCandidate) -> Optional[str]:
        """Clave de deduplicacion para un candidato ya clasificado:
        ruta normalizada si existe en disco, o la URI para tipos sin archivo."""
        destino = c.destination
        launch_type = c.launch_type
        if not destino or not isinstance(destino, str):
            return None
        d = destino.strip()
        if not d:
            return None
        if launch_type in (
            LaunchType.URI_APLICACION.value,
            LaunchType.LANZADOR.value,
        ):
            return d.casefold()
        if ":" in d and not _es_ruta_windows(d):
            return d.casefold()
        if not os.path.exists(d):
            return None
        try:
            return os.path.normcase(os.path.abspath(d))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _puntos_confianza(confianza: str) -> int:
        return {
            "alta": 3,
            "media": 2,
            "baja": 1,
            "ninguna": 0,
        }.get(confianza or "ninguna", 0)

    def deduplicar_por_destino_real(
        self, candidatos: list[DiscoveredCandidate]
    ) -> list[DiscoveredCandidate]:
        """
        Deduplica una lista de `DiscoveredCandidate` ya clasificados por
        identidad y destino real, no solo por nombre (.7.7).

        Requisitos:
        - Mismo destino real (ruta normalizada o URI): se conserva el
          candidato con mayor confianza y, en caso de empate, mayor evidencia.
          No se fusionan instalaciones distintas.
        - Rutas distintas (instalaciones distintas): se conservan todas.
        - Candidatos sin destino identificable se conservan como sueltos.
        - El resultado queda ordenado por confianza descendente y evidencia.
        """
        grupos: dict[str, list[DiscoveredCandidate]] = {}
        sueltos: list[DiscoveredCandidate] = []
        for c in candidatos:
            clave = self._clave_destino_candidato(c)
            if clave is None:
                sueltos.append(c)
            else:
                grupos.setdefault(clave, []).append(c)

        resultado: list[DiscoveredCandidate] = []
        for clave, grupo in grupos.items():
            mejor = max(
                grupo,
                key=lambda c: (self._puntos_confianza(c.confianza), len(c.evidencia)),
            )
            resultado.append(mejor)
        resultado.extend(sueltos)

        resultado.sort(
            key=lambda c: (
                self._puntos_confianza(c.confianza),
                len(c.evidencia),
            ),
            reverse=True,
        )
        return resultado

    # ------------------------------------------------------------------ #
    # Utilidades
    # ------------------------------------------------------------------ #

    @staticmethod
    def _volumen_de(ruta: Optional[str]) -> Optional[str]:
        if not ruta:
            return None
        try:
            p = Path(ruta)
            if os.name == "nt":
                drive = p.drive
                return drive.upper() if drive else None
            return str(p.anchor)
        except (OSError, ValueError):
            return None


def _clave_destino(destino: Optional[str]) -> Optional[str]:
    """Clave de deduplicacion: ruta normalizada si existe en disco, o la URI."""
    if not destino or not isinstance(destino, str):
        return None
    d = destino.strip()
    if not d:
        return None
    # URIs: clave casefold del esquema+ruta (no hay archivo en disco).
    if ":" in d and not _es_ruta_windows(d):
        return d.casefold()
    if not os.path.exists(d):
        return None
    try:
        return os.path.normcase(os.path.abspath(d))
    except (OSError, ValueError):
        return None


def _es_ruta_windows(valor: Optional[str]) -> bool:
    if not valor or not isinstance(valor, str):
        return False
    v = valor.strip()
    if v.startswith("\\\\"):
        return True
    return len(v) >= 2 and v[0].isalpha() and v[1] == ":"
