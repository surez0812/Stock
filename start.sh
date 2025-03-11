#!/bin/bash
source venv/bin/activate
cd "$(dirname "$0")"

# 加载环境变量
if [ -f .env ]; then
    echo "正在加载环境变量..."
    export $(grep -v '^#' .env | xargs)
fi

# 终止占用8080端口的进程
echo "正在检查端口8080是否被占用..."
kill -9 $(lsof -ti:8080) 2>/dev/null || echo "端口8080未被占用，可以正常启动"

# 启动应用
echo "正在启动股市分析工具..."
python3 run.py
