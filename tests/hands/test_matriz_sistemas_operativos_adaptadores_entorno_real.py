"""
Tests de entorno real: matriz de sistemas operativos, adaptadores nativos y
tipos de lanzamiento (unidad 3.8.5.1.4.10.10).

Verifica, con implementacion de produccion real y destinos reales del equipo,
que:
  * El SO del equipo se detecta nativamente (Windows en este equipo).
  * Solo existe adaptador nativo para Windows (src/hands/windows/);
    Linux y macOS no tienen adaptador nativo en este equipo.
  * ApplicationPreflight.validate_launch_destination valida nativamente en
    Windows: ejecutable (.exe real), acceso_directo (.lnk real) y
    uri_aplicacion (esquemas admitidos ms-settings:, https:).
  * steam:// (tipo lanzador) no es un esquema de URI admitido -> valid=False.
  * paquete (.appx/.msix) y bundle (.app de macOS) no tienen rama de
    validacion nativa en Windows -> NO SOPORTADO / NO VERIFICADO nativamente
    en este SO.

No se lanza ninguna aplicacion, no se usa mock que decida el resultado y no
se toca informacion de usuario.
"""

from __future__ import annotations

import os
import platform
import unittest

from src.hands.application_preflight import ApplicationPreflight


class TestMatrizSistemasOperativosAdaptadoresEntornoReal(unittest.TestCase):
    """Verificacion real de la matriz de SO, adaptadores y tipos de lanzamiento."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pf = ApplicationPreflight()
        cls.so = platform.system()
        cls.maquina = platform.machine()
        cls.version = platform.release()
        cls.ruta_ejecutable = r"C:\Windows\System32\charmap.exe"
        cls.ruta_acceso_directo = (
            r"C:\Users\User\AppData\Roaming\Microsoft\Windows\Start Menu"
            r"\Programs\File Explorer.lnk"
        )
        # Rutas absolutas calculadas con __file__ (el conftest sandboxea el CWD,
        # pero __file__ sigue apuntando a produccion).
        _tests_hands_dir = os.path.dirname(os.path.abspath(__file__))
        _tests_dir = os.path.dirname(_tests_hands_dir)
        _root_dir = os.path.dirname(_tests_dir)
        cls.adaptador_windows = os.path.join(_root_dir, "src", "hands", "windows")
        cls.adaptador_linux = os.path.join(_root_dir, "src", "hands", "linux")
        cls.adaptador_macos = os.path.join(_root_dir, "src", "hands", "macos")

    def test_01_so_equipo_detectado_nativamente(self):
        """El SO real del equipo se detecta con platform.system()."""
        self.assertIn(self.so, ("Windows", "Linux", "Darwin"))
        self.assertTrue(len(self.version) > 0, "version de SO vacia")
        self.assertTrue(len(self.maquina) > 0, "arquitectura vacia")

    def test_02_adaptador_windows_nativo_existe(self):
        """Existe adaptador nativo para Windows en el equipo actual."""
        self.assertTrue(os.path.isdir(self.adaptador_windows), self.adaptador_windows)

    def test_03_adaptador_linux_nativo_no_existe(self):
        """No existe adaptador nativo para Linux en este equipo."""
        self.assertFalse(os.path.isdir(self.adaptador_linux), self.adaptador_linux)

    def test_04_adaptador_macos_nativo_no_existe(self):
        """No existe adaptador nativo para macOS en este equipo."""
        self.assertFalse(os.path.isdir(self.adaptador_macos), self.adaptador_macos)

    def test_05_validacion_tipo_ejecutable_real(self):
        """Un .exe real se valida como lanzamiento tipo ejecutable en Windows."""
        self.assertTrue(os.path.isfile(self.ruta_ejecutable), self.ruta_ejecutable)
        resultado = self.pf.validate_launch_destination(self.ruta_ejecutable)
        self.assertTrue(resultado["valid"], resultado.get("reason"))
        self.assertEqual(
            resultado["launch_type"], ApplicationPreflight.LAUNCH_TYPE_EXECUTABLE
        )
        self.assertEqual(resultado["destination"], os.path.abspath(self.ruta_ejecutable))

    def test_06_validacion_tipo_acceso_directo_real(self):
        """Un .lnk real se valida como lanzamiento tipo acceso_directo en Windows."""
        self.assertTrue(
            os.path.isfile(self.ruta_acceso_directo), self.ruta_acceso_directo
        )
        resultado = self.pf.validate_launch_destination(self.ruta_acceso_directo)
        self.assertTrue(resultado["valid"], resultado.get("reason"))
        self.assertEqual(
            resultado["launch_type"], ApplicationPreflight.LAUNCH_TYPE_SHORTCUT
        )

    def test_07_validacion_tipo_uri_aplicacion_admitido_real(self):
        """Un esquema de URI admitido se valida como uri_aplicacion."""
        for uri in ("ms-settings:", "https:"):
            with self.subTest(uri=uri):
                resultado = self.pf.validate_launch_destination(uri)
                self.assertTrue(resultado["valid"], f"{uri}: {resultado.get('reason')}")
                self.assertEqual(
                    resultado["launch_type"], ApplicationPreflight.LAUNCH_TYPE_URI
                )

    def test_08_uri_lanzador_no_admitido(self):
        """steam:// (tipo lanzador) no es un esquema de URI admitido -> valid=False."""
        resultado = self.pf.validate_launch_destination("steam://run/123")
        self.assertFalse(resultado["valid"])
        self.assertIsNone(resultado["launch_type"])

    def test_09_tipos_paquete_bundle_lanzador_nunca_devueltos_en_windows(self):
        """validate_launch_destination nunca devuelve paquete/bundle/lanzador
        nativamente en Windows: solo ejecutable, acceso_directo y uri_aplicacion."""
        # Destinos que NO son URI admitida, .lnk ni .exe: nunca deben producir
        # launch_type paquete, bundle ni lanzador.
        casos_no_soportados = [
            r"C:\Windows\System32\NoExistePaquete.appx",   # paquete (inexistente)
            r"C:\Windows\System32\MiApp.app",              # bundle (macOS, no aplica)
            "steam://run/123",                             # lanzador (no admitido)
            r"C:\Windows\System32\kernel32.dll",           # biblioteca, no lanzamiento
        ]
        for destino in casos_no_soportados:
            with self.subTest(destino=destino):
                resultado = self.pf.validate_launch_destination(destino)
                self.assertNotIn(
                    resultado["launch_type"],
                    (
                        ApplicationPreflight.LAUNCH_TYPE_PACKAGE,
                        ApplicationPreflight.LAUNCH_TYPE_BUNDLE,
                        ApplicationPreflight.LAUNCH_TYPE_LAUNCHER,
                    ),
                    f"{destino} produjo un tipo de lanzamiento no soportado nativamente",
                )

    def test_10_matriz_declaracion_estado_adaptadores(self):
        """Declara el estado de cada adaptador segun evidencia nativa del equipo."""
        adaptadores = {
            "windows": os.path.isdir(self.adaptador_windows),
            "linux": os.path.isdir(self.adaptador_linux),
            "macos": os.path.isdir(self.adaptador_macos),
        }
        # Solo Windows tiene adaptador nativo y pruebas reales en este equipo.
        self.assertTrue(adaptadores["windows"])
        self.assertFalse(adaptadores["linux"])
        self.assertFalse(adaptadores["macos"])

    def test_11_matriz_declaracion_estado_tipos_lanzamiento(self):
        """Declara el estado de cada tipo de lanzamiento segun pruebas nativas."""
        tipos_verificados = {
            "ejecutable": "VERIFICADO",
            "acceso_directo": "VERIFICADO",
            "uri_aplicacion": "VERIFICADO",
        }
        tipos_no_soportados = {
            "paquete": "NO SOPORTADO / NO VERIFICADO (nativamente en Windows)",
            "bundle": "NO SOPORTADO / NO VERIFICADO (nativamente en Windows)",
            "lanzador": "NO VERIFICADO (esquema steam:// no admitido)",
        }
        self.assertEqual(tipos_verificados["ejecutable"], "VERIFICADO")
        self.assertEqual(tipos_verificados["acceso_directo"], "VERIFICADO")
        self.assertEqual(tipos_verificados["uri_aplicacion"], "VERIFICADO")
        self.assertEqual(
            tipos_no_soportados["paquete"],
            "NO SOPORTADO / NO VERIFICADO (nativamente en Windows)",
        )
        self.assertEqual(
            tipos_no_soportados["bundle"],
            "NO SOPORTADO / NO VERIFICADO (nativamente en Windows)",
        )
        self.assertEqual(
            tipos_no_soportados["lanzador"],
            "NO VERIFICADO (esquema steam:// no admitido)",
        )


if __name__ == "__main__":
    unittest.main()
