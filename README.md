# OpsDiagnosis

> OpsDiagnosis - 企业级智能运维诊断系统，支持 RAG、MCP 工具调用和 V4 多 Agent 智能故障诊断

[![Version](https://img.shields.io/badge/version-1.2.1-blue.svg)](pyproject.toml)
[![Python](https://img.shields.io/badge/Python-3.11--3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141%2B-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.x-orange.svg)](https://www.langchain.com/)

## ✨ 核心特性

- 🤖 **智能对话** - LangChain 多轮对话、流式输出和运行时模型路由
- 📚 **RAG 问答** - 向量检索增强，支持文档上传、自动建立向量索引、自动更新知识库
- 🔧 **AIOps 诊断** - Supervisor + 并行专业 Agent，支持有界多轮 ReAct、证据仲裁和交叉验证
- 🌐 **Web 界面** - 现代化 UI，支持多种对话模式：快速问答/流式对话
- 🔌 **MCP 集成** - 日志、监控工具接入，包含租户隔离、审批、重试、审计和调用预算

## 🛠️ 技术栈

- **框架**: FastAPI + LangChain + LangGraph
- **LLM**: OpenAI 兼容接口，默认 DeepSeek；各专业 Agent 与 Supervisor 可独立选模
- **Embedding**: 硅基流动 OpenAI 兼容接口
- **向量库**: Milvus 2.6
- **工具协议**: MCP (Model Context Protocol)
- **状态存储**: SQLite（默认）或 PostgreSQL

## 📌 当前版本能力概览

1. **AIOps Agent 工作流**：采用 Supervisor + 日志、监控、知识三个专业 Agent 的并行 fan-out/fan-in 流程，覆盖任务分派、工具执行、证据分析、交叉验证、异常降级和结构化结果生成。Planner–Executor–Replanner 仅作为兼容的历史实现与 V0–V3 评测基线保留。
2. **统一 MCP 工具网关**：接入日志、监控指标和服务拓扑工具，提供参数校验、失败重试、租户权限隔离、人工审批和调用审计，阻断越权访问及高风险未授权操作。
3. **Milvus RAG 检索**：对运维文档进行切分、向量化和检索，并按租户上下文过滤，为 Agent 提供故障模式、历史案例和处置建议；历史知识不会替代现场证据。
4. **任务与运行治理**：通过 FastAPI 提供诊断、任务管理和审批接口；任务状态、对话记忆、审批和用量记录支持 SQLite 默认后端，并可切换 PostgreSQL。系统支持任务心跳、优先级、失败重试、并发控制，以及 token、延迟和成本统计。
5. **新版评估体系**：保留 1000 条、10 类故障的结构化数据集，将评估矩阵从 V0–V3 扩展为 V0–V4；V4 新增多 Agent 分支成功率、专业证据召回、交叉验证完成率和并行加速比。旧版 V3 开发集结果属于历史单 Agent 对比；2026-07-30 的 5 样例真实模型 Pilot 中，V4 根因 F1/证据 F1 均为 0.933、动作 F1 为 0.960、跨租户泄漏率为 0、并行收益为 2.35×。该 Pilot 仅用于开发验证，不是正式评测结论。

## 🚀 快速开始

### 环境要求
- Python 3.11、3.12 或 3.13
- Docker / Docker Compose（Milvus 和集成测试需要）
- DeepSeek API Key（对话与诊断）
- 硅基流动 API Key（文档向量化）

### 安装和启动

#### Linux/macOS 环境

```bash
# 1. 克隆项目
git clone <repository_url>
cd ops_diagnosis

# 2. 使用锁文件创建环境并安装依赖
pip install uv
uv sync --frozen --extra dev
source .venv/bin/activate

# 3. 创建并编辑配置文件
cp .env.example .env
# 至少配置 DEEPSEEK_API_KEY 和 SILICONFLOW_API_KEY

# 4. 一键初始化（启动 Docker + 服务 + 上传文档）
make init

# 5. 一键启动
make start
```

#### Windows 环境（PowerShell/CMD）

如果Windows 不支持 `make` 命令，可以手动执行以下步骤以启动服务：

```powershell
# 1. 克隆项目
git clone <repository_url>
cd ops_diagnosis

# 2. 使用锁文件创建环境并安装依赖
pip install uv
uv sync --frozen --extra dev
.venv\Scripts\activate

# 3. 创建并编辑配置文件
Copy-Item .env.example .env
notepad .env
# 至少配置 DEEPSEEK_API_KEY 和 SILICONFLOW_API_KEY

# 4. 启动 Docker Desktop
# 确保 Docker Desktop 已安装并正在运行

# 5. 启动 Milvus 向量数据库（Docker Compose）
docker compose -f vector-database.yml up -d

# 6. 查看 Milvus 状态
docker compose -f vector-database.yml ps

# 7. 启动 MCP 服务
# 启动 CLS 日志查询服务（新开一个 PowerShell 窗口）
python mcp_servers/cls_server.py

# 启动 Monitor 监控服务（新开一个 PowerShell 窗口）
python mcp_servers/monitor_server.py

# 8. 启动 FastAPI 主服务（新开一个 PowerShell 窗口）
# 注意：日志会自动输出到 logs\app_YYYY-MM-DD.log
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900

# 9. 通过 http://localhost:9900/docs 调用 /api/upload 上传知识文档
```

**Windows 一键启动脚本**（推荐）

使用启动脚本：

```powershell
# 启动所有服务
.\start-windows.bat

# 停止所有服务
.\stop-windows.bat
```

### 访问服务
- **Web 界面**: http://localhost:9900
- **API 文档**: http://localhost:9900/docs

## 📡 API 接口

### 核心接口

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 普通对话 | POST | `/api/chat` | 一次性返回 |
| 流式对话 | POST | `/api/chat_stream` | SSE 流式输出 |
| AIOps 诊断 | POST | `/api/aiops` | 自动故障诊断（流式） |
| 创建诊断任务 | POST | `/api/aiops/tasks` | 创建可查询、取消的异步诊断任务 |
| 查询诊断任务 | GET | `/api/aiops/tasks/{task_id}` | 获取任务状态、事件和错误信息 |
| 文件上传 | POST | `/api/upload` | 上传并索引文档 |
| 健康检查 | GET | `/health` | 服务状态检查 |
| 运行指标 | GET | `/api/metrics` | Token、延迟、成本和任务指标 |

### 使用示例

```bash
# 普通对话
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}'

# 流式对话
curl -X POST "http://localhost:9900/api/chat_stream" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}' \
  --no-buffer

# AIOps 诊断
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session-123","context":{"symptom":"支付接口大量超时","service_name":"payment-service","severity":"critical","environment":"prod"}}' \
  --no-buffer
```

## 📁 项目结构

```
ops_diagnosis/
├── app/                                    # 应用核心
│   ├── __init__.py                         # 包初始化（自动加载日志配置）
│   ├── main.py                             # FastAPI 应用入口
│   ├── config.py                           # 配置管理（环境变量、MCP 服务器配置）
│   ├── api/                                # API 路由层
│   │   ├── __init__.py
│   │   ├── chat.py                         # 对话接口（RAG 聊天）
│   │   ├── aiops.py                        # AIOps 接口（故障诊断）
│   │   ├── file.py                         # 文件管理（文档上传）
│   │   └── health.py                       # 健康检查（服务状态）
│   ├── services/                           # 业务服务层
│   │   ├── __init__.py
│   │   ├── rag_agent_service.py            # RAG Agent（LangGraph 状态图）
│   │   ├── aiops_service.py                # AIOps 服务（Supervisor 并行编排）
│   │   ├── vector_store_manager.py         # 向量存储管理器
│   │   ├── vector_embedding_service.py     # 向量embedding服务
│   │   ├── vector_index_service.py         # 向量索引服务
│   │   ├── vector_search_service.py        # 向量检索服务
│   │   └── document_splitter_service.py    # 文档分割服务
│   ├── agent/                              # Agent 模块
│   │   ├── __init__.py
│   │   ├── mcp_client.py                   # MCP 客户端（工具调用）
│   │   └── aiops/                          # AIOps 核心逻辑
│   │       ├── __init__.py
│   │       ├── team.py                     # Supervisor、专业 Agent 与交叉验证
│   │       ├── state.py                    # 并行 fan-out/fan-in 状态定义
│   │       └── utils.py                    # 工具函数
│   ├── models/                             # 数据模型层
│   │   ├── __init__.py
│   │   ├── aiops.py                        # AIOps 模型
│   │   ├── document.py                     # 文档模型
│   │   ├── request.py                      # 请求模型
│   │   └── response.py                     # 响应模型
│   ├── tools/                              # Agent 工具集
│   │   ├── __init__.py
│   │   ├── knowledge_tool.py               # 知识库查询工具
│   │   └── time_tool.py                    # 时间工具
│   ├── core/                               # 核心组件
│   │   ├── __init__.py
│   │   ├── llm_factory.py                  # LLM 工厂（模型管理）
│   │   └── milvus_client.py                # Milvus 客户端
│   └── utils/                              # 工具类
│       ├── __init__.py
│       └── logger.py                       # 日志配置（Loguru）
├── static/                                 # Web 前端（纯静态）
│   ├── index.html                          # 主页面
│   ├── app.js                              # 前端逻辑
│   └── styles.css                          # 样式表
├── mcp_servers/                            # MCP 服务器
│   ├── cls_server.py                       # CLS 日志查询服务
│   ├── monitor_server.py                   # 监控数据服务
│   └── README.md                           # MCP 服务说明
├── aiops-docs/                             # 运维知识库（Markdown 文档）
├── skills/                                 # Agent 定义与外置 Prompt
│   ├── agents/                             # 日志、监控、知识 Agent 配置
│   └── prompts/                            # ReAct、仲裁等 Prompt 模板
├── evaluation/                             # V0–V4 数据集、Schema、结果与评分逻辑
├── scripts/                                # 评测和 Docker 集成测试脚本
├── tests/                                  # 单元测试与集成测试
├── deploy/Dockerfile                       # 应用生产镜像
├── logs/                                   # 日志目录（Loguru 自动创建）
│   └── app_YYYY-MM-DD.log                  # 按天轮转的日志文件
├── uploads/                                # 上传文件临时目录
├── volumes/                                # Milvus 数据持久化目录
├── .env                                    # 环境变量配置（需手动创建）
├── Makefile                                # 项目管理命令（Linux/macOS）
├── start-windows.bat                       # Windows 启动脚本
├── stop-windows.bat                        # Windows 停止脚本
├── vector-database.yml                     # Milvus Docker Compose 配置
├── pyproject.toml                          # 项目配置（依赖、元数据）
├── uv.lock                                 # uv 依赖锁定文件
├── pyrightconfig.json                      # Pyright 类型检查配置
└── README.md                               # 项目说明
```

## ⚙️ 配置说明

通过 `.env` 文件配置：

```bash
# 对话与诊断模型
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 文档向量化
SILICONFLOW_API_KEY=sk-your-siliconflow-api-key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# RAG 配置
RAG_TOP_K=3
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

# V4 Agent 模型与有界 ReAct
AIOPS_LOG_MODEL=deepseek-chat
AIOPS_MONITOR_MODEL=deepseek-chat
AIOPS_KNOWLEDGE_MODEL=deepseek-chat
AIOPS_SUPERVISOR_MODEL=deepseek-reasoner
AIOPS_SPECIALIST_MAX_ITERATIONS=5
AIOPS_SPECIALIST_MAX_TOOL_CALLS=12
AIOPS_SPECIALIST_REPEAT_CALL_LIMIT=2
```

完整配置、后端切换、安全和预算选项见 [`.env.example`](.env.example)。生产环境应启用认证、替换 `AUTH_SECRET`，并限制 `CORS_ALLOWED_ORIGINS` 与 `LLM_ALLOWED_BASE_URLS`。

## 🎯 AIOps 智能运维

基于 **Supervisor + 专业 Agent 团队** 实现自动故障诊断。Supervisor 使用
LangGraph `Send` API 将同一事件并行派发给日志、监控和知识 Agent，收齐独立
假设后进行交叉验证与最终仲裁。

> 架构说明：Planner–Executor–Replanner 是历史实现和 V0–V3 消融评测基线，
> 当前主线采用 Supervisor + 并行专业 Agent。V4 Pilot 结果见下方“测试与评测”，
> 小样本开发结果不能替代经过审核的 sealed test 正式评测。

### 核心特性
- ✅ `Send` fan-out 并行调查，降低串行等待时间
- ✅ 日志 / 监控 / 知识 Agent 使用独立工具白名单与专属 Prompt
- ✅ 有界多轮 ReAct：限制迭代数、总工具调用数和重复调用次数
- ✅ 每个 Agent 可配置不同模型，Supervisor 可使用强推理模型
- ✅ Supervisor 同时接收专家结论和允许访问的现场证据，按证据质量而非多数票仲裁
- ✅ 外部 Prompt 启动时校验占位符和路径，工具输出按不可信数据处理
- ✅ 流式输出诊断过程
- ✅ 生成结构化报告

### 快速测试

```bash
# 服务已通过 make init 自动启动
# 如需重启服务：make restart

# 访问 Web 界面，点击"智能运维与诊断工具"
# 或使用 API
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test"}' \
  --no-buffer
```

### 诊断流程
```
1. Supervisor 分派任务 → 日志 / 监控 / 知识三个独立调查任务
2. LangGraph Send fan-out → 三个专业 Agent 并行调用各自工具
3. fan-in 汇聚 → 每个 Agent 提交假设、置信度、证据与反证
4. Supervisor 仲裁 → 交叉验证冲突并输出根因、证据链与处置建议
```

可通过环境变量为各角色单独选模；留空时跟随运行时全局模型路由：

```dotenv
AIOPS_LOG_MODEL=deepseek-chat
AIOPS_MONITOR_MODEL=deepseek-chat
AIOPS_KNOWLEDGE_MODEL=deepseek-chat
AIOPS_SUPERVISOR_MODEL=deepseek-reasoner
```

## 🧪 测试与评测

### 单元测试与代码质量

```powershell
# 全量测试；默认生成覆盖率报告并执行 25% 最低门槛
python -m pytest

# CI 使用的致命错误检查
python -m ruff check app tests scripts evaluation --select E9,F63,F7,F82
```

当前工作区验证结果（2026-07-30）：38 个测试通过，3 个 Docker 集成测试在普通单测中按设计跳过，覆盖率 29.52%。CI 在 Python 3.11、3.12、3.13 上运行同一套质量门槛。

### Docker 集成测试

Docker Desktop 启动后，在 PowerShell 执行：

```powershell
.\scripts\integration-test.ps1
```

脚本会启动 PostgreSQL、etcd、MinIO、Milvus 以及本地 MCP 测试服务，运行 `tests/test_integration_stack.py`，并在结束后清理容器和测试卷。需要保留环境排查时使用 `-KeepRunning`。

应用镜像可以独立构建：

```powershell
docker build -f deploy/Dockerfile -t ops-diagnosis:1.2.1 .
```

### V0–V4 真实模型 Pilot

真实模型评测会产生 API 费用，默认只运行开发集前 5 个样例，并同时生成 V0–V4 对照结果：

```powershell
python scripts/run_real_model_evaluation.py `
  --mode pilot `
  --limit 5 `
  --model deepseek-chat `
  --output-dir evaluation/results/my-v4-pilot

python scripts/score_evaluation_results.py `
  --results-dir evaluation/results/my-v4-pilot
```

最新开发 Pilot 报告位于 [`evaluation/results/real-pilot-v4-evidence-v3-deepseek-chat-20260730/report.md`](evaluation/results/real-pilot-v4-evidence-v3-deepseek-chat-20260730/report.md)：V4 完成率 1.000、根因 F1 0.933、证据 F1 0.933、动作 F1 0.960、泄漏率 0、专业 Agent 成功率与交叉验证完成率均为 1.000、并行收益 2.35×。该批次只有 5 个开发样例，仅用于回归验证；正式发布数据必须使用审核通过的 sealed test，并遵守 [`docs/evaluation/running.md`](docs/evaluation/running.md) 中的结果契约。

## 📝 开发指南

### 常用命令

```bash
# 项目管理
make init              # 一键初始化（Docker + 服务 + 文档）
make start             # 启动所有服务
make stop              # 停止所有服务
make restart           # 重启所有服务

# 依赖管理
make install-dev       # 安装开发依赖
make sync              # 同步依赖

# Docker 管理
make up                # 启动 Docker 容器
make down              # 停止 Docker 容器

# 代码质量
make format            # 格式化代码
make lint              # 代码检查
make test              # 全量测试与覆盖率
```


## 🐛 常见问题

### Windows 环境问题

#### 1. `make` 命令不可用
Windows 不支持 `make` 命令，请使用提供的批处理脚本：
```powershell
# 启动服务
.\start-windows.bat

# 停止服务
.\stop-windows.bat
```

#### 2. PowerShell 执行策略限制
如果遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：
```powershell
# 临时允许脚本执行（管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 或者使用 CMD 而不是 PowerShell
cmd
.\start-windows.bat
```

#### 3. 端口被占用（Windows）
```powershell
# 查看占用端口的进程
netstat -ano | findstr :9900

# 结束进程（替换 PID 为实际进程 ID）
taskkill /F /PID <PID>
```

### 通用问题

### API Key 错误
```bash
# Linux/macOS：只检查配置项是否存在，不要把密钥值粘贴到日志或 Issue
grep -E '^(DEEPSEEK_API_KEY|SILICONFLOW_API_KEY)=' .env

# Windows
Select-String -Path .env -Pattern '^(DEEPSEEK_API_KEY|SILICONFLOW_API_KEY)='
```

### Milvus 连接失败
```bash
# 确保本机有 Docker 服务并且已经启动（可以使用 Docker Desktop）

# 检查 Milvus 状态
docker ps | grep milvus

# 重启 Milvus（使用 docker compose）
docker compose -f vector-database.yml restart

# 或者重启单个服务
docker compose -f vector-database.yml restart standalone
```

### 服务无法启动

**Linux/macOS:**
```bash
# 查看服务日志
tail -f logs/app_$(date +%Y-%m-%d).log  # FastAPI 主服务（Loguru 日志）
tail -f mcp_cls.log                      # CLS MCP 服务
tail -f mcp_monitor.log                  # Monitor MCP 服务

# 检查端口占用
lsof -i :9900  # FastAPI
lsof -i :8003  # CLS MCP
lsof -i :8004  # Monitor MCP
```

**Windows:**
```powershell
# 查看服务日志（获取今天的日期）
$today = Get-Date -Format "yyyy-MM-dd"
type logs\app_$today.log  # FastAPI 主服务（Loguru 日志）
type mcp_cls.log          # CLS MCP 服务
type mcp_monitor.log      # Monitor MCP 服务

# 或者查看最新的日志文件
Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 50

# 检查端口占用
netstat -ano | findstr :9900  # FastAPI
netstat -ano | findstr :8003  # CLS MCP
netstat -ano | findstr :8004  # Monitor MCP
```

## 📚 参考资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [LangChain 文档](https://python.langchain.com/)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [阿里云 DashScope](https://dashscope.aliyun.com/)
- [MCP 协议](https://modelcontextprotocol.io/)

## 📄 许可证
author： chief

MIT License
