"""Tests de aliases e historial de ConversationMemory.

Cubren:
- carga de aliases estaticos desde un fichero JSON {frase: comando};
- busqueda por texto normalizado (mayusculas, puntuacion, palabra 'jarvis');
- get_alias devuelve siempre un comando, nunca un identificador de objetivo;
- save_alias guarda de forma persistente y sobrevive a un reinicio;
- save_conversation reescribe el historial sin duplicar entradas y lo recorta;
- get_conversation_history elimina duplicados de ficheros antiguos.

Todo ocurre en carpetas temporales: el directorio de trabajo es el sandbox de
tests/conftest.py y el fichero de aliases estaticos se sustituye por uno
temporal. No se leen ni escriben datos reales del proyecto.
"""

import json
from pathlib import Path

import pytest

from src.memory.conversation import ConversationMemory


@pytest.fixture
def memoria(tmp_path, monkeypatch):
    """ConversationMemory aislada con aliases estaticos de prueba."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "jarvis_memory.json").write_text("[]", encoding="utf-8")

    estaticos = tmp_path / "aliases_estaticos.json"
    estaticos.write_text(
        json.dumps(
            {
                "jarvis calibra chrome": "calibrar_chrome",
                "abre chrome": "abrir_chrome",
                "entrada invalida": 123,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ConversationMemory, "STATIC_COMMAND_ALIASES_FILE", str(estaticos))
    monkeypatch.setattr(ConversationMemory, "_static_alias_cache", None)
    yield ConversationMemory()
    ConversationMemory._static_alias_cache = None


def _historial(tmp_path: Path):
    return json.loads((tmp_path / "data" / "conversational_memory.json").read_text(encoding="utf-8"))


class TestAliases:
    def test_carga_aliases_estaticos_validos(self, memoria):
        assert memoria.command_aliases == {
            "jarvis calibra chrome": "calibrar_chrome",
            "abre chrome": "abrir_chrome",
        }

    def test_get_alias_normaliza_el_texto(self, memoria):
        assert memoria.get_alias("jarvis calibra chrome") == "calibrar_chrome"
        assert memoria.get_alias("Calibra Chrome") == "calibrar_chrome"
        assert memoria.get_alias("JARVIS, abre Chrome!") == "abrir_chrome"

    def test_get_alias_desconocido_devuelve_none(self, memoria):
        assert memoria.get_alias("abre una cosa que no existe") is None
        assert memoria.get_alias("") is None

    def test_get_alias_nunca_devuelve_objetivo(self, memoria):
        resultado = memoria.get_alias("abre chrome")
        assert resultado == "abrir_chrome"
        assert not resultado.startswith("GOAL:")

    def test_save_alias_persiste_y_sobrevive_a_reinicio(self, memoria, tmp_path):
        assert memoria.save_alias("Jarvis pon musica tranquila", "abrir_spotify") is True
        guardado = json.loads((tmp_path / "data" / "jarvis_learned_aliases.json").read_text(encoding="utf-8"))
        assert guardado == {"pon musica tranquila": "abrir_spotify"}

        nueva = ConversationMemory()
        assert nueva.get_alias("pon musica tranquila") == "abrir_spotify"

    def test_save_alias_rechaza_entradas_no_validas(self, memoria, tmp_path):
        assert memoria.save_alias("", "abrir_spotify") is False
        assert memoria.save_alias("algo", "") is False
        assert memoria.save_alias("algo", "GOAL:123") is False
        assert not (tmp_path / "data" / "jarvis_learned_aliases.json").exists()

    def test_save_alias_no_deja_temporales(self, memoria, tmp_path):
        memoria.save_alias("frase", "abrir_chrome")
        assert list((tmp_path / "data").glob("*.tmp")) == []


class TestHistorial:
    def test_guardar_no_duplica_y_recorta(self, memoria, tmp_path, monkeypatch):
        limite = 3
        monkeypatch.setattr(
            "src.memory.conversation.get_memory_config",
            lambda: type("Cfg", (), {"max_history_length": limite})(),
        )
        for i in range(5):
            assert memoria.save_conversation(f"pregunta {i}", f"respuesta {i}") is True

        contenidos = [e["content"] for e in _historial(tmp_path)]
        assert contenidos == [
            "pregunta 2", "respuesta 2",
            "pregunta 3", "respuesta 3",
            "pregunta 4", "respuesta 4",
        ]

    def test_historial_duplicado_antiguo_se_limpia(self, memoria, tmp_path):
        memoria.save_conversation("hola", "que tal")
        fichero = tmp_path / "data" / "conversational_memory.json"
        entradas = _historial(tmp_path)
        fichero.write_text(json.dumps(entradas + entradas), encoding="utf-8")

        assert len(memoria.get_conversation_history()) == 2
        memoria.save_conversation("otra", "respuesta")
        assert len(_historial(tmp_path)) == 4

    def test_texto_vacio_no_se_guarda(self, memoria, tmp_path):
        assert memoria.save_conversation("solo usuario", "") is False
        assert memoria.save_conversation("", "solo respuesta") is False
        assert not (tmp_path / "data" / "conversational_memory.json").exists()

    def test_clear_history_vacia_el_fichero(self, memoria, tmp_path):
        memoria.save_conversation("hola", "que tal")
        assert memoria.clear_history() is True
        assert _historial(tmp_path) == []
