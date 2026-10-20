# -*- coding: utf-8 -*-
"""Plugin pytest: vuelca a JSON el resultado de cada test (para triaje)."""
import json
import os


def pytest_runtest_makereport(item, call):
    rep = item.config.pluginmanager.getplugin("terminalreporter")
    if rep is None:
        return
    if call.when != "call" and not (call.excinfo and call.excinfo.errisinstance(SystemExit)):
        return
    outcome = "passed"
    msg = ""
    if call.excinfo is not None:
        outcome = "failed"
        msg = str(call.excinfo.value)
        if len(msg) > 400:
            msg = msg[:400] + "..."
    data = rep.stats.setdefault("jarvis_json", {})
    data[item.nodeid] = {"outcome": outcome, "msg": msg.replace("\n", " | ")}


def pytest_sessionfinish(session, exitstatus):
    rep = session.config.pluginmanager.getplugin("terminalreporter")
    if rep is None:
        return
    data = rep.stats.get("jarvis_json", {})
    path = os.environ.get("JARVIS_REPORT_JSON")
    if not path:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
