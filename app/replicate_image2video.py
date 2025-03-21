import os
import json
import time
import logging
import uuid
import requests
import replicate
from io import BytesIO
from PIL import Image
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from app.oss_client import oss_client
from datetime import datetime
from urllib.parse import unquote, quote
from http import HTTPStatus
# 导入数据库操作函数
from app.db_utils import ReplicateImage2VideoDBHelper
# 兼容性导入
from app.db_utils import save_replicate_image2video_request, update_replicate_image2video_status, get_replicate_image2video_history

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('replicate_image2video')

# 创建蓝图
replicate_image2video_bp = Blueprint('replicate_image2video', __name__, url_prefix='/api/replicate/image2video')

# 任务状态存储
task_status = {}

# 计数器记录
request_times = {}

# 加载环境变量
load_dotenv()
REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN')
# 设置 Replicate API 密钥
os.environ['REPLICATE_API_TOKEN'] = REPLICATE_API_TOKEN

# 图片到视频生成端点
@replicate_image2video_bp.route('', methods=['POST'])
def generate_video():
    logger.info(f"收到Replicate图片到视频生成请求: {request.form}")
    
    # 记录开始时间
    start_time = time.time()
    task_id = str(uuid.uuid4())
    
    try:
        # 检查是否上传了图片
        if 'image' not in request.files:
            return jsonify({'error': '没有上传图片'}), 400
            
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'error': '没有选择图片文件'}), 400
            
        # 生成安全的文件名并保存
        filename = secure_filename(image_file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext not in ['.jpg', '.jpeg', '.png']:
            return jsonify({'error': '不支持的图片格式，请上传JPG或PNG格式'}), 400
            
        # 创建带有时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{timestamp}_{filename}"
        
        # 保存图片到上传文件夹
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        image_path = os.path.join(upload_folder, new_filename)
        image_file.save(image_path)
        
        # 上传到OSS并获取URL
        success, image_url = oss_client.upload_file(image_path)
        
        if not success or not image_url:
            logger.error("OSS上传失败")
            return jsonify({'error': 'OSS上传失败'}), 500
            
        logger.info(f"图片已上传至OSS: {image_url}")
        
        # 获取请求参数
        prompt = request.form.get('prompt', '')
        model = request.form.get('model', 'wavespeedai/wan-2.1-i2v-480p')
        num_frames = int(request.form.get('num_frames', 81))
        fps = int(request.form.get('fps', 16))
        guide_scale = float(request.form.get('guide_scale', 5.0))
        steps = int(request.form.get('steps', 30))
        shift = int(request.form.get('shift', 3))
        max_area = request.form.get('max_area', '832x480')
        fast_mode = request.form.get('fast_mode', 'Balanced')
        seed = request.form.get('seed')
        
        if seed and seed.strip():
            try:
                seed = int(seed)
            except ValueError:
                seed = None
                
        # 准备Replicate API调用的输入参数
        input_params = {
            "image": image_url,
            "prompt": prompt,
            "num_frames": num_frames,
            "fps": fps,
            "guide_scale": guide_scale,
            "steps": steps,
            "shift": shift,
                "max_area": max_area,
                "fast_mode": fast_mode,
            "max_area": max_area,
            "fast_mode": fast_mode
        }
        
        # 添加可选参数
        if seed is not None:
            input_params["seed"] = seed
            
        # 计算宽度和高度
        if "480p" in model:
            input_params["width"] = 480
            input_params["height"] = 480
        elif "720p" in model:
            input_params["width"] = 720
            input_params["height"] = 720
        else:
            input_params["width"] = 480
            input_params["height"] = 480
            
        # 保存请求到数据库
        ReplicateImage2VideoDBHelper.save_request(
            task_id=task_id,
            image_url=image_url,
            params={
                "prompt": prompt,
                "model": model,
                "width": input_params["width"],
                "height": input_params["height"],
                "num_frames": num_frames,
                "fps": fps,
                "seed": seed,
                "guide_scale": guide_scale,
                "steps": steps,
                "shift": shift,
                "max_area": max_area,
                "fast_mode": fast_mode
            }
        )
        
        # 启动Replicate API调用任务（异步）
        # 注意：实际的Replicate API调用将在状态检查路由中进行
        task_status[task_id] = {
            "status": "PENDING",
            "image_url": image_url,
            "model": model,
            "params": input_params,
            "start_time": start_time,
            "replicate_id": None,
            "video_url": None,
            "error": None
        }
        
        logger.info(f"任务已创建: {task_id}")
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '图片到视频任务已创建，请定期检查状态'
        })
        
    except Exception as e:
        logger.error(f"处理请求时发生错误: {e}", exc_info=True)
        return jsonify({'error': f'处理请求时发生错误: {str(e)}'}), 500

