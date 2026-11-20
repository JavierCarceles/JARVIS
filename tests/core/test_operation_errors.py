# -*- coding: ascii -*-
"""
Tests de ``src/core/operation_errors.py``: errores estructurados, evidencia
redactada, reintentos acotados e idempotencia.

Comportamientos comprobados:
- ``RetryPolicy``: limite duro de intentos (nunca ilimitados), espera
  exponencial acotada sin dormir de verdad (``sleep`` inyectado), reintento
  solo de fallos reintentables (por defecto, timeouts), conversion del ultimo
  fallo en ``OperationError`` y ``retry_limit`` no reintentable al agotar los
  intentos; un exito corta los reintentos (sin doble ejecucion).
- Idempotencia: una operacion con exito vigente no se repite; caduca por TTL
  o cuando su validador dice que el efecto ya no existe; los fallos no se
  recuerdan.
- Resultado estructurado: ``next_step`` = ``clarify`` (seleccion insegura o
  ambigua con candidatos), ``retry`` (fallo recuperable) o ``abort``.
- ``OperationError``: etapa normalizada, mensaje, instrucciones, candidatos y
  evidencia siempre redactados; conversion de errores del contrato de
  escritorio.
- Redaccion: carpeta y nombre de usuario, rutas de perfiles Windows/POSIX,
  secretos en linea y claves con aspecto de secreto.

Multiplataforma, sin SO ni data/.
"""

from __future__ import annotations

import os
from enum import Enum
from types import SimpleNamespace
from typing import Any, List

import pytest

import src.core.operation_errors as oe
from src.core.operation_errors import (
    HOME_MARKER,
    NEXT_STEP_ABORT,
    NEXT_STEP_CLARIFY,
    NEXT_STEP_NONE,
    NEXT_STEP_RETRY,
    REDACTED,
    USER_MARKER,
    ErrorCode,
    IdempotencyRegistry,
    OperationError,
    OperationFailed,
    OperationOutcome,
    OperationStage,
    RetryPolicy,
    next_step_for,
    redact_evidence,
    redact_text,
)


class _Contador:
    """Funcion que devuelve una secuencia de resultados (o lanza excepciones)."""

    def __init__(self, *resultados: Any) -> None:
        self.resultados = list(resultados)
        self.llamadas = 0

    def __call__(self) -> Any:
        self.llamadas += 1
        valor = self.resultados[min(self.llamadas - 1, len(self.resultados) - 1)]
        if isinstance(valor, BaseException):
            raise valor
        return valor


def _politica(max_attempts: int = 3, registry: Any = None) -> "tuple[RetryPolicy, List[float]]":
    esperas: List[float] = []
    politica = RetryPolicy(max_attempts=max_attempts, base_delay=0.5, max_delay=2.0,
                           registry=registry or IdempotencyRegistry(), sleep=esperas.append)
    return politica, esperas


def _ok(valor: Any) -> bool:
    return valor == "ok"


# ---------------------------------------------------------------------------
# Reintentos acotados
# ---------------------------------------------------------------------------


