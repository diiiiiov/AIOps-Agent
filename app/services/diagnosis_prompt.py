"""构建可审计的智能诊断任务。"""

import re
from typing import Any

from app.agent.skill_loader import load_diagnosis_template
from app.models.aiops import DiagnosisContext


def build_diagnosis_task(context: DiagnosisContext | None) -> str:
    """将结构化现场信息转换为诊断任务，并约束证据和结论格式。

    诊断任务模板从 skills/diagnosis/diagnosis_task.md 加载，
    修改模板无需改代码，直接编辑 Markdown 文件即可。
    """
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

    template = load_diagnosis_template("diagnosis_task")
    return template.format(target=target)


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
