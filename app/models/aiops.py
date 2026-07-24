"""
AIOps 请求和响应模型
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class DiagnosisContext(BaseModel):
    """用户提供的故障现场信息。所有字段均可选，兼容一键巡检。"""

    symptom: Optional[str] = Field(default=None, max_length=2000, description="故障现象")
    service_name: Optional[str] = Field(default=None, max_length=200, description="目标服务")
    alert_name: Optional[str] = Field(default=None, max_length=200, description="告警名称")
    severity: Optional[str] = Field(default=None, max_length=50, description="告警级别")
    start_time: Optional[str] = Field(default=None, max_length=50, description="排查开始时间")
    end_time: Optional[str] = Field(default=None, max_length=50, description="排查结束时间")
    environment: Optional[str] = Field(default=None, max_length=100, description="环境，如 prod")
    recent_change: Optional[str] = Field(default=None, max_length=1000, description="近期变更")

    @field_validator("severity")
    @classmethod
    def normalize_severity(cls, value: Optional[str]) -> Optional[str]:
        return value.strip().lower() if value else value


class AIOpsRequest(BaseModel):
    """AIOps 诊断请求"""
    
    session_id: Optional[str] = Field(
        default="default",
        description="会话ID，用于追踪诊断历史"
    )
    context: Optional[DiagnosisContext] = Field(
        default=None,
        description="具体故障上下文；不传时执行当前系统巡检",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session-123",
                "context": {
                    "symptom": "支付接口从 10:20 开始大量超时",
                    "service_name": "payment-service",
                    "alert_name": "HighLatency",
                    "severity": "critical",
                    "start_time": "2026-07-22 10:15:00",
                    "end_time": "2026-07-22 10:45:00",
                    "environment": "prod",
                    "recent_change": "10:10 发布了 v2.4.1"
                }
            }
        }


class AlertInfo(BaseModel):
    """告警信息"""
    alertname: str
    severity: str
    instance: str
    duration: str
    description: Optional[str] = None


class DiagnosisResponse(BaseModel):
    """诊断响应（非流式）"""
    
    code: int = 200
    message: str = "success"
    data: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 200,
                "message": "success",
                "data": {
                    "status": "completed",
                    "target_alert": {
                        "alertname": "HighCPUUsage",
                        "severity": "critical"
                    },
                    "diagnosis": {
                        "root_cause": "数据库连接池耗尽",
                        "recommendations": ["扩容数据库连接池", "优化SQL查询"]
                    }
                }
            }
        }
