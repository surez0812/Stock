#!/bin/bash

# 股市分析工具安装脚本

echo "=== 开始安装股市分析工具 ==="
echo "正在检查Python版本..."

# 检查Python版本
python3 --version > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "错误: 未找到Python3，请安装Python 3.8或更高版本"
    exit 1
fi

# 创建虚拟环境
echo "正在创建虚拟环境..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "错误: 创建虚拟环境失败，请确保已安装python3-venv"
    exit 1
fi

# 激活虚拟环境
echo "正在激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo "正在升级pip..."
pip install --upgrade pip

# 安装依赖
echo "正在安装依赖包..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "错误: 安装依赖失败"
    exit 1
fi

# 确保OpenAI库是最新版本，并安装处理图像所需的库
echo "正在安装其他必要库..."
pip install --upgrade openai==1.14.0 httpx==0.27.2 pillow oss2

if [ $? -ne 0 ]; then
    echo "警告: 升级库失败，可能影响某些功能"
else
    echo "成功安装和升级所需库"
fi

# 创建上传目录
echo "正在创建上传目录..."
mkdir -p app/uploads
if [ $? -ne 0 ]; then
    echo "警告: 创建上传目录失败，可能会影响图片上传功能"
fi

# 创建启动脚本
echo "正在创建启动脚本..."
cat > start.sh << 'EOF'
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
EOF

# 授予执行权限给启动脚本
echo "正在设置执行权限..."
chmod +x start.sh
if [ $? -ne 0 ]; then
    echo "警告: 设置启动脚本权限失败，请手动运行: chmod +x start.sh"
fi

# 完成
echo "=== 安装完成! ==="
echo "运行 ./start.sh 启动应用"
echo "注意: 请确保您的.env文件包含所需的API密钥" 