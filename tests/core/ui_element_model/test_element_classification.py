"""
Tests unitarios de clasificacion de elementos UI - unidad 3.8.6.3.3.10.

Pruebas puras de logica/contrato (sin GUI ni modelos):
- El enum ElementClassification expone las 8 categorias del roadmap.
- classify_element clasifica segun la evidencia de interactividad.
- Solo UIA_ACTIONABLE acredita interactividad verificada (patron de accion
  UIA utilizable, habilitado, visible y dentro de pantalla).
- Un elemento detectado solo visualmente queda como candidato sin verificar.
"""

from __future__ import annotations

import unittest

from src.core.ui_element_model import (
    ElementClassification,
    classify_element,
    UIElementData,
)


class TestElementClassificationEnum(unittest.TestCase):
    """El enum expone exactamente las categorias del roadmap."""

    def test_categorias_esperadas(self):
        valores = {e.value for e in ElementClassification}
        esperado = {
            "uia_actionable",
            "visual_interactable_candidate",
            "text_label",
            "container",
            "static_content",
            "offscreen",
            "disabled",
            "unknown",
        }
        self.assertEqual(valores, esperado)

    def test_son_strings(self):
        for e in ElementClassification:
            self.assertIsInstance(e.value, str)


class TestClassifyElement(unittest.TestCase):
    """Logica pura de clasificacion."""

    def _uia(self, patterns=(), enabled=True, visible=True, offscreen=False):
        return dict(
            uia_patterns=list(patterns),
            enabled=enabled,
            visible=visible,
            offscreen=offscreen,
        )

    def test_elemento_sin_evidencia_es_unknown(self):
        self.assertEqual(
            classify_element(UIElementData()), ElementClassification.UNKNOWN
        )

    def test_boton_con_patron_invoke_es_uia_actionable(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Invoke"])),
            ElementClassification.UIA_ACTIONABLE,
        )

    def test_boton_con_patron_valor_es_uia_actionable(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Value"])),
            ElementClassification.UIA_ACTIONABLE,
        )

    def test_boton_con_varios_patrones_uno_actionable_es_uia_actionable(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Scroll", "Invoke"])),
            ElementClassification.UIA_ACTIONABLE,
        )

    def test_boton_sin_patron_uia_es_candidato_visual(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e),
            ElementClassification.VISUAL_INTERACTABLE_CANDIDATE,
        )

    def test_icono_visual_con_geometria_es_candidato_no_estatico(self):
        e = UIElementData(
            type="element", interactive=True, bbox=[10, 10, 50, 50], center=[30, 30]
        )
        self.assertEqual(
            classify_element(e),
            ElementClassification.VISUAL_INTERACTABLE_CANDIDATE,
        )

    def test_elemento_generico_sin_geometria_es_estatico(self):
        e = UIElementData(type="element")
        self.assertEqual(
            classify_element(e), ElementClassification.STATIC_CONTENT
        )

    def test_elemento_generico_interactivo_sin_geometria_es_estatico(self):
        e = UIElementData(type="element", interactive=True)
        self.assertEqual(
            classify_element(e), ElementClassification.STATIC_CONTENT
        )

    def test_etiqueta_de_texto_es_text_label(self):
        e = UIElementData(type="text", text="Etiqueta")
        self.assertEqual(
            classify_element(e), ElementClassification.TEXT_LABEL
        )

    def test_menu_es_contenedor(self):
        e = UIElementData(type="menu", name="Menu")
        self.assertEqual(
            classify_element(e), ElementClassification.CONTAINER
        )

    def test_toolbar_es_contenedor(self):
        e = UIElementData(type="toolbar", name="Barra")
        self.assertEqual(
            classify_element(e), ElementClassification.CONTAINER
        )

    def test_link_es_candidato_visual(self):
        e = UIElementData(type="link", text="Ir a")
        self.assertEqual(
            classify_element(e),
            ElementClassification.VISUAL_INTERACTABLE_CANDIDATE,
        )

    def test_fuera_de_pantalla_es_offscreen_incluso_con_patron_uia(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Invoke"], offscreen=True)),
            ElementClassification.OFFSCREEN,
        )

    def test_deshabilitado_es_disabled_incluso_con_patron_uia(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Invoke"], enabled=False)),
            ElementClassification.DISABLED,
        )

    def test_patron_uia_sin_habilitado_ni_visible_no_es_actionable(self):
        e = UIElementData(type="button", name="Aceptar")
        self.assertEqual(
            classify_element(
                e,
                uia_patterns=["Invoke"],
                enabled=False,
                visible=False,
                offscreen=False,
            ),
            ElementClassification.DISABLED,
        )

    def test_patron_no_actionable_no_hace_uia_actionable(self):
        e = UIElementData(type="text", text="Etiqueta")
        self.assertEqual(
            classify_element(e, **self._uia(patterns=["Text"])),
            ElementClassification.TEXT_LABEL,
        )

    def test_tipo_desconocido_es_unknown(self):
        e = UIElementData(type="tipo_inexistente")
        self.assertEqual(
            classify_element(e), ElementClassification.UNKNOWN
        )

    def test_tipo_vacio_es_unknown(self):
        e = UIElementData(type="")
        self.assertEqual(
            classify_element(e), ElementClassification.UNKNOWN
        )


if __name__ == "__main__":
    unittest.main()
