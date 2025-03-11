import os
import sys
import logging
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# 检查Python版本
if sys.version_info < (3, 8):
    logging.warning("推荐使用Python 3.8或更高版本")

# 检查环境变量
required_vars = ['SILICONFLOW_API_KEY', 'DASHSCOPE_API_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.warning(f"缺少以下环境变量: {', '.join(missing_vars)}")
    logging.warning("将使用默认API密钥，这可能导致AI服务不可用")

from app import create_app

if __name__ == '__main__':
    logging.info("启动股市分析应用...")
    app = create_app()
    logging.info("应用已启动，访问 http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True) 