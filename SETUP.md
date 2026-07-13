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

## 3. 配置

### 方式 A：网页一键配置（推荐）
启动后端，打开 `http://localhost:3000`，点击右上角 **Setup**。
选择提供商，填入 API Key，点击 Apply。重启后端即可。

### 方式 B：手动编辑
复制 `.env.example` 为 `.env`，填入：

```
RESEARCH_AGENT_LLM_PROVIDER=deepseek
RESEARCH_AGENT_LLM_MODEL=deepseek-v4-pro
RESEARCH_AGENT_LLM_BASE_URL=https://api.deepseek.com/v1
RESEARCH_AGENT_LLM_API_KEY=你的API密钥
RESEARCH_AGENT_LLM_TIMEOUT=300
RESEARCH_AGENT_LLM_MAX_TOKENS=0
RESEARCH_AGENT_LLM_RETRY=1
RESEARCH_AGENT_CONTEXT_WINDOW=1000000
```

## 4. 启动

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
