# 股市分析工具

这是一个基于AI技术的股市分析工具，可以展示股市投资知识和分析K线图，给出买卖建议。

## 功能特点

- **股市知识库**：展示股市投资知识，包括炒股方法、技术指标分析、量价关系等
- **K线图分析**：上传K线图，利用AI技术自动分析并给出操作建议
- **多AI提供商支持**：支持DeepSeek、SiliconFlow、Aliyun和OpenAI等多种AI服务

## 快速开始

### Linux/macOS 系统

只需运行以下命令:

```bash
# 安装
./setup.sh

# 启动
./start.sh
```

### Windows 系统

双击运行以下批处理文件:

1. 首先运行 `setup.bat` 进行安装
2. 然后运行 `start.bat` 启动应用

## 手动安装步骤

如果脚本无法运行，可以按照以下步骤手动安装:

1. 克隆此仓库
2. 创建并激活虚拟环境

```bash
# Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

3. 安装所需依赖

```bash
pip install -r requirements.txt
```

4. 运行应用

```bash
python run.py
```

5. 访问 `http://localhost:8080` 开始使用

## API密钥配置

应用默认内置了以下AI服务的API密钥：

- DeepSeek: `sk-382c25079b474b2ba3b261e8c98f7eb0`
- Aliyun: `sk-e2250cb7d371480bbecff854f40a3269`
- SiliconFlow: `sk-eenrfnlprxfltfqppbpjfpclbztarlzhuzqqxvcexvtqqsvx`

如需使用OpenAI服务，请在环境变量中设置`OPENAI_API_KEY`。

## 使用方法

1. **查看股市知识**：在"股市知识库"选项卡中浏览股市相关知识
2. **分析K线图**：
   - 切换到"K线图分析"选项卡
   - 上传K线图片（支持JPG、PNG、GIF格式）
   - 可选填写图片描述（如股票名称、时间周期等）
   - 选择AI提供商
   - 点击"开始分析"
   - 等待分析结果

## 系统要求

- Python 3.8+
- 现代浏览器（Chrome, Firefox, Safari等）
- 网络连接（用于连接AI服务）

## 注意事项

- 分析结果仅供参考，实际投资决策请结合多方面因素
- 部分AI提供商可能需要网络代理才能正常访问
- 图片上传大小限制为10MB 