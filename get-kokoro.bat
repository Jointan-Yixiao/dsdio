@echo off
chcp 65001 >nul
cd /d %~dp0

if not exist .venv (
    echo [x] 还没初始化，请先双击 run.bat 跑一次，再来双击本脚本。
    pause
    exit /b 1
)

REM Kokoro 既要依赖也要模型。先确保依赖装上（已装则秒过），再下模型，一步到位。
echo [*] 第 1/2 步：确认 Kokoro 依赖（已装会很快跳过）...
".venv\Scripts\python.exe" -m pip install -r requirements-voice.txt
if errorlevel 1 (
    echo [x] 依赖安装失败，检查网络后重试。
    pause
    exit /b 1
)

echo.
echo [*] 第 2/2 步：下载 Kokoro 本地音色模型（约 340MB，需联网，请耐心等，期间窗口会安静一会儿）...
".venv\Scripts\python.exe" download_models.py
if errorlevel 1 (
    echo [x] 模型下载失败。GitHub 慢的话，在 .env 里设 KOKORO_MODEL_URL / KOKORO_VOICES_URL 换镜像后重试。
    pause
    exit /b 1
)

echo.
echo [OK] 下载完成！最后一步：打开挂件 → 点 齿轮设置 → 语音引擎 → 选 Kokoro，才会启用本地音色。
pause