class TestReintentosAcotados:
    @pytest.mark.parametrize("pedido,efectivo", [(0, 1), (-5, 1), (3, 3), (100, RetryPolicy.MAX_ATTEMPTS_HARD_LIMIT)])
    def test_limite_duro_de_intentos(self, pedido, efectivo):
        assert RetryPolicy(max_attempts=pedido).max_attempts == efectivo

    def test_espera_exponencial_acotada(self):
        politica, _ = _politica()
        assert [politica.delay_for(i) for i in range(5)] == [0.0, 0.5, 1.0, 2.0, 2.0]

    def test_exito_al_primer_intento_no_reintenta(self):
        politica, esperas = _politica()
        fn = _Contador("ok")
        resultado = politica.run(fn, _ok)
        assert resultado.ok and resultado.value == "ok"
        assert fn.llamadas == 1 and resultado.attempts == 1
        assert esperas == []
        assert resultado.next_step == NEXT_STEP_NONE

    def test_timeout_se_reintenta_y_luego_tiene_exito(self):
        politica, esperas = _politica()
        fn = _Contador(TimeoutError("lento"), "ok")
        resultado = politica.run(fn, _ok)
        assert resultado.ok and resultado.attempts == 2
        assert esperas == [0.5]

    def test_timeouts_hasta_el_limite_devuelven_retry_limit_no_reintentable(self):
        politica, esperas = _politica(max_attempts=3)
        fn = _Contador(TimeoutError("lento"))
        resultado = politica.run(fn, _ok, stage=OperationStage.LAUNCH)
        assert not resultado.ok
        assert fn.llamadas == 3 and resultado.attempts == 3
        assert esperas == [0.5, 1.0]
        assert resultado.error.code == ErrorCode.RETRY_LIMIT
        assert resultado.error.retryable is False
        assert resultado.error.evidence["last_code"] == ErrorCode.TIMEOUT
        assert resultado.next_step == NEXT_STEP_ABORT

    def test_fallo_no_reintentable_se_detiene_en_el_primer_intento(self):
        politica, esperas = _politica()
        fn = _Contador("fallo")
        resultado = politica.run(fn, _ok, stage=OperationStage.PREFLIGHT)
        assert fn.llamadas == 1 and esperas == []
        assert resultado.error.code == ErrorCode.VERIFICATION_FAILED
        assert resultado.error.stage == OperationStage.PREFLIGHT

    def test_excepcion_inesperada_se_convierte_en_error_interno(self):
        politica, _ = _politica()
        resultado = politica.run(_Contador(ValueError("roto")), _ok, stage=OperationStage.CALIBRATION)
        assert resultado.error.code == ErrorCode.INTERNAL
        assert "ValueError" in resultado.error.message
        assert resultado.error.stage == OperationStage.CALIBRATION

    def test_to_error_concreto_se_propaga(self):
        politica, _ = _politica()
        concreto = OperationError(OperationStage.PERMISSION, ErrorCode.PERMISSION_DENIED, "sin permiso",
                                  instructions="Conceder el permiso")
        resultado = politica.run(_Contador("fallo"), _ok, to_error=lambda r: concreto)
        assert resultado.error is concreto
        assert resultado.error.instructions == "Conceder el permiso"

    def test_is_retryable_personalizado_y_resultado_fallido_reintentable(self):
        politica, _ = _politica(max_attempts=4)
        fn = _Contador("parcial", "parcial", "ok")
        resultado = politica.run(fn, _ok, is_retryable=lambda r: r == "parcial")
        assert resultado.ok and fn.llamadas == 3

    def test_is_retryable_que_falla_no_reintenta(self):
        politica, _ = _politica()
        fn = _Contador("fallo")

        def explota(_r: Any) -> bool:
            raise RuntimeError("bug")

        resultado = politica.run(fn, _ok, is_retryable=explota)
        assert not resultado.ok and fn.llamadas == 1


# ---------------------------------------------------------------------------
# Idempotencia: no repetir una operacion que ya tuvo exito
# ---------------------------------------------------------------------------


class TestIdempotencia:
    def test_exito_previo_no_se_repite(self):
        registro = IdempotencyRegistry()
        politica, _ = _politica(registry=registro)
        fn = _Contador("ok")
        primero = politica.run(fn, _ok, idempotency_key="open:notepad")
        segundo = politica.run(fn, _ok, idempotency_key="open:notepad")
        assert primero.ok and segundo.ok
        assert fn.llamadas == 1
        assert segundo.from_idempotency_cache and segundo.attempts == 0
        assert segundo.value == "ok"

    def test_los_fallos_no_se_recuerdan(self):
        registro = IdempotencyRegistry()
        politica, _ = _politica(registry=registro)
        fn = _Contador("fallo", "ok")
        assert not politica.run(fn, _ok, idempotency_key="k").ok
        assert politica.run(fn, _ok, idempotency_key="k").ok
        assert fn.llamadas == 2

    def test_validador_que_invalida_permite_repetir(self):
        registro = IdempotencyRegistry()
        politica, _ = _politica(registry=registro)
        vivo = {"proceso": True}
        fn = _Contador("ok")
        politica.run(fn, _ok, idempotency_key="k", still_valid=lambda _v: vivo["proceso"])
        vivo["proceso"] = False
        politica.run(fn, _ok, idempotency_key="k", still_valid=lambda _v: vivo["proceso"])
        assert fn.llamadas == 2

    def test_validador_que_lanza_invalida_la_entrada(self):
        registro = IdempotencyRegistry()

        def explota(_v: Any) -> bool:
            raise OSError("pid desconocido")

        registro.mark_success("k", "ok", still_valid=explota)
        assert registro.get("k") == (False, None)
        assert "k" not in registro.keys()

    def test_ttl_caducado_permite_repetir(self, monkeypatch):
        registro = IdempotencyRegistry()
        reloj = {"t": 100.0}
        monkeypatch.setattr(oe.time, "monotonic", lambda: reloj["t"])
        registro.mark_success("k", "ok", ttl_seconds=5.0)
        reloj["t"] = 104.0
        assert registro.get("k") == (True, "ok")
        reloj["t"] = 106.0
        assert registro.get("k") == (False, None)

    def test_forget_y_clear(self):
        registro = IdempotencyRegistry()
        registro.mark_success("a", 1)
        registro.mark_success("b", 2)
        registro.forget("a")
        assert registro.keys() == ["b"]
        registro.clear()
        assert registro.keys() == []


