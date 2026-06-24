@echo off
chcp 65001 >nul
cd /d %~dp0

if not exist .venv (
    echo [x] 还没初始化，请先双击 run.bat 跑一次，再来双击本脚本。
    pause
    exit /b 1
)

echo [*] 正在安装语音功能依赖（麦克风识别 + Kokoro，需联网，约几分钟）...
".venv\Scripts\python.exe" -m pip install -r requirements-voice.txt
if errorlevel 1 (
    echo [x] 安装失败，检查网络后重试。
    pause
    exit /b 1
)

echo.
echo [OK] 装好了！
echo     - 语音说话：回到挂件，直接点麦克风图标即可（中文识别模型首次用会自动下载）。
echo     - 想要本地 Kokoro 音色：再双击 get-kokoro.bat 下载模型。
pause
