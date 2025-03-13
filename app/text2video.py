import os
import json
import time
import logging
import uuid
import requests
from flask import Blueprint, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
from http import HTTPStatus
# 导入 DashScope SDK
from dashscope import VideoSynthesis

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('text2video')

# 加载环境变量
load_dotenv()

# 创建蓝图
text2video_bp = Blueprint('text2video', __name__)

# 获取API密钥
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
# 设置 DashScope API 密钥
os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY

# 存储任务状态
task_status = {}

# 存储重试计数
retry_counters = {}
MAX_RETRIES = 5  # 最大重试次数

@text2video_bp.route('/api/text2video', methods=['POST'])
def generate_video():
    try:
        # 记录开始时间
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        data = request.get_json()
        prompt = data.get('prompt')
        model = data.get('model')
        size = data.get('size')
        
        # 获取新增参数
        fps = int(data.get('fps', 16))
        seed = data.get('seed', '')  # 获取随机数种子，默认为空字符串
        prompt_extend = data.get('prompt_extend', 'true')  # 获取是否开启提示词智能改写，默认为true

        logger.info(f"收到生成视频请求: prompt='{prompt}', model='{model}', size='{size}', fps={fps}")
        if seed:
            logger.info(f"随机数种子: {seed}")
        logger.info(f"提示词智能改写: {prompt_extend}")

        if not all([prompt, model, size]):
            return jsonify({'error': '缺少必要参数'}), 400

        # 准备参数
        parameters = {
            'size': size,
            'fps': fps,
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
            'prompt': prompt,
            'parameters': parameters
        }
        
        logger.info(f"DashScope API调用参数: {json.dumps(api_params, ensure_ascii=False)}")
        
        # 调用API
        try:
            logger.info(f"开始调用DashScope VideoSynthesis API")
            
            # 使用SDK的async_call方法
            response = VideoSynthesis.async_call(
                model=model,
                prompt=prompt,
                size=size,
                fps=fps,
                format='mp4',
                seed=parameters.get('seed') if 'seed' in parameters else None,
                prompt_extend=parameters.get('prompt_extend')
            )
            
            logger.info(f"DashScope API响应状态码: {response.status_code}")
            
            # 解析响应
            if response.status_code == HTTPStatus.OK:
                # 获取任务ID
                task_id = response.output.task_id
                
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
                
                # 初始化重试计数器
                retry_counters[task_id] = 0
                
                # 构建响应数据
                response_data = {
                    'task_id': task_id,
                    'status': 'PENDING',
                    'message': '视频生成任务已提交，请稍后查询结果',
                    'process_time': round(current_process_time, 2),
                    'process_time_formatted': f"{int(current_process_time // 60)}分{int(current_process_time % 60)}秒"
                }
                
                logger.info(f"成功创建任务: task_id={task_id}")
                return jsonify(response_data)
            else:
                # 处理失败情况
                error_message = f"API调用失败: 状态码 {response.status_code}"
                if hasattr(response, 'message'):
                    error_message += f", 错误信息: {response.message}"
                
                logger.error(error_message)
                return jsonify({
                    'error': error_message,
                    'status': 'FAILED'
                }), 500
                
        except Exception as e:
            error_message = f"调用 DashScope API 时出错: {str(e)}"
            logger.exception(error_message)
            return jsonify({
                'error': error_message,
                'status': 'FAILED'
            }), 500

    except Exception as e:
        logger.exception("生成视频时发生异常")
        return jsonify({'error': str(e)}), 500

