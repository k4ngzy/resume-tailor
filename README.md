# Auto-Resume - AI 简历优化助手

基于大语言模型 + 离线检索的简历优化工具：从本地职位库中检索匹配岗位，生成评估与优化建议，并导出 PDF 简历。

## 核心流程
1) 上传简历（PDF/DOCX/TXT）并抽取结构化信息
2) 选择岗位类别，进行离线向量检索（RAG-style retrieval）
3) 对选中岗位进行综合评估
4) 按模块优化/生成简历内容并可复评
5) 导出 LaTeX → PDF（可上传照片）

## 功能亮点
- 简历解析：抽取结构化字段，支持主流格式。
- 离线检索：本地职位库 + Chroma 向量检索。
- AI 评估与优化：针对岗位生成综合评估与模块优化建议。
- 导出：生成 LaTeX 并编译 PDF。

## 依赖与前置条件
- Python 3.10+
- 推荐使用 [uv](https://github.com/astral-sh/uv) 管理依赖
- LaTeX（PDF 导出需 `xelatex`）
- 可选：Playwright 浏览器（仅用于离线采集脚本）

## 快速开始
1) 安装依赖：
   ```bash
   uv sync
   ```
2) 配置环境变量：在项目根目录创建 `.env`：
   ```env
   API_KEY=your_api_key
   BASE_URL=https://api.openai.com/v1/
   ```
3) 启动全栈（后端 + 前端）：
   ```bash
   ./start.sh
   ```
4) 访问：浏览器打开 http://localhost:8501

## 可选：离线数据采集
离线采集脚本 `tools/offline_job_crawl.py`，用于生成/补充本地职位库（非主流程依赖）。

1) 安装 Playwright 浏览器：
   ```bash
   uv run playwright install chromium
   ```
2) 采集并生成 JSONL（以Python岗位示例）：
   ```bash
   uv run python tools/offline_job_crawl.py --jobs Python --max-count 50
   ```
3) 重新构建索引：
   ```bash
   uv run python tools/build_job_index.py \
     --source-path backend/data/offline_jobs.jsonl \
     --db-path backend/chromadb_data \
     --collection offline_jobs \
     --device cpu \
     --allow-remote
   ```

## 项目结构
```
backend/          FastAPI 主应用、Prompt 与工具；运行数据目录 data/、user_data/
frontend/         Streamlit UI、表单与模块编辑
llm/              LLM 工厂（OpenAI 兼容）
tools/            文本抽取、LaTeX 编译辅助、离线索引构建、可选离线采集
resume-template/  LaTeX 模板与资源
docs/             示例/调试文件
start.sh          一键启动脚本
```

## 使用提示
- PDF 导出依赖 `xelatex`，请先安装 TeX Live / MacTeX。

