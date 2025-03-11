@echo off
echo === 开始安装股市分析工具 ===
echo 正在检查Python版本...

:: 检查Python版本
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请安装Python 3.8或更高版本
    exit /b 1
)

:: 创建虚拟环境
echo 正在创建虚拟环境...
python -m venv venv
if %errorlevel% neq 0 (
    echo 错误: 创建虚拟环境失败，请确保已安装venv模块
    exit /b 1
)

:: 激活虚拟环境
echo 正在激活虚拟环境...
call venv\Scripts\activate.bat

:: 安装依赖
echo 正在安装依赖包...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 错误: 安装依赖失败
    exit /b 1
)

:: 创建上传目录
echo 正在创建上传目录...
if not exist app\uploads mkdir app\uploads

:: 完成
echo === 安装完成! ===
echo 运行 start.bat 启动应用 