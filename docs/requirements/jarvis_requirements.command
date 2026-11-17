#!/bin/bash
# Instalador de dependencias de JARVIS - macOS
# Doble clic en Finder o:  bash docs/requirements/jarvis_requirements.command [--si] [--sin-modelos]
# Solo localiza un Python >= 3.14 y lanza docs/requirements/install_jarvis.py,
# que crea .venv e instala todo lo necesario para macOS.

cd "$(dirname "$0")" || exit 1
SCRIPT="$(pwd)/install_jarvis.py"

echo "============================================================"
echo "     INSTALADOR DE DEPENDENCIAS DE JARVIS - macOS"
echo "============================================================"

if [ "$(uname)" != "Darwin" ]; then
    echo "Este instalador es para macOS. En Windows usa docs\\requirements\\jarvis_requirements.bat"
    exit 1
fi

PYCMD=""
for c in python3.14 python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && \
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)' 2>/dev/null; then
        PYCMD="$c"
        break
    fi
done

if [ -z "$PYCMD" ]; then
    echo "ERROR: no se encontro Python 3.14 o superior (el de macOS es 3.9)."
    if command -v brew >/dev/null 2>&1; then
        echo "Instalalo con:  brew install python@3.14"
    else
        echo "Instala Homebrew (https://brew.sh) y despues:  brew install python@3.14"
        echo "o descarga Python de https://www.python.org/downloads/macos/"
    fi
    read -r -p "Pulsa Enter para cerrar..." _
    exit 1
fi

echo "Usando: $PYCMD ($("$PYCMD" --version))"
"$PYCMD" "$SCRIPT" "$@"
RESULTADO=$?
echo
if [ $RESULTADO -eq 0 ]; then
    echo "INSTALACION COMPLETADA"
else
    echo "INSTALACION TERMINADA CON ERRORES - revisa el resumen"
fi
read -r -p "Pulsa Enter para cerrar..." _
exit $RESULTADO
