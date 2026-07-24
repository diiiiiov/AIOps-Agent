"""知识检索工具 - 从向量数据库中检索相关信息"""

from typing import List, Tuple
import json

from langchain_core.documents import Document
from langchain_core.tools import tool
from loguru import logger

from app.config import config
from app.services.vector_store_manager import vector_store_manager
from app.core.request_context import get_request_context


@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> Tuple[str, List[Document]]:
    """从知识库中检索相关信息来回答问题
    
    当用户的问题涉及专业知识、文档内容或需要参考资料时，使用此工具。
    
    Args:
        query: 用户的问题或查询
        
    Returns:
        Tuple[str, List[Document]]: (格式化的上下文文本, 原始文档列表)
    """
    try:
        logger.info(f"知识检索工具被调用: query='{query}'")
        
        # 从向量存储中检索相关文档
        vector_store = vector_store_manager.get_vector_store()
        request_context = get_request_context()
        tenant_id = request_context.tenant_id
        acl_expr = build_acl_expr(request_context)
        retriever = vector_store.as_retriever(
            search_kwargs={"k": config.rag_top_k, "expr": acl_expr}
        )

        docs = retriever.invoke(query)
        # 旧文档没有租户标识时仅允许 public 租户读取，避免跨租户泄露。
        docs = [doc for doc in docs if _can_read(doc, request_context)]
        docs = docs[:config.rag_top_k]
        
        if not docs:
            logger.warning("未检索到相关文档")
            return "没有找到相关信息。", []
        
        # 格式化文档为上下文
        context = format_docs(docs)
        
        logger.info(f"检索到 {len(docs)} 个相关文档")
        return context, docs
        
    except Exception as e:
        logger.error(f"知识检索工具调用失败: {e}")
        return f"检索知识时发生错误: {str(e)}", []


def _can_read(doc: Document, request_context) -> bool:
    metadata = doc.metadata
    if metadata.get("_tenant_id", "public") != request_context.tenant_id:
        return False
    visibility = metadata.get("_visibility", "tenant")
    if visibility == "tenant":
        return True
    if visibility == "private":
        return metadata.get("_owner_id") == request_context.user_id
    if visibility == "restricted":
        allowed = set(metadata.get("_allowed_roles", []))
        return bool(allowed.intersection(request_context.roles)) or "admin" in request_context.roles
    return False


def build_acl_expr(request_context) -> str:
    """构建 Milvus JSON 元数据权限表达式。所有值使用 JSON 编码防止表达式注入。"""
    tenant = json.dumps(request_context.tenant_id, ensure_ascii=False)
    owner = json.dumps(request_context.user_id, ensure_ascii=False)
    tenant_clause = f'metadata["_tenant_id"] == {tenant}'
    if "admin" in request_context.roles:
        return tenant_clause

    visibility = 'metadata["_visibility"]'
    clauses = [f'{visibility} == "tenant"', f'({visibility} == "private" and metadata["_owner_id"] == {owner})']
    role_checks = [
        f'json_contains(metadata["_allowed_roles"], {json.dumps(role, ensure_ascii=False)})'
        for role in sorted(set(request_context.roles))
    ]
    if role_checks:
        clauses.append(f'({visibility} == "restricted" and ({" or ".join(role_checks)}))')
    return f'{tenant_clause} and ({" or ".join(clauses)})'


def format_docs(docs: List[Document]) -> str:
    """
    格式化文档列表为上下文文本
    
    Args:
        docs: 文档列表
        
    Returns:
        str: 格式化的上下文文本
    """
    formatted_parts = []
    
    for i, doc in enumerate(docs, 1):
        # 提取元数据
        metadata = doc.metadata
        source = metadata.get("_file_name", "未知来源")
        
        # 提取标题信息 (如果有)
        headers = []
        for key in ["h1", "h2", "h3"]:
            if key in metadata and metadata[key]:
                headers.append(metadata[key])
        
        header_str = " > ".join(headers) if headers else ""
        
        # 构建格式化文本
        formatted = f"【参考资料 {i}】"
        if header_str:
            formatted += f"\n标题: {header_str}"
        formatted += f"\n来源: {source}"
        formatted += f"\n内容:\n{doc.page_content}\n"
        
        formatted_parts.append(formatted)
    
    return "\n".join(formatted_parts)
