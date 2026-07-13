# Research Agent Setup Guide

## 1. Clone

```bash
git clone https://github.com/ZR1314521/research-agent.git
cd research-agent
```

## 2. Install Dependencies

### Python
```bash
pip install fastapi uvicorn python-docx pypdf openpyxl
```

### Node.js (frontend)
```bash
cd workbench
npm install
cd ..
```

## 3. Configure

### Option A: Web UI (recommended)
Start the backend, open `http://localhost:3000`, click **Setup** in the top-right.
Select your provider, paste your API key, click Apply. Restart backend.

### Option B: Manual
Copy `.env.example` to `.env` and fill in:

```
RESEARCH_AGENT_LLM_PROVIDER=deepseek
RESEARCH_AGENT_LLM_MODEL=deepseek-v4-pro
RESEARCH_AGENT_LLM_BASE_URL=https://api.deepseek.com/v1
RESEARCH_AGENT_LLM_API_KEY=your-api-key-here
RESEARCH_AGENT_LLM_TIMEOUT=300
RESEARCH_AGENT_LLM_MAX_TOKENS=0
RESEARCH_AGENT_LLM_RETRY=1
RESEARCH_AGENT_CONTEXT_WINDOW=1000000
```

## 4. Start

Open TWO terminals:

### Terminal 1 - Backend
```bash
cd research-agent
$env:PYTHONPATH = "."
python -m uvicorn research_agent.app:app --host 127.0.0.1 --port 8877
```

### Terminal 2 - Frontend
```bash
cd research-agent/workbench
npm start
```

Open `http://localhost:3000`

## 5. Supported Providers

| Provider | Base URL |
|----------|----------|
| DeepSeek | https://api.deepseek.com/v1 |
| OpenAI | https://api.openai.com/v1 |
| Qwen | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| Moonshot | https://api.moonshot.cn/v1 |
| Zhipu | https://open.bigmodel.cn/api/paas/v4 |

## Features

- Multi-source academic search (OpenAlex, PubMed, Semantic Scholar, arXiv)
- PDF download from open-access URLs
- Reference formatting (Nature, IEEE, APA, GB/T 7714 + 14 more)
- Literature review pipeline (search → screen → matrix → draft)
- Document conversion (DOCX ↔ Markdown)
- Python code execution
- Shell command execution
- Git version control
- Plan mode with approval flow
- Streaming chat UI with real-time process visibility
