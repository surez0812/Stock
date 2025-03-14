import os
import json
import time
import logging
import uuid
import requests
from io import BytesIO
from PIL import Image
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from app.oss_client import oss_client
from datetime import datetime
from urllib.parse import unquote, quote
from http import HTTPStatus
# 导入 DashScope SDK
from dashscope import VideoSynthesis
# 导入数据库操作函数
from app.db_utils import save_image2video_request, update_image2video_status, get_image2video_history

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('image2video')

# 创建蓝图
image2video_bp = Blueprint('image2video', __name__, url_prefix='/api/image2video')

# 任务状态存储
task_status = {}

# 计数器记录
request_times = {}

# 加载环境变量
load_dotenv()
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
# 设置 DashScope API 密钥
os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY

# 图片到视频生成端点
@image2video_bp.route('', methods=['POST'])
def generate_video():
    logger.info(f"收到图片到视频生成请求: {request.form}")
    logger.info(f"DashScope SDK版本信息: {getattr(VideoSynthesis, '__version__', '未知')}")
    logger.info(f"可用方法: {[method for method in dir(VideoSynthesis) if not method.startswith('_')]}")
    
    # 记录开始时间
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    try:
        # 检查是否上传了图片
        if 'image' not in request.files:
            return jsonify({'error': '未找到图片文件'}), 400
        
        image_file = request.files['image']
        
        # 检查文件名是否为空
        if image_file.filename == '':
            return jsonify({'error': '未选择图片文件'}), 400
        
        # 检查文件大小
        image_file.seek(0, os.SEEK_END)
        file_size = image_file.tell()
        image_file.seek(0)
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'error': '文件大小超过限制，最大5MB'}), 400
        
        # 获取请求参数
        model = request.form.get('model', 'wanx2.1-i2v-turbo')
        size = request.form.get('size', '1280*720')
        duration = float(request.form.get('duration', 3.0))
        fps = int(request.form.get('fps', 16))
        motion_level = request.form.get('motion_level', 'medium')
        prompt = request.form.get('prompt', '')  # 获取提示文本，默认为空字符串
        
        # 获取新增参数
        seed = request.form.get('seed', '')  # 获取随机数种子，默认为空字符串
        prompt_extend = request.form.get('prompt_extend', 'true')  # 获取是否开启提示词智能改写，默认为true
        
        # 记录请求参数
        logger.info(f"处理参数: 模型={model}, 尺寸={size}, 时长={duration}秒, FPS={fps}, 动作级别={motion_level}")
        if prompt:
            logger.info(f"提示文本: {prompt}")
        if seed:
            logger.info(f"随机数种子: {seed}")
        logger.info(f"提示词智能改写: {prompt_extend}")
        
        # 验证图片格式
        try:
            img = Image.open(image_file)
            # 重置文件指针
            image_file.seek(0)
        except Exception as e:
            logger.error(f"图片格式验证失败: {e}")
            return jsonify({'error': '无效的图片格式'}), 400
        
        # 生成唯一的文件名
        original_filename = secure_filename(image_file.filename)
        file_extension = os.path.splitext(original_filename)[1]
        unique_filename = f"image2video_{uuid.uuid4().hex}{file_extension}"
        
        # 创建临时文件保存上传的图片
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        image_file.save(temp_path)
        
        # 上传图片到OSS
        logger.info(f"开始上传图片到OSS: {unique_filename}")
        success, image_url = oss_client.upload_file(temp_path)
        
        # 删除临时文件
        try:
            os.remove(temp_path)
        except Exception as e:
            logger.warning(f"删除临时文件失败: {str(e)}")
        
        if not success:
            return jsonify({'error': '上传图片到OSS失败'}), 500
        
        # 记录OSS URL
        logger.info(f"图片OSS URL: {image_url}")
        
        # 确保API能够访问图片URL (使用签名URL)
        try:
            # 从URL中提取对象路径
            object_path = image_url.split('.com/')[1] if '.com/' in image_url else image_url
            logger.info(f"提取的对象路径: {object_path}")
            
            success, signed_url = oss_client.get_signed_url(object_path, 86400)  # 24小时有效期
            if success:
                image_url = signed_url
                logger.info(f"使用签名URL: {image_url}")
        except Exception as e:
            logger.warning(f"获取签名URL时出错: {str(e)}")
            # 继续使用原始URL
        
        # 使用 DashScope SDK 调用图片到视频生成API
        logger.info(f"准备使用 DashScope SDK 调用图片到视频生成API")
        
        # 准备参数
        parameters = {
            'size': size,
            'duration': duration,
            'fps': fps,
            'motion_level': motion_level,
            'format': 'mp4'
        }
        
        # 添加可选参数
        if seed:
            try:
                seed_int = int(seed)
                if 0 <= seed_int <= 2147483647:
                    parameters['seed'] = seed_int
                    logger.info(f"使用随机数种子: {seed_int}")
                else:
                    logger.warning(f"随机数种子 {seed} 超出范围 [0, 2147483647]，将不使用")
            except ValueError:
                logger.warning(f"随机数种子 {seed} 不是有效整数，将不使用")
        
        # 设置提示词智能改写参数
        prompt_extend_bool = prompt_extend.lower() == 'true'
        parameters['prompt_extend'] = prompt_extend_bool
        logger.info(f"提示词智能改写设置为: {prompt_extend_bool}")
        
        # 记录API调用参数
        api_params = {
            'model': model,
            'img_url': image_url,
            'parameters': parameters
        }
        
        if prompt:
            api_params['prompt'] = prompt
            
        logger.info(f"DashScope API调用参数: {json.dumps(api_params, ensure_ascii=False)}")
        
        # 调用API
        try:
            logger.info(f"开始调用DashScope VideoSynthesis API")
            
            if prompt:
                # 如果有提示文本，包含在请求中
                logger.info("使用带提示文本的调用方式")
                response = VideoSynthesis.call(
                    model=model,
                    prompt=prompt,
                    img_url=image_url,
                    size=size,
                    duration=duration,
                    fps=fps,
                    motion_level=motion_level,
                    format='mp4',
                    seed=parameters.get('seed') if 'seed' in parameters else None,
                    prompt_extend=parameters.get('prompt_extend')
                )
            else:
                # 如果没有提示文本，不包含prompt参数
                logger.info("使用不带提示文本的调用方式")
                response = VideoSynthesis.call(
                    model=model,
                    img_url=image_url,
                    size=size,
                    duration=duration,
                    fps=fps,
                    motion_level=motion_level,
                    format='mp4',
                    seed=parameters.get('seed') if 'seed' in parameters else None,
                    prompt_extend=parameters.get('prompt_extend')
                )
                
            logger.info(f"DashScope API响应状态码: {response.status_code}")
            
            # 解析响应
            if response.status_code == HTTPStatus.OK:
                # 计算处理时间
                process_time = time.time() - start_time
                logger.info(f"视频生成成功，总处理时间: {process_time:.2f}秒")
                
                # 将完整响应返回给前端，但避免使用.to_dict()方法
                try:
                    # 尝试将响应对象转换为字典
                    response_dict = {}
                    # 提取常见属性
                    for attr in ['status_code', 'request_id', 'code', 'message', 'output', 'usage']:
                        try:
                            if attr in response:
                                response_dict[attr] = response[attr]
                        except (KeyError, TypeError):
                            pass
                    
                    logger.info(f"视频生成成功，响应内容: {json.dumps(response_dict, ensure_ascii=False)}")
                except Exception as e:
                    logger.warning(f"序列化响应时出错: {str(e)}")
                    logger.info(f"视频生成成功，基本响应: {str(response)}")
                
                # 构建响应数据
                response_data = {
                    'status': 'SUCCEEDED',
                    'process_time': round(process_time, 2),  # 处理时间（秒）
                    'process_time_formatted': f"{int(process_time // 60)}分{int(process_time % 60)}秒" # 格式化时间
                }
                
                # 添加主要响应字段
                try:
                    response_data['status_code'] = response['status_code'] if 'status_code' in response else 200
                    if 'request_id' in response:
                        response_data['request_id'] = response['request_id']
                    if 'code' in response:
                        response_data['code'] = response['code']
                    if 'message' in response:
                        response_data['message'] = response['message']
                    
                    # 提取output内容
                    if 'output' in response:
                        response_data['output'] = response['output']
                        # 如果output中有task_id，将其提升到顶层
                        if 'task_id' in response['output']:
                            response_data['task_id'] = response['output']['task_id']
                    elif hasattr(response, 'output'):
                        try:
                            output_dict = {}
                            if hasattr(response.output, 'video_url'):
                                output_dict['video_url'] = response.output.video_url
                            # 如果output中有task_id，将其提升到顶层
                            if hasattr(response.output, 'task_id'):
                                response_data['task_id'] = response.output.task_id
                                output_dict['task_id'] = response.output.task_id
                            response_data['output'] = output_dict
                        except Exception as e:
                            logger.warning(f"提取output内容时出错: {str(e)}")
                    
                    # 提取usage内容
                    if 'usage' in response:
                        response_data['usage'] = response['usage']
                    elif hasattr(response, 'usage'):
                        try:
                            usage_dict = data['usage']
                            usage = type('Usage', (), {})
                            
                            # 将字典转换为属性
                            for key, value in usage_dict.items():
                                setattr(usage, key, value)
                            
                            response_data['usage'] = usage
                        except Exception as e:
                            logger.warning(f"提取usage内容时出错: {str(e)}")
                except Exception as e:
                    logger.warning(f"构建响应数据时出错: {str(e)}")
                    # 简单的回退方案
                    if hasattr(response, 'output') and hasattr(response.output, 'video_url'):
                        response_data['video_url'] = response.output.video_url
                
                # 收集请求数据用于保存到数据库
                request_data = {
                    'prompt': prompt,
                    'model': model,
                    'size': size,
                    'duration': duration,
                    'fps': fps,
                    'motion_level': motion_level,
                    'seed': seed,
                    'prompt_extend': prompt_extend
                }
                
                # 将请求保存到数据库
                save_image2video_request(response_data['task_id'], request_data, image_url)
                
                return jsonify(response_data)
            elif hasattr(response, 'task_id'):
                # 异步任务，保存任务ID
                try:
                    task_id = response.task_id
                    
                    # 确保任务ID是有效的字符串
                    if not task_id:
                        raise ValueError("收到空的任务ID")
                        
                    logger.info(f"异步任务已创建，任务ID: {task_id}")
                    
                    # 计算到目前为止的处理时间
                    current_process_time = time.time() - start_time
                    logger.info(f"创建异步任务耗时: {current_process_time:.2f}秒")
                    
                    # 存储任务状态和开始时间
                    task_status[task_id] = {
                        'status': 'PENDING',
                        'start_time': time.time(),
                        'request_id': request_id,
                        'upload_start_time': start_time
                    }
                    
                    # 构建响应数据
                    response_data = {
                        'task_id': task_id,
                        'status': 'PENDING',
                        'message': '视频生成任务已提交，请稍后查询结果',
                        'upload_process_time': round(current_process_time, 2),
                        'upload_process_time_formatted': f"{int(current_process_time // 60)}分{int(current_process_time % 60)}秒"
                    }
                    
                    # 添加其他可能的响应数据
                    try:
                        if hasattr(response, 'status_code'):
                            response_data['status_code'] = response.status_code
                        if hasattr(response, 'request_id'):
                            response_data['request_id'] = response.request_id
                        elif 'request_id' in response:
                            response_data['request_id'] = response['request_id']
                        if hasattr(response, 'code'):
                            response_data['code'] = response.code
                        elif 'code' in response:
                            response_data['code'] = response['code']
                            
                        # 确保output字段存在，并包含task_id
                        response_data['output'] = {
                            'task_id': task_id,
                            'task_status': 'PENDING'
                        }
                    except Exception as e:
                        logger.warning(f"添加异步响应数据时出错: {str(e)}")
                    
                    logger.info(f"返回给前端的任务ID: {task_id}")
                    
                    # 收集请求数据用于保存到数据库
                    request_data = {
                        'prompt': prompt,
                        'model': model,
                        'size': size,
                        'duration': duration,
                        'fps': fps,
                        'motion_level': motion_level,
                        'seed': seed,
                        'prompt_extend': prompt_extend
                    }
                    
                    # 将请求保存到数据库
                    save_image2video_request(task_id, request_data, image_url)
                    
                    return jsonify(response_data)
                    
                except Exception as e:
                    error_message = f"处理异步任务ID时出错: {str(e)}"
                    logger.exception(error_message)
                    return jsonify({
                        'error': error_message,
                        'status': 'FAILED'
                    }), 500
            else:
                # 处理失败情况
                error_message = f"API调用失败: 状态码 {response.status_code}"
                response_data = {
                    'error': error_message,
                    'status': 'FAILED'
                }
                
                # 添加更多错误信息
                try:
                    if hasattr(response, 'code') or 'code' in response:
                        code = getattr(response, 'code', None) or response.get('code')
                        response_data['code'] = code
                        error_message += f", 错误代码: {code}"
                    
                    if hasattr(response, 'message') or 'message' in response:
                        message = getattr(response, 'message', None) or response.get('message')
                        response_data['message'] = message
                        error_message += f", 错误信息: {message}"
                    
                    if hasattr(response, 'request_id') or 'request_id' in response:
                        request_id = getattr(response, 'request_id', None) or response.get('request_id')
                        response_data['request_id'] = request_id
                except Exception as e:
                    logger.warning(f"添加错误响应数据时出错: {str(e)}")
                    
                logger.error(error_message)
                
                # 尝试创建一个虚拟任务ID并保存失败记录
                fail_task_id = f"fail_{uuid.uuid4().hex}"
                request_data = {
                    'prompt': prompt,
                    'model': model,
                    'size': size,
                    'duration': duration,
                    'fps': fps,
                    'motion_level': motion_level,
                    'seed': seed,
                    'prompt_extend': prompt_extend,
                    'error': error_message
                }
                save_image2video_request(fail_task_id, request_data, image_url)
                update_image2video_status(fail_task_id, 'FAILED', response_data)
                
                return jsonify(response_data), 500
                
        except Exception as e:
            error_message = f"调用 DashScope API 时出错: {str(e)}"
            logger.exception(error_message)
            return jsonify({
                'error': error_message,
                'status': 'FAILED'
            }), 500
    
    except Exception as e:
        error_message = f"处理请求时出错: {str(e)}"
        logger.exception(error_message)
        return jsonify({
            'error': error_message,
            'status': 'FAILED'
        }), 500

