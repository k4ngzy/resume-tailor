from __future__ import annotations

import time
from typing import Any, Dict

# 简单的内存会话存储，后续可替换为持久化方案
sessions: Dict[str, Dict[str, Any]] = {}


def get_or_create_session(session_id: str) -> Dict[str, Any]:
    """获取或创建会话"""
    if session_id not in sessions:
        sessions[session_id] = {
            "state": {
                "messages": [],
                "except_job": {},
                "resume_data": {},
                "selected_jobs": [],
                "job_results": [],
                "url": "",
            },
            "current_step": "form",
        }
    return sessions[session_id]


def add_ids_to_resume_data(resume_data: dict) -> dict:
    """为简历数据中的列表项添加唯一ID，方便前端定位"""
    timestamp = int(time.time() * 1000)

    if "education" in resume_data:
        for i, edu in enumerate(resume_data["education"]):
            edu["id"] = str(timestamp + i)

    if "workExperience" in resume_data:
        for i, work in enumerate(resume_data["workExperience"]):
            work["id"] = str(timestamp + i + 100)

    if "internshipExperience" in resume_data:
        for i, intern in enumerate(resume_data["internshipExperience"]):
            intern["id"] = str(timestamp + i + 150)

    if "projects" in resume_data:
        for i, proj in enumerate(resume_data["projects"]):
            proj["id"] = str(timestamp + i + 200)

    return resume_data
