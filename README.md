# AI 社交关系维护助手 Agent

> 本地优先、人工确认的个人社交关系维护工作台。

AI 社交关系维护助手通过屏幕视觉识别聊天列表，结合好友档案、互动记录与关系记忆，识别值得关注的关系，并生成可编辑的话术建议。第一阶段严格采用 **“识别 → 分析 → 生成建议 → 用户确认”** 工作流，系统不会自动输入或发送任何消息。

## 核心能力

- **本地视觉识别**：使用 MSS 截图、OpenCV 预处理和 PaddleOCR 提取聊天列表文本。
- **关系维护 Agent**：基于 LangGraph 编排关系评估、优先级判断、沟通策略和话术生成。
- **关系记忆**：保存好友档案、互动记录、长期事实与偏好，持续补充决策上下文。
- **安全话术建议**：支持 OpenAI 兼容 API；未配置模型时提供本地安全兜底建议。
- **本地管理后台**：提供关系概览、好友管理、AI 建议中心、扫描记录和设置页。
- **定时扫描**：通过 APScheduler 支持每日定时截图、识别和关系分析。
- **未来自动化预留**：定义 Computer Use 接口，但当前版本会拒绝所有键鼠、输入和发送操作。

## 安全模式

```text
截图 → OCR 识别 → 聊天列表解析 → Agent 分析 → 候选话术 → 用户复制/确认
```

- 不提供消息发送 API。
- 不执行鼠标点击、键盘输入或浏览器自动化。
- 截图、互动数据和 SQLite 数据库默认保存在本机。
- 模型密钥仅通过本地 `.env` 配置，不应提交至 Git。

## 技术栈

| 领域 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Pydantic Settings |
| Agent | LangGraph、LangChain Core |
| 视觉 | MSS、OpenCV、PaddleOCR |
| 数据库 | SQLite、SQLAlchemy 2.0（可迁移 PostgreSQL） |
| 调度 | APScheduler |
| 前端 | Vue 3、Vite、TypeScript、Element Plus |
| 模型接入 | OpenAI Chat Completions 兼容接口 |

## 项目结构

```text
AI-Social-Relationship-Agent/
├── backend/
│   ├── app/
│   │   ├── api/                 # REST API：仪表盘、好友、扫描、建议、设置
│   │   ├── agent/               # LangGraph 状态、评估器、规划器与工作流
│   │   ├── automation/          # 未来 Computer Use 接口（当前强制拒绝执行）
│   │   ├── core/                # 配置、日志等基础设施
│   │   ├── database/            # SQLAlchemy 会话、模型与初始化
│   │   ├── llm/                 # LLM Provider 与话术生成器
│   │   ├── memory/              # 关系记忆服务
│   │   ├── scheduler/           # APScheduler 定时任务
│   │   ├── services/            # 扫描、关系分析等跨域业务服务
│   │   ├── vision/              # 截图、图像预处理、OCR、聊天列表解析
│   │   ├── main.py              # FastAPI 应用入口
│   │   └── schemas.py           # API 请求与响应模型
│   ├── tests/                   # Agent 单元测试
│   ├── .env.example             # 本地环境变量样例
│   └── requirements.txt         # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── api/                 # 后端 API 客户端
│   │   ├── router/              # Vue 路由
│   │   ├── styles/              # AI 工作台视觉样式
│   │   ├── types/               # TypeScript 领域类型
│   │   ├── views/               # 概览、好友、建议、设置页面
│   │   ├── App.vue              # 工作台整体布局
│   │   └── main.ts              # 前端入口
│   ├── package.json
│   └── vite.config.ts
├── data/
│   └── screenshots/             # 可选的本地截图存储目录
├── docs/
│   └── architecture.md          # 架构与安全流说明
├── .gitignore
└── README.md
```

## 快速开始

### 1. 启动后端

要求：Python 3.11+。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

后端健康检查：`http://localhost:8000/health`

### 2. 启动前端

要求：Node.js 20+。

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

## 配置 LLM（可选）

编辑 `backend/.env`：

```dotenv
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your_api_key
LLM_MODEL=your_model_name
```

三个值均已配置时，系统才会请求外部模型服务；否则会使用本地规则与兜底话术。OCR 仍在本机运行。

## 使用流程

1. 在“好友管理”中建立好友档案，并设置关系类型、优先级和标签。
2. 在“设置”中限定 OCR 截图区域，避免识别无关屏幕内容。
3. 在“关系概览”手动启动扫描，或使用每日定时扫描。
4. 在“AI 建议中心”查看推荐原因和候选话术。
5. 编辑或复制话术后，由用户自行在聊天工具中确认并发送。

## 开发与验证

```powershell
# 后端语法与单元测试
cd backend
python -m compileall -q app tests
pytest

# 前端生产构建
cd ../frontend
npm run build
```

> PaddleOCR 首次运行时可能下载其本地模型文件。请在网络可用时完成依赖安装；截图不会因 OCR 而被上传。

## 发展路线

- 支持更多聊天平台的专用界面解析策略。
- 支持 PostgreSQL、数据库迁移与多设备数据同步。
- 支持浏览器 DOM 解析，作为 OCR 的补充信号。
- 在显式授权、可回放审计与逐步确认基础上，扩展 Computer Use 能力。

## License

当前仓库尚未声明许可证；请在公开分发或商业化前补充 `LICENSE` 文件。
