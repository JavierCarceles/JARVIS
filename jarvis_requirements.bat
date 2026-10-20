@echo off

title Instalador de Dependencias - JARVIS

color 0A

echo ============================================================

echo      INSTALADOR DE DEPENDENCIAS DE JARVIS

echo ============================================================

echo.

echo [1/3] Actualizando pip a la ultima version...

python -m pip install --upgrade pip

echo.

echo [2/3] Instalando todas las dependencias de Python...

echo Esto puede tardar unos minutos dependiendo de tu conexion...

pip install "numpy>=1.21.0" "Pillow>=9.0.0" "matplotlib>=3.7.0" "scikit-learn>=1.3.0" "pandas>=2.0.0" "Flask>=3.0.0" "Flask-SocketIO>=5.3.0" "joblib>=1.2.0" "plotly>=5.15.0" "pyautogui>=0.9.53" "pygetwindow>=0.0.9" "sounddevice>=0.4.5" "soundfile>=0.12.1" "pycaw>=2022.3.1" "mss>=1.6.3" "transformers>=4.30.0" "torch>=2.0.0" "onnxruntime>=1.15.0" "faster-whisper>=0.9.0" "ollama==0.6.2" "pydantic>=2.0.0,<3.0.0" "requests>=2.28.0" "aiohttp>=3.8.0" "python-dotenv>=0.19.0" "pywin32>=305" "comtypes>=1.1.11" "psutil>=5.9.0" "colorlog>=6.7.0" "structlog>=22.0.0" "pefile>=2024.8.26" "pytest>=7.0.0" "pytest-cov>=4.0.0" "black>=22.0.0" "flake8>=5.0.0" "colorama>=0.4.6"

echo.

echo Comprobando shutil...

python -c "import shutil; print('shutil detectado correctamente')"

if errorlevel 1 (

    echo.

    echo ============================================================

    echo ERROR: Python no puede importar shutil.

    echo ============================================================

    echo.

    echo shutil forma parte de Python y no se instala con pip.

    echo El problema esta en la instalacion de Python utilizada.

    echo.

    pause

    exit /b 1

)

echo.

echo shutil OK.

echo.

echo ============================================================

echo [3/3] Descargando el modelo de vision en Ollama...

echo ATENCION: Asegurate de tener la aplicacion de Ollama abierta.

echo ============================================================

ollama pull qwen3-vl:8b

ollama pull qwen3-vl:8b-instruct

echo.

echo ============================================================

echo               ¡INSTALACION COMPLETADA!

echo ============================================================

echo Ya puedes cerrar esta ventana.

pause