@text2video_bp.route('/api/text2video/status/<task_id>', methods=['GET'])
def check_status(task_id):
    logger.info(f"检查任务状态: task_id={task_id}")
    
    # 验证任务ID是否有效
    if not task_id or task_id == 'undefined' or task_id == 'null':
        logger.error(f"接收到无效的任务ID: {task_id}")
        return jsonify({
            'error': '无效的任务ID',
            'status': 'INVALID',
            'task_id': task_id
        }), 400
    
    try:
        # 使用SDK的fetch方法查询任务状态
        try:
            logger.info(f"使用 VideoSynthesis.fetch 查询任务状态")
            # 创建一个模拟的响应对象，包含task_id
            class TaskResponse:
                def __init__(self, task_id):
                    self.output = type('Output', (), {})()
                    self.output.task_id = task_id
            
            task_response = TaskResponse(task_id)
            response = VideoSynthesis.fetch(task_response)
            
        except Exception as sdk_error:
            # 如果SDK方法出错，使用HTTP请求直接查询
            logger.warning(f"SDK查询方法出错: {str(sdk_error)}，将使用HTTP请求直接查询")
            
            # 构建API请求URL
            api_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
            
            # 设置API请求头
            headers = {
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}"
            }
            
            # 发送请求到阿里云API
            logger.info(f"发送HTTP请求到: {api_url}")
            http_response = requests.get(api_url, headers=headers, timeout=10)
            logger.info(f"HTTP请求状态码: {http_response.status_code}")
            
            if http_response.status_code == 200:
                response_json = http_response.json()
                logger.info(f"HTTP响应内容: {json.dumps(response_json, ensure_ascii=False)}")
                
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
            else:
                # 处理HTTP错误
                error_message = f"HTTP请求失败: {http_response.status_code}"
                try:
                    error_data = http_response.json()
                    logger.error(f"错误响应: {json.dumps(error_data, ensure_ascii=False)}")
                    error_message += f", 错误信息: {json.dumps(error_data, ensure_ascii=False)}"
                except:
                    logger.error(f"错误响应(非JSON): {http_response.text[:500]}")
                    error_message += f", 响应内容: {http_response.text[:100]}..."
                
                raise Exception(error_message)
        
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
                    # 尝试获取results数组
                    if hasattr(response.output, 'results'):
                        results = response.output.results
                        if results and len(results) > 0:
                            if hasattr(results[0], 'url'):
                                output_data['video_url'] = results[0].url
                
                if output_data:
                    response_data['output'] = output_data
                    
                    # 如果output中有video_url，也将其提升到顶层
                    if 'video_url' in output_data:
                        response_data['video_url'] = output_data['video_url']
            except Exception as e:
                logger.warning(f"提取输出数据时出错: {str(e)}")
            
            # 如果任务成功完成
            if task_status_value == 'SUCCEEDED':
                video_url = None
                # 从输出获取视频URL
                if 'output' in response_data and 'video_url' in response_data['output']:
                    video_url = response_data['output']['video_url']
                    # 确保video_url也在顶层
                    response_data['video_url'] = video_url
                
                if not video_url and hasattr(response, 'output'):
                    # 尝试从output.video_url获取
                    if hasattr(response.output, 'video_url'):
                        video_url = response.output.video_url
                        response_data['video_url'] = video_url
                    # 尝试从output.results[0].url获取
                    elif hasattr(response.output, 'results'):
                        results = response.output.results
                        if results and len(results) > 0 and hasattr(results[0], 'url'):
                            video_url = results[0].url
                            response_data['video_url'] = video_url
                
                # 如果仍然没有找到视频URL
                if not video_url:
                    # 增加重试计数
                    if task_id not in retry_counters:
                        retry_counters[task_id] = 0
                    retry_counters[task_id] += 1
                    
                    # 检查是否超过最大重试次数
                    if retry_counters[task_id] > MAX_RETRIES:
                        logger.error(f"任务 {task_id} 已重试 {retry_counters[task_id]} 次，仍无法获取视频URL")
                        return jsonify({
                            'status': 'FAILED',
                            'error': f'任务成功但无法获取视频URL (已重试 {retry_counters[task_id]} 次)'
                        })
                    
                    # 任务成功但没有URL，可能是API响应结构变化或延迟
                    logger.warning(f"任务成功但暂时没有结果URL，返回PENDING状态 (重试 {retry_counters[task_id]}/{MAX_RETRIES})")
                    # 返回PENDING状态而不是FAILED，让前端继续轮询
                    return jsonify({
                        'status': 'PENDING',
                        'message': f'任务已完成，正在等待视频URL (重试 {retry_counters[task_id]}/{MAX_RETRIES})'
                    })
                
                # 成功获取URL，重置计数器
                if task_id in retry_counters:
                    del retry_counters[task_id]
                
                # 计算处理总时间（如果有记录起始时间）
                if task_id in task_status and 'upload_start_time' in task_status[task_id]:
                    upload_start_time = task_status[task_id]['upload_start_time']
                    total_time = time.time() - upload_start_time
                    logger.info(f"任务 {task_id} 从提交到完成总耗时: {total_time:.2f}秒")
                    
                    # 添加处理时间到响应中
                    response_data['process_time'] = round(total_time, 2)
                    response_data['process_time_formatted'] = f"{int(total_time // 60)}分{int(total_time % 60)}秒"
                
                logger.info(f"任务 {task_id} 成功完成，视频URL: {video_url}")
                return jsonify(response_data)
            
            # 如果任务失败
            elif task_status_value == 'FAILED':
                if 'message' in response:
                    response_data['message'] = response['message']
                    response_data['error'] = response['message']
                elif hasattr(response, 'message'):
                    response_data['message'] = response.message
                    response_data['error'] = response.message
                
                # 清理计数器
                if task_id in retry_counters:
                    del retry_counters[task_id]
                
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

@text2video_bp.route('/api/video_proxy', methods=['GET'])
def video_proxy():
    """
    视频代理接口，用于解决CORS问题
    接收视频URL作为查询参数，然后代理请求该URL并将响应流式传输回客户端
    """
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': '缺少视频URL参数'}), 400
    
    logger.info(f"视频代理请求: {video_url}")
    
    try:
        # 发送请求到视频URL，并使用stream=True来流式传输响应
        response = requests.get(video_url, stream=True, timeout=30)
        
        if response.status_code != 200 and response.status_code != 206:
            logger.error(f"视频代理请求失败: 状态码 {response.status_code}")
            return jsonify({'error': f'无法获取视频: HTTP {response.status_code}'}), 500
        
        # 创建一个生成器，用于流式传输响应内容
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk
        
        # 创建流式响应
        headers = {
            'Content-Type': response.headers.get('Content-Type', 'video/mp4'),
            'Content-Length': response.headers.get('Content-Length', ''),
            'Accept-Ranges': response.headers.get('Accept-Ranges', 'bytes'),
            'Cache-Control': 'no-cache',
            'Access-Control-Allow-Origin': '*'  # 允许任何来源访问
        }
        
        # 如果有Range头，需要传递给客户端
        if 'Content-Range' in response.headers:
            headers['Content-Range'] = response.headers['Content-Range']
        
        logger.info(f"视频代理响应: 状态码 {response.status_code}，内容类型 {headers['Content-Type']}")
        
        return Response(
            stream_with_context(generate()),
            status=response.status_code,
            headers=headers
        )
        
    except Exception as e:
        logger.exception(f"视频代理出错: {str(e)}")
        return jsonify({'error': f'视频代理错误: {str(e)}'}), 500 