# 检查任务状态端点
@replicate_image2video_bp.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    logger.info(f"检查任务状态: {task_id}")
    
    try:
        if task_id not in task_status:
            # 尝试从数据库加载任务
            tasks = ReplicateImage2VideoDBHelper.get_history()
            task_found = False
            
            for task in tasks:
                if task['task_id'] == task_id:
                    task_found = True
                    return jsonify({
                        'status': task['status'],
                        'video_url': task['video_url'],
                        'process_time': task['process_time'],
                        'replicate_id': task['replicate_id']
                    })
                    
            if not task_found:
                return jsonify({'error': f'找不到任务: {task_id}'}), 404
                
        task_info = task_status[task_id]
        current_status = task_info["status"]
        
        # 如果任务是PENDING状态，启动Replicate API调用
        if current_status == "PENDING" and not task_info.get("replicate_id"):
            try:
                # 设置Replicate客户端
                client = replicate.Client(api_token=REPLICATE_API_TOKEN)
                
                # 开始Replicate预测
                logger.info(f"开始调用Replicate API: {task_info['model']} 参数: {task_info['params']}")
                prediction = client.run(
                    task_info['model'],
                    input=task_info['params']
                )
                
                # 检查预测结果
                if prediction:
                    logger.info(f"Replicate API返回结果: {prediction}")
                    
                    # 从预测结果中获取视频URL
                    video_url = prediction
                    if isinstance(prediction, list) and len(prediction) > 0:
                        video_url = prediction[0]
                    
                    # 确保video_url是字符串类型
                    if hasattr(video_url, 'url'):  # 如果是FileOutput类型的对象，它可能有url属性
                        video_url = video_url.url
                    video_url = str(video_url)  # 确保转换为字符串
                        
                    # 更新任务状态
                    task_info["status"] = "SUCCEEDED"
                    task_info["video_url"] = video_url
                    task_info["end_time"] = time.time()
                    task_info["process_time"] = task_info["end_time"] - task_info["start_time"]
                    task_info["replicate_id"] = getattr(prediction, 'id', 'unknown')
                    
                    # 准备response_data以便安全序列化
                    if isinstance(prediction, dict):
                        # 创建一个新字典，确保所有值都是可序列化的
                        response_data = {}
                        for k, v in prediction.items():
                            try:
                                # 尝试将值转换为JSON，确保可序列化
                                json.dumps({k: v})
                                response_data[k] = v
                            except:
                                # 如果无法序列化，则转换为字符串
                                response_data[k] = str(v)
                    else:
                        # 尝试转换为可序列化的格式
                        try:
                            # 不要直接使用__dict__，它可能包含不可序列化的对象
                            if hasattr(prediction, '__dict__'):
                                response_data = {"result": str(prediction)}
                            else:
                                response_data = {"result": str(prediction)}
                        except:
                            response_data = {"result": str(prediction)}
                    
                    # 更新数据库
                    ReplicateImage2VideoDBHelper.update_status(
                        task_id=task_id,
                        status="SUCCEEDED",
                        replicate_id=task_info["replicate_id"],
                        video_url=video_url,
                        response_data=response_data,
                        process_time=task_info["process_time"]
                    )
                    
                    logger.info(f"任务完成: {task_id}, 视频URL: {video_url}")
                else:
                    # 预测失败
                    task_info["status"] = "FAILED"
                    task_info["error"] = "Replicate API调用未返回结果"
                    
                    # 更新数据库
                    ReplicateImage2VideoDBHelper.update_status(
                        task_id=task_id,
                        status="FAILED",
                        response_data={"error": task_info["error"]},
                        process_time=time.time() - task_info["start_time"]
                    )
                    
                    logger.error(f"任务失败: {task_id}, 错误: {task_info['error']}")
                    
            except Exception as api_error:
                # API调用异常
                task_info["status"] = "FAILED"
                task_info["error"] = f"Replicate API调用失败: {str(api_error)}"
                
                # 更新数据库
                ReplicateImage2VideoDBHelper.update_status(
                    task_id=task_id,
                    status="FAILED",
                    response_data={"error": task_info["error"]},
                    process_time=time.time() - task_info["start_time"]
                )
                
                logger.error(f"任务失败: {task_id}, 错误: {task_info['error']}")
        elif current_status == "SUCCEEDED" and task_info.get("video_url"):
            # 如果任务已成功，确保数据库状态已更新
            # 检查数据库中的状态
            tasks = ReplicateImage2VideoDBHelper.get_history()
            for db_task in tasks:
                if db_task['task_id'] == task_id:
                    # 如果数据库中的状态不是SUCCEEDED，更新它
                    if db_task['status'] != "SUCCEEDED":
                        logger.info(f"任务 {task_id} 内存状态已是SUCCEEDED，但数据库中仍是 {db_task['status']}，正在更新...")
                        
                        # 准备response_data
                        response_data = {"result": str(task_info.get("video_url", ""))}
                        
                        try:
                            # 确保可以序列化
                            json.dumps(response_data)
                        except:
                            # 如果序列化失败，简化response_data
                            response_data = {"result": "success"}
                            
                        # 更新数据库
                        ReplicateImage2VideoDBHelper.update_status(
                            task_id=task_id,
                            status="SUCCEEDED",
                            replicate_id=task_info.get("replicate_id", "unknown"),
                            video_url=task_info.get("video_url", ""),
                            response_data=response_data,
                            process_time=task_info.get("process_time", 0)
                        )
                    break
        
        # 格式化处理时间
        process_time = None
        process_time_formatted = None
        
        if task_info["status"] in ["SUCCEEDED", "FAILED"] and "start_time" in task_info:
            end_time = task_info.get("end_time", time.time())
            process_time = end_time - task_info["start_time"]
            
            if process_time < 60:
                process_time_formatted = f"{process_time:.2f}秒"
            else:
                minutes = int(process_time // 60)
                seconds = process_time % 60
                process_time_formatted = f"{minutes}分 {seconds:.2f}秒"
                
        # 构造返回结果
        result = {
            'status': task_info["status"],
            'request_id': task_id
        }
        
        if task_info.get("video_url"):
            result['video_url'] = task_info["video_url"]
            
        if task_info.get("error"):
            result['error'] = task_info["error"]
            
        if process_time is not None:
            result['process_time'] = process_time
            result['process_time_formatted'] = process_time_formatted
            
        if task_info.get("replicate_id"):
            result['replicate_id'] = task_info["replicate_id"]
            
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"检查任务状态时发生错误: {e}", exc_info=True)
        return jsonify({'error': f'检查任务状态时发生错误: {str(e)}'}), 500

