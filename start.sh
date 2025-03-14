#!/bin/bash
source venv/bin/activate
cd "$(dirname "$0")"

# 加载环境变量
if [ -f .env ]; then
    echo "正在加载环境变量..."
    export $(grep -v '^#' .env | xargs)
fi

# 启动应用
echo "正在启动股市分析工具..."
python3 run.py
