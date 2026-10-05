@echo off
REM ============================================================
REM  Web Denetim Merkezi - kurulum (Windows)
REM  Repo icinde .venv sanal ortamini kurar, paketleri ve Chromium'u indirir.
REM  Bir kez calistirin. Guncellemeden sonra tekrar calistirmak guvenlidir.
REM ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo  Web Denetim Merkezi - kurulum
echo  ------------------------------------------------------------

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :python_yok

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 goto :surum_eski
%PY% -c "import tkinter" 2>nul
if errorlevel 1 echo  [!] Bu Python'da tkinter yok; arayuz acilmaz. Python'u python.org'dan "tcl/tk" secenegiyle kurun.

if not exist ".venv\Scripts\python.exe" (
    echo  [1/3] Sanal ortam olusturuluyor: .venv
    %PY% -m venv .venv
    if errorlevel 1 goto :hata
) else (
    echo  [1/3] Sanal ortam zaten var: .venv
)
echo  [2/3] Python paketleri kuruluyor (birkac dakika)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :hata
echo  [3/3] Chromium tarayicisi indiriliyor...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :hata

echo.
echo  Kurulum tamam. Programi BASLAT.bat ile acin.
goto :son

:python_yok
echo  [HATA] Python bulunamadi.
echo  https://www.python.org/downloads/ adresinden Python 3.9 veya ustunu kurun.
echo  Kurulumda "Add python.exe to PATH" kutusunu isaretleyin, sonra bu dosyayi tekrar calistirin.
goto :hata_son
:surum_eski
echo  [HATA] Python 3.9 veya ustu gerekli. Kurulu surum:
%PY% --version
goto :hata_son
:hata
echo.
echo  [HATA] Kurulum tamamlanamadi. Yukaridaki mesaja bakin; internet baglantisini
echo  ve kurum agindaysaniz proxy ayarlarini kontrol edin.
:hata_son
if /i not "%~1"=="/sessiz" pause
exit /b 1
:son
if /i not "%~1"=="/sessiz" pause
exit /b 0