# 检查任务状态端点
@image2video_bp.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    logger.info(f"检查任务状态: {task_id}")
    logger.info(f"DashScope SDK版本信息: {getattr(VideoSynthesis, '__version__', '未知')}")
    logger.info(f"可用方法: {[method for method in dir(VideoSynthesis) if not method.startswith('_')]}")
    
    # 验证任务ID是否有效
    if not task_id or task_id == 'undefined' or task_id == 'null':
        logger.error(f"接收到无效的任务ID: {task_id}")
        return jsonify({
            'error': '无效的任务ID',
            'status': 'INVALID',
            'task_id': task_id
        }), 400
    
    try:
        # 尝试使用SDK查询任务状态
        try:
            # 使用SDK的方法查询
            logger.info(f"使用 VideoSynthesis.get_async_result 查询任务状态")
            response = VideoSynthesis.get_async_result(task_id=task_id)
        except (AttributeError, Exception) as sdk_error:
            # 如果SDK方法不存在或出错，使用HTTP请求直接查询
            logger.warning(f"SDK查询方法出错: {str(sdk_error)}，将使用HTTP请求直接查询")
            
            # 构建API请求URL
            api_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            
            # 设置API请求头
            headers = {
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}"
            }
            
            # 发送请求到阿里云API
            logger.info(f"发送HTTP请求到: {api_url}")
            try:
                http_response = requests.get(api_url, headers=headers, timeout=10)  # 添加超时设置
                logger.info(f"HTTP请求状态码: {http_response.status_code}")
                
                # 将HTTP响应转换为类似SDK响应的格式
                if http_response.status_code == 200:
                    try:
                        response_json = http_response.json()
                        logger.info(f"HTTP响应内容: {json.dumps(response_json, ensure_ascii=False)}")
                        
                        # 验证响应数据
                        if not response_json:
                            logger.error("HTTP响应内容为空")
                            raise Exception("API返回了空的响应内容")
                        
                        # 检查任务ID是否匹配
                        if 'output' in response_json and 'task_id' in response_json['output']:
                            api_task_id = response_json['output']['task_id']
                            if api_task_id != task_id:
                                logger.warning(f"API返回的任务ID ({api_task_id}) 与请求的任务ID ({task_id}) 不匹配")
                    
                        # 创建一个类似SDK响应的对象
                        class HttpResponse:
                            def __init__(self, data):
                                self.status_code = http_response.status_code
                                self.data = data
                                
                                # 添加其他属性
                                if 'request_id' in data:
                                    self.request_id = data['request_id']
                                
                                # 构造output对象
                                if 'output' in data:
                                    output_dict = data['output']
                                    output = type('Output', (), {})
                                    
                                    # 将字典转换为属性
                                    for key, value in output_dict.items():
                                        setattr(output, key, value)
                                    
                                    self.output = output
                                
                                # 构造usage对象
                                if 'usage' in data:
                                    usage_dict = data['usage']
                                    usage = type('Usage', (), {})
                                    
                                    # 将字典转换为属性
                                    for key, value in usage_dict.items():
                                        setattr(usage, key, value)
                                    
                                    self.usage = usage
                            
                            def __getitem__(self, key):
                                return self.data.get(key)
                            
                            def __contains__(self, key):
                                return key in self.data
                        
                        response = HttpResponse(response_json)
                    except json.JSONDecodeError as json_err:
                        logger.error(f"解析HTTP响应JSON失败: {str(json_err)}")
                        logger.error(f"原始响应内容: {http_response.text[:500]}")  # 只记录前500字符
                        raise Exception(f"解析API响应失败: {str(json_err)}")
                else:
                    # 处理HTTP错误
                    error_message = f"HTTP请求失败: {http_response.status_code}"
                    try:
                        error_data = http_response.json()
                        logger.error(f"错误响应: {json.dumps(error_data, ensure_ascii=False)}")
                        error_message += f", 错误信息: {json.dumps(error_data, ensure_ascii=False)}"
                    except:
                        logger.error(f"错误响应(非JSON): {http_response.text[:500]}")  # 只记录前500字符
                        error_message += f", 响应内容: {http_response.text[:100]}..."
                    
                    raise Exception(error_message)
            except requests.exceptions.Timeout:
                logger.error("HTTP请求超时")
                raise Exception("查询任务状态超时，请稍后重试")
            except requests.exceptions.ConnectionError as conn_err:
                logger.error(f"HTTP连接错误: {str(conn_err)}")
                raise Exception("网络连接错误，无法连接到服务器")
        
        # 安全地记录响应内容
        try:
            response_dict = {}
            for attr in ['status_code', 'request_id', 'code', 'message', 'output', 'usage']:
                try:
                    if attr in response:
                        response_dict[attr] = response[attr]
                except (KeyError, TypeError):
                    pass
            logger.info(f"任务状态查询响应: {json.dumps(response_dict, ensure_ascii=False)}")
        except Exception as e:
            logger.warning(f"序列化响应时出错: {str(e)}")
            logger.info(f"任务状态查询基本响应: {str(response)}")
        
        # 处理响应
        if response.status_code == HTTPStatus.OK:
            # 提取任务状态
            task_status_value = 'UNKNOWN'
            task_id_value = task_id  # 默认使用请求中的task_id
            
            # 从响应中提取task_id和status
            if hasattr(response, 'output') and hasattr(response.output, 'task_status'):
                task_status_value = response.output.task_status
                if hasattr(response.output, 'task_id'):
                    task_id_value = response.output.task_id
            elif 'output' in response and 'task_status' in response['output']:
                task_status_value = response['output']['task_status']
                if 'task_id' in response['output']:
                    task_id_value = response['output']['task_id']
            
            # 构建基本响应数据
            response_data = {
                'task_id': task_id_value,  # 始终在顶层包含task_id
                'status': task_status_value,  # 始终在顶层包含status
                'status_code': response.status_code
            }
            
            # 添加请求ID（如果有）
            try:
                if hasattr(response, 'request_id'):
                    response_data['request_id'] = response.request_id
                elif 'request_id' in response:
                    response_data['request_id'] = response['request_id']
            except Exception:
                pass
            
            # 添加输出数据（如果有）
            try:
                output_data = {}
                # 首先尝试作为字典访问
                if 'output' in response:
                    output_data = response['output']
                # 然后尝试作为属性访问
                elif hasattr(response, 'output'):
                    if hasattr(response.output, 'task_status'):
                        output_data['task_status'] = response.output.task_status
                    if hasattr(response.output, 'task_id'):
                        output_data['task_id'] = response.output.task_id
                    if hasattr(response.output, 'video_url'):
                        output_data['video_url'] = response.output.video_url
                    if hasattr(response.output, 'submit_time'):
                        output_data['submit_time'] = response.output.submit_time
                    if hasattr(response.output, 'scheduled_time'):
                        output_data['scheduled_time'] = response.output.scheduled_time
                    if hasattr(response.output, 'end_time'):
                        output_data['end_time'] = response.output.end_time
                
                if output_data:
                    response_data['output'] = output_data
                    
                    # 如果output中有video_url，也将其提升到顶层
                    if 'video_url' in output_data:
                        response_data['video_url'] = output_data['video_url']
            except Exception as e:
                logger.warning(f"提取输出数据时出错: {str(e)}")
            
            # 添加使用数据（如果有）
            try:
                usage_data = {}
                if 'usage' in response:
                    usage_data = response['usage']
                elif hasattr(response, 'usage'):
                    for attr in ['video_count', 'video_duration', 'video_ratio']:
                        if hasattr(response.usage, attr):
                            usage_data[attr] = getattr(response.usage, attr)
                
                if usage_data:
                    response_data['usage'] = usage_data
            except Exception as e:
                logger.warning(f"提取使用数据时出错: {str(e)}")
            
            # 如果任务成功完成
            if task_status_value == 'SUCCEEDED':
                video_url = None
                # 从输出获取视频URL
                if 'output' in response_data and 'video_url' in response_data['output']:
                    video_url = response_data['output']['video_url']
                    # 确保video_url也在顶层
                    response_data['video_url'] = video_url
                
                if not video_url and hasattr(response, 'output') and hasattr(response.output, 'video_url'):
                    video_url = response.output.video_url
                    response_data['video_url'] = video_url
                    if 'output' not in response_data:
                        response_data['output'] = {}
                    response_data['output']['video_url'] = video_url
                
                # 新增: 更新数据库并上传视频到OSS
                if video_url:
                    logger.info(f"任务 {task_id} 成功完成，视频URL: {video_url}，开始更新数据库并上传到OSS")
                    
                    # 计算处理总时间（如果有记录起始时间）
                    process_time = None
                    if task_id in task_status and 'upload_start_time' in task_status[task_id]:
                        upload_start_time = task_status[task_id]['upload_start_time']
                        process_time = time.time() - upload_start_time
                        logger.info(f"任务 {task_id} 从上传到完成总耗时: {process_time:.2f}秒")
                        
                        # 添加处理时间到响应中
                        response_data['process_time'] = round(process_time, 2)
                        response_data['process_time_formatted'] = f"{int(process_time // 60)}分{int(process_time % 60)}秒"
                    
                    # 调用更新函数
                    from app.db_utils import update_image2video_status
                    update_success = update_image2video_status(
                        task_id=task_id,
                        status='SUCCEEDED',
                        response_data=response_data,
                        video_url=video_url,
                        process_time=process_time
                    )
                    
                    if update_success:
                        logger.info(f"任务 {task_id} 成功更新数据库并上传视频到OSS")
                    else:
                        logger.warning(f"任务 {task_id} 更新数据库或上传视频到OSS失败")
                else:
                    logger.warning(f"任务 {task_id} 成功完成，但未获取到视频URL")
                
                # 如果有任务开始和结束时间，也计算API处理时间
                if ('output' in response_data and 
                    'submit_time' in response_data['output'] and 
                    'end_time' in response_data['output']):
                    
                    try:
                        # 获取时间字符串
                        submit_time_str = response_data['output']['submit_time']
                        end_time_str = response_data['output']['end_time']
                        
                        # 尝试不同的日期格式
                        date_formats = [
                            "%Y-%m-%d %H:%M:%S.%f",  # 带毫秒
                            "%Y-%m-%d %H:%M:%S",     # 不带毫秒
                            "%Y-%m-%dT%H:%M:%S.%fZ", # ISO格式带Z
                            "%Y-%m-%dT%H:%M:%SZ"     # ISO格式不带毫秒
                        ]
                        
                        submit_time = None
                        end_time = None
                        
                        # 尝试解析提交时间
                        for fmt in date_formats:
                            try:
                                submit_time = datetime.strptime(submit_time_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        # 尝试解析结束时间
                        for fmt in date_formats:
                            try:
                                end_time = datetime.strptime(end_time_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        # 如果两个时间都成功解析
                        if submit_time and end_time:
                            api_process_time = (end_time - submit_time).total_seconds()
                            
                            response_data['api_process_time'] = round(api_process_time, 2)
                            response_data['api_process_time_formatted'] = f"{int(api_process_time // 60)}分{int(api_process_time % 60)}秒"
                            logger.info(f"API处理时间: {api_process_time:.2f}秒 (从 {submit_time_str} 到 {end_time_str})")
                        else:
                            logger.warning(f"无法解析日期格式: submit_time={submit_time_str}, end_time={end_time_str}")
                    except Exception as e:
                        logger.warning(f"计算API处理时间时出错: {str(e)}")
                
                logger.info(f"任务 {task_id} 成功完成，视频URL: {video_url}")
                return jsonify(response_data)
            
            # 如果任务失败
            elif task_status_value == 'FAILED':
                if 'message' in response:
                    response_data['message'] = response['message']
                elif hasattr(response, 'message'):
                    response_data['message'] = response.message
                
                # 新增: 更新数据库记录为失败状态
                from app.db_utils import update_image2video_status
                update_image2video_status(
                    task_id=task_id,
                    status='FAILED',
                    response_data=response_data
                )
                
                logger.error(f"任务 {task_id} 失败: {response_data.get('message', '')}")
                return jsonify(response_data)
            
            # 任务进行中
            else:
                return jsonify(response_data)
        else:
            # API请求失败
            error_message = f"任务状态查询失败: 状态码 {response.status_code}"
            response_data = {
                'task_id': task_id,
                'status': 'UNKNOWN',
                'error': error_message
            }
            
            # 添加额外错误信息
            try:
                if hasattr(response, 'code') or 'code' in response:
                    code = getattr(response, 'code', None) or response.get('code')
                    response_data['code'] = code
                
                if hasattr(response, 'message') or 'message' in response:
                    message = getattr(response, 'message', None) or response.get('message')
                    response_data['message'] = message
                    
                if hasattr(response, 'request_id') or 'request_id' in response:
                    request_id = getattr(response, 'request_id', None) or response.get('request_id')
                    response_data['request_id'] = request_id
                    
                # 确保output字段存在
                response_data['output'] = {
                    'task_id': task_id,
                    'task_status': 'UNKNOWN'
                }
            except Exception as e:
                logger.warning(f"添加错误信息时出错: {str(e)}")
                
            logger.error(error_message)
            return jsonify(response_data)
    
    except Exception as e:
        error_message = f"查询任务状态时出错: {str(e)}"
        logger.exception(error_message)
        return jsonify({
            'task_id': task_id,
            'status': 'UNKNOWN',
            'error': error_message,
            'output': {
                'task_id': task_id,
                'task_status': 'UNKNOWN'
            }
        })

@image2video_bp.route('/history', methods=['GET'])
def get_history():
    """获取图片生成视频历史记录"""
    try:
        records = get_image2video_history()
        return jsonify({
            'status': 'success',
            'count': len(records),
            'data': records
        })
    except Exception as e:
        logger.exception(f"获取历史记录失败: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'获取历史记录失败: {str(e)}',
            'data': []
        }), 500

# 视频代理端点，解决CORS问题
@image2video_bp.route('/video-proxy', methods=['GET'])
def video_proxy():
    """
    视频代理API，用于解决跨域请求问题
    使用方式：/api/image2video/video-proxy?url=原始视频URL
    """
    try:
        # 获取原始视频URL
        video_url = request.args.get('url')
        if not video_url:
            return jsonify({'error': '缺少视频URL参数'}), 400
        
        # URL解码
        video_url = unquote(video_url)
        logger.info(f"视频代理请求: {video_url}")
        
        # 发送请求获取视频内容
        def generate():
            with requests.get(video_url, stream=True, timeout=30) as resp:
                if resp.status_code != 200:
                    logger.error(f"获取视频失败，状态码: {resp.status_code}")
                    yield json.dumps({
                        'error': f'获取视频失败，状态码: {resp.status_code}'
                    }).encode('utf-8')
                    return
                
                # 获取响应头
                headers = resp.headers
                content_type = headers.get('Content-Type', 'video/mp4')
                content_length = headers.get('Content-Length')
                
                logger.info(f"视频内容类型: {content_type}, 大小: {content_length}")
                
                # 流式传输视频内容
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
        
        # 创建流式响应
        response = Response(stream_with_context(generate()), content_type='video/mp4')
        
        # 添加CORS头
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        
        # 添加视频相关头
        response.headers['Content-Disposition'] = 'inline'
        
        logger.info("视频代理响应已创建")
        return response
        
    except Exception as e:
        error_message = f"视频代理出错: {str(e)}"
        logger.exception(error_message)
        return jsonify({
            'error': error_message
        }), 500 