# Slay the Spire 2 AI Agent 架构

本文档描述当前可运行的 Slay the Spire 2 自动战斗架构。游戏侧使用 Godot/.NET Mod，决策侧使用 Python 和文本大模型，全程不依赖截图或视觉识别。

## 系统总览

```mermaid
flowchart LR
    GAME[Slay the Spire 2] --> MOD[Godot/.NET Mod]
    MOD -->|GET /state| ENGINE[Python AI Engine]
    ENGINE -->|Prompt| LLM[DeepSeek / Ollama / Claude]
    LLM -->|PLAY / POTION / END| ENGINE
    ENGINE -->|POST /decision| MOD
    MOD -->|Godot 主线程| GAME
```

核心职责：

- `mod/`：从游戏内存生成结构化战斗状态，并在 Godot 主线程执行动作。
- `engine/`：轮询状态、构建 Prompt、调用模型、校验响应并发送动作。
- `config/`：保存模型和策略配置；真实 API Key 使用被 Git 忽略的 `config/api_key.yaml`。

## 目录结构

```text
.
├── mod/                       # Godot/.NET Mod
│   ├── src/
│   │   ├── CombatHooks.cs
│   │   ├── DecisionExecutor.cs
│   │   ├── HttpServer.cs
│   │   ├── MainThreadDispatcher.cs
│   │   ├── Models.cs
│   │   ├── StateReader.cs
│   │   └── StateSnapshotCache.cs
│   ├── deploy.ps1
│   └── Sts2AiMod.csproj
├── engine/                    # Python 决策引擎
│   ├── communication/
│   ├── decisions/
│   ├── llm/
│   ├── state/
│   ├── tests/
│   └── main.py
├── config/
├── architecture/
└── run.ps1
```

## 战斗决策流程

```mermaid
sequenceDiagram
    participant G as Game
    participant M as Godot Mod
    participant E as Python Engine
    participant L as LLM

    E->>M: GET /state
    M->>G: 在主线程读取战斗状态
    G-->>M: 手牌、能量、敌人、意图、药水
    M-->>E: 不可变 JSON 快照
    E->>E: 检查 decision_ready
    E->>L: 发送结构化 Prompt
    L-->>E: PLAY / POTION / END
    E->>E: 严格解析并验证索引
    E->>M: POST /decision
    M->>M: 动作门闩置为 in-flight
    M->>G: 在 Godot 主线程入队动作
    G-->>M: 动作结算、状态变化
    M-->>E: decision_ready=true
```

## HTTP API

服务默认监听 `http://127.0.0.1:18888`。

### `GET /state`

返回当前战斗快照，关键字段包括：

- `decision_ready`：是否允许提交下一条动作。
- `action_in_flight`：上一条动作是否仍在队列中。
- `action_in_progress`：游戏是否正在结算卡牌或药水效果。
- `state_revision`：真实游戏状态变化时递增。
- `player.phase`：当前玩家回合阶段，只有 `Play` 可手动操作。
- `monsters[].intent_damage` 和 `intent_hits`：通过游戏的 `AttackIntent` 计算。
- `monsters[].targetable` 和 `target_index`：与动作接口使用同一目标索引。
- `hand[].uuid`：同名卡牌也具有不同的运行时标识。

### `GET /status`

返回连接状态、战斗状态、动作门闩和状态版本。

### `POST /decision`

支持以下战斗动作：

```json
{"type":"play_card","hand_index":0,"monster_index":1}
```

```json
{"type":"use_potion","potion_slot":0,"monster_index":1}
```

```json
{"type":"end_turn"}
```

动作尚未结算时再次提交会返回 HTTP `409` 和 `status=busy`。

## 并发与失败策略

游戏对象具有主线程约束，因此 Mod 使用以下边界：

1. HTTP 后台线程接收请求。
2. `MainThreadDispatcher` 将状态读取或动作执行切换到 Godot 主线程。
3. `StateSnapshotCache` 将完整状态序列化为不可变 JSON。
4. HTTP 线程只读取缓存，不直接访问场景树或战斗对象。
5. `DecisionGate` 保证同一时间最多有一个动作。

Python 引擎采用失败即停策略：

- 模型网络错误不会生成默认动作。
- 空响应或无法识别的最后一行会被拒绝。
- 越界手牌、不可用卡牌、无效敌人索引和不可用药水会被拒绝。
- 没有可用卡牌时由确定性逻辑发送 `END`，无需调用模型。
- Mod 返回非 `ok` 时，当前状态不再盲目重试。

## 模型输出协议

模型必须在最后一行输出一条命令：

```text
PLAY <hand_index> <monster_index>
POTION <slot> <monster_index>
END
```

响应解析器只读取最后一个非空行，避免把推理正文中的示例误当成动作。

## 配置与运行

模型配置位于 `config/ai_config.yaml`。API Key 建议写入本机文件：

```yaml
llm:
  api_key: "your-api-key"
```

该文件路径为 `config/api_key.yaml`，已被 `.gitignore` 排除。

常用命令：

```powershell
# 构建 Mod
dotnet build .\mod\Sts2AiMod.csproj

# 部署 Mod
powershell -NoProfile -ExecutionPolicy Bypass -File .\mod\deploy.ps1

# 运行测试
py -m pytest .\engine\tests

# 无 API 冒烟测试
py .\engine\main.py --dry-run

# 使用 DeepSeek
.\run.ps1 -Backend deepseek
```

## 当前能力边界

当前已经实机验证：

- 单敌人和多敌人目标选择。
- 单段攻击意图伤害。
- 卡牌、药水和结束回合。
- 并发动作拒绝和动作完成恢复。
- 完整无视觉轮询决策链路。

当前 Mod 只覆盖战斗自动化。地图路线、奖励、事件、休息点、商店和宝箱等非战斗界面仍需要新增状态读取与动作执行接口。

## 验证标准

提交前至少执行：

```powershell
dotnet build .\mod\Sts2AiMod.csproj
py -m pytest .\engine\tests
```

实机验证时还应检查：

- Godot 日志不存在 `SceneTree is only allowed from the main thread`。
- Mod 日志不存在 `Main thread action timed out`。
- 动作期间 `decision_ready=false`，完成后恢复为 `true`。
- 多敌人动作只影响指定 `target_index`。