# ---------------------------------------------------------------------------
# Resultado estructurado: reintento / aclaracion / abortar
# ---------------------------------------------------------------------------


class TestSiguientePaso:
    def test_seleccion_ambigua_pide_aclaracion_con_candidatos(self):
        error = OperationError(OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS, "Varias coincidencias",
                               needs_clarification=True, candidates=["Chrome", "Chrome Beta"])
        resultado = OperationOutcome.failure(error, attempts=1)
        assert resultado.next_step == NEXT_STEP_CLARIFY
        assert "Opciones: Chrome, Chrome Beta." in error.user_message()

    def test_fallo_recuperable_sugiere_reintento(self):
        error = OperationError(OperationStage.WINDOW, ErrorCode.TIMEOUT, "sin ventana", retryable=True)
        assert OperationOutcome.failure(error).next_step == NEXT_STEP_RETRY
        assert next_step_for(error) == NEXT_STEP_RETRY

    def test_fallo_definitivo_aborta(self):
        error = OperationError(OperationStage.PREFLIGHT, ErrorCode.PREFLIGHT_BLOCKED, "bloqueada")
        assert OperationOutcome.failure(error).next_step == NEXT_STEP_ABORT
        assert next_step_for(None) == NEXT_STEP_NONE

    def test_user_message_muestra_como_maximo_cinco_opciones(self):
        error = OperationError(OperationStage.RESOLUTION, ErrorCode.AMBIGUOUS, "Cual?",
                               needs_clarification=True, candidates=["a%d" % i for i in range(8)])
        assert "a4" in error.user_message() and "a5" not in error.user_message()

    def test_to_dict_del_resultado_redacta_el_valor(self):
        home = os.path.expanduser("~")
        resultado = OperationOutcome(True, {"ruta": os.path.join(home, "secreto.txt")}, attempts=1)
        assert home not in str(resultado.to_dict())

    def test_operation_failed_transporta_el_error(self):
        error = OperationError(OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED, "no arranco")
        excepcion = OperationFailed(error)
        assert excepcion.error is error
        assert "no arranco" in str(excepcion)


# ---------------------------------------------------------------------------
# OperationError y conversion de errores del contrato de escritorio
# ---------------------------------------------------------------------------


