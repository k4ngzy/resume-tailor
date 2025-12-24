import json
from typing import Any, Dict, List


def parse_json_response(content: str) -> Dict[str, Any]:
    """
    解析LLM返回的JSON响应，自动移除markdown代码块标记

    Args:
        content: LLM返回的内容

    Returns:
        解析后的JSON对象
    """
    content = content.strip()

    # 移除可能的 markdown 代码块标记
    if content.startswith("```"):
        lines = content.split("\n")
        start_idx = 1 if lines[0].startswith("```") else 0
        end_idx = len(lines) - 1 if lines[-1].startswith("```") else len(lines)
        content = "\n".join(lines[start_idx:end_idx])

    return json.loads(content)


def read_jobs_from_results(job_results: List[Dict[str, Any]], job_indices: List[int]) -> List[Dict[str, Any]]:
    """
    从检索结果中读取指定的职位数据

    Args:
        job_results: 检索结果列表
        job_indices: 职位索引列表（0-based）

    Returns:
        职位数据列表
    """
    selected_jobs = []
    for job_idx in job_indices:
        if 0 <= job_idx < len(job_results):
            selected_jobs.append(job_results[job_idx])
    return selected_jobs


def build_custom_job_entries(custom_jd: str) -> List[Dict[str, Any]]:
    """
    将用户自定义 JD 封装成职位格式，便于复用现有格式化逻辑。

    Args:
        custom_jd: 用户输入的 JD 文本

    Returns:
        单条职位数据列表
    """
    cleaned_jd = custom_jd.strip()
    return [
        {
            "职位名称": "用户自定义JD",
            "公司名称": "用户提供",
            "岗位描述": cleaned_jd,
        }
    ]


def format_jobs_summary(selected_jobs: List[Dict[str, Any]]) -> str:
    """
    格式化职位信息为简洁摘要

    Args:
        selected_jobs: 职位数据列表

    Returns:
        格式化后的职位摘要文本
    """
    return "\n".join([f"- {job.get('职位名称', 'N/A')} @ {job.get('公司名称', 'N/A')}" for job in selected_jobs])


def format_jobs_detail(selected_jobs: List[Dict[str, Any]]) -> str:
    """
    格式化职位信息为详细描述

    Args:
        selected_jobs: 职位数据列表

    Returns:
        格式化后的职位详细文本
    """
    return "\n\n".join(
        [
            f"### 岗位 {i + 1}: {job.get('职位名称', 'N/A')} @ {job.get('公司名称', 'N/A')}\n"
            f"**描述**: {job.get('岗位描述', 'N/A')}\n"
            for i, job in enumerate(selected_jobs)
        ]
    )


def format_module_data(module_data: Any) -> str:
    """
    格式化模块数据为文本

    Args:
        module_data: 模块数据（可能是dict、list或str）

    Returns:
        格式化后的文本
    """
    if isinstance(module_data, (dict, list)):
        return json.dumps(module_data, ensure_ascii=False, indent=2)
    return str(module_data)


def parse_modified_module(modified_content: str, module_name: str, original_data: Any) -> Any:
    """
    解析修改后的模块内容

    Args:
        modified_content: 修改后的内容
        module_name: 模块名称
        original_data: 原始数据（用于解析失败时返回）

    Returns:
        解析后的模块数据
    """
    # 移除可能的 markdown 代码块标记
    modified_content = modified_content.strip()
    if modified_content.startswith("```"):
        lines = modified_content.split("\n")
        start_idx = 1 if lines[0].startswith("```") else 0
        end_idx = len(lines) - 1 if lines[-1].startswith("```") else len(lines)
        modified_content = "\n".join(lines[start_idx:end_idx])

    # 尝试解析为 JSON（如果是数组或对象类型）
    if module_name in ["education", "workExperience", "internshipExperience", "projects", "awards"]:
        try:
            return json.loads(modified_content)
        except json.JSONDecodeError:
            # 如果解析失败，返回原内容
            return original_data
    else:
        # 文本类型直接返回
        return modified_content
