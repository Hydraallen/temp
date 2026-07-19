# -*- coding: utf-8 -*-
"""
考试信号挖掘模块（迁移自 cheatsheet-creator skill Step 3）。

职责：
  - 学科 → 题目 PDF 的映射（7 本 0715 题目集）
  - 整本题目集 render → OCR → 文本模型抽取考点信号
  - 学科级 `exam-signals.md` 的缓存（每学科只挖一次）

复用 glm_pipeline 的现成件（按原签名调用，不复制实现）：
  - `render_pages`           渲染 PDF 页为 PNG
  - `ocr_pages`              逐页 OCR + 磁盘缓存
  - `_call_text_openai`      调用 glm-5.2 文本模型（OpenAI 兼容端点）
  - `OCR_PROMPT_ROUGH`       粗转写 prompt（题目集无需逐字精校）
  - `TEXT_MODEL` / `WRITER_MAX_TOKENS`

fitz 只在 `get_pdf_page_count` 内延迟导入，便于 dry-run / ast.parse 在
未装 fitz 的环境下也能通过。
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径与学科 → 题目 PDF 映射
# ---------------------------------------------------------------------------
WORK_DIR = Path(
    "/Users/hydraallen/Desktop/Study/工作/找工/国家电网/天行/课本/temp/Study"
)
QUESTION_DIR = WORK_DIR / "题目"

# 学科 → 题目 PDF 文件名（与 01-章节任务表.md 一致；7 本 0715 题目集）
# 学科键与 glm_pipeline.Chapter.subject 完全一致，便于按 CHAPTERS 反查输出目录。
SUBJECT_QUESTION_PDF: dict[str, str] = {
    "操作系统":       "4-3-操作系统-题目.pdf",
    "计算机网络":     "5-5-计算机网络-题目.pdf",
    "软件设计与开发": "6-3-软件设计与开发-题目.pdf",
    "数据结构":       "7-3-数据结构-题目.pdf",
    "数据库":         "8-3-数据库-题目.pdf",
    "计算机组成":     "2-3-计算机组成-题目.pdf",
    "信息技术":       "3-2-信息技术-题目.pdf",
}


def exam_signals_path(subject_out_dir: Path) -> Path:
    """给定学科的 cheatsheets 输出目录，返回 exam-signals.md 的标准路径。

    落盘约定（skill 强调"partial progress survives"）：中间产物持久化到
    `cheatsheets/<学科>/intermediate/exam-signals.md`，便于中断后续跑、
    且每学科只挖一次（缓存命中即 skip）。
    """
    return subject_out_dir / "intermediate" / "exam-signals.md"


def get_subject_out_dir(subject: str, chapters: list) -> Path:
    """从 CHAPTERS 里查 subject 对应的 cheatsheets 输出目录。

    chapters 元素只需有 `.subject` 与 `.out_path` 属性（glm_pipeline.Chapter 满足）。
    """
    for ch in chapters:
        if ch.subject == subject:
            return (WORK_DIR / ch.out_path).parent
    raise KeyError(f"未知学科：{subject}")


def get_pdf_page_count(pdf_path: Path) -> int:
    """返回 PDF 总页数。fitz 延迟导入，便于 dry-run 不依赖 fitz。"""
    import fitz  # type: ignore[import-not-found]
    doc = fitz.open(pdf_path)
    n = doc.page_count
    doc.close()
    return n


# ---------------------------------------------------------------------------
# 题目集 OCR prompt（skill Step 3 的"信号源"准备）
# ---------------------------------------------------------------------------
def _exam_ocr_prompt() -> str:
    """题目集 OCR prompt：保留题号 + 选项 + 关键术语，无需逐字精校。

    题目集只用于挖掘考点信号（被考概念 / 频次 / 题型模式），与讲义 OCR 的
    `OCR_PROMPT_FULL`（逐字保真）需求不同，因此单独定制。
    """
    return (
        "请粗略转写这张扫描题目集页面的文字，用于后续挖掘考点。要求：\n"
        "1. 只输出文字，不要解释；\n"
        "2. 完整保留题号、选项（A/B/C/D）、关键术语；公式用 LaTeX；\n"
        "3. 看不清用 [?] 标注，绝不猜测；\n"
        "4. 保持题号层级（一/二/三 大题、1/2/3 小题）。"
    )


# ---------------------------------------------------------------------------
# 核心：挖一门学科的考试信号
# ---------------------------------------------------------------------------
def mine_exam_signals(
    pdf_path: Path,
    pdf_id: str,
    api_key: str,
    subject: str,
    page_range: tuple[int, int] | None = None,
) -> str:
    """对整本题目 PDF 做 render → OCR → 文本模型抽取，返回 exam-signals.md 正文。

    pdf_id：OCR 缓存命名空间前缀（建议形如 `"题目-<学科>"`），避免与讲义缓存撞键。
    page_range：可选 (起, 止)；默认渲染整本（用于首次挖掘）。

    复用 glm_pipeline 的 render_pages / ocr_pages / _call_text_openai，
    天然走现有 OCR 磁盘缓存（key=`{png.stem}-{mode}.txt`）。
    """
    # 延迟导入 glm_pipeline：避免循环依赖，且 dry-run 不强依赖 fitz
    from glm_pipeline import (  # noqa: WPS433（延迟导入是必要的）
        OCR_PROMPT_ROUGH,
        TEXT_MODEL,
        WRITER_MAX_TOKENS,
        _call_text_openai,
        ocr_pages,
        render_pages,
    )
    from .skill_prompts import EXAM_MINING_PROMPT_TEMPLATE

    if page_range is None:
        n_pages = get_pdf_page_count(pdf_path)
        page_range = (1, n_pages)
    else:
        n_pages = page_range[1] - page_range[0] + 1

    print(
        f"[exam-miner] {subject} 渲染题目 PDF {pdf_path.name} 页{page_range} ..."
    )
    pngs = render_pages(pdf_path, page_range[0], page_range[1], pdf_id=pdf_id)
    # 用题目集专用 prompt（更注重题号与选项保留），mode="exam-rough" 走独立缓存
    print(
        f"[exam-miner] {subject} OCR {len(pngs)} 页（题目集专用 prompt，mode=exam-rough）..."
    )
    exam_ocr, _usage = ocr_pages(
        pngs, api_key, _exam_ocr_prompt(), f"{subject}题目", "exam-rough"
    )

    prompt = EXAM_MINING_PROMPT_TEMPLATE.format(
        subject=subject,
        exam_pdf=pdf_path.name,
        n_pages=n_pages,
        exam_ocr=exam_ocr,
    )
    print(
        f"[exam-miner] {subject} 调用 {TEXT_MODEL} 抽取考点信号"
        f"（max_tokens={WRITER_MAX_TOKENS}）..."
    )
    text, usage, finish = _call_text_openai(
        [{"role": "user", "content": prompt}], api_key, WRITER_MAX_TOKENS
    )
    print(
        f"[exam-miner] {subject} 完成：{len(text)} 字  "
        f"in={usage.get('prompt_tokens', '?')} "
        f"out={usage.get('completion_tokens', '?')}  finish={finish}"
    )
    return text


def ensure_exam_signals(
    subject: str,
    api_key: str,
    subject_out_dir: Path,
    force: bool = False,
) -> str:
    """确保学科级 `exam-signals.md` 存在；存在且非 force 时直接复用（缓存策略）。

    与 run_all 的 skip 逻辑一致：挖过的学科若 exam-signals.md 已存在则 skip。
    force=True 时强制重挖（用于题目集更新或挖掘质量复检）。

    返回 exam-signals.md 正文，供写稿 prompt 注入。
    """
    out_p = exam_signals_path(subject_out_dir)
    if (
        out_p.exists()
        and not force
        and out_p.read_text(encoding="utf-8").strip()
    ):
        print(f"[exam-miner] {subject} 缓存命中：{out_p}")
        return out_p.read_text(encoding="utf-8")

    pdf_name = SUBJECT_QUESTION_PDF.get(subject)
    if not pdf_name:
        raise KeyError(f"该学科无对应题目 PDF：{subject}")
    pdf_path = QUESTION_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(f"题目 PDF 不存在：{pdf_path}")

    pdf_id = f"题目-{subject}"
    text = mine_exam_signals(pdf_path, pdf_id, api_key, subject)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(text, encoding="utf-8")
    print(
        f"[exam-miner] {subject} exam-signals 写入 {out_p}（{len(text)} 字）"
    )
    return text


def run_mine_only(force: bool = False) -> None:
    """CLI `--mine-only` 入口：只跑考试挖掘，不写稿。

    遍历 SUBJECT_QUESTION_PDF 全部 7 个学科，逐门挖一遍 exam-signals.md。
    """
    # 延迟导入 CHAPTERS 与 load_api_key，避免模块顶层循环
    from glm_pipeline import CHAPTERS, load_api_key  # noqa: WPS433

    api_key = load_api_key()
    total = len(SUBJECT_QUESTION_PDF)
    done = skipped = failed = 0
    print(
        f"[mine-only] 开始挖掘 {total} 个学科的考试信号"
        f"（force={'True' if force else 'False'}）"
    )
    for n, subject in enumerate(SUBJECT_QUESTION_PDF, 1):
        print(f"\n========== [mine {n}/{total}] {subject} ==========")
        try:
            subject_out_dir = get_subject_out_dir(subject, CHAPTERS)
            before = exam_signals_path(subject_out_dir).exists()
            ensure_exam_signals(subject, api_key, subject_out_dir, force=force)
            if before and not force:
                skipped += 1
            else:
                done += 1
        except Exception as e:  # 单学科异常不中断整批
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"    [FAILED] {subject}: {e} — 继续下一学科")
    print(
        f"\n[mine-only] 结束：DONE={done} SKIP={skipped} FAILED={failed} / {total}"
    )
