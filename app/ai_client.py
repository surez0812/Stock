import os
import logging
import base64
import time
import json
import math
import requests
from openai import OpenAI
import dashscope
from dashscope import MultiModalConversation
from PIL import Image
from app.oss_client import oss_client
import copy

# 确保没有设置HTTP代理环境变量
# 如果用户已设置代理，这可能导致OpenAI客户端报错
if 'HTTP_PROXY' in os.environ:
    logging.warning("检测到HTTP_PROXY环境变量，这可能会导致AI客户端初始化失败")
    os.environ.pop('HTTP_PROXY')
    
if 'HTTPS_PROXY' in os.environ:
    logging.warning("检测到HTTPS_PROXY环境变量，这可能会导致AI客户端初始化失败")
    os.environ.pop('HTTPS_PROXY')

class AIClient:
    def __init__(self):
        # 配置日志
        logging.basicConfig(level=logging.INFO)
        
        # 初始化可用提供商列表
        self.available_providers = []
        
        # 基本配置 - 只保留SiliconFlow和Aliyun
        self.base_configs = {
            'siliconflow': {
                'api_key': os.getenv("SILICONFLOW_API_KEY") or "sk-eenrfnlprxfltfqppbpjfpclbztarlzhuzqqxvcexvtqqsvx",
                'base_url': "https://api.siliconflow.cn/v1",
                'timeout': 760,
                'models': ['Pro/deepseek-ai/DeepSeek-R1'],
                'max_tokens': 8192  # Silicon Flow支持较大的token数
            },
            'aliyun': {
                'api_key': os.getenv("DASHSCOPE_API_KEY") or "sk-e2250cb7d371480bbecff854f40a3269",
                'base_url': "https://dashscope.aliyuncs.com/compatible-mode/v1",
                'timeout': 760,
                'models': [
                    'qwen-vl-plus',      # 通义千问视觉语言大模型
                    'qwen-plus',         # 通义千问大模型
                    'qvq-72b-preview',   # 通义千问72B预览版
                    'qwen-vl-max',       # 通义千问VL Max (dashscope专用)
                    'qwen-vl-max-latest', # 通义千问VL Max最新版 (dashscope专用)
                    'qwq-32b',           # 兼容旧配置
                    'qwq-plus'           # 兼容旧配置
                ],
                'use_dashscope': True,    # 使用dashscope SDK而不是OpenAI兼容模式
                'max_tokens': 16384  # 提高阿里云的最大token数以支持qvq-72b-preview
            }
        }

        # 初始化客户端
        self.clients = {}
        
        # 初始化所有提供商
        for provider, config in self.base_configs.items():
            try:
                api_key = config['api_key']
                if not api_key:
                    logging.warning(f"缺少{provider}的API密钥，跳过初始化")
                    continue

                try:
                    logging.info(f"正在初始化 {provider} 客户端...")
                    
                    # 现在已降级httpx，可以使用更多参数
                    client = OpenAI(
                        api_key=api_key,
                        base_url=config['base_url'],
                        timeout=config['timeout']
                    )
                    
                    self.clients[provider] = {
                        'client': client,
                        'models': config['models']
                    }
                    self.available_providers.append(provider)
                    logging.info(f"成功初始化 {provider} 客户端，可用模型: {config['models']}")
                    
                except Exception as e:
                    logging.error(f"初始化 {provider} 客户端失败: {str(e)}")
                    logging.error(f"异常类型: {type(e).__name__}")
                    continue
                    
            except Exception as e:
                logging.error(f"设置 {provider} 时出错: {str(e)}")
                continue

        if not self.available_providers:
            logging.warning("没有可用的AI提供商，应用将无法进行图像分析")
        else:
            logging.info(f"初始化完成，可用提供商: {self.available_providers}")

    def smart_resize(self, image_path, factor=28, vl_high_resolution_images=False):
        """
        计算图像的最佳尺寸和token数量
        
        参数:
            image_path：图像的路径
            factor：图像转换为Token的最小单位
            vl_high_resolution_images：是否提高模型的单图Token上限
        
        返回:
            tuple: (调整后的高度, 调整后的宽度, token数量)
        """
        try:
            # 打开指定的图片文件
            image = Image.open(image_path)

            # 获取图片的原始尺寸
            height = image.height
            width = image.width
            
            # 记录原始尺寸
            logging.info(f"图像原始尺寸: {width}x{height}")
            
            # 将高度调整为28的整数倍
            h_bar = round(height / factor) * factor
            # 将宽度调整为28的整数倍
            w_bar = round(width / factor) * factor
            
            # 图像的Token下限：4个Token
            min_pixels = 28 * 28 * 4
            
            # 根据vl_high_resolution_images参数确定图像的Token上限
            if not vl_high_resolution_images:
                max_pixels = 1280 * 28 * 28
            else:
                max_pixels = 16384 * 28 * 28
                
            # 对图像进行缩放处理，调整像素的总数在范围[min_pixels,max_pixels]内
            if h_bar * w_bar > max_pixels:
                beta = math.sqrt((height * width) / max_pixels)
                h_bar = math.floor(height / beta / factor) * factor
                w_bar = math.floor(width / beta / factor) * factor
            elif h_bar * w_bar < min_pixels:
                beta = math.sqrt(min_pixels / (height * width))
                h_bar = math.ceil(height * beta / factor) * factor
                w_bar = math.ceil(width * beta / factor) * factor
            
            # 计算图像的Token数：总像素除以28 * 28
            token = int((h_bar * w_bar)/(28 * 28))
            
            # <|vision_bos|> 和 <|vision_eos|> 作为视觉标记，每个需计入 1个Token
            total_tokens = token + 2
            
            logging.info(f"图像最佳尺寸: {w_bar}x{h_bar}, 总Token数: {total_tokens}")
            
            return h_bar, w_bar, total_tokens
        except Exception as e:
            logging.error(f"计算图像token失败: {str(e)}")
            # 返回原始尺寸和估计的token
            return height, width, int((height * width) / (28 * 28)) + 2

    def encode_image_base64(self, image_path, use_high_resolution=False):
        """将图像编码为base64字符串"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
                
            # 检查文件大小
            file_size = os.path.getsize(image_path)
            if file_size == 0:
                raise ValueError(f"图片文件为空: {image_path}")
                
            logging.info(f"准备Base64编码图片: {image_path}, 大小: {file_size} 字节")
            
            # 计算图像的token数量 - 根据分辨率模式
            _, _, image_tokens = self.smart_resize(image_path, vl_high_resolution_images=use_high_resolution)
            logging.info(f"当前分辨率模式下图像估计将消耗 {image_tokens} tokens")
            
            # 尝试读取图像并确定其格式
            try:
                with Image.open(image_path) as img:
                    image_format = img.format
                    width, height = img.size
                    logging.info(f"图片格式: {image_format}, 尺寸: {width}x{height}")
                    
                    # 如果是不常见格式，或者不是JPEG/PNG，转换为JPEG
                    if image_format not in ['JPEG', 'PNG']:
                        logging.info(f"转换图片格式 {image_format} 为 JPEG")
                        converted_path = f"{image_path}.jpg"
                        img.convert('RGB').save(converted_path, 'JPEG')
                        image_path = converted_path
                        logging.info(f"已转换并保存为: {converted_path}")
                    
                    # 优化图像尺寸以适应不同模型
                    max_dimension = 2400  # 默认最大尺寸
                    
                    # 如果图像太大，需要压缩
                    if width > max_dimension or height > max_dimension or file_size > 1024*1024*4:  # 4MB
                        logging.info("图像太大，进行压缩")
                        aspect = width / height
                        if width > height:
                            new_width = min(width, max_dimension)
                            new_height = int(new_width / aspect)
                        else:
                            new_height = min(height, max_dimension) 
                            new_width = int(new_height * aspect)
                            
                        try:
                            resized_path = f"{image_path}.resized.jpg"
                            img_to_save = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            
                            # 确保转换为RGB模式（解决RGBA转JPEG的问题）
                            if img_to_save.mode == 'RGBA':
                                img_to_save = img_to_save.convert('RGB')
                                
                            img_to_save.save(resized_path, 'JPEG', quality=85)
                            image_path = resized_path
                            logging.info(f"已调整大小并保存为: {resized_path}, 新尺寸: {new_width}x{new_height}")
                            
                            # 重新计算压缩后的token消耗
                            _, _, compressed_tokens = self.smart_resize(image_path, vl_high_resolution_images=use_high_resolution)
                            logging.info(f"压缩后图像估计将消耗 {compressed_tokens} tokens (减少了 {image_tokens - compressed_tokens} tokens)")
                        except Exception as e:
                            logging.warning(f"调整图像大小失败: {str(e)}，将使用原始图像")
            except Exception as e:
                logging.warning(f"PIL处理图像失败: {str(e)}，将直接尝试编码原始图像")
            
            # 读取并编码图片
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
                encoded_len = len(encoded)
                logging.info(f"成功Base64编码图片: {image_path}, 编码后长度: {encoded_len} 字符")
                
                # 显示编码结果的一小部分样本（安全起见）
                logging.info(f"编码前10个字符: {encoded[:10]}..., 后10个字符: ...{encoded[-10:]}")
                
                return encoded
        except Exception as e:
            error_msg = f"Base64图像编码失败 {image_path}: {str(e)}"
            logging.error(error_msg)
            raise ValueError(error_msg)
            
    def upload_to_oss(self, image_path, use_high_resolution=False):
        """将图像上传到OSS并返回URL"""
        try:
            # 检查文件是否存在
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
                
            # 检查文件大小
            file_size = os.path.getsize(image_path)
            if file_size == 0:
                raise ValueError(f"图片文件为空: {image_path}")
                
            logging.info(f"准备上传图片到OSS: {image_path}, 大小: {file_size} 字节")
            
            # 计算图像的token数量 - 根据分辨率模式
            _, _, image_tokens = self.smart_resize(image_path, vl_high_resolution_images=use_high_resolution)
            logging.info(f"当前分辨率模式下图像估计将消耗 {image_tokens} tokens")
            
            # 尝试读取图像并确定其格式
            try:
                with Image.open(image_path) as img:
                    image_format = img.format
                    width, height = img.size
                    content_type = f"image/{image_format.lower()}" if image_format else "image/jpeg"
                    logging.info(f"图片格式: {image_format}, 尺寸: {width}x{height}")
                    
                    # 如果是不常见格式，或者不是JPEG/PNG，转换为JPEG
                    if image_format not in ['JPEG', 'PNG']:
                        logging.info(f"转换图片格式 {image_format} 为 JPEG")
                        converted_path = f"{image_path}.jpg"
                        img.convert('RGB').save(converted_path, 'JPEG')
                        image_path = converted_path
                        content_type = "image/jpeg"
                        logging.info(f"已转换并保存为: {converted_path}")
                    
                    # 优化图像尺寸以适应不同模型
                    max_dimension = 2400  # 默认最大尺寸
                    
                    # 如果图像太大，需要压缩
                    if width > max_dimension or height > max_dimension or file_size > 1024*1024*4:  # 4MB
                        logging.info("图像太大，进行压缩")
                        aspect = width / height
                        if width > height:
                            new_width = min(width, max_dimension)
                            new_height = int(new_width / aspect)
                        else:
                            new_height = min(height, max_dimension) 
                            new_width = int(new_height * aspect)
                            
                        try:
                            resized_path = f"{image_path}.resized.jpg"
                            img_to_save = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            
                            # 确保转换为RGB模式（解决RGBA转JPEG的问题）
                            if img_to_save.mode == 'RGBA':
                                img_to_save = img_to_save.convert('RGB')
                                
                            img_to_save.save(resized_path, 'JPEG', quality=85)
                            image_path = resized_path
                            content_type = "image/jpeg"
                            logging.info(f"已调整大小并保存为: {resized_path}, 新尺寸: {new_width}x{new_height}")
                            
                            # 重新计算压缩后的token消耗
                            _, _, compressed_tokens = self.smart_resize(image_path, vl_high_resolution_images=use_high_resolution)
                            logging.info(f"压缩后图像估计将消耗 {compressed_tokens} tokens (减少了 {image_tokens - compressed_tokens} tokens)")
                        except Exception as e:
                            logging.warning(f"调整图像大小失败: {str(e)}，将使用原始图像")
            except Exception as e:
                logging.warning(f"PIL处理图像失败: {str(e)}，将直接尝试上传原始图像")
                content_type = "image/jpeg"  # 默认类型
            
            # 检查OSS客户端是否可用
            if not oss_client.is_available():
                logging.error("阿里云OSS客户端不可用，无法上传图像")
                raise ValueError("阿里云OSS客户端不可用，请检查OSS配置")
                
            # 上传图像
            success, image_url = oss_client.upload_file(image_path, content_type)
            if not success:
                logging.error("上传图像到OSS失败")
                raise ValueError("上传图像到OSS失败，请检查OSS配置和连接")
                
            logging.info(f"成功上传图像到OSS，使用OSS URL: {image_url}")
                
            # 在使用URL之前添加延迟，确保文件在OSS上完全可用
            logging.info("等待5秒，确保OSS文件完全可用...")
            time.sleep(5)
                
            # 验证URL是否可以访问
            try:
                logging.info(f"验证OSS URL可访问性: {image_url}")
                response = requests.head(image_url, timeout=5)
                if response.status_code == 200:
                    logging.info(f"OSS URL验证成功，状态码: {response.status_code}")
                    content_type = response.headers.get('Content-Type', '')
                    content_length = response.headers.get('Content-Length', 'unknown')
                    logging.info(f"Content-Type: {content_type}, Content-Length: {content_length}")
                else:
                    logging.warning(f"OSS URL可能无法访问，状态码: {response.status_code}")
                    raise ValueError(f"OSS URL可能无法访问，状态码: {response.status_code}")
            except Exception as e:
                logging.warning(f"验证OSS URL时出错: {str(e)}")
                raise ValueError(f"验证OSS URL时出错: {str(e)}")
                
            return image_url
            
        except Exception as e:
            error_msg = f"上传图像到OSS失败 {image_path}: {str(e)}"
            logging.error(error_msg)
            raise ValueError(error_msg)
    
    # 保留原兼容方法
    def encode_image(self, image_path):
        """兼容旧代码的方法"""
        return self.encode_image_base64(image_path)

    def analyze_image(self, provider, model, prompt, image_path, description='', use_oss_upload=True):
        """分析图像并返回结果"""
        logging.info(f"开始分析图片: {image_path}, 提供商: {provider}, 模型: {model}, 使用OSS上传: {use_oss_upload}")
        
        # 检查文件是否存在
        if not os.path.exists(image_path):
            logging.error(f"图片文件不存在: {image_path}")
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        # 验证提供商可用性
        if provider not in self.clients:
            available = ', '.join(self.available_providers)
            error_msg = f"提供商 {provider} 不可用。请选择可用的提供商: {available}"
            logging.error(error_msg)
            raise ValueError(error_msg)
            
        client_info = self.clients[provider]
        client = client_info['client']
        
        # 确保模型可用
        if not model or model not in client_info['models']:
            model = client_info['models'][0]
            logging.info(f"使用默认模型: {model}")
        
        # 判断模型是否支持高分辨率图像处理 (16384 tokens)
        high_res_models = [
            'qwen-vl-max', 'qwen-vl-max-latest', 'qwen-vl-max-0125', 
            'qwen-vl-max-1230', 'qwen-vl-max-1119', 'qwen-vl-max-1030', 
            'qwen-vl-max-0809', 'qwen-vl-plus-latest', 'qwen-vl-plus-0125',
            'qwen-vl-plus-0102', 'qwen-vl-plus-0809', 'qwen2-vl-72b-instruct',
            'qwen2-vl-7b-instruct', 'qwen2-vl-2b-instruct', 'qvq-72b-preview'
        ]
        
        use_high_resolution = model in high_res_models
        if use_high_resolution:
            logging.info(f"模型 {model} 支持高分辨率图像处理 (最大16384 tokens)，自动启用高分辨率模式")
        else:
            logging.info(f"模型 {model} 使用标准分辨率图像处理 (最大1280 tokens)")
        
        # 根据选择的上传方式处理图像
        image_data = None
        image_url = None
        
        try:
            if use_oss_upload:
                # 使用OSS上传获取URL
                image_url = self.upload_to_oss(image_path, use_high_resolution)
                logging.info(f"使用OSS URL方式: {image_url}")
            else:
                # 使用Base64编码
                image_data = self.encode_image_base64(image_path, use_high_resolution)
                logging.info(f"使用Base64编码方式，编码长度: {len(image_data)} 字符")
        except Exception as e:
            error_msg = f"图像处理失败: {str(e)}"
            logging.error(error_msg)
            raise ValueError(error_msg)
        
        # 最大重试次数
        max_retries = 2
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                # 根据不同提供商调整请求格式
                if provider == 'siliconflow':
                    # 构建请求数据
                    messages = [
                        {"role": "system", "content": "你是一名专业的股票分析师，擅长分析K线图并给出专业的交易建议。"},
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt}
                        ]}
                    ]
                    
                    # 根据图像处理方式添加图像信息
                    if use_oss_upload and image_url:
                        messages[1]["content"].append({"type": "image_url", "image_url": {"url": image_url}})
                    elif not use_oss_upload and image_data:
                        messages[1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}})
                    
                    # 记录请求数据（不包含图片内容，防止日志过大）
                    log_messages = copy.deepcopy(messages)
                    if len(log_messages) > 1 and isinstance(log_messages[1].get('content'), list):
                        for item in log_messages[1]['content']:
                            if item.get('type') == 'image_url':
                                if use_oss_upload:
                                    item['image_url']['url'] = f"(OSS URL: {image_url})"
                                else:
                                    item['image_url']['url'] = '(base64 image data omitted)'
                    logging.info(f"SiliconFlow请求数据: {json.dumps(log_messages, ensure_ascii=False)}")
                    
                    # 调用API
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=5000
                    )
                    # 返回分析结果
                    return response.choices[0].message.content
                elif provider == 'aliyun':
                    # 判断是否使用dashscope SDK
                    use_dashscope = self.base_configs[provider].get('use_dashscope', True)
                    
                    # 确定使用的阿里云模型
                    if not model or model not in self.base_configs[provider]['models']:
                        model = 'qwen-vl-plus'  # 默认使用通义千问多模态模型
                    
                    # 确定合适的最大token数
                    max_tokens = 8192  # 默认值
                    if model == 'qvq-72b-preview':
                        max_tokens = 16384  # 对于72B模型使用更大的token数
                    
                    logging.info(f"使用阿里云模型: {model}，最大tokens: {max_tokens}, 使用dashscope SDK: {use_dashscope}")
                    
                    # 为不同模型定制系统提示
                    system_content = "你是一名专业的股票分析师，擅长分析K线图并给出专业的交易建议。请详细分析提供的K线图，即使图片不是很清晰，也请尽力分析可见的部分。"
                    
                    # 针对更高级的72B模型，使用更详细的系统提示
                    if model == 'qvq-72b-preview' or model == 'qwen-vl-max' or model == 'qwen-vl-max-latest':
                        system_content = """你是一名专业的股票分析师，擅长分析K线图并给出专业、精确的交易建议。
