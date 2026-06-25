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

REM ---- Node 音乐服务依赖（网易云搜索 + UNM 解锁）。装不上不影响聊天 / 新闻 ----
where node >nul 2>nul
if errorlevel 1 (
    echo [!] 未检测到 Node.js —— 音乐功能将不可用（聊天 / 新闻不受影响）。
    echo     如需音乐，安装 Node.js 18+ 后重跑本脚本： https://nodejs.org/
) else (
    if not exist "music-api\node_modules" (
        echo [*] 安装网易云 API 依赖（仅首次，需联网）...
        pushd music-api && call npm install && popd
    )
    if not exist "unm-api\node_modules" (
        echo [*] 安装 UNM 解锁依赖（仅首次，需联网）...
        pushd unm-api && call npm install && popd
    )
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
