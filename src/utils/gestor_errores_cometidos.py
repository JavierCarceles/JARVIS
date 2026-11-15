"""
Gestor de Errores Cometidos - JARVIS
------------------------------------
Gestiona el registro de errores cometidos con conteo de repeticiones.

Reglas de negocio:
- Cada 4 veces que se cometa un mismo error, se agrega a las reglas
  (improvement_rules.json) el indicativo de "no repetir ese error".
- Tras editar las reglas, los errores que tengan 4 repeticiones o mas
  se mueven al archivo de archivo (errores_cometidos_archivados.json).
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # raiz del proyecto JARVIS
DATA_DIR = BASE_DIR / "data"

ERRORES_COMETIDOS_PATH = DATA_DIR / "errores_cometidos.json"
ERRORES_ARCHIVADOS_PATH = DATA_DIR / "errores_cometidos_archivados.json"
IMPROVEMENT_RULES_PATH = DATA_DIR / "improvement_rules.json"

UMBRAL_REPETICIONES = 4  # cada 4 repeticiones se activa "no repetir"


def _cargar_json(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar_json(path: Path, data: List[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _cargar_reglas() -> List[Dict]:
    if not IMPROVEMENT_RULES_PATH.exists():
        return []
    with open(IMPROVEMENT_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar_reglas(reglas: List[Dict]) -> None:
    with open(IMPROVEMENT_RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(reglas, f, indent=2, ensure_ascii=False)


def _ya_existe_regla_no_repetir(reglas: List[Dict], error_id: str) -> bool:
    return any(
        r.get("no_repetir") is True and r.get("error_id") == error_id
        for r in reglas
    )


def _construir_regla_no_repetir(error: Dict) -> Dict:
    rep = error.get("repeticiones", 0)
    return {
        "rule_id": f"no_repetir_{error['error_id']}",
        "name": f"No repetir error de {error.get('error_type', 'desconocido')}",
        "description": (
            "NO REPETIR ESTE ERROR: "
            f"{error.get('error_message', '')}. "
            f"Se ha cometido {rep} veces. "
            "Indicativo de no repetir este error."
        ),
        "condition": f"error_id == '{error['error_id']}'",
        "action": f"bloquear_repeticion_error('{error['error_id']}')",
        "priority": 1,
        "enabled": True,
        "success_rate": 0.0,
        "execution_count": 0,
        "last_execution": None,
        "improvement_score": 0.0,
        "no_repetir": True,
        "error_id": error["error_id"],
        "repeticiones_origen": rep,
    }


def registrar_error(
    error_id: str,
    error_type: str,
    error_message: str,
    component: str,
) -> Dict:
    """
    Registra (o incrementa) un error cometido.
    Retorna el diccionario del error actualizado.
    """
    errores = _cargar_json(ERRORES_COMETIDOS_PATH)
    ahora = datetime.now().isoformat()

    # Buscar si ya existe el error activo
    existente = None
    for e in errores:
        if e["error_id"] == error_id:
            existente = e
            break

    if existente:
        existente["repeticiones"] = existente.get("repeticiones", 0) + 1
        existente["fecha_ultima_vez"] = ahora
        error_actual = existente
    else:
        error_actual = {
            "error_id": error_id,
            "error_type": error_type,
            "error_message": error_message,
            "component": component,
            "repeticiones": 1,
            "fecha_primera_vez": ahora,
            "fecha_ultima_vez": ahora,
            "no_repetir": False,
            "regla_agregada": False,
            "movido_a_archivo": False,
        }
        errores.append(error_actual)

    _guardar_json(ERRORES_COMETIDOS_PATH, errores)
    return error_actual


def procesar_reglas_y_mover() -> Dict:
    """
    Evalua los errores cometidos:
    1. Para cada error que alcance UMBRAL_REPETICIONES (4) o mas y no tenga
       regla de 'no repetir', agrega la regla a improvement_rules.json.
    2. Mueve los errores con 4 repeticiones o mas al archivo archivado.

    Retorna un resumen de lo realizado.
    """
    errores = _cargar_json(REPOMETER_PATH if False else ERRORES_COMETIDOS_PATH)
    reglas = _cargar_reglas()
    archivados = _cargar_json(ERRORES_ARCHIVADOS_PATH)

    reglas_agregadas = []
    errores_movidos = []
    errores_restantes = []

    ahora = datetime.now().isoformat()

    for error in errores:
        repeticiones = error.get("repeticiones", 0)
        error_id = error["error_id"]

        if repeticiones >= UMBRAL_REPETICIONES:
            # Agregar regla de no repetir si no existe
            if not error.get("regla_agregada", False) and not _ya_existe_regla_no_repetir(reglas, error_id):
                regla = _construir_regla_no_repetir(error)
                reglas.append(regla)
                error["regla_agregada"] = True
                reglas_agregadas.append(regla["rule_id"])

            # Marcar no_repetir y preparar para mover al archivo
            error["no_repetir"] = True
            error["movido_a_archivo"] = True
            error["fecha_movido_a_archivo"] = ahora
            error["motivo_movido"] = (
                f"Repeticiones >= {UMBRAL_REPETICIONES} ({repeticiones}). "
                "Regla de no repetir agregada a improvement_rules.json"
            )
            archivados.append(error)
            errores_movidos.append(error_id)
        else:
            errores_restantes.append(error)

    # Guardar cambios
    _guardar_json(ERRORES_COMETIDOS_PATH, errores_restantes)
    _guardar_json(ERRORES_ARCHIVADOS_PATH, archivados)
    _guardar_reglas(reglas)

    return {
        "reglas_agregadas": reglas_agregadas,
        "errores_movidos": errores_movidos,
        "errores_restantes": [e["error_id"] for e in errores_restantes],
        "total_archivados": len(archivados),
    }


def obtener_resumen() -> Dict:
    """Retorna un resumen del estado actual de errores cometidos."""
    activos = _cargar_json(ERRORES_COMETIDOS_PATH)
    archivados = _cargar_json(ERRORES_ARCHIVADOS_PATH)
    reglas = _cargar_reglas()

    reglas_no_repetir = [
        r for r in reglas if r.get("no_repetir") is True
    ]

    return {
        "errores_activos": len(activos),
        "errores_archivados": len(archivados),
        "errores_con_regla_no_repetir": len(reglas_no_repetir),
        "reglas_no_repetir": [r["rule_id"] for r in reglas_no_repetir],
        "umbral_repeticiones": UMBRAL_REPETICIONES,
    }


if __name__ == "__main__":
    resumen = procesar_reglas_y_mover()
    print("=== Procesamiento de errores cometidos ===")
    print(f"Reglas de 'no repetir' agregadas: {resumen['reglas_agregadas']}")
    print(f"Errores movidos a archivo (>= {UMBRAL_REPETICIONES} repeticiones): {resumen['errores_movidos']}")
    print(f"Errores restantes activos: {resumen['errores_restantes']}")
    print(f"Total archivados: {resumen['total_archivados']}")
    print()
    print("=== Resumen general ===")
    print(json.dumps(obtener_resumen(), indent=2, ensure_ascii=False))
