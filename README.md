# AI 社交关系维护助手

本地运行的社交关系维护 Agent：识别聊天列表、结合关系记忆分析维护优先级，并生成**待用户确认**的话术建议。第一阶段不会执行输入、点击或发送消息。

## 功能

- 屏幕区域截取、OpenCV 预处理、PaddleOCR 识别
- 可配置的聊天列表文本解析规则
- 基于关系优先级、互动间隔和近期主题的分析工作流（LangGraph）
- SQLite 持久化，SQLAlchemy 数据访问层，可迁移 PostgreSQL
- APScheduler 每日扫描任务
- Vue 3 + Element Plus 本地管理后台
- LLM Provider 抽象：兼容 OpenAI 风格接口；未配置时提供明确标识的本地建议兜底

## 快速启动

需要 Python 3.11+ 与 Node.js 20+。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

另开终端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。默认 API 地址为 `http://localhost:8000/api/v1`。

## 安全边界

- 所有消息建议只能复制或标记处理，系统不提供发送 API。
- 截图默认存于本机 `data/screenshots`，可在设置中关闭保留。
- 模型密钥存于本地 `.env`，不要提交到版本库。
- `automation/` 仅定义未来执行能力的安全接口，当前实现会拒绝任何执行请求。

