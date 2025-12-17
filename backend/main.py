import json
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain.messages import HumanMessage, SystemMessage

# 添加项目根目录到 Python 路径
sys.path.append(str(Path(__file__).parent.parent))

from backend.job_search import query_jobs
from backend.latex_generator import generate_latex_resume
from backend.prompts import PromptTemplates
from backend.schemas import (
    ComprehensiveEvaluationRequest,
    ModifyResumeModuleRequest,
    ResumeDataRequest,
)
from backend.state import add_ids_to_resume_data, get_or_create_session, sessions
from backend.utils import (
    format_jobs_detail,
    format_jobs_summary,
    format_module_data,
    parse_json_response,
    parse_modified_module,
    read_jobs_from_results,
)
from llm.llm import create_llm
from tools import compile_latex_to_pdf, extract_text_from_file

app = FastAPI(title="Auto-Resume Agent API")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = create_llm()


# ==================== API 端点 ====================


@app.post("/api/extract_resume")
async def extract_resume(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """上传简历并提取信息"""
    session = get_or_create_session(session_id)

    # 验证文件格式
    allow_extensions = {".txt", ".pdf", ".docx"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allow_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}，请使用 .txt, .pdf, .docx 格式",
        )

    # 提取简历文本
    content = await file.read()
    resume_text = await extract_text_from_file(content, file.filename)
    if not resume_text:
        raise HTTPException(status_code=400, detail="简历内容为空或无法解析")

    # 使用 LLM 提取结构化信息
    system_prompt = PromptTemplates.get_resume_extraction_prompt()
    system_msg = SystemMessage(content=system_prompt)
    user_msg = HumanMessage(content=f"请提取以下简历的信息：\n\n{resume_text}")

    messages = [system_msg, user_msg]
    response = await llm.ainvoke(messages)

    # 解析 JSON 响应
    try:
        resume_data = parse_json_response(response.content)
        resume_data = add_ids_to_resume_data(resume_data)

        # 保存到会话
        session["state"]["resume_data"] = resume_data

        return {
            "message": "简历信息提取成功",
            "resume_data": resume_data,
        }

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM 返回的 JSON 格式错误: {str(e)}\n原始内容: {response.content[:500]}",
        )


@app.post("/api/save_resume_data")
async def save_resume_data(request: ResumeDataRequest):
    """保存用户填写的简历数据"""
    session = get_or_create_session(request.session_id)
    session["state"]["resume_data"] = request.resume_data

    return {
        "message": "简历数据已保存",
        "step": "analysis",
    }