请详细分析提供的K线图，识别所有关键技术指标和形态。注意分析:
1. 股票价格的整体趋势和波动
2. K线形态和模式
3. 成交量与价格变化的关系
4. MACD、KDJ等技术指标的信号
5. 支撑位和阻力位
6. 潜在的突破点或反转信号

即使图片不是很清晰，也请尽力分析可见的部分，并明确标出你的确定性程度。"""
                    
                    try:
                        if use_dashscope:
                            # 使用dashscope SDK调用
                            logging.info(f"使用dashscope SDK调用阿里云API, 模型: {model}")
                            
                            # 设置dashscope API密钥
                            dashscope_api_key = self.base_configs['aliyun']['api_key']
                            dashscope_model = model
                            
                            # 对于dashscope专用模型名称的映射
                            if model == 'qwen-vl-plus':
                                dashscope_model = 'qwen-vl-plus'
                            elif model == 'qvq-72b-preview':
                                dashscope_model = 'qwen-vl-max'  # 使用max模型替代72b-preview
                                
                            # 构建dashscope消息格式
                            messages = [
                                {
                                    "role": "system",
                                    "content": [{"text": system_content}]
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {"text": prompt}
                                    ]
                                }
                            ]
                            
                            # 根据图像处理方式添加图像
                            if use_oss_upload and image_url:
                                messages[1]["content"].insert(0, {"image": image_url})
                            elif not use_oss_upload and image_data:
                                messages[1]["content"].insert(0, {"image": f"data:image/jpeg;base64,{image_data}"})
                            
                            # 记录请求数据
                            messages_log = copy.deepcopy(messages)
                            if use_oss_upload:
                                logging.info(f"使用OSS URL: {image_url}")
                            else:
                                logging.info(f"使用Base64编码，长度: {len(image_data) if image_data else 0} 字符")
                            messages_log = json.dumps(messages_log, ensure_ascii=False)
                            logging.info(f"Dashscope API请求数据: {messages_log}")
                            
                            # 调用dashscope API
                            if use_oss_upload:
                                logging.info(f"调用Dashscope API，模型: {dashscope_model}，图像URL: {image_url}")
                            else:
                                logging.info(f"调用Dashscope API，模型: {dashscope_model}，使用Base64编码图像")
                            
                            # 设置高分辨率参数
                            parameters = {}
                            if use_high_resolution:
                                parameters['vl_high_resolution_images'] = True
                                logging.info("已启用高分辨率图像处理参数 vl_high_resolution_images=True")
                            
                            response = MultiModalConversation.call(
                                api_key=dashscope_api_key,
                                model=dashscope_model,
                                messages=messages,
                                result_format='message',
                                **parameters
                            )
                            
                            # 检查响应
                            if response.status_code != 200:
                                error_msg = f"Dashscope API返回错误: 状态码 {response.status_code}, 信息: {response.message}"
                                logging.error(error_msg)
                                raise ValueError(error_msg)
                                
                            # 获取分析结果
                            if hasattr(response, 'output') and hasattr(response.output, 'choices') and len(response.output.choices) > 0:
                                full_content = response.output.choices[0].message.content[0]["text"]
                                logging.info(f"成功获取Dashscope API分析结果，长度: {len(full_content)} 字符")
                            else:
                                error_msg = f"Dashscope API返回格式异常: {response}"
                                logging.error(error_msg)
                                raise ValueError(error_msg)
                        else:
                            # 使用OpenAI兼容模式调用通义千问API
                            logging.info(f"使用OpenAI兼容模式调用阿里云API, 模型: {model}")
                            client = client_info['client']
                            
                            # 按照新的阿里云示例代码构建请求
                            messages = [
                                {"role": "system", "content": system_content},
                                {"role": "user", "content": [
                                    {"type": "text", "text": prompt}
                                ]}
                            ]
                            
                            # 根据图像处理方式添加图像
                            if use_oss_upload and image_url:
                                messages[1]["content"].append({"type": "image_url", "image_url": {"url": image_url}})
                            elif not use_oss_upload and image_data:
                                messages[1]["content"].append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}})
                            
                            # 记录请求数据（不含图像内容）
                            log_messages = copy.deepcopy(messages)
                            if len(log_messages) > 1 and isinstance(log_messages[1].get('content'), list):
                                for item in log_messages[1]['content']:
                                    if item.get('type') == 'image_url':
                                        if use_oss_upload:
                                            item['image_url']['url'] = f"(OSS URL: {image_url})"
                                        else:
                                            item['image_url']['url'] = '(base64 image data omitted)'
                            logging.info(f"阿里云API请求数据: {json.dumps(log_messages, ensure_ascii=False)}")
                            
                            # 使用OpenAI兼容模式调用通义千问API
                            if use_oss_upload:
                                logging.info(f"调用OpenAI兼容模式API，模型: {model}，图像URL: {image_url}")
                            else:
                                logging.info(f"调用OpenAI兼容模式API，模型: {model}，使用Base64编码图像")
                                
                            # 使用OpenAI兼容模式调用通义千问API
                            completion = client.chat.completions.create(
                                model=model,
                                messages=messages,
                                max_tokens=max_tokens
                            )
                            
                            # 获取响应内容
                            full_content = completion.choices[0].message.content
                            logging.info(f"成功获取OpenAI兼容模式API分析结果，长度: {len(full_content)} 字符")
                            
                        # 检查是否有"没有上传图片"的提示
                        if "没有上传图片" in full_content or "未提供图片" in full_content or "无法直接查看" in full_content or "无法查看" in full_content:
                            logging.warning(f"阿里云API报告图像识别问题: '{full_content[:100]}...'")
                            logging.warning("尝试其他解决方案...")
                            
                            # 如果是第一次尝试，增加延迟，再次尝试
                            if retry_count < max_retries:
                                retry_count += 1
                                logging.info(f"等待10秒后重试 ({retry_count}/{max_retries})...")
                                time.sleep(10)
                                continue
                            
                            # 如果已经重试过，返回错误信息
                            error_msg = "阿里云AI服务无法识别图片，请检查图片内容是否为有效的K线图。"
                            logging.error(error_msg)
                            return f"{error_msg}\n\n服务器返回: {full_content}"
                        
                        return full_content
                    except Exception as e:
                        logging.error(f"阿里云API调用失败: {str(e)}")
                        # 重新抛出错误，让外层错误处理逻辑处理
                        raise
                else:
                    raise ValueError(f"未知的提供商: {provider}")
                
            except Exception as e:
                retry_count += 1
                last_error = e
                error_msg = f"调用 {provider} API 失败 (尝试 {retry_count}/{max_retries+1}): {str(e)}"
                logging.error(error_msg)
                
                if retry_count > max_retries:
                    # 达到最大重试次数，返回错误
                    final_error = f"分析失败，已达最大重试次数。错误: {str(last_error)}"
                    logging.error(final_error)
                    raise RuntimeError(final_error)
                
                # 等待一段时间再重试
                time.sleep(2 * retry_count) # 递增等待时间 