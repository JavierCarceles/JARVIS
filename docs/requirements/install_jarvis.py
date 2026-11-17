#!/usr/bin/env python3
"""
Instalador de JARVIS para Windows y macOS.

Se lanza desde:
  - Windows: docs\\requirements\\jarvis_requirements.bat
  - macOS:   docs/requirements/jarvis_requirements.command (doble clic) o
             python3 docs/requirements/install_jarvis.py

Que hace, segun el sistema operativo detectado:
  1. Comprueba la version de Python (minimo 3.14: src/memory/conversation.py
     usa anotaciones que solo se resuelven con la evaluacion diferida de 3.14).
  2. macOS: crea y usa un entorno virtual en <proyecto>/.venv (Homebrew no
     permite instalar paquetes en el Python del sistema). Windows: usa el
     Python con el que se lanza, salvo que se pase --venv.
  3. Actualiza pip/setuptools/wheel.
  4. Instala torch (con CUDA en Windows si hay GPU NVIDIA; MPS en macOS).
  5. Instala docs/requirements/requirements.txt (los paquetes de cada SO se filtran por
     marcadores). Si la instalacion conjunta falla, reintenta paquete a
     paquete e informa de cuales fallan.
  6. Intenta paddlepaddle (opcional; JARVIS usa el motor onnxruntime de
     PaddleOCR si no hay rueda para la version de Python).
  7. Comprueba que cada modulo se importa.
  8. Instala/arranca Ollama y descarga los modelos llama3, qwen3-vl:8b y
     qwen3-vl:8b-instruct.
  9. Descarga por adelantado el modelo Whisper "medium" y los pesos de
     OmniParser (icon_detect_v3) para que no se descarguen en el primer uso.
 10. macOS: indica los permisos de privacidad necesarios.

Opciones:
  --si            responder si a todas las preguntas (instalar Ollama, etc.)
  --sin-modelos   no instalar Ollama ni descargar modelos
  --sin-gpu       instalar torch sin CUDA
  --venv          (Windows) usar tambien un entorno virtual en .venv
  --cuda cuXXX    indice CUDA de PyTorch (por defecto cu128)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # docs/requirements/ -> raiz
REQUIREMENTS = Path(__file__).resolve().parent / "requirements.txt"
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

OLLAMA_MODELS = ["llama3", "qwen3-vl:8b", "qwen3-vl:8b-instruct"]
WHISPER_MODEL = "medium"
OMNIPARSER_REPO = "microsoft/OmniParser-v2.0"
OMNIPARSER_FILE = "icon_detect_v3/model.pt"

# Modulo a importar por cada paquete (nombre pip -> nombre import).
IMPORTS_COMUNES = {
    "numpy": "numpy", "pandas": "pandas", "scikit-learn": "sklearn",
    "joblib": "joblib", "pydantic": "pydantic", "requests": "requests",
    "psutil": "psutil", "watchdog": "watchdog", "pefile": "pefile",
    "matplotlib": "matplotlib", "plotly": "plotly", "Flask": "flask",
    "Flask-SocketIO": "flask_socketio",
    "Pillow": "PIL", "mss": "mss", "opencv-python": "cv2",
    "pyautogui": "pyautogui", "pygetwindow": "pygetwindow", "ollama": "ollama",
    "torch": "torch", "huggingface_hub": "huggingface_hub",
    "onnxruntime": "onnxruntime", "paddleocr": "paddleocr",
    "faster-whisper": "faster_whisper", "ctranslate2": "ctranslate2",
    "av": "av", "sounddevice": "sounddevice", "soundfile": "soundfile",
    "pyttsx3": "pyttsx3", "rapidfuzz": "rapidfuzz",
    "pytest": "pytest",
}
IMPORTS_WINDOWS = {
    "pywin32": "win32con", "comtypes": "comtypes", "pywinauto": "pywinauto",
    "dxcam": "dxcam",
}
IMPORTS_MAC = {
    "pyobjc-framework-Cocoa": "AppKit", "pyobjc-framework-Quartz": "Quartz",
    "pyobjc-framework-ApplicationServices": "ApplicationServices",
    "pyobjc-framework-ScreenCaptureKit": "ScreenCaptureKit",
}

problemas: list[str] = []
avisos: list[str] = []


# ----------------------------------------------------------------- utilidades
def titulo(texto: str) -> None:
    print("\n" + "=" * 64 + f"\n {texto}\n" + "=" * 64, flush=True)


def ejecutar(cmd: list[str], **kw) -> int:
    print("  > " + " ".join(cmd), flush=True)
    try:
        return subprocess.call(cmd, **kw)
    except FileNotFoundError:
        return 127


def pip(*args: str) -> int:
    return ejecutar([sys.executable, "-m", "pip", *args])


def preguntar(texto: str, por_defecto_si: bool) -> bool:
    if por_defecto_si:
        return True
    try:
        return input(f"{texto} [s/N]: ").strip().lower() in ("s", "si", "y", "yes")
    except EOFError:
        return False


def leer_requirements() -> list[str]:
    lineas = []
    for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            lineas.append(linea)
    return lineas


def aplica_a_este_so(req: str) -> bool:
    if ";" not in req:
        return True
    marcador = req.split(";", 1)[1].replace(" ", "")
    if 'sys_platform=="win32"' in marcador:
        return IS_WINDOWS
    if 'sys_platform=="darwin"' in marcador:
        return IS_MAC
    return True


# ------------------------------------------------------------------- 1. python
def comprobar_python() -> None:
    titulo("[1/9] Sistema y Python")
    print(f"  SO: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Python: {sys.version.split()[0]} en {sys.executable}")
    if sys.version_info < (3, 14):
        print("\nERROR: JARVIS necesita Python 3.14 o superior.")
        if IS_MAC:
            print("Instala uno con:  brew install python@3.14  (https://brew.sh)")
        else:
            print("Descargalo de https://www.python.org/downloads/ (marca 'Add to PATH').")
        sys.exit(1)
    if not (IS_WINDOWS or IS_MAC):
        avisos.append("Sistema no soportado oficialmente (solo Windows y macOS); se intenta igualmente.")


# ---------------------------------------------------------------------- 2. venv
def asegurar_venv(args: argparse.Namespace, argv: list[str]) -> None:
    usar_venv = IS_MAC or args.venv
    en_venv = sys.prefix != sys.base_prefix
    if not usar_venv or en_venv:
        return
    titulo("[2/9] Entorno virtual .venv")
    if not VENV_DIR.exists():
        import venv
        print(f"  Creando {VENV_DIR} ...")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    py = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
    print(f"  Continuando la instalacion con {py}")
    sys.exit(subprocess.call([str(py), str(Path(__file__).resolve()), *argv]))


# ---------------------------------------------------------------------- 3. pip
def actualizar_pip() -> None:
    titulo("[3/9] Actualizando pip")
    if pip("install", "--upgrade", "pip", "setuptools", "wheel") != 0:
        problemas.append("No se pudo actualizar pip.")


# --------------------------------------------------------------------- 4. torch
def hay_gpu_nvidia() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    return subprocess.call(["nvidia-smi"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0


def instalar_torch(args: argparse.Namespace) -> None:
    titulo("[4/9] PyTorch")
    req = next((r for r in leer_requirements() if r.lower().startswith("torch")), "torch")
    if IS_WINDOWS and not args.sin_gpu and hay_gpu_nvidia():
        indice = f"https://download.pytorch.org/whl/{args.cuda}"
        print(f"  GPU NVIDIA detectada: instalando torch con CUDA ({args.cuda})")
        if pip("install", req, "--index-url", indice) == 0:
            return
        avisos.append(f"torch con CUDA {args.cuda} fallo; se instala la version CPU. "
                      "Prueba otro indice con --cuda cu126 o --cuda cu130.")
    elif IS_MAC:
        print("  macOS: torch estandar (usa la GPU de Apple via MPS cuando existe).")
    if pip("install", req) != 0:
        problemas.append("No se pudo instalar torch.")


# ------------------------------------------------------------ 5. requirements
def instalar_requirements() -> None:
    titulo("[5/9] Dependencias de requirements.txt")
    print("  Puede tardar varios minutos...")
    if pip("install", "-r", str(REQUIREMENTS)) == 0:
        return
    print("\n  La instalacion conjunta fallo; reintentando paquete a paquete...")
    for req in leer_requirements():
        if not aplica_a_este_so(req):
            continue
        if pip("install", req) != 0:
            problemas.append(f"No se pudo instalar: {req}")


# ------------------------------------------------------------ 6. paddlepaddle
def instalar_paddle() -> None:
    titulo("[6/9] paddlepaddle (opcional)")
    if sys.version_info >= (3, 14):
        print("  Sin rueda conocida para Python 3.14+: PaddleOCR usara el motor onnxruntime.")
        return
    if pip("install", "paddlepaddle") != 0:
        avisos.append("paddlepaddle no se instalo; PaddleOCR usara el motor onnxruntime.")


# ------------------------------------------------------------- 7. verificacion
def verificar_imports() -> None:
    titulo("[7/9] Comprobando que cada modulo se importa")
    mapa = dict(IMPORTS_COMUNES)
    mapa.update(IMPORTS_WINDOWS if IS_WINDOWS else {})
    mapa.update(IMPORTS_MAC if IS_MAC else {})
    for paquete, modulo in mapa.items():
        r = subprocess.run([sys.executable, "-c", f"import {modulo}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print(f"  OK    {paquete}")
        else:
            ultima = (r.stderr.strip().splitlines() or ["?"])[-1]
            print(f"  FALLO {paquete} ({modulo}): {ultima}")
            problemas.append(f"Import fallido: {paquete} -> {ultima}")


# ------------------------------------------------------------------ 8. ollama
def ollama_responde() -> bool:
    return subprocess.call(["ollama", "list"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0


def instalar_ollama(args: argparse.Namespace) -> bool:
    if shutil.which("ollama"):
        return True
    print("  Ollama no esta instalado.")
    if not preguntar("  Instalar Ollama ahora?", args.si):
        avisos.append("Ollama no instalado: descargalo de https://ollama.com/download")
        return False
    if IS_WINDOWS and shutil.which("winget"):
        ejecutar(["winget", "install", "-e", "--id", "Ollama.Ollama"])
    elif IS_MAC and shutil.which("brew"):
        ejecutar(["brew", "install", "--cask", "ollama"])
    else:
        avisos.append("Instala Ollama a mano desde https://ollama.com/download y vuelve a ejecutar.")
        return False
    if shutil.which("ollama"):
        return True
    # En Windows el PATH nuevo no se ve hasta abrir otra consola.
    candidato = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
    if IS_WINDOWS and candidato.exists():
        os.environ["PATH"] = str(candidato.parent) + os.pathsep + os.environ["PATH"]
        return True
    avisos.append("Ollama instalado pero no aparece en el PATH: cierra y vuelve a abrir la consola.")
    return False


def arrancar_ollama() -> bool:
    if ollama_responde():
        return True
    print("  Arrancando el servidor de Ollama...")
    if IS_MAC and Path("/Applications/Ollama.app").exists():
        subprocess.call(["open", "-a", "Ollama"])
    else:
        flags = 0x00000008 if IS_WINDOWS else 0  # DETACHED_PROCESS
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=flags,
                         start_new_session=not IS_WINDOWS)
    for _ in range(30):
        time.sleep(1)
        if ollama_responde():
            return True
    return False


def preparar_ollama(args: argparse.Namespace) -> None:
    titulo("[8/9] Ollama y modelos de lenguaje/vision")
    if not instalar_ollama(args):
        problemas.append("Ollama no disponible: Brain y Vision no funcionaran.")
        return
    if not arrancar_ollama():
        problemas.append("El servidor de Ollama no responde; abre la aplicacion Ollama y repite.")
        return
    for modelo in OLLAMA_MODELS:
        if ejecutar(["ollama", "pull", modelo]) != 0:
            problemas.append(f"No se pudo descargar el modelo Ollama {modelo}.")


# ------------------------------------------------------------ 9. otros modelos
def precargar_modelos() -> None:
    titulo("[9/9] Modelos locales (Whisper y OmniParser)")
    codigo_whisper = (
        "from faster_whisper import WhisperModel;"
        f"WhisperModel('{WHISPER_MODEL}', device='cpu', compute_type='int8');"
        "print('  Whisper listo')"
    )
    if ejecutar([sys.executable, "-c", codigo_whisper]) != 0:
        avisos.append(f"Whisper '{WHISPER_MODEL}' no se descargo; se intentara en el primer uso.")
    codigo_omni = (
        "from huggingface_hub import hf_hub_download;"
        f"print('  OmniParser:', hf_hub_download(repo_id='{OMNIPARSER_REPO}', filename='{OMNIPARSER_FILE}'))"
    )
    if ejecutar([sys.executable, "-c", codigo_omni]) != 0:
        avisos.append("Pesos de OmniParser no descargados; se intentara en el primer uso.")


# ------------------------------------------------------------ permisos macOS
def permisos_mac() -> None:
    if not IS_MAC:
        return
    titulo("Permisos de macOS (hazlo una vez)")
    print("  Ajustes del Sistema > Privacidad y seguridad. Concede a la aplicacion")
    print("  desde la que ejecutas JARVIS (Terminal, iTerm o VS Code):")
    print("    - Accesibilidad          (mover ventanas, raton y teclado)")
    print("    - Grabacion de pantalla  (capturas para vision/calibracion)")
    print("    - Microfono              (voz)")
    print("    - Automatizacion         (si se piden permisos de control de apps)")
    print("  Despues cierra y vuelve a abrir esa aplicacion.")


# ---------------------------------------------------------------------- main
def main() -> None:
    argv = sys.argv[1:]
    p = argparse.ArgumentParser(description="Instalador de JARVIS (Windows/macOS)")
    p.add_argument("--si", action="store_true")
    p.add_argument("--sin-modelos", action="store_true")
    p.add_argument("--sin-gpu", action="store_true")
    p.add_argument("--venv", action="store_true")
    p.add_argument("--cuda", default="cu128")
    args = p.parse_args(argv)

    os.chdir(ROOT)
    comprobar_python()
    asegurar_venv(args, argv)
    actualizar_pip()
    instalar_torch(args)
    instalar_requirements()
    instalar_paddle()
    verificar_imports()
    if args.sin_modelos:
        print("\n  --sin-modelos: se omiten Ollama y la descarga de modelos.")
    else:
        preparar_ollama(args)
        precargar_modelos()
    permisos_mac()

    titulo("RESUMEN")
    for a in avisos:
        print(f"  AVISO: {a}")
    for e in problemas:
        print(f"  ERROR: {e}")
    en_venv = sys.prefix != sys.base_prefix
    lanzar = (f"{VENV_DIR / ('Scripts/python.exe' if IS_WINDOWS else 'bin/python')} main.py"
              if en_venv else "python main.py")
    if problemas:
        print("\n  Instalacion terminada CON ERRORES (ver arriba).")
    else:
        print("\n  INSTALACION COMPLETADA.")
    print(f"  Para arrancar JARVIS desde {ROOT}:\n    {lanzar}")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
