p='c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt'
s=open(p,encoding='utf-8').read()
entry = """

REGISTRO DE UNIDAD: 2.8.11.3.7
FECHA: NO REGISTRADA
ESTADO: IMPLEMENTADA
OBJETIVO: Verificar que una propuesta no validada, incompatible o fuera del contrato se rechaza con un resultado identificable.
TIPO DE TRABAJO: VERIFICACION
CAMBIOS / HALLAZGOS:
- Se verifico validate_adapted_goal: devuelve dict con "valid" (bool) y "errors" (lista de strings identificables). Cuando la propuesta es invalida/incompatible/fuera de contrato, errors no esta vacio y valid=False, por lo que el rechazo es identificable mediante el resultado.
ARCHIVOS MODIFICADOS:
- PRODUCCION: NO APLICA
- TESTS: NO APLICA
- DOCUMENTACION: c:/Informatica/PROYECTOS/BACKEND/IA_PYTHON/IA/JARVIS/prompt_mejoraActual.txt
TESTS Y RESULTADOS:
- UNITARIOS: NO EJECUTADOS
- INTEGRACION: NO EJECUTADOS
- NO REGRESION: NO EJECUTADA
VERIFICACION:
- SINTAXIS: NO APLICA
- MAIN.PY: NO EJECUTADO
- COMPORTAMIENTO / INTEGRACION REAL: analisis estatico.
DISCREPANCIAS: NINGUNA REGISTRADA
PENDIENTES: NINGUNO
ESTADO FINAL: 2.8.11.3.7 - IMPLEMENTADA
"""
s=s.replace('CURRENT_WORK_UNIT: 2.8.11.3.7\nCURRENT_WORK_STATUS: EN PROCESO','CURRENT_WORK_UNIT: 2.8.11.3.8\nCURRENT_WORK_STATUS: PENDIENTE')
s=s.rstrip('\n')+entry
open(p,'w',encoding='utf-8').write(s)
print('done')
