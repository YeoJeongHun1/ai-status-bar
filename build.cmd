@echo off
rem Builds dist\AIStatusBar\ (one-folder build) and dist\AIStatusBar-<ver>-win64.zip
rem Needs: pip install pillow pystray pywin32 pyinstaller
rem
rem Why one-folder, not one-file: the one-file bootloader unpacks itself to %TEMP% and runs from there,
rem which is exactly what antivirus ML heuristics flag (Trojan:Win32/Sabsik.*!ml, Wacatac.*!ml ...).
rem A plain folder with a normal exe + DLLs is far less likely to be flagged.
cd /d "%~dp0"
for /f "tokens=3 delims= " %%v in ('findstr /b "__version__" version.py') do set VER=%%~v
set VER=%VER:"=%
if exist dist\AIStatusBar rmdir /s /q dist\AIStatusBar
pyinstaller --noconfirm --onedir --windowed --name AIStatusBar ^
  --icon "%~dp0app.ico" ^
  --add-data "%~dp0app.ico;." ^
  --add-data "%~dp0statusline_export.ps1;." ^
  --version-file "%~dp0version_info.txt" ^
  --hidden-import pystray._win32 --hidden-import win32com.shell --hidden-import pythoncom ^
  --hidden-import providers.claude_code --hidden-import providers.codex ^
  --exclude-module numpy ^
  --distpath dist --workpath build --specpath build ^
  "%~dp0ai_status_bar.py"
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
copy /y README.md dist\AIStatusBar\README.md >nul
copy /y LICENSE dist\AIStatusBar\LICENSE >nul
if exist "dist\AIStatusBar-%VER%-win64.zip" del "dist\AIStatusBar-%VER%-win64.zip"
python -c "import shutil; shutil.make_archive('dist/AIStatusBar-%VER%-win64', 'zip', 'dist', 'AIStatusBar')"
rem SHA-256 next to the zip so downloads can be verified (attach both files to the release)
python -c "import hashlib; p='dist/AIStatusBar-%VER%-win64.zip'; h=hashlib.sha256(open(p,'rb').read()).hexdigest(); open(p+'.sha256','w',newline='').write(h+'  '+p.split('/')[-1]+'\n'); print('sha256', h)"
echo.
echo OK -> dist\AIStatusBar\AIStatusBar.exe  and  dist\AIStatusBar-%VER%-win64.zip (+ .sha256)
pause
