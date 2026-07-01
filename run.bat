@echo off
cd /d %~dp0

if not exist .venv (
    echo [*] 首次运行，正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [x] 创建虚拟环境失败，请确认已安装 Python 3.10+ 。
        pause
        exit /b 1
    )
    echo [*] 正在安装 Python 依赖（仅首次，需联网）...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

if not exist .env (
    echo [!] 未找到 .env 文件，已从 .env.example 复制一份，请填入 DEEPSEEK_API_KEY 后重新运行。
    copy .env.example .env >nul
    notepad .env
    exit /b 0
)

REM ---- 首次在桌面创建「Dsdio」快捷方式（指向 pythonw，无黑框；只在缺失时建）----
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $p=Join-Path $d 'Dsdio.lnk'; if(-not(Test-Path $p)){ $s=(New-Object -ComObject WScript.Shell).CreateShortcut($p); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0app.py\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0icon.ico'; $s.Save(); Write-Host '[*] 已在桌面创建 Dsdio 快捷方式（以后双击它启动，无黑框）。' }" 2>nul

REM ---- 用 pythonw 无窗口启动并立刻退出本脚本：不再残留黑框 ----
echo [*] 启动 Dsdio ...（以后可直接用桌面的 Dsdio 快捷方式）
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
