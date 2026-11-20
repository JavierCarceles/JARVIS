# -*- coding: ascii -*-
"""
Eleccion de destino cuando el descubrimiento de Windows devuelve varios.

`preferir_destino_de_la_misma_aplicacion` solo elige cuando todos los
destinos son la MISMA aplicacion del propio Windows expuesta por varias vias
(paquete + stub de System32, o System32 + copia en WindowsApps). Con dos
aplicaciones distintas devuelve None y la resolucion queda ambigua.

Multiplataforma: funcion pura sobre rutas de Windows (ntpath), sin APIs nativas.
"""

from __future__ import annotations

import unittest
import unittest.mock
from types import SimpleNamespace

from src.hands.apps.launch_windows import (
    WindowsLaunchAdapter,
    preferir_destino_de_la_misma_aplicacion,
)
from src.hands.apps.platform_launch import (
    AMBIGUOUS,
    RESOLVED,
    TARGET_AUMID,
    TARGET_COMMAND,
    TARGET_EXE,
    LaunchTarget,
)

RAIZ = r"C:\Windows"
AUMID_CALC = "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
WINDOWSAPPS = r"C:\Program Files\WindowsApps"


def _t(target_type: str, target: str, confianza: str = "alta") -> LaunchTarget:
    return LaunchTarget(
        identity="id:%s" % target,
        display_name=target,
        target_type=target_type,
        target=target,
        platform="windows",
        source="prueba",
        evidence={"confianza": confianza},
    )


class TestPaqueteFrenteACopiasDelSistema(unittest.TestCase):
    def test_paquete_y_stub_de_system32_elige_paquete(self):
        paquete = _t(TARGET_AUMID, AUMID_CALC)
        stub = _t(TARGET_EXE, RAIZ + r"\System32\calc.exe")
        self.assertIs(preferir_destino_de_la_misma_aplicacion([stub, paquete], RAIZ), paquete)

    def test_paquete_y_alias_de_windowsapps_elige_paquete(self):
        paquete = _t(TARGET_AUMID, AUMID_CALC)
        alias = _t(TARGET_EXE, r"C:\Users\u\AppData\Local\Microsoft\WindowsApps\calc.exe")
        self.assertIs(preferir_destino_de_la_misma_aplicacion([alias, paquete], RAIZ), paquete)

    def test_stub_con_mayusculas_de_path_y_variable_sin_expandir(self):
        # shutil.which devuelve la carpeta tal como esta en PATH
        # ("C:\WINDOWS\system32") y App Paths puede traer "%windir%".
        paquete = _t(TARGET_AUMID, AUMID_CALC)
        stub = _t(TARGET_EXE, r"C:\WINDOWS\system32\calc.exe")
        with unittest.mock.patch.dict("os.environ", {"windir": RAIZ}):
            variable = _t(TARGET_EXE, r"%windir%\system32\calc.exe")
            self.assertIs(
                preferir_destino_de_la_misma_aplicacion([stub, variable, paquete], RAIZ), paquete
            )

    def test_paquete_y_exe_instalado_por_el_usuario_es_ambiguo(self):
        # Una app con version de la Store y version de escritorio son dos
        # destinos distintos: no se elige en silencio.
        paquete = _t(TARGET_AUMID, "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify")
        escritorio = _t(TARGET_EXE, r"C:\Users\u\AppData\Roaming\Spotify\Spotify.exe")
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([paquete, escritorio], RAIZ))

    def test_dos_paquetes_es_ambiguo(self):
        a = _t(TARGET_AUMID, AUMID_CALC)
        b = _t(TARGET_AUMID, "Otra.Calculadora_123!App")
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([a, b], RAIZ))

    def test_la_confianza_no_decide(self):
        # La regla anterior elegia por confianza; ahora la confianza no rompe
        # una ambiguedad real entre dos aplicaciones distintas.
        a = _t(TARGET_EXE, r"C:\Program Files\Editor A\editor.exe", "alta")
        b = _t(TARGET_EXE, r"C:\Program Files\Editor B\editor2.exe", "baja")
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([a, b], RAIZ))


class TestExeFrenteACopiaDeWindowsApps(unittest.TestCase):
    def test_system32_y_copia_en_windowsapps_elige_system32(self):
        sistema = _t(TARGET_EXE, RAIZ + r"\System32\notepad.exe", "alta")
        copia = _t(TARGET_EXE, WINDOWSAPPS + r"\Microsoft.WindowsNotepad_11.0_x64__8wekyb3d8bbwe\Notepad\Notepad.exe", "baja")
        self.assertIs(preferir_destino_de_la_misma_aplicacion([copia, sistema], RAIZ), sistema)

    def test_comando_sin_ruta_y_copia_en_windowsapps(self):
        comando = _t(TARGET_COMMAND, "notepad")
        copia = _t(TARGET_EXE, WINDOWSAPPS + r"\Microsoft.WindowsNotepad_x\Notepad\notepad.exe")
        self.assertIs(preferir_destino_de_la_misma_aplicacion([comando, copia], RAIZ), comando)

    def test_copia_con_otro_nombre_es_ambigua(self):
        sistema = _t(TARGET_EXE, RAIZ + r"\System32\notepad.exe")
        otra = _t(TARGET_EXE, WINDOWSAPPS + r"\Otra_x\otra.exe")
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([sistema, otra], RAIZ))

    def test_dos_exe_fuera_de_windowsapps_es_ambiguo(self):
        a = _t(TARGET_EXE, RAIZ + r"\System32\notepad.exe")
        b = _t(TARGET_EXE, r"D:\Portables\notepad.exe")
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([a, b], RAIZ))

    def test_un_solo_destino_no_aplica(self):
        self.assertIsNone(preferir_destino_de_la_misma_aplicacion([_t(TARGET_EXE, r"C:\a.exe")], RAIZ))


class TestFromResolutionUsaLaRegla(unittest.TestCase):
    """`_from_resolution` declara ambiguedad cuando la regla no elige."""

    def _adaptador(self, targets_por_candidato):
        adapter = WindowsLaunchAdapter.__new__(WindowsLaunchAdapter)
        adapter._candidate_to_target = lambda c: targets_por_candidato[c]
        return adapter

    def test_dos_aplicaciones_distintas_es_ambiguo(self):
        a = _t(TARGET_EXE, r"C:\Program Files\A\a.exe", "alta")
        b = _t(TARGET_EXE, r"C:\Program Files\B\b.exe", "baja")
        adapter = self._adaptador({"ca": a, "cb": b})
        resolucion = SimpleNamespace(candidatos=["ca", "cb"], alternativas=[], requiere_desambiguacion=False, ambiguo=False)
        outcome = adapter._from_resolution(resolucion, "nativo")
        self.assertEqual(outcome.status, AMBIGUOUS)

    def test_paquete_y_stub_resuelve_paquete(self):
        paquete = _t(TARGET_AUMID, AUMID_CALC)
        stub = _t(TARGET_EXE, r"C:\Windows\System32\calc.exe")
        adapter = self._adaptador({"p": paquete, "s": stub})
        resolucion = SimpleNamespace(candidatos=["s", "p"], alternativas=[], requiere_desambiguacion=False, ambiguo=False)
        outcome = adapter._from_resolution(resolucion, "nativo")
        self.assertEqual(outcome.status, RESOLVED)
        self.assertIs(outcome.target, paquete)


if __name__ == "__main__":
    unittest.main()
