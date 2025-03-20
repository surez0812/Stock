from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class Text2VideoRequest(db.Model):
    """文本生成视频的请求记录表"""
    
    __tablename__ = 'text2video_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    task_id = db.Column(db.String(64), unique=True, nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    model = db.Column(db.String(64), nullable=False)
    size = db.Column(db.String(32), nullable=False)
    fps = db.Column(db.Integer, nullable=False)
    seed = db.Column(db.String(32), nullable=True)
    prompt_extend = db.Column(db.Boolean, default=True, nullable=False)
    request_params = db.Column(db.Text, nullable=False)  # 存储为JSON字符串
    response_data = db.Column(db.Text, nullable=True)    # 存储为JSON字符串
    status = db.Column(db.String(16), default='PENDING', nullable=False)
    video_url = db.Column(db.String(512), nullable=True)
    oss_video_url = db.Column(db.String(512), nullable=True)
    process_time = db.Column(db.Float, nullable=True)  # 处理时间（秒）
    
    def to_dict(self):
        """转换为字典，用于JSON序列化"""
        try:
            request_params = json.loads(self.request_params) if self.request_params else {}
        except:
            request_params = {}
            
        try:
            response_data = json.loads(self.response_data) if self.response_data else {}
        except:
            response_data = {}
        
        return {
            'id': self.id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'task_id': self.task_id,
            'prompt': self.prompt,
            'model': self.model,
            'size': self.size,
            'fps': self.fps,
            'seed': self.seed,
            'prompt_extend': self.prompt_extend,
            'request_params': request_params,
            'response_data': response_data,
            'status': self.status,
            'video_url': self.video_url,
            'oss_video_url': self.oss_video_url,
            'process_time': self.process_time
        }

class Image2VideoRequest(db.Model):
    """图片生成视频的请求记录表"""
    
    __tablename__ = 'image2video_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    task_id = db.Column(db.String(64), unique=True, nullable=False)
    image_url = db.Column(db.String(512), nullable=False)
    prompt = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(64), nullable=False)
    size = db.Column(db.String(32), nullable=False)
    duration = db.Column(db.Float, nullable=False)
    fps = db.Column(db.Integer, nullable=False)
    motion_level = db.Column(db.String(16), nullable=False)
    seed = db.Column(db.String(32), nullable=True)
    prompt_extend = db.Column(db.Boolean, default=True, nullable=False)
    request_params = db.Column(db.Text, nullable=False)  # 存储为JSON字符串
    response_data = db.Column(db.Text, nullable=True)    # 存储为JSON字符串
    status = db.Column(db.String(16), default='PENDING', nullable=False)
    video_url = db.Column(db.String(512), nullable=True)
    oss_video_url = db.Column(db.String(512), nullable=True)
    process_time = db.Column(db.Float, nullable=True)  # 处理时间（秒）
    
    def to_dict(self):
        """转换为字典，用于JSON序列化"""
        try:
            request_params = json.loads(self.request_params) if self.request_params else {}
        except:
            request_params = {}
            
        try:
            response_data = json.loads(self.response_data) if self.response_data else {}
        except:
            response_data = {}
            
        return {
            'id': self.id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'task_id': self.task_id,
            'image_url': self.image_url,
            'prompt': self.prompt,
            'model': self.model,
            'size': self.size,
            'duration': self.duration,
            'fps': self.fps,
            'motion_level': self.motion_level,
            'seed': self.seed,
            'prompt_extend': self.prompt_extend,
            'request_params': request_params,
            'response_data': response_data,
            'status': self.status,
            'video_url': self.video_url,
            'oss_video_url': self.oss_video_url,
            'process_time': self.process_time
        }

class ReplicateImage2VideoRequest(db.Model):
    """Replicate平台图片生成视频的请求记录表"""
    
    __tablename__ = 'replicate_image2video_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    task_id = db.Column(db.String(64), unique=True, nullable=False)
    image_url = db.Column(db.String(512), nullable=False)
    prompt = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(64), nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    num_frames = db.Column(db.Integer, nullable=False)
    fps = db.Column(db.Integer, nullable=False)
    seed = db.Column(db.Integer, nullable=True)
    guide_scale = db.Column(db.Float, nullable=True)
    steps = db.Column(db.Integer, nullable=True)
    shift = db.Column(db.Integer, nullable=True)
    request_params = db.Column(db.Text, nullable=False)  # 存储为JSON字符串
    response_data = db.Column(db.Text, nullable=True)    # 存储为JSON字符串
    status = db.Column(db.String(16), default='PENDING', nullable=False)
    video_url = db.Column(db.String(512), nullable=True)
    oss_video_url = db.Column(db.String(512), nullable=True)
    process_time = db.Column(db.Float, nullable=True)  # 处理时间（秒）
    replicate_id = db.Column(db.String(128), nullable=True)  # Replicate API返回的预测ID
    
    def to_dict(self):
        """转换为字典，用于JSON序列化"""
        try:
            request_params = json.loads(self.request_params) if self.request_params else {}
        except:
            request_params = {}
            
        try:
            response_data = json.loads(self.response_data) if self.response_data else {}
        except:
            response_data = {}
            
        return {
            'id': self.id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'task_id': self.task_id,
            'image_url': self.image_url,
            'prompt': self.prompt,
            'model': self.model,
            'width': self.width,
            'height': self.height,
            'num_frames': self.num_frames,
            'fps': self.fps,
            'seed': self.seed,
            'guide_scale': self.guide_scale,
            'steps': self.steps,
            'shift': self.shift,
            'request_params': request_params,
            'response_data': response_data,
            'status': self.status,
            'video_url': self.video_url,
            'oss_video_url': self.oss_video_url,
            'process_time': self.process_time,
            'replicate_id': self.replicate_id
        } 