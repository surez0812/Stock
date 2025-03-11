@echo off

:: 股市分析工具启动脚本

:: 检查虚拟环境是否存在
if not exist venv (
    echo 错误: 虚拟环境不存在，请先运行 setup.bat 安装应用
    exit /b 1
)

:: 激活虚拟环境
echo 正在激活虚拟环境...
call venv\Scripts\activate.bat

:: 检查是否存在uploads目录
if not exist app\uploads (
    echo 正在创建上传目录...
    mkdir app\uploads
)

:: 启动应用
echo 正在启动股市分析工具...
echo 应用将在 http://localhost:8080 运行
echo 按 Ctrl+C 停止应用
echo =====================================

:: 运行应用
python run.py

:: 检查退出代码
if %errorlevel% neq 0 (
    echo 应用异常退出，退出码: %errorlevel%
    echo 请检查日志获取详细信息
    exit /b 1
) 