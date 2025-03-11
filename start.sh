#!/bin/bash

# 检查并关闭占用8080端口的进程
echo "检查8080端口占用情况..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    PORT_PID=$(lsof -ti:8080)
    if [ ! -z "$PORT_PID" ]; then
        echo "发现8080端口被占用，正在关闭进程 (PID: $PORT_PID)..."
        kill -9 $PORT_PID
        echo "进程已终止"
    fi
else
    # Linux
    PORT_PID=$(netstat -tulpn 2>/dev/null | grep ':8080' | awk '{print $7}' | cut -d'/' -f1)
    if [ ! -z "$PORT_PID" ]; then
        echo "发现8080端口被占用，正在关闭进程 (PID: $PORT_PID)..."
        kill -9 $PORT_PID
        echo "进程已终止"
    fi
fi

# 激活虚拟环境
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
