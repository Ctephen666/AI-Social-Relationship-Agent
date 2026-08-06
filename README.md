# 个人工作 Agent

运行在 Windows 本机的个人工作助手。桌面入口是一只卡通便便悬浮助手，支持语音唤醒、手动对话、文字命令、权限确认和可插拔 Skill。

当前内置两个抖音 Skill：只读火花扫描，以及受控的批量续火花发送。明确说出“续火花”即视为本次任务授权，Agent 会打开右上角消息面板，单次滚动聊天列表并边识别边逐人发送；开发测试不会向真实好友发送消息。

## 主要能力

- 蓝白卡通悬浮 UI：动态状态徽标、粒子反馈和可滚动完整回复框；空闲时不持续重绘，避免透明窗口残影。
- 左击：进入一次语音命令窗口。
- 右击：打开快捷选择栏，可选择手动对话、进入设置、开始聆听或退出。
- 默认唤醒词：`史蒂芬`，可在设置中修改。
- SenseVoice Small INT8 + Silero VAD 本地中文识别；Windows SAPI 作为自动降级方案。
- Agent 回复仅用文字展示，不加载语音合成模型，启动与响应更轻量。
- Skill Registry：工作能力以独立插件注册。
- Permission Policy：本地操作、外部写入和禁止能力分级。
- Human-in-the-loop：火花扫描等桌面操作必须确认。
- Qwen3.7 Plus：通过阿里云百炼 OpenAI 兼容接口进行普通对话。
- RapidOCR/ONNX Runtime、UIA 和 OpenCV 低延迟火花扫描。
- 发送保护：抖音前台校验、聊天行/编辑区/发送箭头白名单区域、联系人去重、审计和 `Ctrl+Shift+Q` 紧急停止。

## 使用方法

运行：

```text
start_desktop_agent.bat
```

或者直接启动：

```text
backend/dist/StephenAgent/StephenAgent.exe
```

语音示例：

```text
用户：“史蒂芬”
状态：正在聆听
用户：“帮我抖音续个火花”
```

手动对话：右击便便助手，选择“手动对话”，状态栏旁会弹出迷你输入窗口。按 `Enter` 发送，使用 `Shift+Enter` 换行。手动输入和语音识别结果会进入同一套 Agent、LLM 与 Skill 路由。

识别到续火花指令后会直接开始，不再询问确认。

```text
“史蒂芬”
“扫描一下火花”

Agent：“我将打开抖音并滚动聊天列表……确认开始吗？”
“确认”
```

也可以一次说完：

```text
“史蒂芬，扫描火花”
```

续火花发送流程：

```text
用户：“史蒂芬，帮我抖音续个火花”
Agent：打开抖音右上角“消息”面板
Agent：单次滚动聊天列表，逐行点击对话、编辑“发送消息”栏并点击右侧箭头
Agent：“续火花发送已完成……”
```

说出明确指令后会产生真实外部发送。执行中按 `Ctrl+Shift+Q` 可停止，已经发送的消息无法撤回。

右击便便助手选择“进入设置”后，会打开左侧导航、右侧内容的设置中心：

- 总览：运行状态、快速命令和交互提示
- 语音与唤醒：SenseVoice/Silero VAD 状态、唤醒词和识别后端
- 模型配置：Base URL、模型名称、API Key、请求超时和连接测试
- 续火花：扫描模式、OCR 后端和滚动稳定时间
- 续火花发送：消息模板、人数、间隔和固定安全策略

设置保存在本地：

```text
data/agent_settings.json
data/skill_settings.json
```

## 新 Skill 的设置页

每个已注册 Skill 会自动出现在设置中心左侧。新 Skill 可在 `SkillManifest.settings_schema` 中声明字段，桌面端会自动生成文本、密码、数字、布尔或下拉控件，并保存到 `data/skill_settings.json`：

```python
SkillManifest(
    id="calendar",
    name="日程管理",
    description="管理个人日程",
    settings_schema=[
        SkillSettingField(key="calendar_id", label="日历 ID", kind="text"),
        SkillSettingField(key="reminder", label="默认提醒", kind="boolean", default=True),
    ],
)
```

## 普通对话

项目默认接入阿里云百炼 `qwen3.7-plus`。在 `backend/.env` 填入百炼 API Key：

