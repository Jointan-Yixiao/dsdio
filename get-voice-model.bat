@echo off
cd /d %~dp0

if not exist .venv (
    echo [x] 还没初始化，请先双击 run.bat 跑一次，再来双击本脚本。
    pause
    exit /b 1
)

REM 离线识别（SenseVoice）既要依赖也要模型。先装依赖（已装会很快跳过），再下模型，一步到位。
echo [*] 第 1/2 步：确认语音识别依赖（已装会很快跳过）...
".venv\Scripts\python.exe" -m pip install -r requirements-voice.txt
if errorlevel 1 (
    echo [x] 依赖安装失败，检查网络后重试。
    pause
    exit /b 1
)

echo.
echo [*] 第 2/2 步：下载 SenseVoice 离线识别模型（约 229MB，需联网，期间窗口会安静一会儿）...
".venv\Scripts\python.exe" -c "from backend import stt; stt.ensure_sensevoice()"
if errorlevel 1 (
    echo [x] 模型下载失败。GitHub 慢的话，在 .env 里设 SENSEVOICE_MODEL_URL 换镜像后重试。
    pause
    exit /b 1
)

echo.
echo [OK] 下载完成！现在挂件的语音识别（点麦克风 / 唤醒词）即用 SenseVoice：离线、免 VPN、能识别中/英。
pause