@app.post("/api/search_jobs_new")
async def search_jobs_new(
    session_id: str = Form(...),
    except_job: str = Form(...),
):
    """搜索岗位（离线向量检索）"""
    session = get_or_create_session(session_id)

    try:
        except_job_dict = json.loads(except_job)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="except_job格式错误")

    # 验证必需的 job 参数
    if "job" not in except_job_dict:
        raise HTTPException(status_code=400, detail="缺少必需的 job 参数")

    try:
        # 获取简历数据
        resume_data = session["state"].get("resume_data")
        if not resume_data:
            raise HTTPException(status_code=400, detail="请先填写简历信息")

        session["state"]["except_job"] = except_job_dict

        # 将简历数据转换为文本
        resume_text = json.dumps(resume_data, ensure_ascii=False, indent=2)
        job_category = except_job_dict.get("job")

        job_results = query_jobs(resume_text, top_k=20, job_category=job_category)
        if not job_results and job_category:
            job_results = query_jobs(resume_text, top_k=20, job_category=None)

        if not job_results:
            raise HTTPException(status_code=400, detail="未能检索到任何职位")

        session["state"]["job_results"] = job_results

        jobs = []
        for idx, job in enumerate(job_results):
            jobs.append(
                {
                    "index": idx,
                    "name": job.get("职位名称", ""),
                    "company": job.get("公司名称", ""),
                    "salary": job.get("薪资范围", ""),
                    "location": job.get("工作地点", ""),
                    "experience": job.get("工作经验", ""),
                    "education": job.get("学历要求", ""),
                    "tags": job.get("职位标签", ""),
                    "skills": job.get("所需技能", ""),
                    "company_info": job.get("所属行业", ""),
                    "description": job.get("岗位描述", ""),
                }
            )

        if not jobs:
            raise HTTPException(status_code=400, detail="未能抓取到任何职位")

        session["current_step"] = "job_search"

        return {"jobs": jobs, "step": "job_search"}

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_detail = f"搜索职位失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/api/comprehensive_evaluation")
async def comprehensive_evaluation(request: ComprehensiveEvaluationRequest):
    """综合评估所有选中的岗位"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = sessions[request.session_id]

    # 获取简历数据
    resume_data = session["state"].get("resume_data")
    if not resume_data:
        raise HTTPException(status_code=400, detail="简历数据不存在")

    # 获取职位数据路径
    job_results = session["state"].get("job_results", [])
    if not job_results:
        raise HTTPException(status_code=400, detail="职位数据不存在")

    try:
        # 读取所有选中的岗位
        selected_jobs = read_jobs_from_results(job_results, request.job_indices)

        # 将简历数据转换为文本
        resume_text = json.dumps(resume_data, ensure_ascii=False, indent=2)

        # 将所有岗位信息合并
        jobs_text = format_jobs_detail(selected_jobs)
        jobs_count = len(selected_jobs)

        # 使用 Prompt 模板
        system_prompt = PromptTemplates.get_comprehensive_evaluation_prompt()
        sys_msg = SystemMessage(content=system_prompt)

        user_msg = HumanMessage(
            content=(
                f"## 用户简历\n```json\n{resume_text}\n```\n\n"
                f"## 选中的岗位（共 {jobs_count} 个）\n{jobs_text}\n\n"
                "请进行综合评估，并给出优化建议。"
            )
        )

        messages = [sys_msg, user_msg]
        evaluation_response = await llm.ainvoke(messages)

        # 解析评估结果
        try:
            evaluation_report = parse_json_response(evaluation_response.content)

            # 保存到会话
            session["state"]["evaluation_report"] = evaluation_report
            session["state"]["selected_jobs"] = selected_jobs
            session["current_step"] = "analysis"

            return {
                "evaluation_report": evaluation_report,
                "step": "analysis",
            }

        except json.JSONDecodeError:
            # 如果 JSON 解析失败，返回一个基本的报告结构
            fallback_report = {
                "summary": "综合评估完成，但无法解析详细结果。",
                "strengths": ["简历内容完整"],
                "weaknesses": ["需要进一步优化"],
                "key_recommendations": ["请根据岗位要求调整简历内容"],
                "module_suggestions": {},
                "raw_feedback": evaluation_response.content,
            }

            session["state"]["evaluation_report"] = fallback_report
            session["state"]["selected_jobs"] = selected_jobs
            session["current_step"] = "analysis"

            return {
                "evaluation_report": fallback_report,
                "step": "analysis",
            }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_detail = f"综合评估失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/api/modify_resume_module")
async def modify_resume_module(request: ModifyResumeModuleRequest):
    """AI优化/生成简历的特定模块"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = sessions[request.session_id]

    # 获取选中的岗位信息
    selected_jobs = session["state"].get("selected_jobs", [])
    if not selected_jobs:
        raise HTTPException(status_code=400, detail="未找到选中的岗位信息")

    # 获取简历数据用于生成新模块
    resume_data = session["state"].get("resume_data", {})

    try:
        # 格式化岗位信息
        jobs_summary = format_jobs_summary(selected_jobs)

        # 判断是生成还是优化
        is_empty = False
        if isinstance(request.module_data, str):
            is_empty = not request.module_data or request.module_data.strip() == ""
        elif isinstance(request.module_data, list):
            is_empty = len(request.module_data) == 0
        elif isinstance(request.module_data, dict):
            is_empty = not request.module_data or all(not v for v in request.module_data.values())

        operation_type = "生成" if is_empty else "优化"

        # 格式化模块数据
        module_text = format_module_data(request.module_data)

        # 获取模块描述
        module_descriptions = PromptTemplates.get_module_descriptions()
        module_description = module_descriptions.get(request.module_name, f"{request.module_name} 模块")

        # 构建 AI prompt（区分生成和优化）
        if is_empty:
            # 生成新模块
            sys_prompt = SystemMessage(
                content=(
                    f"你是专业的简历撰写专家，请根据用户的简历信息和目标岗位，生成 **{module_description}** 模块。\n\n"
                    "## 生成原则：\n"
                    "1. 基于用户简历中的其他信息进行合理推断\n"
                    "2. 突出与目标岗位相关的内容\n"
                    "3. 使用专业、简洁的表达\n"
                    "4. 内容要具体、有针对性\n\n"
                    "## 输出格式：\n"
                    "- 如果是文本类型（如 personalSummary, skills），直接返回生成的文本\n"
                    "- 如果是数组类型（如 education, workExperience, projects），返回 JSON 数组\n\n"
                    "## 注意事项：\n"
                    "- 不要添加 markdown 代码块标记\n"
                    "- 如果是 JSON，确保格式正确\n"
                    "- 内容长度适中，不要过长或过短"
                )
            )

            # 将简历数据转换为文本
            resume_text = json.dumps(resume_data, ensure_ascii=False, indent=2)

            user_prompt = HumanMessage(
                content=(
                    f"## 参考的目标岗位\n{jobs_summary}\n\n"
                    f"## 用户简历信息\n```json\n{resume_text}\n```\n\n"
                    f"## 评估建议\n{request.evaluation_feedback}\n\n"
                    f"请生成 {request.module_name} 模块的内容。"
                )
            )
        else:
            # 优化现有模块 - 使用 Prompt 模板
            system_prompt = PromptTemplates.get_module_optimization_prompt(module_description)
            sys_prompt = SystemMessage(content=system_prompt)

            user_prompt = HumanMessage(
                content=(
                    f"## 参考的目标岗位\n{jobs_summary}\n\n"
                    f"## 评估建议\n{request.evaluation_feedback}\n\n"
                    f"## 当前内容\n```\n{module_text}\n```\n\n"
                    f"请优化 {request.module_name} 模块的内容。"
                )
            )

        messages = [sys_prompt, user_prompt]
        modification_response = await llm.ainvoke(messages)

        # 解析修改结果
        modified_module = parse_modified_module(modification_response.content, request.module_name, request.module_data)

        # 生成操作说明
        operation_log = f"AI已{operation_type}{module_description}模块"
        if is_empty:
            operation_log += "，基于您的简历信息和目标岗位要求，生成了针对性的内容。"
        else:
            operation_log += "，根据评估建议进行了优化，突出了与目标岗位相关的内容。"

        return {
            "modified_module": modified_module,
            "message": f"{request.module_name} 模块已{operation_type}",
            "operation_log": operation_log,
            "operation_type": operation_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_detail = f"模块修改失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/api/re_evaluate_module")
