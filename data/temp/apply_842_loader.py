#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplica el bloque nuevo de `load_adaptation_rules` por rango de lineas."""

import io
import os

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "src", "utils", "contextual_adaptation_engine.py")
ENGINE = os.path.normpath(ENGINE)

with io.open(ENGINE, "r", encoding="utf-8") as handle:
    lineas = handle.readlines()

# Bloque a sustituir: lineas 1831..1863 (1-indexadas) -> indices 1830..1862
INI = 1830
FIN = 1863

INI_ESPERADO = "            if not isinstance(rows, list):\n"
FIN_ESPERADO = "                loaded[row[\"rule_id\"]] = AdaptationRule(row[\"rule_id\"]"
assert lineas[INI] == INI_ESPERADO, repr(lineas[INI])
assert lineas[FIN - 1].startswith(FIN_ESPERADO), repr(lineas[FIN - 1])

NUEVO = '''            candidatas: List[Tuple[Any, Any]] = []
            es_contenedor = not isinstance(rows, list)
            if es_contenedor:
                # RECUPERACIÓN PARCIAL (2.8.8.9.7.2): el CONTENEDOR `rules`
                # cambió de FORMA, pero su contenido puede seguir siendo válido:
                # se RECONSTRUYE con los valores que sean MAPEOS y cada uno pasa
                # por el MISMO pipeline de fila que la vía de LISTA. Las claves
                # NO se usan como identidad.
                candidatas = self._valores_del_contenedor_de_reglas(rows)
            else:
                candidatas = [(None, fila) for fila in rows]
            loaded = {}
            identidades: Set[str] = set()
            recuperadas_contenedor: List[Dict[str, Any]] = []
            for clave, fila in candidatas:
                # DETECCIÓN DE CORRUPCIÓN (2.8.8.9.6.3), RECUPERACIÓN PARCIAL
                # (2.8.8.9.7.2) e IDENTIDAD (2.8.8.9.8.4.2): el pipeline descarta
                # la fila que se aparta del FORMATO REAL o que no tiene
                # identidad REGISTRABLE, y recupera la que solo tiene un CAMPO
                # corrupto. Las HERMANAS de la fila descartada sobreviven.
                regla, recuperaciones = self._procesar_fila_de_regla(fila, identidades)
                if regla is None: continue
                identidades.add(regla.rule_id)
                loaded[regla.rule_id] = regla
                if es_contenedor:
                    recuperadas_contenedor.append({"clave": clave, "politica": "adapt_container",
                                                    "rule_id": regla.rule_id})
                if recuperaciones:
                    self._registrar_recuperacion("adaptation_rules", f"fila:{regla.rule_id}", recuperaciones)
                    self.logger.warning("Regla recuperada: campo corrupto por defecto (%s)", regla.rule_id)
            if recuperadas_contenedor:
                self._registrar_recuperacion("adaptation_rules", "bloque:rules", recuperadas_contenedor)
                self.logger.warning("Contenedor de reglas reconstruido: cambio de forma")
'''

nuevas = lineas[:INI] + [NUEVO] + lineas[FIN:]
with io.open(ENGINE, "w", encoding="utf-8", newline="") as handle:
    handle.write("".join(nuevas))
print("OK: bloque sustituido")
