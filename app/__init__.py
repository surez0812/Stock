from flask import Flask
from flask_cors import CORS
import os
import logging

def create_app():
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    app = Flask(__name__)
    CORS(app)
    
    # 配置上传文件夹
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制
    
    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # 注册蓝图
    from app.routes import main
    app.register_blueprint(main)
    
    # 启动日志
    app.logger.info("股市分析应用已启动")
    
    return app 