async def re_evaluate_module(request: ModifyResumeModuleRequest):
    """重新评估修改后的模块"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = sessions[request.session_id]

    # 获取选中的岗位信息
    selected_jobs = session["state"].get("selected_jobs", [])
    if not selected_jobs:
        raise HTTPException(status_code=400, detail="未找到选中的岗位信息")

    try:
        # 格式化岗位信息
        jobs_summary = format_jobs_summary(selected_jobs)

        # 格式化模块数据
        module_text = format_module_data(request.module_data)

        # 获取模块描述
        module_descriptions = PromptTemplates.get_module_descriptions()
        module_description = module_descriptions.get(request.module_name, f"{request.module_name} 模块")

        # 使用 Prompt 模板
        system_prompt = PromptTemplates.get_module_re_evaluation_prompt(module_description)
        sys_msg = SystemMessage(content=system_prompt)

        user_msg = HumanMessage(
            content=(f"参考岗位\n{jobs_summary}\n\n{module_description}模块的内容为：{module_text}")
        )

        messages = [sys_msg, user_msg]
        evaluation_response = await llm.ainvoke(messages)

        # 返回新的评估建议
        new_suggestion = evaluation_response.content.strip()

        return {
            "suggestion": new_suggestion,
            "message": f"{request.module_name} 模块已重新评估",
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_detail = f"重新评估失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/api/generate_pdf")
async def generate_pdf(
    session_id: str = Form(...),
    template_type: str = Form(...),
    module_order: str = Form(None),
    photo: UploadFile = File(None),
):
    """生成PDF简历"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")

    session = sessions[session_id]
    resume_data = session["state"].get("resume_data")

    if not resume_data:
        raise HTTPException(status_code=400, detail="简历数据不存在")

    try:
        # 解析模块顺序
        module_order_list = None
        if module_order:
            try:
                module_order_list = json.loads(module_order)
            except json.JSONDecodeError:
                print("⚠️ 模块顺序解析失败，使用默认顺序")

        template_dir = (
            Path(__file__).parent.parent / "resume-template" / ("classic" if template_type == "classic" else "modern")
        )

        # 确定是否有照片
        has_photo = photo is not None

        # 如果有照片，保存到模板目录
        if has_photo:
            images_dir = template_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # 保存照片为 avatar.jpg
            photo_path = images_dir / "avatar.jpg"
            photo_content = await photo.read()
            with open(photo_path, "wb") as f:
                f.write(photo_content)

            print(f"✅ 照片已保存到: {photo_path}")

        # 生成LaTeX代码
        latex_content = generate_latex_resume(
            resume_data, template_type=template_type, has_photo=has_photo, module_order=module_order_list
        )

        name = resume_data.get("basicInfo", {}).get("name", "resume")
        filename = f"{name}_简历"

        success, pdf_path, error_msg = compile_latex_to_pdf(latex_content, template_dir, filename=filename)
        if not success or not pdf_path:
            raise HTTPException(status_code=500, detail=error_msg or "PDF生成失败")

        tex_path = template_dir / f"{filename}.tex"

        return {"message": "PDF生成成功", "pdf_path": str(pdf_path), "tex_path": str(tex_path)}

    except Exception as e:
        import traceback

        error_detail = f"PDF生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "active_sessions": len(sessions)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
