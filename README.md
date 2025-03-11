# 股市分析工具

一个集成多种AI大模型的K线图分析应用，可以帮助用户分析股票K线图并提供专业建议。

## 功能特点

- 支持上传K线图片并获取AI分析
- 集成多种AI提供商（通义千问、SiliconFlow等）
- 支持多种视觉语言模型选择
- 支持OSS远程上传图片减轻API压力
- 内置股市知识库
- 美观的界面与交互体验

## 预览

![应用截图](https://github.com/surez0812/Stock/raw/main/docs/screenshot.png)

## 快速开始

### 环境要求

- Python 3.8+
- 阿里云OSS账号（用于远程上传图片）
- 阿里云通义千问API密钥（用于AI分析）
- SiliconFlow API密钥（可选，用于更多AI模型选择）

### 安装步骤

1. 克隆项目

```bash
git clone https://github.com/surez0812/Stock.git
cd Stock
```

2. 安装依赖

```bash
# Windows
setup.bat

# macOS/Linux
chmod +x setup.sh
./setup.sh
```

3. 配置环境变量

```bash
cp .env.example .env
# 编辑.env文件，填入你的API密钥和OSS配置
```

4. 启动应用

```bash
# Windows
start.bat

# macOS/Linux
chmod +x start.sh
./start.sh
```

5. 访问应用

浏览器打开 http://localhost:8080

## 使用指南

1. 上传K线图片（支持拖拽上传）
2. 选择AI提供商和模型
3. 填写可选的图片描述信息
4. 点击「开始分析」
5. 查看分析结果

## 配置选项

- **使用精简提示词**：减少token消耗，提高分析速度
- **使用OSS远程上传**：通过阿里云OSS上传图片，使用URL调用API，提高兼容性

## 贡献

欢迎提交Issue和Pull Request！

## 许可

[MIT License](LICENSE)