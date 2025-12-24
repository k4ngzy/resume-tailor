from pydantic import BaseModel


class ResumeDataRequest(BaseModel):
    session_id: str
    resume_data: dict


class ComprehensiveEvaluationRequest(BaseModel):
    session_id: str
    job_indices: list[int]
    custom_jd: str | None = None


class ModifyResumeModuleRequest(BaseModel):
    session_id: str
    module_name: str
    module_data: dict | str | list
    evaluation_feedback: str


class GeneratePDFRequest(BaseModel):
    session_id: str
    template_type: str  # "template1" or "template2"
    module_order: list[str] | None = None  # 自定义模块顺序
