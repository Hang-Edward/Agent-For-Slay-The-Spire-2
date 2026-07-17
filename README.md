# Agent For Slay The Spire 2

这是一个面向《Slay the Spire 2》的本地 AI 自动打牌项目。仓库保留可发布的源码、配置样例和设计文档；运行日志、训练数据、聊天交接记录和本机状态都放在被 Git 忽略的本地目录里。

## 项目结构

- `engine/`：Python 决策引擎、策略、教师复盘、训练数据写入和测试。
- `mod/`：STS2 Godot/.NET Mod 桥接层，负责读取游戏状态并执行动作。
- `config/`：公开配置和配置样例；真实 API Key 写在 `config/api_key.yaml`，该文件不会提交。
- `architecture/`：架构说明。
- `docs/`：设计文档、方案记录和可发布文档。
- `run.ps1` / `run.sh`：本地启动脚本。
- `.local/`：本机运行产物归档目录，包含日志、聊天记录导出等，不发布到 GitHub。
- `data/`：本地训练/经验数据目录，不发布到 GitHub。

## 本地运行

Windows:

```powershell
.\run.ps1
```

如果只想检查链路，不调用外部模型：

```powershell
.\run.ps1 -DryRun
```

API Key 可以通过环境变量 `DEEPSEEK_API_KEY` 提供，也可以写入被忽略的 `config/api_key.yaml`。

## 发布约定

发布到 GitHub 时应包含源码、配置样例、测试和文档；不要提交以下内容：

- `.local/`
- `data/`
- `.superpowers/`
- `config/api_key.yaml`
- `*.log`
- `handoff/`

这些目录或文件包含本机状态、运行记录、训练记录、聊天导出或密钥相关内容，不适合作为公开仓库内容。
