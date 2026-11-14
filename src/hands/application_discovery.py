"""
Descubrimiento de aplicaciones reutilizando primero las fuentes existentes del SO.

Unidad 3.8.5.1.4.7.2: localiza destinos de aplicaciones consultando, en orden,
(1) las fuentes de descubrimiento ya existentes (menu de aplicaciones/Get-StartApps,
accesos directos .lnk del menu Inicio, paquetes AppX, registro de desinstaladores,
rutas PATH y App Paths del registro de Windows) y (2), solo para destinos faltantes,
el inventario persistente del sistema de archivos como fuente complementaria.

Unidad 3.8.5.1.4.9.7: antes de consultar el inventario se verifica que este
pertenezca al equipo actual (`verificar_aislamiento_inventario`, delegado en
`SystemInventoryStorage.verificar_identidad_equipo`). Si la base de datos del
inventario se copio a otro equipo (host distinto), no se consultan ni se usan
los destinos del inventario y se senaliza que se exige reescaneo antes de
usarlos (`inventario_requiere_reescaneo`). `record_machine` nunca mezcla
identidades de equipos distintos en una misma base.

Este modulo NO lanza aplicaciones, no modifica `data/knowledge/entities.json` y sus
operaciones de descubrimiento son de lectura sola sobre el equipo. A partir de la
unidad 3.8.5.1.4.11, `auto_registrar_descubiertos` escribe en el catalogo global
`data/memory/entities.json` (upsert por ID estable, idempotente; sin tocar
`data/knowledge/entities.json`, sin lanzar aplicaciones y sin pedir alta manual).
Toda validacion de destino se delega en `ApplicationPreflight.validate_launch_destination`
(sin lanzar).
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from src.hands.application_launch_classifier import (
    CONFIANZA_NINGUNA,
    LaunchClassification,
    LaunchClassifier,
    LaunchType,
    leer_version_archivo_windows,
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
from src.memory.storage import Entity


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

# Fuentes de resolución de mayor precedencia (no duplican mecanismos existentes;
# se reutilizan ApplicationManager y la detección de procesos del SO).
FUENTE_CATALOGO = "catalogo_conocido"          # ApplicationManager / conocimiento estructurado
FUENTE_APLICACION_ABIERTA = "aplicacion_abierta"  # proceso ya en ejecución detectado en el SO

# Fuentes primarias (se consultan primero, en este orden de prioridad).
FUENTES_PRIMARIAS = (
    FUENTE_START_MENU,
    FUENTE_APPX,
    FUENTE_UNINSTALL_REGISTRY,
    FUENTE_PATH,
    FUENTE_APP_PATHS,
)

# Orden de precedencia de fuentes para resolución por nombre (3.8.5.1.4.9.2).
# Menor número = mayor precedencia. Una aplicación ya abierta tiene la máxima
# precedencia, seguida del catálogo conocido, luego las fuentes nativas
# instaladas y, por último, los candidatos del inventario.
_PRECEDENCIA_FUENTE = {
    FUENTE_APLICACION_ABIERTA: 0,
    FUENTE_CATALOGO: 1,
    FUENTE_START_MENU: 2,
    FUENTE_APPX: 3,
    FUENTE_UNINSTALL_REGISTRY: 4,
    FUENTE_PATH: 5,
    FUENTE_APP_PATHS: 6,
    FUENTE_INVENTARIO: 7,
}

# Fuentes cuya resolución se considera autoritativa para un nombre: una
# aplicación ya abierta en el SO o una entrada del catálogo conocido deciden
# de forma inequívoca y no generan ambigüedad por sí solas (3.8.5.1.4.9.2).
_FUENTES_AUTORITATIVAS = {FUENTE_APLICACION_ABIERTA, FUENTE_CATALOGO}

# Índice de prioridad legado: menor número = mayor prioridad al dedupar por destino.
# Se mantiene por compatibilidad; _PRECEDENCIA_FUENTE es la fuente de verdad.
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
    preflight_policy: Optional[dict] = None
    disponible: bool = True

    @classmethod
    def from_classification(
        cls,
        clasificacion: LaunchClassification,
        fuente: str,
        destino_original: Optional[str] = None,
        preflight_decision: Optional[dict] = None,
        preflight_policy: Optional[dict] = None,
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
            preflight_policy=dict(preflight_policy) if preflight_policy else None,
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
            "preflight_policy": self.preflight_policy,
            "disponible": self.disponible,
        }


@dataclass
class ResultadoResolucionCandidatos:
    """
    Resultado de la resolución de candidatos por nombre con señal de ambigüedad
    (3.8.5.1.4.9.3).

    Cuando existen varias coincidencias plausibles para un mismo nombre y la
    evidencia no permite elegir una de forma inequívoca, ``ambiguo`` es True,
    ``requiere_desambiguacion`` es True y ``alternativas`` conserva todos los
    candidatos para que el llamador solicite desambiguación al usuario en lugar
    de elegir silenciosamente uno posiblemente incorrecto. Ninguna aplicación
    se lanza ni se modifica el catálogo conocido como consecuencia de este
    resultado.
    """

    candidatos: list[DiscoveredCandidate]
    ambiguo: bool
    motivo_ambiguedad: Optional[str]
    alternativas: list[DiscoveredCandidate]
    requiere_desambiguacion: bool
    fuente_autoritaria: Optional[str]

    def to_dict(self) -> dict:
        return {
            "candidatos": [c.to_dict() for c in self.candidatos],
            "ambiguo": self.ambiguo,
            "motivo_ambiguedad": self.motivo_ambiguedad,
            "alternativas": [c.to_dict() for c in self.alternativas],
            "requiere_desambiguacion": self.requiere_desambiguacion,
            "fuente_autoritaria": self.fuente_autoritaria,
        }


@dataclass
class CandidatoConCatalogo:
    """
    Resultado de vincular un `DiscoveredCandidate` con el catálogo global de
    aplicaciones (`ApplicationManager` / `data/memory/entities.json`) sin
    modificarlo.

    Mantiene separados los conceptos de la unidad 3.8.5.1.4.9.5: el archivo
    inventariado (origen del candidato), el propio candidato descubierto, la
    entidad global del catálogo (si existe) y su `ApplicationKnowledge`, y el
    destino autorizado (validado por `ApplicationPreflight`, sin lanzar). No
    lanza aplicaciones, no escribe en `entities.json` ni registra ni
    auto-registra candidatos (el puente de auto-registro corresponde a
    3.8.5.1.4.11) y no crea rutas paralelas de Brain/Planner/Executor.
    """

    candidato: DiscoveredCandidate
    en_catalogo_global: bool
    conocimiento: Optional[Any]
    fuente_autoritaria: Optional[str]

    def to_dict(self) -> dict:
        conocimiento = None
        if self.conocimiento is not None:
            conocimiento = {
                "name": self.conocimiento.name,
                "type": self.conocimiento.type,
                "executable": self.conocimiento.executable,
                "url": self.conocimiento.url,
                "login_required": self.conocimiento.login_required,
                "default_state": self.conocimiento.default_state.value,
                "capabilities": [
                    cap.capability.value for cap in (self.conocimiento.capabilities or [])
                ],
            }
        return {
            "candidato": self.candidato.to_dict(),
            "en_catalogo_global": self.en_catalogo_global,
            "conocimiento": conocimiento,
            "fuente_autoritaria": self.fuente_autoritaria,
        }


# ---------------------------------------------------------------------------
# Identidad global estable (unidad 3.8.5.1.4.11.2)
# ---------------------------------------------------------------------------

_TIPO_EVIDENCIA_PAQUETE = "paquete"
_TIPO_EVIDENCIA_FABRICANTE_PRODUCTO = "fabricante_producto"
_TIPO_EVIDENCIA_NOMBRE_COMERCIAL = "nombre_comercial"
_TIPO_EVIDENCIA_INSUFICIENTE = "insuficiente"

_PREFIJO_ENTIDAD_PAQUETE = "paquete"
_PREFIJO_ENTIDAD_FABRICANTE_PRODUCTO = "fabprod"
_PREFIJO_ENTIDAD_NOMBRE = "nombre"
_PREFIJO_ENTIDAD_CANDIDATO = "candidato"


def _normalizar_texto_identidad(texto: Optional[str]) -> str:
    """Normaliza texto para usarlo como base de identidad estable.

    Aplica minusculas, recorta extremos, colapsa espacios interiores y elimina
    caracteres no alfanumericos. Nunca incluye rutas absolutas ni datos que
    puedan cambiar entre maquinas.
    """
    if not texto or not isinstance(texto, str):
        return ""
    normalizado = re.sub(r"\s+", " ", texto.strip()).lower()
    normalizado = re.sub(r"[^a-z0-9\s]", "", normalizado)
    return normalizado.strip()


@dataclass
class IdentidadGlobalEstable:
    """
    Identidad global estable de una aplicacion descubierta (3.8.5.1.4.11.2).

    La identidad se establece por evidencia estable disponible, en este orden
    de precedencia:

      1. identificador de paquete / AUMID (evidencia de aporte de fuente de
         descubrimiento, ej. catalogo de paquetes o registro de
         desinstaladores);
      2. fabricante + producto (metadatos de recursos de version del
         ejecutable, leidos del sistema operativo);
      3. nombre comercial normalizado (evidencia mas debil: por si sola no
         justifica fusionar entidades);
      4. insuficiente: no hay evidencia estable, el candidato se conserva
         separado con sus alternativas y no se fusiona por nombre.

    La ruta absoluta nunca es base de la identidad global: puede cambiar entre
    maquinas y no se usa para construir el ``entity_id``.
    """

    entity_id: str
    nombre_canonico: str
    tipo_evidencia: str
    evidencia_base: dict
    confianza: str
    fusionar_por_nombre_desaconsejado: bool
    alternativas: list


def _extraer_evidencia_identidad(candidato: DiscoveredCandidate) -> dict:
    """Extrae evidencia de identidad estable de un candidato descubierto.

    Lee metadatos verificables observados (identificador de paquete/AUMID
    cuando una fuente de descubrimiento lo aporta, fabricante y producto de los
    recursos de version del ejecutable, nombre comercial y version) sin
    basarse en la ruta absoluta como identidad.
    """
    evidencia: dict[str, Any] = {}
    nombre_comercial = str(candidato.nombre_comercial or "").strip()

    # Lectura real de recursos de version del ejecutable (CompanyName,
    # ProductName, versiones) cuando el destino existe en el equipo.
    ruta = str(candidato.absolute_path or "").strip()
    version_info: Optional[dict] = None
    if ruta and os.path.isfile(ruta):
        version_info = leer_version_archivo_windows(ruta)

    if version_info:
        if version_info.get("ProductName"):
            evidencia["nombre_comercial"] = version_info["ProductName"]
            nombre_comercial = str(version_info["ProductName"]).strip()
        if version_info.get("CompanyName"):
            evidencia["fabricante"] = str(version_info["CompanyName"]).strip()
        version = version_info.get("ProductVersion") or version_info.get("FileVersion")
        if version:
            evidencia["version"] = str(version).strip()
        evidencia["version_recurso_leida"] = True
    elif nombre_comercial:
        evidencia["nombre_comercial"] = nombre_comercial

    # Datos ya observados por el clasificador.
    if (
        candidato.producto
        and str(candidato.producto).strip()
        and str(candidato.producto).strip().lower() != nombre_comercial.lower()
    ):
        evidencia.setdefault("fabricante", str(candidato.producto).strip())
    if candidato.producto and str(candidato.producto).strip():
        evidencia.setdefault("producto", str(candidato.producto).strip())
    if candidato.version:
        evidencia.setdefault("version", str(candidato.version).strip())

    # Identificador de paquete / AUMID aportado por alguna fuente de descubrimiento.
    for item in candidato.evidencia:
        if isinstance(item, str) and item.startswith("paquete_id:"):
            evidencia["paquete_id"] = item[len("paquete_id:"):].strip()
            break

    evidencia["fuentes"] = list(
        dict.fromkeys([str(candidato.fuente or "")] + list(candidato.fuentes_consultadas or []))
    )
    return evidencia


def calcular_identidad_estable(candidato: DiscoveredCandidate) -> IdentidadGlobalEstable:
    """
    Calcula la identidad global estable de un candidato (3.8.5.1.4.11.2).

    Precedencia de evidencia estable:
      1. paquete_id / AUMID (maxima estabilidad, independiente de la ruta);
      2. fabricante + producto (estable, independiente de la ruta de instalacion);
      3. nombre comercial normalizado (evidencia mas debil: no fusiona entidades
         por nombre solo; se mantienen separadas con alternativas);
      4. insuficiente: sin evidencia estable, el candidato se conserva separado.

    Nunca se usa la ruta absoluta como base de la identidad global.
    """
    evidencia = _extraer_evidencia_identidad(candidato)
    nombre_canonico = _normalizar_texto_identidad(
        candidato.nombre_comercial or candidato.name or ""
    )
    confianza = str(candidato.confianza or CONFIANZA_NINGUNA)
    nombre_normalizado = _normalizar_texto_identidad(candidato.name or "")

    # 1. Identificador de paquete / AUMID: maxima estabilidad.
    paquete_id = str(evidencia.get("paquete_id", "")).strip()
    if paquete_id:
        return IdentidadGlobalEstable(
            entity_id=f"{_PREFIJO_ENTIDAD_PAQUETE}:{paquete_id}",
            nombre_canonico=nombre_canonico or nombre_normalizado,
            tipo_evidencia=_TIPO_EVIDENCIA_PAQUETE,
            evidencia_base=evidencia,
            confianza=confianza,
            fusionar_por_nombre_desaconsejado=False,
            alternativas=[],
        )

    # 2. Fabricante + producto: estable e independiente de la ruta de instalacion.
    fabricante = str(evidencia.get("fabricante", "")).strip()
    producto = str(evidencia.get("producto", "")).strip()
    if fabricante and producto:
        return IdentidadGlobalEstable(
            entity_id=(
                f"{_PREFIJO_ENTIDAD_FABRICANTE_PRODUCTO}:"
                f"{_normalizar_texto_identidad(fabricante)}:"
                f"{_normalizar_texto_identidad(producto)}"
            ),
            nombre_canonico=nombre_canonico or nombre_normalizado,
            tipo_evidencia=_TIPO_EVIDENCIA_FABRICANTE_PRODUCTO,
            evidencia_base=evidencia,
            confianza=confianza,
            fusionar_por_nombre_desaconsejado=False,
            alternativas=[],
        )

    # 3. Nombre comercial normalizado: evidencia mas debil, no fusiona por nombre solo.
    if nombre_canonico:
        return IdentidadGlobalEstable(
            entity_id=f"{_PREFIJO_ENTIDAD_NOMBRE}:{nombre_canonico}",
            nombre_canonico=nombre_canonico,
            tipo_evidencia=_TIPO_EVIDENCIA_NOMBRE_COMERCIAL,
            evidencia_base=evidencia,
            confianza=confianza,
            fusionar_por_nombre_desaconsejado=True,
            alternativas=[candidato.to_dict()],
        )

    # 4. Evidencia insuficiente: se conserva el candidato separado con alternativas.
    clave_sufijo = candidato.candidate_id or nombre_normalizado or "desconocido"
    return IdentidadGlobalEstable(
        entity_id=f"{_PREFIJO_ENTIDAD_CANDIDATO}:{clave_sufijo}",
        nombre_canonico=nombre_canonico or nombre_normalizado,
        tipo_evidencia=_TIPO_EVIDENCIA_INSUFICIENTE,
        evidencia_base=evidencia,
        confianza=confianza,
        fusionar_por_nombre_desaconsejado=True,
        alternativas=[candidato.to_dict()],
    )


# ---------------------------------------------------------------------------
# Registro mínimo de aplicación del catálogo global (unidad 3.8.5.1.4.11.3)
# ---------------------------------------------------------------------------

# Claves de propiedades del registro mínimo que debe incluir cada entidad de
# tipo "application" del catálogo global `data/memory/entities.json`.
PROP_RUTA_ABSOLUTA_OBSERVADA = "ruta_absoluta_observada"
PROP_TIPO_LANZAMIENTO_NATIVO = "tipo_lanzamiento_nativo"
PROP_ESTADO_DISPONIBLE = "estado_disponible"
VALOR_ESTADO_DISPONIBLE = "available"
VALOR_ESTADO_NO_DISPONIBLE = "no_disponible"
PROP_FECHA_OBSERVACION = "fecha_observacion"
PROP_FUENTE_OBSERVACION = "fuente_observacion"
PROP_EVIDENCIA_OBSERVACION = "evidencia_observacion"
PROP_CAPACIDADES_VERIFICADAS = "capacidades_verificadas"
PROP_CAPACIDADES_NO_VERIFICADAS = "capacidades_no_verificadas"
PROP_TIPO_EVIDENCIA_IDENTIDAD = "tipo_evidencia_identidad"
PROP_FUSION_POR_NOMBRE_DESACONSEJADA = "fusionar_por_nombre_desaconsejada"

# Campos obligatorios del registro mínimo. Sin ellos el registro no es válido
# para persistir en el catálogo global de aplicaciones.
_CAMPOS_REQUERIDOS_REGISTRO_MINIMO = (
    "entity_id",
    "nombre",
    "tipo",
    "aliases",
    "categoria_rol",
    "estado_disponible",
    "fecha_observacion",
    "fuente_observacion",
    "evidencia_observacion",
)


def destino_observable(candidato: DiscoveredCandidate) -> bool:
    """
    Indica si el destino del candidato fue observado como accesible.

    Se considera observable cuando existe un archivo de disco en la ruta
    absoluta observada (ejecutable, acceso directo, etc.) o, para destinos
    que no son archivos de disco (paquetes, URI, lanzadores), cuando se
    conserva un destino nativo verificado. Nunca se asume disponibilidad solo
    por la extensión de archivo.
    """
    if str(candidato.absolute_path or "").strip() and os.path.isfile(
        str(candidato.absolute_path)
    ):
        return True
    if not str(candidato.absolute_path or "").strip() and str(
        candidato.destination or ""
    ).strip():
        return True
    return False


@dataclass
class RegistroMinimoAplicacion:
    """
    Registro mínimo de aplicación del catálogo global
    `data/memory/entities.json` (3.8.5.1.4.11.3).

    Cada entidad creada o actualizada del catálogo global incluye como mínimo:
    identificador estable, nombre, aliases observados y seguros, categoría/rol
    clasificado, ruta absoluta observada cuando existe, tipo de lanzamiento
    nativo y estado `available` con fecha, fuente de observación y evidencia.

    Los paquetes y URI sin `.exe` conservan su identificador y su destino
    nativo verificado (la ruta absoluta queda ausente). Nunca se inventan
    capacidades: `capacidades_verificadas` y `capacidades_no_verificadas`
    permanecen vacías a menos que existan acciones reales que las sustenten.
    El identificador estable proviene de `calcular_identidad_estable`
    (3.8.5.1.4.11.2) y nunca incorpora rutas absolutas.
    """

    entity_id: str
    nombre: str
    tipo: str = "application"
    aliases: list[str] = field(default_factory=list)
    categoria_rol: str = "desconocido"
    ruta_absoluta_observada: Optional[str] = None
    tipo_lanzamiento_nativo: Optional[str] = None
    estado_disponible: str = VALOR_ESTADO_DISPONIBLE
    fecha_observacion: str = ""
    fuente_observacion: str = ""
    evidencia_observacion: list[str] = field(default_factory=list)
    capacidades_verificadas: list[str] = field(default_factory=list)
    capacidades_no_verificadas: list[str] = field(default_factory=list)
    metadata: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""

    def a_dict_entidad(self) -> dict:
        """
        Convierte el registro en un diccionario compatible con `Entity` de
        `src.memory.storage`, listo para persistir en `entities.json`.
        """
        properties: dict[str, Any] = {
            PROP_RUTA_ABSOLUTA_OBSERVADA: self.ruta_absoluta_observada,
            PROP_TIPO_LANZAMIENTO_NATIVO: self.tipo_lanzamiento_nativo,
            PROP_ESTADO_DISPONIBLE: self.estado_disponible,
            PROP_FECHA_OBSERVACION: self.fecha_observacion,
            PROP_FUENTE_OBSERVACION: self.fuente_observacion,
            PROP_EVIDENCIA_OBSERVACION: list(self.evidencia_observacion),
            PROP_CAPACIDADES_VERIFICADAS: list(self.capacidades_verificadas),
            PROP_CAPACIDADES_NO_VERIFICADAS: list(self.capacidades_no_verificadas),
        }
        if self.metadata:
            properties.update(self.metadata)
        return {
            "id": self.entity_id,
            "type": self.tipo,
            "name": self.nombre,
            "properties": properties,
            "aliases": list(self.aliases),
            "tags": [self.categoria_rol] if self.categoria_rol else [],
            "confidence": 1.0,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def construir_registro_minimo_aplicacion(
    candidato: DiscoveredCandidate,
    identidad: IdentidadGlobalEstable,
    ahora_iso: Optional[str] = None,
) -> RegistroMinimoAplicacion:
    """
    Construye el registro mínimo de aplicación de un candidato descubierto
    y su identidad global estable (3.8.5.1.4.11.3).

    Reutiliza `calcular_identidad_estable` (3.8.5.1.4.11.2) para el
    `entity_id` estable, nunca la ruta absoluta. Clasifica el rol a partir
    del `launch_subtype` real del candidato. Marca `estado_disponible` como
    `available` solo cuando el destino fue observado como accesible
    (archivo existente o destino nativo de paquete/URI/lanzador); conserva
    la ruta absoluta observada cuando existe y nunca inventa capacidades.
    """
    ahora = ahora_iso or _ahora_iso()
    observable = destino_observable(candidato)
    ruta = str(candidato.absolute_path or "").strip() or None
    launch_subtype = getattr(candidato.launch_subtype, "value", None)
    categoria_rol = (
        str(launch_subtype) if launch_subtype else str(candidato.launch_subtype or "desconocido")
    )
    return RegistroMinimoAplicacion(
        entity_id=identidad.entity_id,
        nombre=str(
            identidad.nombre_canonico
            or candidato.nombre_comercial
            or candidato.name
            or ""
        ),
        tipo="application",
        aliases=list(candidato.aliases or []),
        categoria_rol=categoria_rol,
        ruta_absoluta_observada=ruta,
        tipo_lanzamiento_nativo=candidato.launch_type,
        estado_disponible=(
            VALOR_ESTADO_DISPONIBLE if observable else VALOR_ESTADO_NO_DISPONIBLE
        ),
        fecha_observacion=ahora,
        fuente_observacion=str(candidato.fuente or ""),
        evidencia_observacion=list(candidato.evidencia or []),
        capacidades_verificadas=[],
        capacidades_no_verificadas=[],
        metadata={
            PROP_TIPO_EVIDENCIA_IDENTIDAD: identidad.tipo_evidencia,
            PROP_FUSION_POR_NOMBRE_DESACONSEJADA: bool(
                identidad.fusionar_por_nombre_desaconsejado
            ),
        },
        created_at=ahora,
        updated_at=ahora,
    )


def _datos_para_validar_registro(
    registro: Union[RegistroMinimoAplicacion, dict],
) -> dict:
    """
    Normaliza un registro mínimo (dataclass o diccionario, también en forma
    de diccionario `Entity` de `a_dict_entidad`) a los nombres de campo del
    registro mínimo para validar sus campos obligatorios.
    """
    if isinstance(registro, RegistroMinimoAplicacion):
        return {
            "entity_id": registro.entity_id,
            "nombre": registro.nombre,
            "tipo": registro.tipo,
            "aliases": list(registro.aliases or []),
            "categoria_rol": registro.categoria_rol,
            "estado_disponible": registro.estado_disponible,
            "fecha_observacion": registro.fecha_observacion,
            "fuente_observacion": registro.fuente_observacion,
            "evidencia_observacion": list(registro.evidencia_observacion or []),
        }
    datos = dict(registro)
    # Soporte para diccionario estilo Entity (claves id/name/type/tags/properties).
    if "id" in datos and "entity_id" not in datos:
        datos["entity_id"] = datos.get("id")
    if "name" in datos and "nombre" not in datos:
        datos["nombre"] = datos.get("name")
    if "type" in datos and "tipo" not in datos:
        datos["tipo"] = datos.get("type")
    propiedades = datos.get("properties") or {}
    if isinstance(propiedades, dict):
        for campo in (
            "estado_disponible",
            "fecha_observacion",
            "fuente_observacion",
            "evidencia_observacion",
        ):
            if campo not in datos and campo in propiedades:
                datos[campo] = propiedades[campo]
    if "categoria_rol" not in datos and datos.get("tags"):
        tags = datos["tags"]
        datos["categoria_rol"] = tags[0] if tags else ""
    return datos


def validar_registro_minimo_aplicacion(
    registro: Union[RegistroMinimoAplicacion, dict],
) -> list[str]:
    """
    Devuelve los campos obligatorios faltantes de un registro mínimo de
    aplicación. Lista vacía cuando el registro es válido para persistir en
    el catálogo global de aplicaciones.
    """
    datos = _datos_para_validar_registro(registro)
    faltantes: list[str] = []
    for campo in _CAMPOS_REQUERIDOS_REGISTRO_MINIMO:
        valor = datos.get(campo)
        if valor is None or (isinstance(valor, str) and valor.strip() == ""):
            faltantes.append(campo)
    return faltantes


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
        app_manager: Optional[Any] = None,
    ) -> None:
        self.preflight = preflight or ApplicationPreflight()
        # El clasificador ya valida con preflight internamente (.7.10).
        self.clasificador = clasificador or LaunchClassifier(preflight=self.preflight)
        self.storage = storage or SystemInventoryStorage()
        self.calibration = calibration or CalibrationManager()
        self.machine_id = machine_id or generate_machine_id()
        # Gestor del catálogo global (ApplicationManager / entities.json).
        # Inyectable para pruebas; por defecto la instancia singleton real.
        from src.hands.applications_core import get_application_manager

        self.app_manager = app_manager or get_application_manager()
        # Estado de la última resolución: candidatos cuyo destino dejó de ser
        # accesible (ruta cambiada, desaparecida o inaccesible); su estado se
        # actualiza (disponible=False) y su ruta no se intenta ni se devuelve.
        self._inaccesibles_ultima_resolucion: list[DiscoveredCandidate] = []
        # Informe de aislamiento del equipo para el inventario persistente
        # (unidad 3.8.5.1.4.9.7): se rellena al verificar la identidad antes de
        # usar destinos del inventario.
        self._informe_aislamiento_ultima_resolucion: Optional[dict] = None

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
        Busca candidatos por nombre aplicando el orden de precedencia de
        fuentes (3.8.5.1.4.9.2):

        1. Aplicación ya abierta (proceso en ejecución detectado en el SO).
        2. Catálogo conocido (ApplicationManager / conocimiento estructurado).
        3. Fuentes nativas instaladas (menú, paquetes, registro, PATH, App Paths).
        4. Candidatos del inventario persistente (fuente complementaria).

        Se conserva la procedencia (`fuente`) y la confianza (`confianza`) de
        cada candidato, y se deduplica por destino real conservando la fuente
        de mayor precedencia. No lanza aplicaciones ni modifica el catálogo.
        """
        if not nombre or not isinstance(nombre, str):
            return []
        nombre = nombre.strip()
        if not nombre:
            return []

        nombre_lower = nombre.casefold()
        fuentes_consultadas: list[str] = []
        crudos: list[dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Paso 1: catálogo conocido (ApplicationManager) — alta precedencia.
        # ------------------------------------------------------------------
        catalogo = self._candidato_desde_catalogo(nombre)
        if catalogo is not None:
            fuentes_consultadas.append(catalogo["source"])
            crudos.append(catalogo)

        # ------------------------------------------------------------------
        # Paso 2: fuentes nativas instaladas (FUENTES_PRIMARIAS).
        # ------------------------------------------------------------------
        primarios = self._fuentes_primarias(limite_por_fuente)
        for fuente in FUENTES_PRIMARIAS:
            if any(str(p.get("source", "")).casefold() == fuente for p in primarios):
                fuentes_consultadas.append(fuente)

        coincidencias = [
            p
            for p in primarios
            if nombre_lower in str(p.get("name", "")).casefold()
        ]
        for c in coincidencias:
            crudos.append(
                {
                    **c,
                    "source": str(c.get("source", "")).strip(),
                    "fuentes_consultadas": list(fuentes_consultadas),
                }
            )

        # ------------------------------------------------------------------
        # Paso 3: inventario persistente como fuente complementaria solo si
        # el nombre no quedó resuelto por catálogo ni fuentes nativas.
        # ------------------------------------------------------------------
        nombres_resueltos = {
            str(c.get("name", "")).casefold() for c in crudos if c.get("name")
        }
        destinos_resueltos = {
            str(c.get("destination") or c.get("absolute_path", "")).casefold()
            for c in crudos
            if c.get("destination") or c.get("absolute_path")
        }
        if incluir_inventario and (
            not crudos or nombre_lower not in nombres_resueltos
        ):
            self.verificar_aislamiento_inventario()
            if not self.inventario_utilizable_para_maquina_actual:
                # 3.8.5.1.4.9.7: el inventario pertenece a otro equipo (base de
                # datos copiada a otro host); no se consultan ni se usan sus
                # destinos hasta reescanear el equipo actual.
                entradas = []
            else:
                try:
                    self.storage.connect()
                    entradas = self.storage.search(
                        machine_id=self.machine_id,
                        extension=".exe",
                        tipo=EntryType.FILE.value,
                        disponible=True,
                        limit=limite_por_fuente,
                        solo_volumes_montados=True,
                    )
                except (OSError, PermissionError, sqlite3.Error):
                    entradas = []
                except Exception:
                    entradas = []
                finally:
                    try:
                        self.storage.close()
                    except Exception:
                        pass

            if entradas:
                fuentes_consultadas.append(FUENTE_INVENTARIO)
                # Filtrar por nombre en Python (coincidencia case-insensitive de
                # subcadena), consistente con _complemento_inventario que no usa
                # el filtro exacto de name en storage.search.
                entradas_filtradas = [
                    e
                    for e in entradas
                    if nombre_lower in str(e.get("name", "")).casefold()
                    and str(e.get("name", "")).casefold() not in nombres_resueltos
                    and str(e.get("absolute_path", "")).casefold()
                    not in destinos_resueltos
                ]
                for e in entradas_filtradas:
                    crudos.append(
                        {
                            "candidate_id": str(e.get("absolute_path", "")),
                            "name": str(e.get("name", "")),
                            "absolute_path": str(e.get("absolute_path", "")),
                            "destination": str(e.get("absolute_path", "")),
                            "source": FUENTE_INVENTARIO,
                            "volume": str(e.get("volume", "")) or None,
                            "last_checked_at": str(e.get("last_checked_at", "")),
                            "fuentes_consultadas": list(fuentes_consultadas),
                            "esta_en_inventario": True,
                        }
                    )

        if not crudos:
            return []

        # ------------------------------------------------------------------
        # Marcar como "aplicación ya abierta" los candidatos cuyo proceso
        # esté en ejecución: elevan su fuente a la máxima precedencia.
        # ------------------------------------------------------------------
        crudos = self._elevar_si_abierta(crudos)

        # ------------------------------------------------------------------
        # Deduplicar por destino real conservando la fuente de mayor
        # precedencia.
        # ------------------------------------------------------------------
        unicos = self._dedup_por_destino(crudos)

        # ------------------------------------------------------------------
        # 3.8.5.1.4.9.4: antes de clasificar/validar, descartar los candidatos
        # cuyo destino ya no es accesible en el equipo (ruta cambiada,
        # desaparecida o inaccesible), actualizando su estado. Asi no se
        # intenta la ruta obsoleta y la resolucion se repite con las fuentes
        # vigentes.
        # ------------------------------------------------------------------
        ahora = _ahora_iso()
        unicos_vigentes: list[dict[str, Any]] = []
        inaccesibles: list[DiscoveredCandidate] = []
        for c in unicos:
            destino = c.get("absolute_path") or c.get("destination")
            if self._destino_compruebe_en_disco(destino) and not self._existe_destino_vigente(
                c, destino
            ):
                inaccesibles.append(self._candidato_inaccesible(c, destino, ahora))
                continue
            unicos_vigentes.append(c)
        self._inaccesibles_ultima_resolucion = inaccesibles

        return self._clasificar_y_validar(
            unicos_vigentes,
            fuente_defecto=FUENTE_INVENTARIO,
            fuentes_consultadas=fuentes_consultadas,
        )

    def buscar_por_nombre_con_desambiguacion(
        self,
        nombre: str,
        incluir_inventario: bool = True,
        limite_por_fuente: int = 50,
    ) -> ResultadoResolucionCandidatos:
        """
        Resuelve un nombre por fuentes conservando todas las alternativas y
        señalando ambigüedad cuando la evidencia no permite elegir una
        (3.8.5.1.4.9.3).

        `buscar_por_nombre` ya devuelve todos los candidatos encontrados sin
        elegir uno silenciosamente. Este método añade la señal explícita de
        ambigüedad: cuando existen varias coincidencias plausibles para el
        mismo nombre y ninguna fuente autoritativa (aplicación ya abierta o
        catálogo conocido) resuelve de forma inequívoca, ``ambiguo`` es True,
        ``requiere_desambiguacion`` es True y ``alternativas`` contiene todos
        los candidatos para que el llamador solicite desambiguación al usuario.

        No lanza aplicaciones, no modifica el catálogo conocido ni persiste
        capacidades inferidas.
        """
        candidatos = self.buscar_por_nombre(
            nombre,
            incluir_inventario=incluir_inventario,
            limite_por_fuente=limite_por_fuente,
        )
        ambiguo, motivo, fuente_autoritaria = self._evaluar_ambiguedad(candidatos)
        return ResultadoResolucionCandidatos(
            candidatos=list(candidatos),
            ambiguo=ambiguo,
            motivo_ambiguedad=motivo,
            alternativas=list(candidatos) if ambiguo else [],
            requiere_desambiguacion=ambiguo,
            fuente_autoritaria=fuente_autoritaria,
        )

    # ------------------------------------------------------------------ #
    # Conexión con el catálogo global (ApplicationManager / ApplicationKnowledge)
    # (unidad 3.8.5.1.4.9.5)
    # ------------------------------------------------------------------ #

    def _conocimiento_para_candidato(
        self, candidato: DiscoveredCandidate
    ) -> Optional[Any]:
        """
        Resuelve el candidato contra el catálogo global probando, en orden:
        (1) el nombre del candidato tal cual; (2) el nombre del ejecutable sin
        extensión (ej. "notepad.exe" -> "notepad"); (3) el nombre comercial
        observado. Solo usa `ApplicationManager.get_application` (contrato
        verificado); nunca escribe ni registra en el catálogo.
        """
        nombres_a_probar: list[str] = []
        nombre = str(candidato.nombre_comercial or candidato.name or "").strip()
        if nombre:
            nombres_a_probar.append(nombre)
        ruta = str(candidato.absolute_path or candidato.destination or "").strip()
        if ruta:
            try:
                stem = Path(ruta).stem
            except (OSError, ValueError):
                stem = ""
            if stem and stem.casefold() != nombre.casefold():
                nombres_a_probar.append(stem)
        for nombre_probar in dict.fromkeys(nombres_a_probar):
            app = self.app_manager.get_application(nombre_probar)
            if app is not None:
                return app
        return None

    def vincular_con_catalogo(
        self, candidatos: list[DiscoveredCandidate]
    ) -> list[CandidatoConCatalogo]:
        """
        Vincula cada candidato resuelto con el catálogo global de aplicaciones
        (`ApplicationManager` / `data/memory/entities.json`) mediante contratos
        verificados: `get_application_manager()` y
        `ApplicationManager.get_application(nombre)`.

        Cuando un candidato se encuentra en el catálogo se devuelve su
        `ApplicationKnowledge` con `en_catalogo_global=True`; si no, se devuelve
        `en_catalogo_global=False` y `conocimiento=None`. La fuente autoritativa
        se preserva cuando el candidato ya proviene de una fuente autoritativa
        (aplicación ya abierta o catálogo conocido).

        No lanza aplicaciones, no modifica `entities.json`, no registra ni
        auto-registra candidatos (el puente de auto-registro corresponde a
        3.8.5.1.4.11) y no crea rutas paralelas de Brain/Planner/Executor.
        """
        vinculados: list[CandidatoConCatalogo] = []
        for c in candidatos:
            conocimiento = self._conocimiento_para_candidato(c)
            en_catalogo = conocimiento is not None
            fuente_prop = str(c.fuente or "").strip()
            if fuente_prop in _FUENTES_AUTORITATIVAS:
                fuente_autoritaria = fuente_prop
            elif en_catalogo:
                fuente_autoritaria = FUENTE_CATALOGO
            else:
                fuente_autoritaria = None
            vinculados.append(
                CandidatoConCatalogo(
                    candidato=c,
                    en_catalogo_global=en_catalogo,
                    conocimiento=conocimiento,
                    fuente_autoritaria=fuente_autoritaria,
                )
            )
        return vinculados

    def buscar_por_nombre_con_catalogo(
        self,
        nombre: str,
        incluir_inventario: bool = True,
        limite_por_fuente: int = 50,
    ) -> tuple[list[DiscoveredCandidate], list[CandidatoConCatalogo]]:
        """
        Resuelve un nombre por fuentes (como `buscar_por_nombre`) y vincula cada
        candidato resuelto con el catálogo global de aplicaciones.

        Retorna `(candidatos, vinculados)` con el mismo orden: `candidatos` es
        la lista de `DiscoveredCandidate` y `vinculado[i]` es la vinculación de
        `candidatos[i]` con `ApplicationManager`/`ApplicationKnowledge`. No
        lanza aplicaciones ni modifica `entities.json`.
        """
        candidatos = self.buscar_por_nombre(
            nombre,
            incluir_inventario=incluir_inventario,
            limite_por_fuente=limite_por_fuente,
        )
        vinculados = self.vincular_con_catalogo(candidatos)
        return candidatos, vinculados

    def _evaluar_ambiguedad(
        self, candidatos: list[DiscoveredCandidate]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Evalúa si una lista de candidatos resuelta para un mismo nombre es
        ambigua (3.8.5.1.4.9.3).

        Reglas:
        - 0 o 1 candidato: no hay ambigüedad (no hay nada que elegir).
        - Si exactamente una fuente autoritativa (aplicación abierta o
          catálogo conocido) resuelve el nombre, esa fuente decide: no es
          ambigua.
        - Si varias fuentes autoritativas resuelven a destinos distintos: la
          ambigüedad es real aunque sean fuentes autoritativas.
        - Sin fuente autoritativa y varios candidatos con destinos distintos:
          la evidencia no permite elegir uno de forma inequívoca; se conservan
          las alternativas y se requiere desambiguación.

        Retorna (es_ambiguo, motivo_ambiguedad, fuente_autoritaria).
        """
        if not candidatos:
            return False, None, None
        if len(candidatos) == 1:
            fuente = str(candidatos[0].fuente or "").strip()
            return (
                False,
                None,
                fuente if fuente in _FUENTES_AUTORITATIVAS else None,
            )
        autoritativas = [
            c
            for c in candidatos
            if str(c.fuente or "").strip() in _FUENTES_AUTORITATIVAS
        ]
        if len(autoritativas) == 1:
            return False, None, str(autoritativas[0].fuente or "").strip()
        if len(autoritativas) > 1:
            return (
                True,
                "Varias fuentes autoritativas resuelven el mismo nombre a "
                "destinos distintos; se conservan alternativas y se requiere "
                "desambiguación",
                None,
            )
        return (
            True,
            f"Se encontraron {len(candidatos)} candidatos plausibles para el "
            "nombre sin evidencia que permita elegir uno de forma inequívoca; "
            "se conservan alternativas y se requiere desambiguación",
            None,
        )

    def _candidato_desde_catalogo(
        self, nombre: str
    ) -> Optional[dict[str, Any]]:
        """
        Resuelve el nombre contra ApplicationManager (catálogo conocido).

        Devuelve un dict de candidato crudo con fuente
        ``catalogo_conocido``, o ``None`` si no existe en el catálogo. Si el
        proceso ya está en ejecución, eleva la fuente a
        ``aplicacion_abierta``. No lanza nada ni modifica el catálogo.
        """
        from src.hands.applications_core import (
            _is_process_running,
            get_application_manager,
        )

        app_manager = get_application_manager()
        app = app_manager.get_application(nombre)
        if app is None:
            return None

        fuente = FUENTE_CATALOGO
        ejecutable = str(getattr(app, "executable", None) or "").strip()
        # Resolver nombres bare (ej. "notepad.exe") a su ruta absoluta real
        # mediante PATH/App Paths, igual que _check_application_available, para
        # que preflight pueda validar el destino existente.
        ruta_absoluta: Optional[str] = None
        if ejecutable:
            if os.path.isabs(ejecutable) or any(
                sep in ejecutable for sep in ("/", "\\")
            ):
                ruta_absoluta = ejecutable if os.path.isfile(ejecutable) else None
            else:
                resuelto = shutil.which(ejecutable)
                ruta_absoluta = resuelto if resuelto else None
        if ejecutable and ruta_absoluta and _is_process_running(
            os.path.basename(ruta_absoluta)
        ):
            fuente = FUENTE_APLICACION_ABIERTA

        return {
            "candidate_id": ruta_absoluta or ejecutable or nombre,
            "name": app.name,
            "absolute_path": ruta_absoluta,
            "destination": ruta_absoluta or getattr(app, "url", None) or None,
            "source": fuente,
            "volume": self._volumen_de(ruta_absoluta) if ruta_absoluta else None,
            "last_checked_at": "",
            "fuentes_consultadas": [fuente],
        }

    def _elevar_si_abierta(
        self, candidatos: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Eleva a ``aplicacion_abierta`` la fuente de los candidatos cuyo proceso
        ya esté en ejecución en el sistema operativo.

        La detección usa ``_is_process_running`` sobre el ejecutable del
        candidato (lectura sola del SO, no lanza nada). Cuando se eleva, la
        fuente pasa a la máxima precedencia del orden de 3.8.5.1.4.9.2.
        """
        from src.hands.applications_core import _is_process_running

        resultado: list[dict[str, Any]] = []
        for c in candidatos:
            fuente = str(c.get("source", "")).strip()
            ruta = c.get("absolute_path") or c.get("destination")
            nombre = str(c.get("name", "")).strip()
            es_abierta = False
            if ruta and os.path.isfile(ruta):
                exe = os.path.basename(ruta)
                if _is_process_running(exe):
                    es_abierta = True
            elif nombre:
                if _is_process_running(nombre):
                    es_abierta = True
            if es_abierta:
                c = dict(c)
                c["source"] = FUENTE_APLICACION_ABIERTA
                consultadas = list(
                    dict.fromkeys(
                        c.get("fuentes_consultadas", [])
                        + [FUENTE_APLICACION_ABIERTA]
                    )
                )
                c["fuentes_consultadas"] = consultadas
            resultado.append(c)
        return resultado

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

    @property
    def candidatos_inaccesibles_ultima_resolucion(self) -> list[DiscoveredCandidate]:
        """Candidatos de la última resolución cuyo destino ya no es accesible
        en el equipo (ruta cambiada, desaparecida o inaccesible).

        Su estado fue actualizado (``disponible=False``, ``ultima_comprobacion``
        y evidencia de inaccesibilidad) y su ruta no se intentó ni se devolvió
        como resultado de la resolución; la resolución se repite con las fuentes
        vigentes (3.8.5.1.4.9.4).
        """
        return list(self._inaccesibles_ultima_resolucion)

    # ------------------------------------------------------------------ #
    # Aislamiento por equipo y volumen del inventario (3.8.5.1.4.9.7)
    # ------------------------------------------------------------------ #

    def verificar_aislamiento_inventario(self) -> dict:
        """Comprueba si el inventario persistente pertenece al equipo actual.

        Delegacion en `SystemInventoryStorage.verificar_identidad_equipo`.
        Detecta el caso de base de datos copiada a otro equipo (host distinto)
        y exige reescaneo/revalidacion antes de usar cualquier destino del
        inventario: cuando el equipo no coincide, el inventario no se consulta
        ni se usan sus destinos.

        Retorna un diccionario con `maquina_actual`, `maquina_registrada`,
        `equipo_coincide`, `bloqueado`, `requiere_reescaneo`,
        `inventario_utilizable` y `motivo`. El resultado se almacena en
        `informe_aislamiento_ultima_resolucion`.
        """
        informe = self.storage.verificar_identidad_equipo(self.machine_id)
        if not isinstance(informe, dict):
            # Almacenamiento sin informe de identidad de equipo (doble de
            # prueba o implementacion sin esta capacidad): no se puede exigir
            # el aislamiento, por lo que no se bloquea el inventario.
            normalizado: dict[str, object] = {
                "maquina_actual": self.machine_id,
                "maquina_registrada": None,
                "equipo_coincide": True,
                "bloqueado": False,
                "requiere_reescaneo": False,
                "motivo": None,
                "inventario_utilizable": True,
            }
        else:
            normalizado: dict[str, object] = {
                "maquina_actual": informe.get("maquina_actual"),
                "maquina_registrada": informe.get("maquina_registrada"),
                "equipo_coincide": bool(informe.get("equipo_coincide", False)),
                "bloqueado": bool(informe.get("bloqueado", False)),
                "requiere_reescaneo": bool(informe.get("requiere_reescaneo", False)),
                "motivo": informe.get("motivo"),
                "inventario_utilizable": bool(
                    informe.get("equipo_coincide", False)
                    and not informe.get("bloqueado", False)
                ),
            }
        self._informe_aislamiento_ultima_resolucion = dict(normalizado)
        return normalizado

    @property
    def informe_aislamiento_ultima_resolucion(self) -> dict:
        """Informe de aislamiento del equipo de la ultima verificacion del
        inventario (ver `verificar_aislamiento_inventario`)."""
        return dict(self._informe_aislamiento_ultima_resolucion or {})

    @property
    def inventario_requiere_reescaneo(self) -> bool:
        """True si el inventario pertenece a otro equipo y hay que reescanear
        antes de usar sus destinos."""
        informe = self._informe_aislamiento_ultima_resolucion or {}
        return bool(informe.get("requiere_reescaneo", False))

    @property
    def inventario_utilizable_para_maquina_actual(self) -> bool:
        """True si el inventario persistente puede consultarse para el equipo
        actual (equipo coincidente y sin bloqueo)."""
        informe = self._informe_aislamiento_ultima_resolucion or {}
        return bool(informe.get("inventario_utilizable", False))

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
    # Auto-registro de candidatos descubiertos en el catalogo global
    # (unidad 3.8.5.1.4.11.4)
    # ------------------------------------------------------------------ #

    def auto_registrar_descubiertos(
        self,
        limite_por_fuente: int = 50,
        incluir_inventario: bool = True,
        memory_manager: Optional[Any] = None,
    ) -> dict[str, Any]:
        """
        Auto-registra cada candidato descubierto (incluidos los `.exe`
        accesibles de RecorridoVolumen/inventario y las fuentes nativas de
        Windows `.lnk`, AppX, registro de desinstaladores, PATH y App Paths)
        en el catalogo global `data/memory/entities.json`, sin intervencion
        manual y sin filtrar por ser GUI: registra CLI, servicios,
        instaladores, actualizadores, controladores y roles desconocidos,
        etiquetando cada rol correctamente.

        Para cada candidato accesible calcula la identidad estable
        (3.8.5.1.4.11.2), construye el registro minimo de aplicacion
        (3.8.5.1.4.11.3), valida sus campos obligatorios y lo guarda mediante
        `MemoryManager.save_entity` (upsert por ID estable, idempotente; rechaza
        JSON corrupto sin vaciar el catalogo). No lanza aplicaciones ni pide
        alta manual al usuario.

        Parametros:
        - limite_por_fuente: tope de candidatos leidos de cada fuente.
        - incluir_inventario: si True, complementa con el inventario los
          destinos no cubiertos por las fuentes primarias.
        - memory_manager: gestor de memoria destino; por defecto el del
          `ApplicationManager` asociado (`data/memory/entities.json`).

        Retorna:
        Resumen con contadores y detalle de registrados, omitidos y errores.
        """
        mm = memory_manager or self.app_manager.memory_manager
        descubiertos = self.descubrir_todos(
            limite_por_fuente=limite_por_fuente,
            incluir_inventario=incluir_inventario,
        )
        registrados: list[dict[str, Any]] = []
        omitidos: list[dict[str, Any]] = []
        errores: list[dict[str, Any]] = []
        for c in descubiertos:
            # .11.4: no filtrar por GUI; solo exigir que el destino sea
            # accesible/observable en el equipo.
            if not destino_observable(c):
                omitidos.append(
                    {
                        "candidato": c.name,
                        "razon": "destino_no_observable",
                        "fuente": c.fuente,
                    }
                )
                continue
            identidad = calcular_identidad_estable(c)
            registro = construir_registro_minimo_aplicacion(c, identidad)
            faltantes = validar_registro_minimo_aplicacion(registro)
            if faltantes:
                omitidos.append(
                    {
                        "candidato": c.name,
                        "razon": "campos_obligatorios_faltantes",
                        "faltantes": faltantes,
                        "fuente": c.fuente,
                    }
                )
                continue
            try:
                entity = Entity.from_dict(registro.a_dict_entidad())
                ok = mm.save_entity(entity)
            except Exception as exc:  # noqa: BLE001
                errores.append(
                    {
                        "candidato": c.name,
                        "razon": f"excepcion:{type(exc).__name__}",
                        "fuente": c.fuente,
                    }
                )
                continue
            if ok:
                registrados.append(registro.a_dict_entidad())
            else:
                errores.append(
                    {
                        "candidato": c.name,
                        "razon": "guardado_rechazado_por_gestor",
                        "fuente": c.fuente,
                    }
                )
        return {
            "total_descubiertos": len(descubiertos),
            "registrados": len(registrados),
            "omitidos": len(omitidos),
            "errores": len(errores),
            "detalle_registrados": registrados,
            "detalle_omitidos": omitidos,
            "detalle_errores": errores,
        }

    # ------------------------------------------------------------------ #
    # Estado vigente de destinos (3.8.5.1.4.9.4)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _destino_compruebe_en_disco(destino: Optional[str]) -> bool:
        """True si el destino es una ruta local absoluta cuya existencia y
        acceso pueden comprobarse directamente en el sistema de archivos.

        Se excluyen las URIs, esquemas no locales y paquetes/bundles, que no
        resuelven a un archivo de disco comprobable con ``os.path.exists``."""
        if not destino or not isinstance(destino, str):
            return False
        d = destino.strip()
        if not d:
            return False
        if ":" in d and not _es_ruta_windows(d):
            return False
        return os.path.isabs(d)

    def _existe_destino_vigente(self, candidato: dict[str, Any], destino: str) -> bool:
        """Comprueba si el destino sigue siendo accesible en el equipo.

        Para candidatos del inventario persistente, revalida mediante
        ``SystemInventoryStorage.revalidar_destino_aplicacion``, que realiza
        la comprobacion real en el sistema de archivos y actualiza
        ``last_checked_at`` de la entrada (su estado persistido). Para el
        resto de fuentes se comprueba directamente con ``os.path.exists``.
        Devuelve False si el destino ya no es accesible.
        """
        if not destino:
            return False
        if bool(candidato.get("esta_en_inventario", False)) and candidato.get("volume"):
            try:
                resultado = self.storage.revalidar_destino_aplicacion(
                    self.machine_id, str(candidato["volume"]), destino
                )
            except Exception:
                resultado = None
            if isinstance(resultado, dict) and resultado.get("scan_id") is not None:
                return bool(resultado.get("valido"))
        return os.path.exists(destino)

    def _candidato_inaccesible(
        self, candidato: dict[str, Any], destino: str, ahora: str
    ) -> DiscoveredCandidate:
        """Construye el registro de estado actualizado de un candidato cuyo
        destino ya no es accesible: ``disponible=False``, ultima comprobacion
        y evidencia de inaccesibilidad. No se intenta su ruta ni se valida
        con preflight la ruta obsoleta."""
        return DiscoveredCandidate(
            candidate_id=str(candidato.get("candidate_id") or destino or ""),
            name=str(candidato.get("name", "")),
            absolute_path=destino,
            destination=destino,
            fuente=str(candidato.get("source", FUENTE_INVENTARIO) or FUENTE_INVENTARIO),
            volume=str(candidato.get("volume")) if candidato.get("volume") else None,
            esta_en_inventario=bool(candidato.get("esta_en_inventario", False)),
            disponible=False,
            ultima_comprobacion=ahora,
            razon="ruta_destino_inaccesible",
            advertencias=["ruta_destino_inaccesible"],
            evidencia=[f"ruta_no_accesible_en_disco:{ahora}"],
            preflight_decision=None,
        )

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
        por nombre. Para cada destino conserva la fuente de mayor precedencia
        según ``_PRECEDENCIA_FUENTE`` (3.8.5.1.4.9.2: abierta > catálogo >
        nativas > inventario). Las instalaciones distintas con rutas distintas
        se conservan todas.
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
                prioridad_nueva = _PRECEDENCIA_FUENTE.get(fuente, 99)
                prioridad_vieja = _PRECEDENCIA_FUENTE.get(
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
        self.verificar_aislamiento_inventario()
        if not self.inventario_utilizable_para_maquina_actual:
            # 3.8.5.1.4.9.7: el inventario pertenece a otro equipo (base de
            # datos copiada a otro host); no se consultan ni se usan sus
            # destinos hasta reescanear el equipo actual.
            return []
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

        3.8.5.1.4.9.6: además pasa cada candidato por `ApplicationPreflight.check()`
        (política completa de pre-lanzamiento: nombres bloqueados, app IDs
        bloqueados, login requerido, recursos, manifest de elevación y uiAccess),
        almacenando el resultado en `preflight_policy`. No lanza aplicaciones.

        `fuente_defecto` se usa cuando el candidato no trae fuente propia.
        """
        descubiertos: list[DiscoveredCandidate] = []
        fuentes = list(fuentes_consultadas or [])
        for c in candidatos:
            destino = c.get("absolute_path") or c.get("destination")
            fuente = str(c.get("source", "") or fuente_defecto or FUENTE_INVENTARIO).strip()

            clasificacion = self.clasificador.classify_candidate(c)

            # Validación de destino con preflight (solo lectura, no lanza).
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

            # 3.8.5.1.4.9.6: preflight completo de política sobre el candidato.
            preflight_policy: Optional[dict] = None
            try:
                preflight_policy = self.ejecutar_preflight_sobre_candidato(c, clasificacion)
            except Exception:
                preflight_policy = {
                    "allowed": False,
                    "reason": "Error al ejecutar preflight completo sobre el candidato",
                    "confidence": "high",
                    "blocked_by": "preflight_error",
                    "availability": "unknown",
                }

            descubiertos.append(
                DiscoveredCandidate.from_classification(
                    clasificacion,
                    fuente=fuente,
                    destino_original=destino,
                    preflight_decision=preflight_decision,
                    preflight_policy=preflight_policy,
                    fuentes_consultadas=list(fuentes),
                    esta_en_inventario=bool(c.get("esta_en_inventario", esta_en_inventario)),
                )
            )
        return descubiertos

    # ------------------------------------------------------------------ #
    # Preflight completo de política (3.8.5.1.4.9.6)
    # ------------------------------------------------------------------ #

    def ejecutar_preflight_sobre_candidato(
        self,
        candidato_raw: dict[str, Any],
        clasificacion: LaunchClassification,
    ) -> dict[str, Any]:
        """
        Pasa un candidato por `ApplicationPreflight.check()` (política completa
        de pre-lanzamiento), sin lanzar la aplicación ni verificar procesos/
        ventanas (eso corresponde a 3.8.5.4-3.8.5.6).

        Aplica las políticas existentes: nombres bloqueados, app IDs bloqueados,
        login requerido, recursos no disponibles, manifest de elevación y uiAccess.
        Retorna el dict estructurado de `PreflightResult.to_dict()` con claves
        como `allowed`, `blocked_by`, `reason`, `requires_elevation`, etc.
        """
        nombre = str(clasificacion.name or candidato_raw.get("name", "")).strip()
        ejecutable = str(
            clasificacion.absolute_path
            or clasificacion.destination
            or candidato_raw.get("absolute_path")
            or candidato_raw.get("destination")
            or ""
        ).strip()

        # Si el destino es una URI de aplicación admitida, pasarla como url para
        # que preflight la valide por esquema (no requiere archivo en disco).
        destino_bruto = str(
            clasificacion.destination
            or candidato_raw.get("destination")
            or ""
        ).strip()
        url = (
            destino_bruto
            if ApplicationPreflight._uri_scheme(destino_bruto)
            else ""
        )

        application = {
            "name": nombre,
            "app_id": ejecutable,
            "login_required": None,
            "logged_in": None,
            "resources_available": None,
            "url": url,
        }
        return self.preflight.check(application)

    def filtrar_por_preflight_policy(
        self, candidatos: list[DiscoveredCandidate]
    ) -> list[DiscoveredCandidate]:
        """
        Retorna solo los candidatos autorizados por el preflight completo
        (`preflight_policy["allowed"] is True`).

        Los bloqueados por política (`allowed=False`) se excluyen; su
        `preflight_policy` conserva `blocked_by` y `reason` para consulta.
        No lanza ninguna aplicación.
        """
        return [
            c
            for c in candidatos
            if c.preflight_policy is not None
            and c.preflight_policy.get("allowed") is True
        ]

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
