@echo off
chcp 65001 >nul

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    echo 请先安装 Python 3.10+: https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

if not exist "venv" (
    echo [1/3] 首次运行，创建环境...
    python -m venv venv
)

call venv\Scripts\activate

if not exist "venv\Lib\site-packages\fastapi" (
    echo [2/3] 安装依赖...
    pip install -r requirements.txt
)

if not exist "stock.db" (
    echo [3/3] 拉取A股数据（约 5-10 分钟）...
    python data.py
)

echo.
echo A股选股平台启动中...
echo 浏览器打开 http://localhost:8000
echo 关闭此窗口即可停止服务
echo.
python app.py
pause
