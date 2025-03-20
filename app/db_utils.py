import logging
import json
import requests
import os
from datetime import datetime
from urllib.parse import urlparse
from flask import current_app
from app.models import db, Text2VideoRequest, Image2VideoRequest, ReplicateImage2VideoRequest
from app.oss_client import oss_client

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_utils')

def init_db(app):
    """初始化数据库"""
    # 从环境变量获取MySQL连接信息
    mysql_host = os.environ.get('MYSQL_HOST', 'localhost')
    mysql_user = os.environ.get('MYSQL_USER', 'root')
    mysql_password = os.environ.get('MYSQL_PASSWORD', 'HelloWorld')
    mysql_db = os.environ.get('MYSQL_DB', 'stock_testing_tools')
    
    # 配置MySQL连接
    mysql_uri = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}'
    app.config['SQLALCHEMY_DATABASE_URI'] = mysql_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 初始化SQLAlchemy扩展
    db.init_app(app)
    
    # 创建表
    with app.app_context():
        try:
            # 先尝试连接到数据库
            db.engine.connect()
            logger.info(f"成功连接到MySQL数据库: {mysql_host}/{mysql_db}")
        except Exception as e:
            logger.error(f"连接数据库失败: {str(e)}")
            # 尝试创建数据库
            try:
                # 创建临时引擎连接到MySQL服务器而不指定数据库
                from sqlalchemy import create_engine, text
                temp_engine = create_engine(f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}/')
                with temp_engine.connect() as conn:
                    # 创建数据库 - 使用text()方法确保兼容性
                    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {mysql_db}"))
                    conn.commit()
                logger.info(f"创建数据库{mysql_db}成功")
            except Exception as db_create_error:
                logger.error(f"创建数据库失败: {str(db_create_error)}")
                return False
        
        # 创建表
        try:
            db.create_all()
            logger.info("成功创建数据库表")
            return True
        except Exception as e:
            logger.error(f"创建数据库表失败: {str(e)}")
            return False

def save_text2video_request(task_id, request_data):
    """保存文本生成视频的请求记录"""
    try:
        # 将请求数据转换为JSON字符串
        request_json = json.dumps(request_data, ensure_ascii=False)
        
        # 创建记录
        record = Text2VideoRequest(
            task_id=task_id,
            prompt=request_data.get('prompt', ''),
            model=request_data.get('model', ''),
            size=request_data.get('size', ''),
            fps=request_data.get('fps', 16),
            seed=request_data.get('seed', ''),
            prompt_extend=request_data.get('prompt_extend', 'true').lower() == 'true',
            request_params=request_json,
            status='PENDING'
        )
        
        # 保存到数据库
        db.session.add(record)
        db.session.commit()
        logger.info(f"保存Text2Video请求记录成功，ID: {record.id}, 任务ID: {task_id}")
        return True
        
    except Exception as e:
        logger.error(f"保存Text2Video请求记录失败: {str(e)}")
        # 回滚事务
        db.session.rollback()
        return False

def save_image2video_request(task_id, request_data, image_url):
    """保存图片生成视频的请求记录"""
    try:
        # 将请求数据转换为JSON字符串
        request_json = json.dumps(request_data, ensure_ascii=False)
        
        # 创建记录
        record = Image2VideoRequest(
            task_id=task_id,
            image_url=image_url,
            prompt=request_data.get('prompt', ''),
            model=request_data.get('model', ''),
            size=request_data.get('size', ''),
            duration=request_data.get('duration', 3.0),
            fps=request_data.get('fps', 16),
            motion_level=request_data.get('motion_level', 'medium'),
            seed=request_data.get('seed', ''),
            prompt_extend=request_data.get('prompt_extend', 'true').lower() == 'true',
            request_params=request_json,
            status='PENDING'
        )
        
        # 保存到数据库
        db.session.add(record)
        db.session.commit()
        logger.info(f"保存Image2Video请求记录成功，ID: {record.id}, 任务ID: {task_id}")
        return True
        
    except Exception as e:
        logger.error(f"保存Image2Video请求记录失败: {str(e)}")
        # 回滚事务
        db.session.rollback()
        return False

