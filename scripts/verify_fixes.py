"""Verificacion de las correcciones aplicadas."""
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

fails = []


def check(name, fn):
    try:
        fn()
        print(f"  OK   {name}")
    except Exception as e:
        print(f"  FAIL {name}: {type(e).__name__}: {e}")
        fails.append(name)


# 1) Alias en mayusculas del StructuredLogger
def t_alias():
    from src.utils.logger import get_logger
    lg = get_logger("test.alias")
    for lvl in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        assert hasattr(lg, lvl), f"falta {lvl}"
        getattr(lg, lvl)("mensaje de prueba %s", "ok")


# 2) Los modulos que usaban logger.ERROR/DEBUG deben importar y tener el metodo
def t_modules():
    import src.mouth.speaker as sp
    import src.utils.screen_manager as sm
    import src.memory.conversation as cv
    for mod in (sp, sm, cv):
        lg = mod.logger
        for lvl in ("DEBUG", "INFO", "WARNING", "ERROR"):
            assert hasattr(lg, lvl), f"{mod.__name__} sin {lvl}"


# 3) El SelfImprovementSystem debe completar un ciclo de aprendizaje sin errores
def t_learning_cycle():
    from src.utils.self_improvement_system import SelfImprovementSystem
    sis = SelfImprovementSystem()
    errors = []
    orig = sis.logger.log

    def spy(msg, *a, **k):
        if k.get("level") == "ERROR" and "Error extrayendo" in str(msg):
            errors.append(msg)
        return orig(msg, *a, **k)

    sis.logger.log = spy
    sis._perform_passive_learning()
    sis.logger.log = orig
    assert not errors, f"errores de extraccion: {errors}"


# 4) El dashboard debe arrancar aunque el puerto este ocupado
def t_dashboard():
    import threading
    from src.utils.log_dashboard import LogDashboard

    d1 = LogDashboard(db_path="logs/dashboard.db", port=5000, host="127.0.0.1")
    d2 = LogDashboard(db_path="logs/dashboard.db", port=5000, host="127.0.0.1")

    t1 = threading.Thread(target=d1.start, daemon=True)
    t1.start()
    t1.join(timeout=5)
    assert d1.is_running, "el primer dashboard no arranco"

    # El segundo debe caerse a un puerto alternativo, no morir
    t2 = threading.Thread(target=d2.start, daemon=True)
    t2.start()
    t2.join(timeout=5)
    assert d2.is_running, "el segundo dashboard no arranco"
    assert d2.active_port != d1.active_port, "el segundo dashboard reuso el puerto"


# 5) PerformanceOptimizer: el bucle de optimizacion no debe romperse
def t_perf():
    from src.utils.performance_optimizer import PerformanceOptimizer
    po = PerformanceOptimizer()
    time.sleep(0.5)
    assert po.models is not None


print("\n== VERIFICACION ==")
check("1. Alias mayusculas en StructuredLogger", t_alias)
check("2. Modulos con logger.ERROR/DEBUG importan bien", t_modules)
check("3. Ciclo de aprendizaje sin 'Error extrayendo'", t_learning_cycle)
check("4. Dashboard arranca con puerto ocupado", t_dashboard)
check("5. PerformanceOptimizer inicializa", t_perf)

print(f"\n{'TODO OK' if not fails else 'FALLOS: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
