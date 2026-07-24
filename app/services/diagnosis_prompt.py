"""构建可审计的智能诊断任务。"""

from textwrap import dedent
import re
from typing import Any

from app.models.aiops import DiagnosisContext


def build_diagnosis_task(context: DiagnosisContext | None) -> str:
    """将结构化现场信息转换为诊断任务，并约束证据和结论格式。"""
    fields = []
    if context:
        labels = {
            "symptom": "故障现象",
            "service_name": "目标服务",
            "alert_name": "告警名称",
            "severity": "告警级别",
            "start_time": "开始时间",
            "end_time": "结束时间",
            "environment": "运行环境",
            "recent_change": "近期变更",
        }
        for field, label in labels.items():
            value = getattr(context, field)
            if value:
                fields.append(f"- {label}: {value}")

    target = "\n".join(fields) if fields else "- 未指定具体事件：检查当前系统的活动告警并选择风险最高的异常"

    return dedent(f"""
        你正在执行一次可审计的智能运维诊断。

        ## 诊断目标
        {target}

        ## 调查要求
        1. 优先围绕指定服务、告警和时间范围查询监控、日志、知识库与历史事件。
        2. 每个根因假设必须引用实际工具结果；不得把常识、推测或知识库建议表述为现场事实。
        3. 证据不足时明确标记“待确认”，并说明还需要查询什么。
        4. 比较至少一个替代假设；若没有足够数据，不得给出虚假的精确结论。
        5. 工具失败时保留失败信息，不得跳过或编造结果。

        ## 最终报告格式
        # 智能诊断报告
        ## 事件摘要
        ## 影响范围
        ## 关键证据
        使用表格列出：证据编号、来源工具、查询范围、观测事实、是否支持根因。
        ## 根因假设排序
        每项包含：假设、置信度（高/中/低）、支持证据编号、反证或不确定性。
        ## 建议处置
        区分“立即止损”“根因修复”“验证恢复”，并标明风险；任何变更操作仅提供建议，不自动执行。
        ## 待确认项

        最终输出必须是 Markdown，所有结论必须能追溯到“关键证据”中的编号。
    """).strip()


def extract_root_causes(report: str) -> list[dict[str, Any]]:
    """从 Markdown 诊断报告提取可供 UI/API 使用的根因候选。

    这是一个容错解析器：即使模型没有完全遵循格式，也会尽量保留候选文本，
    并将缺失的置信度标记为“待确认”，避免把解析失败误报为确定结论。
    """
    if not report:
        return []

    section_match = re.search(
        r"##\s*(?:根因假设排序|根因分析|可能根因)(.*?)(?=\n##\s|\Z)",
        report,
        flags=re.IGNORECASE | re.DOTALL,
    )
    section = section_match.group(1) if section_match else report
    candidates: list[dict[str, Any]] = []

    for line in section.splitlines():
        text = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if not text or text.startswith("#"):
            continue
        # 过滤纯粹的字段说明和表头
        if text.startswith(("置信度", "支持证据", "反证", "假设")):
            continue
        confidence_match = re.search(r"(?:置信度|可信度)\s*[:：]?\s*(高|中|低|待确认)", text)
        evidence_ids = sorted(set(re.findall(r"\bE\d+\b", text, flags=re.IGNORECASE)))
        confidence = confidence_match.group(1) if confidence_match else "待确认"
        hypothesis = re.sub(r"(?:置信度|可信度)\s*[:：]?\s*(高|中|低|待确认)", "", text).strip(" ：:，,;")
        if len(hypothesis) < 4:
            continue
        candidates.append({
            "rank": len(candidates) + 1,
            "hypothesis": hypothesis[:500],
            "confidence": confidence,
            "supporting_evidence": evidence_ids,
            "status": "待确认" if confidence == "待确认" else "候选",
        })
        if len(candidates) >= 8:
            break

    return candidates
