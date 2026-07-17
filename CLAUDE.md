# Slay the Spire 2 AI Agent

STS2 的 AI 自动战斗代理。Mod 端使用 C#（.NET 9 + Harmony）通过游戏原生 ModManager 注入，决策端使用 Python + LLM（DeepSeek / Claude / Ollama），全程不依赖截图或视觉识别。

## 项目结构

```
.
├── mod/                       # Godot/.NET Mod
│   ├── src/
│   │   ├── CombatHooks.cs         # 战斗 Hook
│   │   ├── DecisionExecutor.cs    # 动作执行
│   │   ├── HttpServer.cs          # HTTP 服务 (port 18888)
│   │   ├── StateReader.cs         # 游戏状态读取
│   │   ├── StateSnapshotCache.cs  # 主线程状态快照
│   │   ├── UiAutomation.cs        # 界面自动化
│   │   └── Models.cs              # 数据模型
│   ├── deploy.ps1                 # 部署脚本
│   └── Sts2AiMod.csproj
├── engine/                     # Python 决策引擎
│   ├── main.py                 # 入口
│   ├── decisions/              # 屏幕处理器 (COMBAT, CARD_REWARD, MAP, REST...)
│   ├── strategy/               # 战略规划 (Guardrails, 路线评分, 卡组评估, 战斗规划)
│   ├── policy/                 # LocalPolicy 本地策略
│   ├── teacher/                # DeepSeek Teacher
│   ├── learning/               # 训练数据写入器、经验存储
│   ├── telemetry/              # 遥测事件总线
│   ├── dashboard/              # 浏览器仪表盘
│   ├── llm/                    # LLM 客户端 (DeepSeek, Claude, Ollama)
│   └── tests/                  # 测试
├── config/                     # 配置
│   └── ai_config.yaml
├── data/                       # 运行时数据（Git 忽略）
│   ├── runs/                   # 运行存档
│   ├── training/runs/          # 训练样本
│   └── experience.sqlite3      # 经验库
└── CLAUDE.md                   # 本文件
```

## 构建与测试

```powershell
# Mod 构建
dotnet build mod\Sts2AiMod.csproj

# Mod 部署到游戏目录
powershell -File mod\deploy.ps1

# Python 测试
py -m pytest engine\tests

# 启动 AI 引擎（dry-run 模式，不调用真实 LLM）
py engine\main.py --dry-run

# 启动 AI 引擎（LocalPolicy 模式，无需 API Key）
py engine\main.py --local-policy --dry-run
```

## 关键接口

- Mod HTTP: `http://127.0.0.1:18888/state`, `POST /decision`, `GET /status`
- 仪表盘: `http://127.0.0.1:18889/api/snapshot`

## 开发规则

1. **不要擅自推送** — 代码改完后可以自行提交（commit），但**除非用户明确要求，否则绝对不要 push 到 GitHub**。
2. **先读后改** — 修改代码前先理解现有模式和架构，做最小必要改动。
3. **不要重构无关代码** — 只改与当前任务直接相关的文件。
4. **修改前说明改什么** — 改文件前向用户简要说明计划改哪些文件、改什么。
5. **改后运行测试** — 修改后运行 `py -m pytest engine/tests` 确认无回归。
6. **保持进度面板** — 多步骤任务时维护可见的进度跟踪。
7. **一分钟卡顿检查** — 命令超过 1 分钟未推进时检查是否卡住，卡住则排查重试。
8. **不确定就问** — 遇到不确定的问题不要自己做决定，给用户选项说明影响。
9. **中文回答** — 默认使用中文回答，代码/命令/路径保持原文。
10. **不泄露密钥** — 不把 API Key、token 写入日志、代码或回复。

## 决策流程

```
游戏状态 → 注册表获取 Handler → extract_state()
  → normalized_candidates() 构建候选
  → ExperienceService.apply() 历史经验调整
  → LocalPolicy.decide() 选择最佳候选
    → StrategyGuardrail.check() 护栏检查（14 条规则）
  → 执行决策 → TrainingDataWriter 记录
  → 游戏回合结束 → DeepSeek Teacher 复盘
```

## 训练管线

1. `--local-policy` 模式自动运行游戏，收集 transitions
2. Guardrail 纠正错误决策，标注正确行为
3. DeepSeek Teacher 每局结束后给训练建议
4. 用 guardrail修正 + 教师标注做**行为克隆**（监督学习）
5. 模型学到基础策略后再做 RL 微调
