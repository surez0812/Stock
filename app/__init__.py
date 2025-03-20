from flask import Flask
from flask_cors import CORS
import os
import logging
from app.db_utils import init_db
from app.models import db

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
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB限制
    
    # 确保上传文件夹存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # 初始化数据库
    db_init_success = init_db(app)
    if not db_init_success:
        app.logger.error("数据库初始化失败")
    else:
        app.logger.info("数据库初始化成功")
    
    # 注册蓝图
    from app.routes import main
    from app.text2video import text2video_bp
    from app.image2video import image2video_bp
    from app.replicate_image2video import replicate_image2video_bp
    app.register_blueprint(main)
    app.register_blueprint(text2video_bp)
    app.register_blueprint(image2video_bp)
    app.register_blueprint(replicate_image2video_bp)
    
    # 确保数据库表存在
    with app.app_context():
        db.create_all()
    
    # 启动日志
    app.logger.info("股市分析应用已启动")
    
    return app 