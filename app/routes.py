from flask import Blueprint, request, jsonify, send_from_directory, current_app
import os
import uuid
import markdown
import re
import logging
from werkzeug.utils import secure_filename
from app.ai_client import AIClient
import datetime
from PIL import Image

# 创建蓝图
main = Blueprint('main', __name__)

# AI客户端实例
ai_client = AIClient()

# 允许的图片扩展名
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 添加状态路由
@main.route('/api/status')
def get_status():
    """返回服务器状态和配置信息，用于调试"""
    markdown_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '股市投资知识.md')
    uploads_folder = current_app.config['UPLOAD_FOLDER']
    
    # 获取AI提供商信息
    ai_providers = []
    ai_provider_details = {}
    
    if hasattr(ai_client, 'clients'):
        ai_providers = list(ai_client.clients.keys())
        
        # 获取每个提供商的详细信息
        for provider in ai_providers:
            if provider in ai_client.clients:
                ai_provider_details[provider] = {
                    'models': ai_client.clients[provider]['models']
                }
    
    # 检查上传文件夹中的文件数量
    uploaded_files_count = 0
    if os.path.exists(uploads_folder):
        uploaded_files_count = len([f for f in os.listdir(uploads_folder) if os.path.isfile(os.path.join(uploads_folder, f))])
    
    return jsonify({
        'status': 'running',
        'version': '1.0.1',  # 版本号增加
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'tabs': ['knowledge', 'analysis'],
        'ai_providers': ai_providers,
        'ai_provider_details': ai_provider_details,
        'available_providers': ai_client.available_providers if hasattr(ai_client, 'available_providers') else [],
        'markdown_file': {
            'exists': os.path.exists(markdown_path),
            'path': markdown_path
        },
        'upload_folder': {
            'path': uploads_folder,
            'exists': os.path.exists(uploads_folder),
            'files_count': uploaded_files_count
        }
    })

# 从Markdown生成提示词
def generate_prompt(markdown_content, image_description=''):
    prompt = f"""
我是一名专业的股票分析师，需要基于以下K线图和技术指标分析一支股票。

### 图片描述:
{image_description}

### 股市知识库:
{markdown_content}

请根据上传的K线图分析:
1. 当前股票处于什么趋势(上升、下降、震荡)?
2. 结合MACD指标、成交量和均线走势进行分析
3. 根据"量价关系"原则，当前是什么情况(量价齐升、量价背离、放量突破等)?
4. 针对首阴反包策略，该股是否满足相关条件?
5. 给出明确的操作建议(买入、卖出或观望)并说明理由

请用专业、简洁的语言回答，提供具体数据支持你的分析。
"""
    return prompt

def generate_short_prompt(image_description=''):
    prompt = f"""
请分析这张K线图{image_description and '('+image_description+')' or ''}:
1. 当前趋势(上升、下降或震荡)
2. MACD指标、成交量和均线走势分析
3. 量价关系判断(量价齐升、量价背离、放量突破等)
4. 首阴反包策略适用性
5. 操作建议(买入、卖出或观望)及理由

请用专业、简洁的语言回答，提供具体数据支持分析。
"""
    return prompt

@main.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@main.route('/investment-knowledge')
def investment_knowledge():
    """股市投资知识页面"""
    return send_from_directory('templates', 'investment_knowledge.html')

@main.route('/akshare')
def akshare():
    """AKShare数据页面"""
    return send_from_directory('templates', 'akshare.html')

@main.route('/debug')
def debug():
    """调试页面"""
    return send_from_directory('templates', 'debug.html')

@main.route('/simple')
def simple():
    """简单版页面"""
    return send_from_directory('templates', 'simple.html')

@main.route('/test')
def test():
    """测试页面"""
    return send_from_directory('templates', 'test.html')

