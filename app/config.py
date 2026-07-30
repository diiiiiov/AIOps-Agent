"""配置管理模块

使用 Pydantic Settings 实现类型安全的配置管理
"""

from typing import Dict, Any
import json
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "OpsDiagnosis"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900
    # 企业化安全与运行开关
    auth_enabled: bool = False
    auth_secret: str = ""
    auth_issuer: str = ""
    audit_enabled: bool = True
    default_tenant_id: str = "public"
    llm_provider: str = "deepseek"
    llm_fallback_models: str = ""
    llm_allowed_base_urls: str = "https://api.deepseek.com"
    max_concurrent_tasks: int = 20
    tool_call_timeout_seconds: float = 30.0
    diagnosis_timeout_seconds: float = 900.0
    inline_task_execution: bool = True
    worker_poll_interval_seconds: float = 1.0
    task_stale_seconds: float = 300.0
    max_task_events: int = 500
    max_task_event_bytes: int = 65536
    task_store_path: str = "volumes/tasks.db"
    task_store_backend: str = "sqlite"
    state_store_backend: str = ""
    postgres_dsn: str = ""
    checkpoint_backend: str = "memory"
    checkpoint_postgres_dsn: str = ""
    monthly_budget_usd: float = 0.0
    usage_store_path: str = "volumes/usage.db"
    llm_pricing_json: str = '{"deepseek-chat":{"input":0.27,"output":1.10},"deepseek-reasoner":{"input":0.55,"output":2.19}}'
    memory_store_path: str = "volumes/memories.db"
    cors_allowed_origins: str = "http://localhost:9900,http://127.0.0.1:9900"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def allowed_llm_base_urls(self) -> set[str]:
        return {url.strip().rstrip("/") for url in self.llm_allowed_base_urls.split(",") if url.strip()}

    @property
    def llm_pricing(self) -> dict[str, dict[str, float]]:
        return json.loads(self.llm_pricing_json)

    @property
    def effective_state_store_backend(self) -> str:
        return (self.state_store_backend or self.task_store_backend).lower()

    # DeepSeek 配置（对话模型）
    deepseek_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 硅基流动配置（Embedding 模型）
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_embedding_model: str = "BAAI/bge-large-zh-v1.5"

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "deepseek-chat"  # 使用 DeepSeek 对话模型

    # AIOps 专业 Agent 模型。留空时跟随当前全局模型路由；日志扫描可单独
    # 配置低延迟模型，Supervisor/根因仲裁可配置更强的推理模型。
    aiops_log_model: str = ""
    aiops_monitor_model: str = ""
    aiops_knowledge_model: str = ""
    aiops_supervisor_model: str = ""
    # ReAct 多轮工具调用最大迭代次数（全局默认值，可在 agent YAML 中按 agent 覆盖）
    aiops_specialist_max_iterations: int = 5

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP 服务配置
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"

    @property
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        """获取完整的 MCP 服务器配置"""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            }
        }


# 全局配置实例
config = Settings()
