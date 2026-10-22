"""Actualiza `prompt_mejoraActual.txt` con el cierre de la unidad 2.8.8.9.8.4.2.

- Actualiza el BLOQUE DE ESTADO PERSISTENTE (los cuatro campos).
- Anade el REGISTRO CANONICO de la unidad al final del fichero.
- Conserva la CODIFICACION (UTF-8 sin BOM) y el FINAL DE LINEA (CRLF) del fichero.
"""
import io
import os

PROMPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                      "prompt_mejoraActual.txt")

ESTADO_VIEJO = (
    "CURRENT_PHASE: 2.8.8\r\n"
    "CURRENT_WORK_UNIT: 2.8.8.9.8.4.2\r\n"
    "CURRENT_WORK_STATUS: PENDIENTE\r\n"
    "LAST_COMPLETED_UNIT: 2.8.8.9.8.4.1\r\n"
)

ESTADO_NUEVO = (
    "CURRENT_PHASE: 2.8.8\r\n"
    "CURRENT_WORK_UNIT: 2.8.8.9.8.4.3\r\n"
    "CURRENT_WORK_STATUS: PENDIENTE\r\n"
    "LAST_COMPLETED_UNIT: 2.8.8.9.8.4.2\r\n"
)

REGISTRO = """REGISTRO DE UNIDAD: 2.8.8.9.8.4.2
FECHA: 2026-10-22
ESTADO: IMPLEMENTADA
OBJETIVO: Corregir la identidad INVENTADA y la COLISION de filas de regla con `rule_id` no-string, y unificar la via de LISTA con la de CONTENEDOR.
TIPO DE TRABAJO: CORRECCION DE CODIGO | TEST
CAMBIOS / HALLAZGOS:
- HALLAZGO E1 (IDENTIDAD INVENTADA): el FORMATO REAL declara `rule_id` como el campo de identidad y lo declara ademas como CADENA. El cargador, sin embargo, registraba la fila con la identidad INVENTADA `None` cuando `rule_id` no era una cadena, y tambien cuando `rule_id` era una cadena de solo espacios (el filtro `if not row.get("rule_id")` solo rechaza lo FALSO). Una identidad que el FORMATO REAL no declara no es una identidad.
- HALLAZGO E2 (COLISION QUE PISA): dos filas con la MISMA identidad se registraban en el mismo `loaded[rule_id]`: la SEGUNDA SOBREESCRIBIA a la primera y la primera DESAPARECIA del estado sin dejar rastro (2 filas en el fichero -> 1 regla en el estado, la segunda). La identidad de la segunda fila NO identifica a la primera, de modo que sobrescribirla es una perdida de datos.
- HALLAZGO E3 (VIAS CONTRADICTORIAS): la via de LISTA y la de CONTENEDOR se comportaban de forma OPUESTA con la MISMA fila: por LISTA se registraba con identidad inventada, por CONTENEDOR se DESCARTABA, porque `_recuperar_contenedor_de_reglas` exigia por su cuenta una fila valida por el FORMATO REAL. El mismo dato producia dos resultados distintos.
- CORRECCION (IDENTIDAD REGISTRABLE): `_identidad_de_regla` obtiene la IDENTIDAD REGISTRABLE de una fila: un `rule_id` que sea una CADENA NO VACIA. Si la fila no tiene identidad utilizable devuelve `None` y la fila NO se registra: el cargador NUNCA inventa una identidad. La identidad se comprueba ANTES de registrar y en el MISMO sitio para las dos vias. `_campo_de_identidad` la toma del FORMATO REAL declarado, de modo que la regla de la identidad no esta escrita a mano en el codigo.
- CORRECCION (COLISION): `_procesar_fila_de_regla` lleva el conjunto de identidades ya registradas. Una fila cuya identidad YA usa otra fila se RECHAZA (su identidad ya identifica a otra fila, asi que no la identifica a ella): la PRIMERA registrada sobrevive y la segunda se descarta, de modo que ninguna fila pisa a otra y la perdida es EXPLICITA en el log en lugar de silenciosa.
- CORRECCION (VIAS UNIFICADAS): la via de LISTA y la de CONTENEDOR pasan por el MISMO pipeline, `_procesar_fila_de_regla` (identidad -> colision -> desviaciones del FORMATO REAL -> recuperacion a nivel de CAMPO). `_recuperar_contenedor_de_reglas` se sustituye por `_valores_del_contenedor_de_reglas`, que se limita a extraer los VALORES del mapeo (sin exigir por su cuenta la validez de la fila) y deja el juicio al pipeline comun. Las claves del contenedor NO se usan como identidad.
- CORRECCION (DETECCION): la DETECCION de la clase `adaptation_rules.row_missing_identity` usa ahora la MISMA regla de identidad registrable, de modo que el DETECTOR y el CARGADOR coinciden: la sonda que los contrasta ve la MISMA fila descartada por los dos, y no una descartada por uno y aceptada por el otro.
- CONTRATO (IDENTIDAD NO RECUPERABLE): `_desviaciones_de_regla` deja de reportar el campo de identidad como desviacion, porque la identidad NO se RECUPERA: no hay valor por defecto que ponerme, de modo que o vale o la fila se rechaza ENTERA y sus HERMANAS sobreviven. El texto declarado de `adaptation_rules.row_missing_identity` (`reason` y `note`) refleja ahora el comportamiento real, incluida la colision.
- NO SE INVENTA NADA: el motor no fabrica identidades, no convierte una colision en un reemplazo silencioso y no reescribe los ficheros de persistencia. El FORMATO REAL es la unica fuente de lo que es una identidad.
ARCHIVOS MODIFICADOS:
- PRODUCCION: `src/utils/contextual_adaptation_engine.py` (`_campo_de_identidad`, `_identidad_de_regla`, `_procesar_fila_de_regla`, `_valores_del_contenedor_de_reglas`, `_desviaciones_de_regla`, `load_adaptation_rules`, `_deteccion`, `_CORRUPTION_CRITERIA`, `_RECOVERABLE_DATA`).
- TESTS: `tests/utils/contextual_adaptation_engine/test_2_8_8_9_8_4_2_identidad_inventada.py` (nuevo; test permanente, 24 tests).
- DOCUMENTACION: `README.md` (metodos del pipeline de identidad y su comportamiento), `prompt_mejoraActual.txt`.
TESTS Y RESULTADOS:
- UNITARIOS: `tests/utils/contextual_adaptation_engine/test_2_8_8_9_8_4_2_identidad_inventada.py` - 24 PASSED / 0 FAILED / TOTAL 24 (el FORMATO REAL declara la identidad y su tipo; una fila sin identidad registrable NO se registra en sus cuatro variantes; la fila rechazada NO llega al estado; las dos vias dan el MISMO resultado; la colision NO pisa la regla ya registrada, ni por la via de LISTA ni por la de CONTENEDOR; la DETECCION senala la MISMA fila que el cargador descarta).
- INTEGRACION: `tests/utils/contextual_adaptation_engine/` - 692 PASSED / 0 FAILED, 41 subtests (suite completa del motor, incluye la regresion de las 27 clases de corrupcion y de la recuperacion parcial).
- NO REGRESION: 692 PASSED / 0 FAILED, con baseline comparable de 668 PASSED / 0 FAILED (668 previos + 24 nuevos, 0 regresiones). PRUEBA DE QUE EL TEST DETECTA EL DEFECTO: el mismo test ejecutado contra el codigo PRE-fix (14 FAILED / 10 PASSED) demuestra que falla sin la correccion y que no es un test tautologico.
VERIFICACION:
- SINTAXIS: OK (el motor se importa y se ejecuta correctamente dentro de la suite, sin fallo de importacion; el test permanente lo carga y lo ejecuta).
- MAIN.PY: NO APLICA (la hoja no toca el arranque de la aplicacion: `main.py` no referencia el motor de adaptacion contextual ni sus APIs modificadas).
- COMPORTAMIENTO / INTEGRACION REAL: el test permanente se ejecuta de forma independiente (`python -m pytest tests/utils/contextual_adaptation_engine/test_2_8_8_9_8_4_2_identidad_inventada.py`): 24 PASSED / 0 FAILED. La suite del motor se ejecuta de forma independiente (`python -m pytest tests/utils/contextual_adaptation_engine/`): 692 PASSED / 0 FAILED, 41 subtests.
- AISLAMIENTO: los tests crean el motor con `data_dir` TEMPORAL, de modo que la persistencia de PRODUCCION no se toca: los ficheros de persistencia de `data/` (`goal_adaptation_feedback.json`, `goal_adaptation_learning_results.json`) conservan su fecha del 20/10/2026 y los otros dos (`contextual_adaptation_rules.json`, `contextual_knowledge_base.json`) no existen en `data/`. El motor NO reescribe los ficheros que carga.
DISCREPANCIAS: el contrato declarado `adaptation_rules.row_missing_identity` afirmaba "sin `rule_id` no hay identidad: la fila no se puede registrar y no se inventa una", pero el runtime registraba la fila con la identidad INVENTADA `None` y, al colisionar, hacia que la segunda fila sobreescribiera a la primera; ademas, la via de LISTA y la de CONTENEDOR se contradecian con la misma fila. RESOLUCION (2026-10-22): el runtime hace ahora lo que el contrato declara; el texto del contrato se actualiza para recoger que un `rule_id` que no es una cadena no vacia tampoco es identidad y que una identidad ya usada por otra fila tampoco identifica a la que colisiona; y la contradiccion entre las dos vias queda RESUELTA por el pipeline unico. Se conserva el antecedente del hallazgo (E1/E2/E3 de la hoja 2.8.8.9.8.4) como registro explicito de la RESOLUCION.
PENDIENTES: 2.8.8.9.8.4.3 - declarar en `field_defaults` el valor por defecto de `condition_pattern` que usa el cargador (`""`): la recuperacion le sigue asignando `None` porque el campo no tiene valor por defecto declarado (HALLAZGO E5/D2 de la hoja 2.8.8.9.8.4), y esta hoja no lo corrige porque es una unidad distinta. 2.8.8.9.8.4.4 - evitar que la carga del fichero de feedback sobrescriba la seccion `goal_adaptation_feedback` sana de la base (HALLAZGO D3 de la hoja 2.8.8.9.8.4). 2.8.8.9.8.4 - sigue PARCIALMENTE IMPLEMENTADA hasta cerrar 2.8.8.9.8.4.3 y 2.8.8.9.8.4.4.
ESTADO FINAL: 2.8.8.9.8.4.2 - IMPLEMENTADA
"""


def main() -> int:
    with io.open(PROMPT, "rb") as handle:
        crudo = handle.read()
    texto = crudo.decode("utf-8")

    if ESTADO_NUEVO in texto:
        print("AVISO: el bloque de estado ya estaba actualizado; no se duplica")
    else:
        if ESTADO_VIEJO not in texto:
            print("ERROR: no se encuentra el bloque de estado esperado")
            return 1
        texto = texto.replace(ESTADO_VIEJO, ESTADO_NUEVO, 1)

    if "REGISTRO DE UNIDAD: 2.8.8.9.8.4.2" in texto:
        print("AVISO: el registro ya existe; no se anade dos veces")
    else:
        if not texto.endswith("\r\n"):
            texto += "\r\n"
        if not texto.endswith("\r\n\r\n"):
            texto += "\r\n"
        texto += REGISTRO.replace("\n", "\r\n")

    with io.open(PROMPT, "wb") as handle:
        handle.write(texto.encode("utf-8"))
    print("OK: prompt_mejoraActual.txt actualizado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
