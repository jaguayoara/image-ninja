@echo off
REM ImageNinja - compila el .exe portable con PyInstaller
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [build] Creando venv...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [build] Instalando dependencias de build...
python -m pip install --disable-pip-version-check -q -r requirements.txt
python -m pip install --disable-pip-version-check -q pyinstaller==6.10.0

echo.
echo [build] Limpiando build anterior...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [build] Compilando con PyInstaller...
python -m PyInstaller --noconfirm --clean ImageNinja.spec

echo.
if exist dist\ImageNinja\ImageNinja.exe (
    echo ============================================================
    echo   Build OK
    echo   dist\ImageNinja\ImageNinja.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   Build FALLO - revisar log
    echo ============================================================
)
