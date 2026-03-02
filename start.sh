#!/bin/bash
command -v python3 &>/dev/null || { echo "请先安装 Python3"; exit 1; }
[ ! -d "venv" ] && echo "[1/3] 创建环境..." && python3 -m venv venv
source venv/bin/activate
python -c "import fastapi" 2>/dev/null || { echo "[2/3] 安装依赖..."; pip install -r requirements.txt; }
[ ! -f "stock.db" ] && echo "[3/3] 拉取数据..." && python data.py
echo "浏览器打开 http://localhost:8000"
python app.py
