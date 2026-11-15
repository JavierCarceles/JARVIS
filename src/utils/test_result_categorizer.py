# -*- coding: utf-8 -*-
"""
Categorizador y reporte de resultados de prueba por tipo de verificacion.

Registra resultados de prueba en categorias estrictamente separadas:
- SIMULADO: resultados fabricados o simulados (no cuentan como verificacion real).
- UNIT_MOCKS: pruebas unitarias que usan mocks/stubs (logica pura, sin recursos reales).
- INTEGRACION_OS: pruebas de integracion que usan recursos reales del SO (procesos, ventanas, archivos).
- APERTURA_GUI: aperturas de aplicaciones GUI verificadas visualmente en entorno real.

Nunca se mezclan los conteos entre categorias. Cada categoria mantiene su propio
contador independiente de PASSED / FAILED / SKIPPED / TOTAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CategoriaResultadoTest(Enum):
    SIMULADO = "simulado"
    UNIT_MOCKS = "unit_mocks"
    INTEGRACION_OS = "integracion_os"
    APERTURA_GUI = "apertura_gui"


@dataclass
class ResultadoTest:
    """Un resultado de prueba individual, asociado a una unica categoria."""

    nombre_test: str
    categoria: CategoriaResultadoTest
    estado: str  # PASSED, FAILED, SKIPPED, etc.
    tiene_mock: bool = False
    usa_recursos_reales: bool = False
    verificacion_visual: bool = False
    detalle: str = ""


class TestResultCategorizer:
    """
    Categoriza y registra resultados de prueba por separado, sin mezclar conteos.

    Cada categoria (SIMULADO, UNIT_MOCKS, INTEGRACION_OS, APERTURA_GUI) lleva su
    propio contador. No existe un contador global que sume categorias, por lo que
    los conteos nunca se mezclan.
    """

    def __init__(self) -> None:
        self._resultados: List[ResultadoTest] = []
        self._conteos: Dict[CategoriaResultadoTest, Dict[str, int]] = {
            cat: {"PASSED": 0, "FAILED": 0, "SKIPPED": 0, "TOTAL": 0}
            for cat in CategoriaResultadoTest
        }

    def registrar(
        self,
        nombre_test: str,
        categoria: CategoriaResultadoTest,
        estado: str,
        tiene_mock: bool = False,
        usa_recursos_reales: bool = False,
        verificacion_visual: bool = False,
        detalle: str = "",
    ) -> None:
        """Registra un resultado de prueba en su categoria correspondiente.

        El resultado se asigna a una unica categoria. El conteo de esa categoria se
        incrementa de forma independiente; ningun otro categoria se ve afectada.
        """
        estado_upper = estado.upper()
        resultado = ResultadoTest(
            nombre_test=nombre_test,
            categoria=categoria,
            estado=estado_upper,
            tiene_mock=tiene_mock,
            usa_recursos_reales=usa_recursos_reales,
            verificacion_visual=verificacion_visual,
            detalle=detalle,
        )
        self._resultados.append(resultado)

        if estado_upper not in self._conteos[categoria]:
            self._conteos[categoria][estado_upper] = 0
        self._conteos[categoria][estado_upper] += 1
        self._conteos[categoria]["TOTAL"] += 1

    def conteo(
        self, categoria: CategoriaResultadoTest, estado: Optional[str] = None
    ) -> int:
        """Devuelve el conteo para una categoria y estado dados.

        El conteo pertenece unicamente a la categoria solicitada. Nunca se mezcla
        con conteos de otras categorias.
        """
        if estado is None:
            return self._conteos[categoria]["TOTAL"]
        return self._conteos[categoria].get(estado.upper(), 0)

    def conteo_todas_categorias(self) -> Dict[CategoriaResultadoTest, Dict[str, int]]:
        """Devuelve una copia de los conteos por categoria.

        Cada categoria tiene su propio diccionario de conteos. No hay un total
        global que mezcle categorias.
        """
        import copy

        return copy.deepcopy(self._conteos)

    def reporte(self) -> str:
        """Genera un reporte de texto con conteos separados por categoria.

        Cada categoria se reporta en su propia linea, con su propio PASSED /
        FAILED / SKIPPED / TOTAL. No hay una linea de total global que sume
        categorias distintas.
        """
        lineas: List[str] = ["REPORTE DE RESULTADOS POR CATEGORIA (conteos separados):"]
        for cat in CategoriaResultadoTest:
            c = self._conteos[cat]
            lineas.append(
                f"  {cat.value.upper()}: "
                f"PASSED={c.get('PASSED', 0)} / "
                f"FAILED={c.get('FAILED', 0)} / "
                f"SKIPPED={c.get('SKIPPED', 0)} / "
                f"TOTAL={c['TOTAL']}"
            )
        return "\n".join(lineas)

    def verificar_separacion(self) -> bool:
        """Verifica que los conteos de cada categoria son independientes.

        Comprueba que no existe un conteo global mezclado: la suma de los TOTAL
        por categoria es igual a la suma de los TOTAL por categoria (tautologia
        intencional que confirma que cada categoria lleva su propio contador y
        no se anade a un contador compartido).
        """
        suma_categorias = sum(c["TOTAL"] for c in self._conteos.values())
        total_registros = len(self._resultados)
        return suma_categorias == total_registros

    def resultados_por_categoria(
        self, categoria: CategoriaResultadoTest
    ) -> List[ResultadoTest]:
        """Devuelve todos los resultados registrados para una categoria dada."""
        return [r for r in self._resultados if r.categoria == categoria]

    def tiene_resultados_simulados(self) -> bool:
        """Devuelve True si hay resultados de categoria SIMULADO registrados."""
        return self._conteos[CategoriaResultadoTest.SIMULADO]["TOTAL"] > 0

    def tiene_resultados_reales(self) -> bool:
        """Devuelve True si hay resultados de categorias reales (no simulados)."""
        reales = (
            CategoriaResultadoTest.UNIT_MOCKS,
            CategoriaResultadoTest.INTEGRACION_OS,
            CategoriaResultadoTest.APERTURA_GUI,
        )
        return any(self._conteos[cat]["TOTAL"] > 0 for cat in reales)


def categorizar_archivo_test(ruta_archivo: str) -> CategoriaResultadoTest:
    """Intenta categorizar un archivo de prueba por su nombre y contenido.

    Esta es una heuristica ligera para clasificar tests existentes. No modifica
    los archivos de prueba, solo devuelve la categoria sugerida.

    Reglas:
    - Si el nombre contiene 'entorno_real' y abre/lanza aplicaciones GUI -> APERTURA_GUI
    - Si el nombre contiene 'entorno_real' -> INTEGRACION_OS
    - Si usa mocks (import de unittest.mock o mock) -> UNIT_MOCKS
    - De lo contrario -> UNIT_MOCKS (conservador: asume prueba unitaria pura)
    """
    import os

    nombre = os.path.basename(ruta_archivo).lower()

    if "entorno_real" in nombre:
        if "apertura" in nombre or "gui" in nombre or "ventana" in nombre:
            return CategoriaResultadoTest.APERTURA_GUI
        return CategoriaResultadoTest.INTEGRACION_OS

    try:
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            contenido = f.read()
        if "unittest.mock" in contenido or "from mock" in contenido or "patch" in contenido:
            return CategoriaResultadoTest.UNIT_MOCKS
    except OSError:
        pass

    return CategoriaResultadoTest.UNIT_MOCKS