def update_text2video_status(task_id, status, response_data=None, video_url=None, process_time=None):
    """更新文本生成视频的任务状态"""
    try:
        # 查询记录
        record = Text2VideoRequest.query.filter_by(task_id=task_id).first()
        if not record:
            logger.warning(f"未找到Text2Video任务记录: {task_id}")
            return False
        
        # 更新状态
        record.status = status
        
        # 如果有响应数据，保存为JSON字符串
        if response_data:
            record.response_data = json.dumps(response_data, ensure_ascii=False)
            
        # 如果有视频URL，保存并尝试上传到OSS
        if video_url:
            record.video_url = video_url
            
            # 如果状态为成功，尝试上传视频到OSS
            if status == 'SUCCEEDED':
                oss_url = upload_video_to_oss(video_url, 'text2video', task_id)
                if oss_url:
                    record.oss_video_url = oss_url
        
        # 如果有处理时间，保存
        if process_time is not None:
            record.process_time = process_time
        
        # 保存到数据库
        db.session.commit()
        logger.info(f"更新Text2Video任务状态成功，任务ID: {task_id}, 状态: {status}")
        return True
        
    except Exception as e:
        logger.error(f"更新Text2Video任务状态失败: {str(e)}")
        # 回滚事务
        db.session.rollback()
        return False

def update_image2video_status(task_id, status, response_data=None, video_url=None, process_time=None):
    """更新图片生成视频的任务状态"""
    try:
        # 查询记录
        record = Image2VideoRequest.query.filter_by(task_id=task_id).first()
        if not record:
            logger.warning(f"未找到Image2Video任务记录: {task_id}")
            return False
        
        # 更新状态
        record.status = status
        
        # 如果有响应数据，保存为JSON字符串
        if response_data:
            record.response_data = json.dumps(response_data, ensure_ascii=False)
            
        # 如果有视频URL，保存并尝试上传到OSS
        if video_url:
            record.video_url = video_url
            
            # 如果状态为成功，尝试上传视频到OSS
            if status == 'SUCCEEDED':
                oss_url = upload_video_to_oss(video_url, 'image2video', task_id)
                if oss_url:
                    record.oss_video_url = oss_url
        
        # 如果有处理时间，保存
        if process_time is not None:
            record.process_time = process_time
        
        # 保存到数据库
        db.session.commit()
        logger.info(f"更新Image2Video任务状态成功，任务ID: {task_id}, 状态: {status}")
        return True
        
    except Exception as e:
        logger.error(f"更新Image2Video任务状态失败: {str(e)}")
        # 回滚事务
        db.session.rollback()
        return False

def upload_video_to_oss(video_url, video_type, task_id):
    """
    将视频上传到OSS
    
    Args:
        video_url: 原始视频URL
        video_type: 视频类型，'text2video' 或 'image2video'
        task_id: 任务ID
        
    Returns:
        str: 上传成功返回OSS URL，失败返回None
    """
    try:
        # 检查OSS客户端是否可用
        if not oss_client.is_available():
            logger.error("OSS客户端未初始化，无法上传视频")
            return None
        
        # 从URL下载视频文件
        logger.info(f"开始下载视频: {video_url}")
        response = requests.get(video_url, stream=True, timeout=60)
        
        if response.status_code != 200:
            logger.error(f"下载视频失败，状态码: {response.status_code}")
            return None
        
        # 获取Content-Type
        content_type = response.headers.get('Content-Type', 'video/mp4')
        
        # 创建临时文件保存视频
        # 从URL中提取文件名
        parsed_url = urlparse(video_url)
        file_name = os.path.basename(parsed_url.path)
        if not file_name or '.' not in file_name:
            # 如果URL没有文件名或扩展名，使用任务ID并添加.mp4扩展名
            file_name = f"{task_id}.mp4"
        
        # 创建临时文件路径
        temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file_name)
        
        # 下载文件到临时路径
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"视频下载完成，临时文件: {temp_path}")
        
        # 构建OSS目标路径
        date_prefix = datetime.now().strftime('%Y%m%d')
        oss_object_name = f"ai-videos/{date_prefix}/{video_type}_{task_id}_{file_name}"
        
        # 上传到OSS
        logger.info(f"开始上传视频到OSS: {oss_object_name}")
        success, oss_url = oss_client.upload_file(temp_path, content_type)
        
        # 删除临时文件
        try:
            os.remove(temp_path)
            logger.info(f"临时文件已删除: {temp_path}")
        except Exception as e:
            logger.warning(f"删除临时文件失败: {str(e)}")
        
        if not success:
            logger.error("上传视频到OSS失败")
            return None
        
        logger.info(f"视频成功上传到OSS: {oss_url}")
        return oss_url
        
    except Exception as e:
        logger.error(f"上传视频到OSS失败: {str(e)}")
        return None

