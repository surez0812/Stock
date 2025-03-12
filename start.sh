#!/bin/bash

# 检查并杀死占用8080端口的进程
echo "检查8080端口占用情况..."
if [ "$(uname)" == "Darwin" ]; then
    # macOS系统
    PORT_PID=$(lsof -i:8080 -t)
    if [ ! -z "$PORT_PID" ]; then
        echo "端口8080被进程 $PORT_PID 占用，正在终止..."
        kill -9 $PORT_PID
        echo "进程已终止"
    else
        echo "端口8080未被占用"
    fi
else
    # Linux系统
    PORT_PID=$(netstat -tulpn 2>/dev/null | grep ':8080' | awk '{print $7}' | cut -d'/' -f1)
    if [ ! -z "$PORT_PID" ]; then
        echo "端口8080被进程 $PORT_PID 占用，正在终止..."
        kill -9 $PORT_PID
        echo "进程已终止"
    else
        echo "端口8080未被占用"
    fi
fi

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