class TestOperationError:
    def test_etapa_como_texto_se_normaliza_y_la_desconocida_es_verificacion(self):
        assert OperationError("launch", ErrorCode.LAUNCH_FAILED, "x").stage == OperationStage.LAUNCH
        assert OperationError("inexistente", ErrorCode.INTERNAL, "x").stage == OperationStage.VERIFICATION

    def test_campos_de_texto_y_evidencia_se_redactan(self):
        home = os.path.expanduser("~")
        error = OperationError(
            OperationStage.LAUNCH, ErrorCode.LAUNCH_FAILED,
            "Fallo al abrir %s" % os.path.join(home, "app.exe"),
            candidates=[os.path.join(home, "otra.exe")],
            evidence={"api_key": "abc123", "ruta": os.path.join(home, "x"), "intentos": 2},
            instructions="token=zzz9 en %s" % home,
        )
        texto = str(error.to_dict())
        assert home not in texto
        assert "abc123" not in texto and "zzz9" not in texto
        assert error.evidence["api_key"] == REDACTED
        assert error.evidence["intentos"] == 2
        assert str(error).startswith("[launch:launch_failed]")

    @pytest.mark.parametrize("codigo,esperado,reintentable", [
        ("timeout", ErrorCode.TIMEOUT, True),
        ("permission_denied", ErrorCode.PERMISSION_DENIED, False),
        ("window_gone", ErrorCode.WINDOW_NOT_FOUND, False),
        ("dependency_missing", ErrorCode.ADAPTER_MISSING, False),
        ("codigo_nuevo", "codigo_nuevo", False),
    ])
    def test_from_platform_error(self, codigo, esperado, reintentable):
        plataforma = SimpleNamespace(
            code=SimpleNamespace(value=codigo), message="fallo nativo", instructions="Hacer X",
            operation="move_window_to_display", platform="windows",
        )
        error = OperationError.from_platform_error(plataforma, OperationStage.WINDOW)
        assert error.code == esperado
        assert error.retryable is reintentable
        assert error.instructions == "Hacer X"
        assert error.evidence["platform_code"] == codigo
        assert error.evidence["operation"] == "move_window_to_display"


# ---------------------------------------------------------------------------
# Redaccion de evidencia
# ---------------------------------------------------------------------------


class _Color(Enum):
    ROJO = "rojo"


class TestRedaccion:
    def test_ruta_de_perfil_windows(self):
        assert redact_text(r"C:\Users\juanito\Documents\informe.docx") == "C:\\Users\\%s\\Documents\\informe.docx" % USER_MARKER

    def test_ruta_de_perfil_posix(self):
        assert redact_text("/Users/anita/Library/x") == "/Users/%s/Library/x" % USER_MARKER
        assert redact_text("/home/pepe/.config") == "/home/%s/.config" % USER_MARKER

    def test_carpeta_de_usuario_actual(self):
        home = os.path.expanduser("~")
        resultado = redact_text(os.path.join(home, "a.txt"))
        assert home not in resultado
        assert HOME_MARKER in resultado or USER_MARKER in resultado

    @pytest.mark.parametrize("texto,secreto", [
        ("password=hunter2", "hunter2"),
        ("token: abcdef", "abcdef"),
        ("api_key=KEY-1 resto", "KEY-1"),
        ("Bearer eyJhbGciOi", "eyJhbGciOi"),
    ])
    def test_secretos_en_linea(self, texto, secreto):
        resultado = redact_text(texto)
        assert secreto not in resultado
        assert REDACTED in resultado

    def test_claves_con_aspecto_de_secreto_y_estructuras_anidadas(self):
        datos = {
            "Authorization": "Bearer xyz",
            "cookie": "a=b",
            "session_id": "s1",
            "lista": [{"password": "p"}, ("t", r"C:\Users\juanito\x")],
            "color": _Color.ROJO,
            "numero": 3, "nada": None, "booleano": True,
        }
        limpio = redact_evidence(datos)
        assert limpio["Authorization"] == REDACTED
        assert limpio["cookie"] == REDACTED
        assert limpio["session_id"] == REDACTED
        assert limpio["lista"][0]["password"] == REDACTED
        assert isinstance(limpio["lista"][1], tuple)
        assert "juanito" not in str(limpio)
        assert limpio["color"] == "rojo"
        assert (limpio["numero"], limpio["nada"], limpio["booleano"]) == (3, None, True)
        # La entrada original no se modifica.
        assert datos["cookie"] == "a=b"

    def test_profundidad_limitada(self):
        anidado: Any = "fondo"
        for _ in range(30):
            anidado = [anidado]
        resultado = redact_evidence(anidado)
        while isinstance(resultado, list):
            resultado = resultado[0]
        assert resultado == REDACTED

    def test_objetos_con_to_dict_se_redactan(self):
        class _ConDict:
            def to_dict(self) -> dict:
                return {"token": "t0p"}

        assert redact_evidence(_ConDict()) == {"token": REDACTED}