# 获取历史记录
@replicate_image2video_bp.route('/history', methods=['GET'])
def get_history():
    try:
        # 从数据库加载历史记录
        history = ReplicateImage2VideoDBHelper.get_history(limit=20)
        
        return jsonify({
            'success': True,
            'data': history
        })
    except Exception as e:
        logger.error(f"获取历史记录失败: {e}")
        return jsonify({
            'success': False,
            'error': f'获取历史记录失败: {str(e)}'
        }), 500

# 视频代理
@replicate_image2video_bp.route('/video-proxy', methods=['GET'])
def video_proxy():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': '未提供视频URL'}), 400
        
    try:
        # 解码URL
        url = unquote(url)
        
        # 发送请求获取视频数据
        response = requests.get(url, stream=True)
        
        if not response.ok:
            return jsonify({'error': f'获取视频失败: HTTP {response.status_code}'}), response.status_code
            
        # 创建流式响应
        def generate():
            for chunk in response.iter_content(chunk_size=4096):
                yield chunk
                
        # 获取内容类型
        content_type = response.headers.get('Content-Type', 'video/mp4')
        
        # 返回流式响应
        return Response(
            stream_with_context(generate()),
            content_type=content_type,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Content-Disposition': 'inline',
                'Content-Length': response.headers.get('Content-Length', '')
            }
        )
    except Exception as e:
        logger.error(f"代理视频时发生错误: {e}", exc_info=True)
        return jsonify({'error': f'代理视频时发生错误: {str(e)}'}), 500 