@main.route('/api/markdown')
def get_markdown():
    # 读取markdown文件
    markdown_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '股市投资知识.md')
    try:
        with open(markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 转换为HTML
            html_content = markdown.markdown(content, extensions=['extra', 'codehilite'])
            return jsonify({'html': html_content, 'markdown': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/api/upload', methods=['POST'])
def upload_image():
    logging.info(f"接收到上传请求: {request.files}")
    logging.info(f"请求表单: {request.form}")
    
    if 'file' not in request.files and len(request.files) == 0:
        # 检查是否有任何文件上传
        for key in request.files:
            file = request.files[key]
            if file.filename != '':
                # 找到了一个有效文件，使用它
                logging.info(f"使用找到的文件: {key} -> {file.filename}")
                break
        else:
            return jsonify({'error': '没有上传文件'}), 400
    else:
        # 常规处理
        if 'file' in request.files:
            file = request.files['file']
        else:
            # 使用第一个键
            first_key = list(request.files.keys())[0]
            file = request.files[first_key]
            logging.info(f"使用请求中的第一个文件: {first_key} -> {file.filename}")
    
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        # 生成唯一文件名
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
        
        # 保存文件
        file.save(file_path)
        logging.info(f"成功保存文件: {unique_filename} 到 {file_path}")
        
        return jsonify({'filename': unique_filename, 'path': f'/api/uploads/{unique_filename}'})
    
    return jsonify({'error': '不支持的文件类型'}), 400

@main.route('/api/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main.route('/api/analyze', methods=['POST'])
def analyze_image():
    """分析图片API"""
    logging.info(f"收到分析请求，内容类型: {request.content_type}")
    
    # 获取请求数据，根据内容类型区分处理
    data = None
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
            logging.info(f"JSON请求数据: {data}")
        else:
            data = request.form.to_dict()
            logging.info(f"表单请求数据: {data}")
    except Exception as e:
        logging.error(f"解析请求数据失败: {str(e)}")
        return jsonify({'error': f'无效的请求格式: {str(e)}'}), 400
    
    if not data:
        logging.error("请求中没有数据")
        return jsonify({'error': '请求中没有数据'}), 400
        
    # 处理filename参数
    if 'filename' not in data:
        logging.error("请求中没有filename参数")
        return jsonify({'error': '请提供文件名'}), 400
    
    filename = data['filename']
    description = data.get('description', '')
    
    logging.info(f"分析图片: {filename}, 描述: {description}")
    
    # 检查文件是否存在
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        error_msg = f"文件不存在: {filename}"
        logging.error(f"{error_msg}，路径: {file_path}")
        return jsonify({'error': error_msg}), 404
    
    # 验证图像文件
    try:
        img = Image.open(file_path)
        img_format = img.format
        img_size = os.path.getsize(file_path)
        logging.info(f"图像文件有效: {filename}, 格式: {img_format}, 大小: {img_size} 字节")
    except Exception as e:
        error_msg = f"图像文件无效或损坏: {str(e)}"
        logging.error(error_msg)
        return jsonify({'error': error_msg}), 400
    
    # 读取Markdown内容
    markdown_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '股市投资知识.md')
    try:
        with open(markdown_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
            logging.info("成功读取Markdown文件")
    except Exception as e:
        logging.error(f"无法读取Markdown文件: {str(e)}")
        return jsonify({'error': f'无法读取Markdown文件: {str(e)}'}), 500
    
    # 生成提示词
    use_short_prompt = data.get('useShortPrompt', False)
    # 确保布尔值正确解析（JSON中的true会被解析为True，但字符串"true"需要手动转换）
    if isinstance(use_short_prompt, str):
        use_short_prompt = use_short_prompt.lower() in ('true', 'yes', '1', 't', 'y')
        
    if use_short_prompt:
        logging.info("使用精简提示词模式")
        prompt = generate_short_prompt(description)
    else:
        prompt = generate_prompt(markdown_content, description)
    
    try:
        # 获取提供商和模型
        provider = data.get('provider', 'siliconflow')  # 默认使用siliconflow提供商
        model = data.get('model', '')  # 空字符串表示使用默认模型
        
        # 获取图像处理方式选项
        use_oss_upload = data.get('useOssUpload', True)
        # 确保布尔值正确解析
        if isinstance(use_oss_upload, str):
            use_oss_upload = use_oss_upload.lower() in ('true', 'yes', '1', 't', 'y')
            
        logging.info(f"分析请求使用提供商: {provider}, 模型: {model}, 图像上传方式: {'OSS远程' if use_oss_upload else 'Base64本地'}")
        
        # 检查提供商是否可用
        if provider not in ai_client.clients:
            available_providers = list(ai_client.clients.keys())
            logging.warning(f"请求的提供商 {provider} 不可用，可用提供商: {available_providers}")
            
            if len(available_providers) > 0:
                # 自动切换到第一个可用提供商
                provider = available_providers[0]
                logging.info(f"自动切换到可用提供商: {provider}")
            else:
                return jsonify({
                    'error': f'不支持的AI提供商: {provider}, 可用提供商: {available_providers}'
                }), 400
        
        # 确保有有效的模型
        if not model or model not in ai_client.clients[provider]['models']:
            # 使用第一个可用模型
            model = ai_client.clients[provider]['models'][0]
            logging.info(f"使用默认模型: {model}")
        
        logging.info(f"开始分析图片，提供商: {provider}，模型: {model}")
        
        # 调用AI客户端进行分析
        response = ai_client.analyze_image(
            provider=provider,
            model=model,
            prompt=prompt,
            image_path=file_path,
            description=description,
            use_oss_upload=use_oss_upload
        )
        
        logging.info("分析完成，返回结果")
        return jsonify({'analysis': response})
    except Exception as e:
        error_msg = f"分析过程中出错: {str(e)}"
        logging.error(error_msg)
        return jsonify({'error': error_msg}), 500 