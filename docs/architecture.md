# 史蒂芬个人工作 Agent 架构

系统采用单 Agent Core、可插拔 Skill、独立语音网关和统一权限策略。复杂推理才调用 LLM；确定性命令直接路由到 Skill，降低延迟。

```text
Desktop Companion（卡通便便）
  ├── Custom Context Menu：设置 / 聆听 / 退出
  ├── Settings Workspace：左侧导航 + 右侧动态页面
  ├── Voice Gateway：SAPI ASR / Wake Word / SAPI TTS
  ├── Text Command
  └── Agent Core
        ├── Intent Router
        ├── Permission Policy
        ├── Pending Confirmation
        ├── Conversation Provider（Qwen3.7 Plus）
        └── Skill Registry
              ├── Spark Scan Skill
              └── Spark Renew Skill
```

设置中心从 `Skill Registry` 动态生成 Skill 导航项。内置 Skill 使用专用设置页；第三方 Skill 可通过 `SkillManifest.settings_schema` 声明通用字段，UI 自动渲染并由 `SkillSettingsStore` 持久化到 `data/skill_settings.json`。模型密钥单独保存在本机 `.env`，不会进入 Skill 配置文件。

## 火花 Skill

```text
权限确认
  → douyin.exe 进程、窗口和前台状态校验
  → UIA 快速通道
  → RapidOCR 聊天列表 ROI 兜底
  → 感知哈希滚动到底判断
  → HSV、形态学和连通域火花分类
  → SQLite 本地持久化
```

## 续火花发送 Skill

```text
口令“续火花”
  → 第一次确认：允许扫描
  → 扫描所有联系人并生成持久化计划
  → 展示人数、联系人摘要、实际发送文案
  → 第二次确认：一次性令牌授权外部写入
  → 重新从列表顶部遍历
  → UIA 校验当前会话标题和消息输入框
  → Win32 Unicode 输入、Enter 发送、逐条限速
  → SQLite 外发审计
```

发送层没有通用点击接口。坐标必须处于抖音窗口内预定义的聊天列表或消息输入区域；抖音失去前台焦点、标题不匹配、UIA 不可用时都采用失败关闭。计划 15 分钟过期且令牌只能使用一次。批量过程中可按 `Ctrl+Shift+Q` 紧急停止。

## 语音状态机

```text
idle
  → 识别到“史蒂芬”或用户左击
listening
  → 获取命令
thinking
  → 规则路由 / LLM
confirming（有副作用）
  → 用户确认
working
  → Skill Result
speaking
  → idle
```

设置保存在 `data/agent_settings.json`。语音模块使用接口隔离，后续可将 Windows SAPI 替换为 FunASR、sherpa-onnx 或云端实时语音服务，而不改 Agent Core 和 Skill。
