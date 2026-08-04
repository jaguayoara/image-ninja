@echo off
REM ImageNinja - arranca la app en modo dev (sin empaquetar)
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [start] Creando venv...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [start] Instalando dependencias...
python -m pip install --disable-pip-version-check -q -r requirements.txt

echo.
echo ============================================================
echo   ImageNinja - servidor local
echo   Abre en tu navegador: http://127.0.0.1:5050
echo   Ctrl+C para detener
echo ============================================================
echo.

python app.py
