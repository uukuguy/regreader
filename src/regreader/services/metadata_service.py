"""规程元数据生成服务

通过 LLM 分析规程目录和首页内容，自动生成元数据（title, description, keywords, scope）。
用于多规程智能检索时的规程选择。
"""

import json
from typing import TypedDict

from loguru import logger

from regreader.core.config import get_settings


class RegulationMetadata(TypedDict):
    """规程元数据结构"""

    title: str
    """规程标题（从封面提取）"""

    description: str
    """规程简介（一句话描述）"""

    keywords: list[str]
    """主题关键词列表（5-8 个）"""

    scope: str
    """适用范围描述"""


METADATA_GENERATION_PROMPT = """根据以下规程的目录结构和首页内容，生成规程元数据。

## 目录结构
{toc}

## 首页内容
{first_pages}

请生成以下 JSON 格式的元数据，注意：
- title: 规程的完整正式标题（从封面/首页提取，如"2024年国调直调安全自动装置调度运行管理规定（第二版）"）
- description: 一句话描述规程的主要内容和用途（50字以内）
- keywords: 5-8个主题关键词，用于检索时匹配用户问题，应包含该规程的核心术语
- scope: 适用范围描述（说明什么类型的问题应该查询此规程）

只返回 JSON，不要有其他内容：
{{
  "title": "...",
  "description": "...",
  "keywords": ["...", "..."],
  "scope": "..."
}}"""


def _extract_json_from_response(response: str) -> dict:
    """从 LLM 响应中提取 JSON

    处理可能包含 markdown 代码块的响应。
    """
    text = response.strip()

    # 移除 markdown 代码块
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    return json.loads(text.strip())


def _call_anthropic_api(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用 Anthropic API"""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.llm_api_key)

    response = client.messages.create(
        model=model_name,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Anthropic 返回的是 content blocks
    if response.content and len(response.content) > 0:
        return response.content[0].text
    raise ValueError("Anthropic API 返回空响应")


def _call_openai_api(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """调用 OpenAI 兼容 API"""
    from openai import OpenAI

    settings = get_settings()

    # 处理 Ollama 后端 URL（需要添加 /v1 后缀）
    base_url = settings.llm_base_url
    if settings.is_ollama_backend() and not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(
        api_key=settings.llm_api_key or "ollama",  # Ollama 不需要真实 key
        base_url=base_url,
    )

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    result_text = response.choices[0].message.content
    if not result_text:
        raise ValueError("OpenAI API 返回空响应")
    return result_text


def generate_regulation_metadata(
    toc_content: str,
    first_pages_content: str,
    model: str | None = None,
) -> RegulationMetadata:
    """使用 LLM 生成规程元数据

    Args:
        toc_content: 目录内容（Markdown 格式）
        first_pages_content: 首页内容（Markdown 格式）
        model: LLM 模型名称，默认使用配置中的模型

    Returns:
        RegulationMetadata 字典

    Raises:
        ValueError: LLM 返回格式错误
        Exception: LLM 调用失败
    """
    settings = get_settings()
    model_name = model or settings.llm_model_name
    provider = settings.get_llm_provider()

    system_prompt = "你是电力系统规程分析专家，擅长提取规程的核心主题和适用范围。"
    user_prompt = METADATA_GENERATION_PROMPT.format(
        toc=toc_content,
        first_pages=first_pages_content,
    )

    logger.info(f"调用 LLM 生成元数据: model={model_name}, provider={provider}")

    try:
        # 根据提供商选择 API
        if provider == "anthropic":
            result_text = _call_anthropic_api(model_name, system_prompt, user_prompt)
        else:
            result_text = _call_openai_api(model_name, system_prompt, user_prompt)

        logger.debug(f"LLM 响应: {result_text[:200]}...")

        # 解析 JSON
        metadata = _extract_json_from_response(result_text)

        # 验证必需字段
        if "title" not in metadata:
            raise ValueError("元数据缺少 title 字段")
        if "description" not in metadata:
            raise ValueError("元数据缺少 description 字段")
        if "keywords" not in metadata:
            raise ValueError("元数据缺少 keywords 字段")
        if "scope" not in metadata:
            raise ValueError("元数据缺少 scope 字段")

        # 类型验证
        if not isinstance(metadata["keywords"], list):
            metadata["keywords"] = [metadata["keywords"]]

        return RegulationMetadata(
            title=str(metadata["title"]),
            description=str(metadata["description"]),
            keywords=[str(k) for k in metadata["keywords"]],
            scope=str(metadata["scope"]),
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        raise ValueError(f"LLM 返回的 JSON 格式错误: {e}") from e
    except Exception as e:
        logger.error(f"元数据生成失败: {e}")
        raise


def format_toc_for_metadata(toc_items: list, level: int = 0) -> str:
    """将目录树格式化为 Markdown 文本

    Args:
        toc_items: TocItem 列表（或字典列表）
        level: 当前缩进级别

    Returns:
        Markdown 格式的目录文本
    """
    lines = []
    indent = "  " * level

    for item in toc_items:
        # 兼容字典和对象两种格式
        if isinstance(item, dict):
            title = item.get("title", "")
            page_start = item.get("page_start", "")
            children = item.get("children", [])
        else:
            title = getattr(item, "title", "")
            page_start = getattr(item, "page_start", "")
            children = getattr(item, "children", [])

        lines.append(f"{indent}- {title} (P{page_start})")

        if children:
            lines.append(format_toc_for_metadata(children, level + 1))

    return "\n".join(lines)
