# Research Agent 安装指南

## 1. 克隆项目

```bash
git clone https://github.com/ZR1314521/research-agent.git
cd research-agent
```

## 2. 安装依赖

### Python
```bash
pip install -r requirements-local.txt
```

### Node.js（前端）
```bash
cd workbench
npm install
cd ..
```

## 3. 首次启动（用假 Key 占位）

先复制一份空配置：

```bash
cp .env.example .env
```

打开**两个**终端：

### 终端 1 - 后端
```powershell
cd research-agent
$env:PYTHONPATH = "."
python -m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877
```

### 终端 2 - 前端
```powershell
cd research-agent\workbench
npm start
```

浏览器打开 `http://localhost:3000`

## 4. 配置 API Key

点击右上角 **Setup** → 选择提供商 → 填入 API Key → Apply → 重启后端即可使用。

> 也可以手动编辑 `.env` 文件填入真实 Key 后重启。

## 5. 支持的提供商

| 提供商 | 接口地址 |
|--------|----------|
| DeepSeek | https://api.deepseek.com/v1 |
| OpenAI | https://api.openai.com/v1 |
| 通义千问 | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| Moonshot | https://api.moonshot.cn/v1 |
| 智谱 | https://open.bigmodel.cn/api/paas/v4 |

## 功能一览

- 多源学术搜索（OpenAlex、PubMed、Semantic Scholar、arXiv）
- 公开获取论文 PDF 下载
- 参考文献格式化（Nature、IEEE、APA、GB/T 7714 等 18 种）
- 文献综述自动生成（搜索 → 筛选 → 矩阵 → 初稿）
- 文档互转（DOCX ↔ Markdown）
- Python 代码执行
- Shell 命令执行
- Git 版本控制
- Plan 模式（先规划后执行，可审批）
- 流式对话界面，实时展示思考过程
