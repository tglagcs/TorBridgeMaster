@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

echo.
echo  ============================================================
echo   Tor Bridge Master
echo  ============================================================
echo.
echo   1 - Russian
echo   2 - English
echo.
set /p LANG_CHOICE=  Enter 1 or 2:
if "!LANG_CHOICE!"=="1" goto RU
goto EN

rem ============================================================
rem  RUSSIAN
rem ============================================================
:RU
title Проверка зависимостей - Tor Bridge Master
echo.
echo  ============================================================
echo      Tor Bridge Master - Проверка зависимостей
echo  ============================================================
echo.
set PYTHON_OK=0
set PIP_OK=0
set TQDM_OK=0
set TOR_OK=0
set OBFS4_OK=0
set PS7_OK=0

echo [1/6] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 goto RU_NO_PYTHON
echo   OK  Python найден
set PYTHON_OK=1
goto RU_CHECK_PIP

:RU_NO_PYTHON
echo   ERR Python не найден
echo.
echo   Python не установлен или не добавлен в PATH
echo   Скачать: https://www.python.org/downloads/
echo.
set /p Q=  Открыть страницу загрузки? y/n:
if /i "!Q!"=="y" start https://www.python.org/downloads/
echo   При установке отметьте "Add Python to PATH", затем перезапустите скрипт
pause & exit /b 1

:RU_CHECK_PIP
echo.
echo [2/6] Проверка pip...
python -m pip --version >nul 2>&1
if errorlevel 1 goto RU_NO_PIP
echo   OK  pip найден
set PIP_OK=1
goto RU_CHECK_TQDM

:RU_NO_PIP
echo   ERR pip не найден
set /p Q=  Установить pip? y/n:
if /i "!Q!"=="y" goto RU_INSTALL_PIP
echo   Без pip невозможно продолжить
pause & exit /b 1
:RU_INSTALL_PIP
python -m ensurepip --upgrade
if errorlevel 1 (echo   ERR Не удалось установить pip & pause & exit /b 1)
echo   OK  pip установлен
set PIP_OK=1

:RU_CHECK_TQDM
echo.
echo [3/6] Проверка зависимостей Python (tqdm)...
python -c "import tqdm" >nul 2>&1
if errorlevel 1 goto RU_NO_TQDM
echo   OK  tqdm найден
set TQDM_OK=1
goto RU_CHECK_TOR

:RU_NO_TQDM
echo   ERR tqdm не установлен
set /p Q=  Установить из requirements.txt? y/n:
if /i "!Q!"=="y" goto RU_INSTALL_TQDM
echo   Без tqdm невозможно продолжить
pause & exit /b 1
:RU_INSTALL_TQDM
python -m pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (echo   ERR Не удалось установить зависимости & pause & exit /b 1)
echo   OK  Зависимости установлены
set TQDM_OK=1

:RU_CHECK_TOR
echo.
echo [4/6] Проверка tor (опционально)...
where tor >nul 2>&1
if errorlevel 1 (
    echo   --  tor не найден в PATH
    echo       obfs4-хендшейк будет пропущен, останется TCP-проверка
    echo       Полную проверку даёт Tor Browser: https://www.torproject.org/download/
) else (
    echo   OK  tor найден
    set TOR_OK=1
)

:RU_CHECK_OBFS4
echo.
echo [5/6] Проверка obfs4proxy (опционально)...
where obfs4proxy >nul 2>&1
if errorlevel 1 (
    echo   --  obfs4proxy не найден в PATH
    echo       Входит в состав Tor Browser
) else (
    echo   OK  obfs4proxy найден
    set OBFS4_OK=1
)

:RU_CHECK_PS7
echo.
echo [6/6] Проверка PowerShell 7...
set PS7_PATH=
where pwsh >nul 2>&1
if errorlevel 1 goto RU_PS7_NO_PATH
for /f "tokens=*" %%i in ('where pwsh 2^>nul') do set PS7_PATH=%%i
echo   OK  PowerShell 7 найден: !PS7_PATH!
set PS7_OK=1
goto RU_RESULTS

:RU_PS7_NO_PATH
if exist "C:\Program Files\PowerShell\7\pwsh.exe" (
    set PS7_PATH=C:\Program Files\PowerShell\7\pwsh.exe
    echo   OK  PowerShell 7 найден: !PS7_PATH!
    set PS7_OK=1
    goto RU_RESULTS
)
echo   ERR PowerShell 7 не найден
echo   Скачать: https://github.com/PowerShell/PowerShell/releases/latest
set /p Q=  Открыть страницу загрузки? y/n:
if /i "!Q!"=="y" start https://github.com/PowerShell/PowerShell/releases/latest
echo   После установки перезапустите скрипт
pause & exit /b 1

:RU_RESULTS
echo.
echo  ============================================================
echo                   РЕЗУЛЬТАТ ПРОВЕРКИ
echo  ============================================================
if %PYTHON_OK%==1 (echo   Python:       OK) else (echo   Python:       ОШИБКА)
if %PIP_OK%==1    (echo   pip:          OK) else (echo   pip:          ОШИБКА)
if %TQDM_OK%==1   (echo   tqdm:         OK) else (echo   tqdm:         ОШИБКА)
if %TOR_OK%==1    (echo   tor:          OK) else (echo   tor:          нет ^(TCP-режим^))
if %OBFS4_OK%==1  (echo   obfs4proxy:   OK) else (echo   obfs4proxy:   нет ^(TCP-режим^))
if %PS7_OK%==1    (echo   PowerShell 7: OK) else (echo   PowerShell 7: ОШИБКА)
echo  ============================================================
echo.
echo   Обязательные зависимости установлены. Готов к работе!
if not %TOR_OK%==1 echo   ^(Без tor/obfs4proxy проверка идёт только по TCP-порту^)
echo.
echo   Для запуска используйте Start.ps1
if defined PS7_PATH echo   Или вручную: "!PS7_PATH!" -File Start.ps1
echo.
pause
exit /b 0