class ReplicateImage2VideoDBHelper:
    """
    处理Replicate图像转视频的数据库操作
    """
    
    @staticmethod
    def save_request(task_id, image_url, params):
        """
        保存Replicate图片到视频请求到数据库
        
        参数:
            task_id: 任务ID
            image_url: 图片URL
            params: 请求参数字典
        """
        try:
            new_request = ReplicateImage2VideoRequest(
                task_id=task_id,
                image_url=image_url,
                prompt=params.get('prompt', ''),
                model=params.get('model', ''),
                width=params.get('width', 0),
                height=params.get('height', 0),
                num_frames=params.get('num_frames', 81),
                fps=params.get('fps', 0),
                seed=params.get('seed'),
                guide_scale=params.get('guide_scale'),
                steps=params.get('steps'),
                shift=params.get('shift'),
                request_params=json.dumps(params, ensure_ascii=False),
                status='PENDING'
            )
            
            db.session.add(new_request)
            db.session.commit()
            logger.info(f"已保存Replicate图片到视频请求: {task_id}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"保存Replicate图片到视频请求失败: {e}")
            return False
    
    @staticmethod
    def update_status(task_id, status, replicate_id=None, video_url=None, oss_video_url=None, response_data=None, process_time=None):
        """
        更新Replicate图片到视频请求状态
        
        参数:
            task_id: 任务ID
            status: 任务状态
            replicate_id: Replicate预测ID
            video_url: 视频URL
            oss_video_url: OSS视频URL
            response_data: 响应数据
            process_time: 处理时间
        """
        try:
            request = ReplicateImage2VideoRequest.query.filter_by(task_id=task_id).first()
            if not request:
                logger.error(f"未找到Replicate图片到视频请求: {task_id}")
                return False
                
            request.status = status
            
            if replicate_id:
                request.replicate_id = replicate_id
                
            if video_url:
                request.video_url = video_url
                
            if oss_video_url:
                request.oss_video_url = oss_video_url
                
            if response_data:
                request.response_data = json.dumps(response_data, ensure_ascii=False)
                
            if process_time is not None:
                request.process_time = process_time
                
            db.session.commit()
            logger.info(f"已更新Replicate图片到视频请求状态: {task_id} -> {status}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"更新Replicate图片到视频请求状态失败: {e}")
            return False
    
    @staticmethod
    def get_history(limit=10):
        """
        获取Replicate图片到视频历史记录
        
        参数:
            limit: 结果数量限制
        
        返回:
            历史记录列表
        """
        try:
            requests = ReplicateImage2VideoRequest.query.order_by(
                ReplicateImage2VideoRequest.created_at.desc()
            ).limit(limit).all()
            
            result = [request.to_dict() for request in requests]
            return result
        except Exception as e:
            logger.error(f"获取Replicate图片到视频历史记录失败: {e}")
            return []

# 兼容性函数，保持向后兼容性
def save_replicate_image2video_request(task_id, image_url, params):
    """
    保存Replicate图片到视频请求到数据库 (兼容性函数)
    """
    return ReplicateImage2VideoDBHelper.save_request(task_id, image_url, params)

def update_replicate_image2video_status(task_id, status, replicate_id=None, video_url=None, oss_video_url=None, response_data=None, process_time=None):
    """
    更新Replicate图片到视频请求状态 (兼容性函数)
    """
    return ReplicateImage2VideoDBHelper.update_status(task_id, status, replicate_id, video_url, oss_video_url, response_data, process_time)

def get_replicate_image2video_history(limit=10):
    """
    获取Replicate图片到视频历史记录 (兼容性函数)
    """
    return ReplicateImage2VideoDBHelper.get_history(limit)

def get_text2video_history():
    """获取文本生成视频的历史记录"""
    try:
        records = Text2VideoRequest.query.order_by(Text2VideoRequest.created_at.desc()).all()
        return [record.to_dict() for record in records]
    except Exception as e:
        logger.error(f"获取Text2Video历史记录失败: {str(e)}")
        return []

def get_image2video_history():
    """获取图片生成视频的历史记录"""
    try:
        records = Image2VideoRequest.query.order_by(Image2VideoRequest.created_at.desc()).limit(10).all()
        history = [record.to_dict() for record in records]
        return history
    except Exception as e:
        logger.error(f"查询Image2Video历史记录失败: {str(e)}")
        return [] 