```dotenv
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-your-dashscope-key
LLM_MODEL=qwen3.7-plus
LLM_TIMEOUT_SECONDS=60
```

未配置模型时，语音唤醒、手动输入、本地命令和火花 Skill 仍可使用；普通聊天会提示模型尚未配置。

## 架构

```text
卡通便便桌面 UI
  ├── Voice Gateway
  │     ├── SenseVoice Small INT8 + Silero VAD
  │     ├── 唤醒词门控
  │     └── Windows SAPI 识别降级
  ├── Manual Chat
  │     └── 文字输入、历史回复与 Skill 命令复用
  └── Personal Agent Core
        ├── Intent Router（快速规则路由）
        ├── Permission Policy
        ├── Human Confirmation
        ├── LLM Conversation
        └── Skill Registry
              └── spark_scan
                    ├── UIA 快速通道
                    ├── RapidOCR 兜底
                    └── OpenCV 火花检测
              └── spark_renew
                    ├── 自动打开右上角消息面板
                    ├── 单次遍历、边识别边发送
                    ├── 固定编辑区输入与右侧箭头发送
                    └── 限速发送与审计
```

项目结构：

```text
backend/app/
├── personal_agent/
│   ├── core.py
│   ├── policy.py
│   ├── registry.py
│   ├── router.py
│   ├── schemas.py
│   ├── settings_store.py
│   └── skill.py
├── skills/
│   ├── spark_scan/
│   └── spark_renew/
├── voice/
│   ├── neural_gateway.py
│   ├── model_manager.py
│   └── sapi_gateway.py
├── desktop_agent/
├── vision/
├── services/
├── memory/
├── llm/
└── desktop_app.py
```

## Skill 权限模型

| 等级 | 示例 | 行为 |
|---|---|---|
| `READ_ONLY` | 查询最近报告 | 可直接执行 |
| `LOCAL_ACTION` | 打开抖音、截图、滚动 | 默认要求确认 |
| `EXTERNAL_WRITE` | 抖音消息发送 | 仅允许明确匹配的专用 Skill；续火花口令会直接执行 |
| `PROHIBITED` | 当前禁止的能力 | 拒绝执行 |

发送接口仅允许操作抖音聊天行、底部消息编辑区和右侧发送箭头，不提供通用桌面点击能力，也不使用或覆盖系统剪贴板。直接续火花遍历不检查火花图标，每次尝试记录在 `outbound_message_audits` 表中。

## 源码运行

要求：Windows 10/11、Python 3.11+。

```powershell
cd D:\AI-Social-Relationship-Agent\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B scripts\install_voice_models.py
.\.venv\Scripts\python.exe -m app.desktop_app
```

语音模型默认安装到 `data/voice_models`。安装器从 sherpa-onnx 官方 GitHub Release 下载：

- `SenseVoice Small INT8`：中文/英文/粤语/日语/韩语识别
- `Silero VAD`：本地语音端点检测

模型缺失或神经引擎初始化失败时自动使用 Windows SAPI 识别。手动对话入口不受影响。

## 构建 EXE

```powershell
cd D:\AI-Social-Relationship-Agent\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build_exe.ps1
```

产物：

```text
backend/dist/StephenAgent/StephenAgent.exe
```

必须保留整个 `StephenAgent` 文件夹。构建产物只附带 SenseVoice 与 Silero VAD，不再包含 Kokoro。构建脚本会覆盖 PyInstaller 自带的旧 VC++ Runtime，避免 ONNX Runtime DLL 初始化失败。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pytest -q
```

OCR 冒烟测试：

```powershell
.\dist\StephenAgent\StephenAgent.exe --smoke-ocr "D:\path\to\screenshot.png"
```

## 隐私与安全

- SenseVoice 与 Silero VAD 均在本机推理，麦克风音频不会上传。
- 截图、数据库、设置和日志保存在本地数据目录。
- 普通对话只有配置百炼 API Key 后才会请求 `qwen3.7-plus`。
- 桌面 Skill 执行前经过中央权限策略。
- 明确续火花指令会直接开始发送；同一次遍历按联系人去重，不会重复发送。
- 失去抖音前台焦点或 Windows 无法完整输入消息时立即停止整个任务。
