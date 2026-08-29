@echo off
chcp 65001 >nul
setlocal

:: ========== 当前脚本所在目录及路径 ==========
set "ROOT=%~dp0"
set "TEMP_ROOT=%ROOT%build_tmp"
set "OUTPUT_DIR=%ROOT%releases"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "FLAG_DIR=%TEMP_ROOT%\flags"

if not exist "%TEMP_ROOT%" mkdir "%TEMP_ROOT%"
if not exist "%FLAG_DIR%" mkdir "%FLAG_DIR%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo ==============================================
echo            全部打包开始
echo ==============================================
echo 脚本目录: %ROOT%
echo 输出目录: %OUTPUT_DIR%
echo.

:: ========== 生成4个并行打包bat ==========

echo @echo off > "%TEMP_ROOT%\task1.bat"
echo "%PYTHON%" -m PyInstaller "%ROOT%wjfk.py" --onefile --windowed --distpath "%OUTPUT_DIR%" --name wjfk --icon="%ROOT%icon\wjfk.ico" --clean --noconfirm --add-data "%ROOT%icon\wjfk.png;icon" --workpath "%TEMP_ROOT%\build_splitter" --specpath "%TEMP_ROOT%\spec_splitter" >> "%TEMP_ROOT%\task1.bat"
echo echo done ^> "%FLAG_DIR%\task1.flag" >> "%TEMP_ROOT%\task1.bat"
echo exit >> "%TEMP_ROOT%\task1.bat"

echo @echo off > "%TEMP_ROOT%\task2.bat"
echo "%PYTHON%" -m PyInstaller "%ROOT%wjxz.py" --onefile --windowed --distpath "%OUTPUT_DIR%" --name wjxz --icon="%ROOT%icon\wjxz.ico" --clean --noconfirm --add-data "%ROOT%icon\wjxz.png;icon" --workpath "%TEMP_ROOT%\build_downloader" --specpath "%TEMP_ROOT%\spec_downloader" >> "%TEMP_ROOT%\task2.bat"
echo echo done ^> "%FLAG_DIR%\task2.flag" >> "%TEMP_ROOT%\task2.bat"
echo exit >> "%TEMP_ROOT%\task2.bat"

echo @echo off > "%TEMP_ROOT%\task3.bat"
echo "%PYTHON%" -m PyInstaller "%ROOT%app\main.py" --onefile --windowed --distpath "%OUTPUT_DIR%" --name wjfkxz --icon="%ROOT%icon\wjfkxz.ico" --clean --noconfirm --add-data "%ROOT%icon\wjfkxz.png;icon" --workpath "%TEMP_ROOT%\build_main" --specpath "%TEMP_ROOT%\spec_main" >> "%TEMP_ROOT%\task3.bat"
echo echo done ^> "%FLAG_DIR%\task3.flag" >> "%TEMP_ROOT%\task3.bat"
echo exit >> "%TEMP_ROOT%\task3.bat"

echo @echo off > "%TEMP_ROOT%\task4.bat"
echo "%PYTHON%" -m PyInstaller "%ROOT%cli\main.py" --onefile --distpath "%OUTPUT_DIR%" --name cli --icon="%ROOT%icon\wjfkxz-cli.ico" --clean --noconfirm --workpath "%TEMP_ROOT%\build_cli" --specpath "%TEMP_ROOT%\spec_cli" >> "%TEMP_ROOT%\task4.bat"
echo echo done ^> "%FLAG_DIR%\task4.flag" >> "%TEMP_ROOT%\task4.bat"
echo exit >> "%TEMP_ROOT%\task4.bat"

:: ========== 并行启动4个打包 ==========
start "打包-wjfk" "%TEMP_ROOT%\task1.bat"
start "打包-wjxz" "%TEMP_ROOT%\task2.bat"
start "打包-wjfkxz" "%TEMP_ROOT%\task3.bat"
start "打包-cli" "%TEMP_ROOT%\task4.bat"

echo 4个打包任务已启动，正在等待全部完成...
echo.

:: ========== 轮询等待全部完成标志 ==========
:wait_loop
timeout /t 1 /nobreak >nul
if not exist "%FLAG_DIR%\task1.flag" goto wait_loop
if not exist "%FLAG_DIR%\task2.flag" goto wait_loop
if not exist "%FLAG_DIR%\task3.flag" goto wait_loop
if not exist "%FLAG_DIR%\task4.flag" goto wait_loop

echo ==============================================
echo            全部完成，清理临时文件
echo ==============================================
rmdir /s /q "%TEMP_ROOT%"
echo 临时目录已删除
echo EXE 文件已生成至 %OUTPUT_DIR%
pause