rem ============================================================
rem  ENGLISH
rem ============================================================
:EN
title Dependency Check - Tor Bridge Master
echo.
echo  ============================================================
echo      Tor Bridge Master - Dependency Check
echo  ============================================================
echo.
set PYTHON_OK=0
set PIP_OK=0
set TQDM_OK=0
set TOR_OK=0
set OBFS4_OK=0
set PS7_OK=0

echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 goto EN_NO_PYTHON
echo   OK  Python found
set PYTHON_OK=1
goto EN_CHECK_PIP

:EN_NO_PYTHON
echo   ERR Python not found
echo.
echo   Python is not installed or not in PATH
echo   Download: https://www.python.org/downloads/
echo.
set /p Q=  Open download page? y/n:
if /i "!Q!"=="y" start https://www.python.org/downloads/
echo   Check "Add Python to PATH" during installation, then restart this script
pause & exit /b 1

:EN_CHECK_PIP
echo.
echo [2/6] Checking pip...
python -m pip --version >nul 2>&1
if errorlevel 1 goto EN_NO_PIP
echo   OK  pip found
set PIP_OK=1
goto EN_CHECK_TQDM

:EN_NO_PIP
echo   ERR pip not found
set /p Q=  Install pip? y/n:
if /i "!Q!"=="y" goto EN_INSTALL_PIP
echo   Cannot continue without pip
pause & exit /b 1
:EN_INSTALL_PIP
python -m ensurepip --upgrade
if errorlevel 1 (echo   ERR Failed to install pip & pause & exit /b 1)
echo   OK  pip installed
set PIP_OK=1

:EN_CHECK_TQDM
echo.
echo [3/6] Checking Python dependencies (tqdm)...
python -c "import tqdm" >nul 2>&1
if errorlevel 1 goto EN_NO_TQDM
echo   OK  tqdm found
set TQDM_OK=1
goto EN_CHECK_TOR

:EN_NO_TQDM
echo   ERR tqdm not installed
set /p Q=  Install from requirements.txt? y/n:
if /i "!Q!"=="y" goto EN_INSTALL_TQDM
echo   Cannot continue without tqdm
pause & exit /b 1
:EN_INSTALL_TQDM
python -m pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (echo   ERR Failed to install dependencies & pause & exit /b 1)
echo   OK  Dependencies installed
set TQDM_OK=1

:EN_CHECK_TOR
echo.
echo [4/6] Checking tor (optional)...
where tor >nul 2>&1
if errorlevel 1 (
    echo   --  tor not found in PATH
    echo       obfs4 handshake will be skipped, TCP check remains
    echo       Full verification ships with Tor Browser: https://www.torproject.org/download/
) else (
    echo   OK  tor found
    set TOR_OK=1
)

:EN_CHECK_OBFS4
echo.
echo [5/6] Checking obfs4proxy (optional)...
where obfs4proxy >nul 2>&1
if errorlevel 1 (
    echo   --  obfs4proxy not found in PATH
    echo       Ships with Tor Browser
) else (
    echo   OK  obfs4proxy found
    set OBFS4_OK=1
)

:EN_CHECK_PS7
echo.
echo [6/6] Checking PowerShell 7...
set PS7_PATH=
where pwsh >nul 2>&1
if errorlevel 1 goto EN_PS7_NO_PATH
for /f "tokens=*" %%i in ('where pwsh 2^>nul') do set PS7_PATH=%%i
echo   OK  PowerShell 7 found: !PS7_PATH!
set PS7_OK=1
goto EN_RESULTS

:EN_PS7_NO_PATH
if exist "C:\Program Files\PowerShell\7\pwsh.exe" (
    set PS7_PATH=C:\Program Files\PowerShell\7\pwsh.exe
    echo   OK  PowerShell 7 found: !PS7_PATH!
    set PS7_OK=1
    goto EN_RESULTS
)
echo   ERR PowerShell 7 not found
echo   Download: https://github.com/PowerShell/PowerShell/releases/latest
set /p Q=  Open download page? y/n:
if /i "!Q!"=="y" start https://github.com/PowerShell/PowerShell/releases/latest
echo   Restart this script after installation
pause & exit /b 1

:EN_RESULTS
echo.
echo  ============================================================
echo                      CHECK RESULTS
echo  ============================================================
if %PYTHON_OK%==1 (echo   Python:       OK) else (echo   Python:       ERROR)
if %PIP_OK%==1    (echo   pip:          OK) else (echo   pip:          ERROR)
if %TQDM_OK%==1   (echo   tqdm:         OK) else (echo   tqdm:         ERROR)
if %TOR_OK%==1    (echo   tor:          OK) else (echo   tor:          no ^(TCP mode^))
if %OBFS4_OK%==1  (echo   obfs4proxy:   OK) else (echo   obfs4proxy:   no ^(TCP mode^))
if %PS7_OK%==1    (echo   PowerShell 7: OK) else (echo   PowerShell 7: ERROR)
echo  ============================================================
echo.
echo   Required dependencies installed. Ready to go!
if not %TOR_OK%==1 echo   ^(Without tor/obfs4proxy only TCP port check is performed^)
echo.
echo   To start the program use Start.ps1
if defined PS7_PATH echo   Or manually: "!PS7_PATH!" -File Start.ps1
echo.
pause
exit /b 0
