@echo off
REM Web Denetim Merkezi'ni acar. Cift tiklayin. Ilk acilista kurulumu kendisi yapar.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Ilk calistirma: once kurulum yapiliyor...
    call KURULUM.bat /sessiz
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
start "" ".venv\Scripts\pythonw.exe" web_denetim.py
