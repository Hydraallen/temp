# -*- coding: utf-8 -*-
"""
智能同步状态检测与执行（`--status` / `--sync` 入口）。

职责：
  - classify_chapter(ch, use_skill) -> ChapterVerdict
        对单章 cheatsheet 判 OK / MISSING / NEEDS-REPAIR / STALE。
  - classify_exam_signals(subject, chapters) -> (status, path)
        对学科级 exam-signals.md 判 OK / MISSING / STALE。
  - print_status(use_skill)        dry-run，只读不写，打印状态表。
  - run_sync(use_skill, force)     执行智能同步（从零生成 / 增量修复 / skip）。

设计原则（与用户全局规则对齐）：
  - **不依赖 fitz**：顶层不导入 glm_pipeline，--status 在纯校验环境也能跑。
  - **复用现成件**：四维校验复用 cheatsheet_checker；生成/重生复用
    glm_pipeline.run_chapter_full（OCR 磁盘缓存命中即省）。
  - **不破坏现有 --all 语义**：--all 保持「存在即 skip」不动；--sync 才走智能判定。
  - **dry-run 安全**：print_status 只 stat/read，不写任何文件、不调 API。

判定规则速查（详见各 classify 函数 docstring）：

  章节（每章）
    concise 缺失                       -> MISSING（从零生成）
    四维 check_cheatsheet 不过          -> NEEDS-REPAIR（增量修复）
    skill 模式：expanded 缺失 / skill 维不过 -> NEEDS-REPAIR
    讲义 PDF mtime > concise mtime       -> STALE（重生）
    其余                                -> OK（skip）

  exam-signals（每学科）
    不存在/为空                          -> MISSING
    题目 PDF mtime > exam-signals mtime  -> STALE
    其余                                -> OK
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .cheatsheet_checker import (
    CheckResult,
    check_cheatsheet,
    check_skill_structure,
)
from .exam_miner import (
    QUESTION_DIR,
    SUBJECT_QUESTION_PDF,
    exam_signals_path,
    get_subject_out_dir,
)


# ---------------------------------------------------------------------------
# 路径（与 glm_pipeline / exam_miner 保持一致；不导入 glm_pipeline 以避免 fitz 依赖）
# ---------------------------------------------------------------------------
WORK_DIR = Path(
    "/Users/hydraallen/Desktop/Study/工作/找工/国家电网/天行/课本/temp/Study"
)
LECTURE_DIR = WORK_DIR / "讲义"


# ---------------------------------------------------------------------------
# 章节判定
# ---------------------------------------------------------------------------
class ChapterStatus(str, Enum):
    """章节四态（值固定，便于日志与表格汇总）。"""

    OK = "OK"
    MISSING = "MISSING"
    NEEDS_REPAIR = "NEEDS-REPAIR"
    STALE = "STALE"


@dataclass(frozen=True)
class ChapterVerdict:
    """单章判定结果。reason 为空字符串表示无失败原因（OK 时）。"""

    status: ChapterStatus
    reason: str = ""
    check_result: CheckResult | None = None

    def label(self) -> str:
        """形如 `NEEDS-REPAIR(structure; length)`，用于日志一行展示。"""
        if self.reason:
            return f"{self.status.value}({self.reason})"
        return self.status.value


def classify_chapter(ch, use_skill: bool) -> ChapterVerdict:
    """对单章 cheatsheet 做状态判定。

    判定顺序（先粗后细，先命中先返回）：
      1. concise 主文件不存在                -> MISSING
      2. 四维 check_cheatsheet 不过          -> NEEDS-REPAIR（附失败维度名）
      3. skill 模式额外：
           - expanded 文件缺失                -> NEEDS-REPAIR
           - check_skill_structure 不过       -> NEEDS-REPAIR（附失败项）
      4. 新鲜度：讲义 PDF mtime > concise mtime -> STALE
      5. 否则                                -> OK

    chapter 只需具备 `.subject/.pdf/.pages/.out_path/.title/.idx` 属性
    （glm_pipeline.Chapter 满足）。不传 ocr_text：coverage 维度自动记 N/A，
    dry-run 不重读 OCR 中间产物。
    """
    out_p = WORK_DIR / ch.out_path
    if not out_p.exists():
        return ChapterVerdict(
            ChapterStatus.MISSING, reason=f"concise 缺失: {out_p.name}"
        )

    md = out_p.read_text(encoding="utf-8")
    cr = check_cheatsheet(md, ch, None)  # coverage 维度 N/A
    if not cr.passed:
        failed_dims = [
            d
            for d, r in cr.scores.items()
            if r.get("active", True) and not r.get("pass", True)
        ]
        reason = "; ".join(failed_dims) if failed_dims else "check failed"
        return ChapterVerdict(
            ChapterStatus.NEEDS_REPAIR, reason=reason, check_result=cr
        )

    if use_skill:
        exp_p = out_p.with_name(out_p.stem + "-expanded.md")
        if not exp_p.exists():
            return ChapterVerdict(
                ChapterStatus.NEEDS_REPAIR,
                reason=f"expanded 缺失: {exp_p.name}",
                check_result=cr,
            )
        # exam_signals_present=False：status dry-run 时不强求 Worked Examples
        # （exam-signals 可能尚未挖，避免误报）。
        ok, detail = check_skill_structure(md, exam_signals_present=False)
        if not ok:
            fails = detail.get("failures", [])
            return ChapterVerdict(
                ChapterStatus.NEEDS_REPAIR,
                reason="; ".join(fails) if fails else "skill-structure failed",
                check_result=cr,
            )

    # 新鲜度：讲义 PDF 更新过（理论罕见，但允许重生场景）
    pdf_path = LECTURE_DIR / ch.pdf
    if pdf_path.exists() and pdf_path.stat().st_mtime > out_p.stat().st_mtime:
        return ChapterVerdict(
            ChapterStatus.STALE,
            reason="讲义 PDF 较新（pdf mtime > md mtime）",
            check_result=cr,
        )

    return ChapterVerdict(ChapterStatus.OK, check_result=cr)


# ---------------------------------------------------------------------------
# exam-signals（学科级）判定
# ---------------------------------------------------------------------------
def classify_exam_signals(subject: str, chapters: list) -> tuple[str, str]:
    """对学科级 exam-signals.md 判定。

    返回 (status, path)，status ∈ {"OK", "MISSING", "STALE"}：
      - 不存在或为空       -> MISSING
      - 题目 PDF 较新       -> STALE
      - 否则               -> OK

    chapters 参数与 exam_miner.get_subject_out_dir 签名一致。
    """
    out_dir = get_subject_out_dir(subject, chapters)
    es_p = exam_signals_path(out_dir)
    if not es_p.exists() or not es_p.read_text(encoding="utf-8").strip():
        return ("MISSING", str(es_p))

    pdf_name = SUBJECT_QUESTION_PDF.get(subject)
    if pdf_name:
        pdf_p = QUESTION_DIR / pdf_name
        if pdf_p.exists() and pdf_p.stat().st_mtime > es_p.stat().st_mtime:
            return ("STALE", str(es_p))
    return ("OK", str(es_p))


# ---------------------------------------------------------------------------
# --status：dry-run 状态表
# ---------------------------------------------------------------------------
def print_status(use_skill: bool = False) -> dict:
    """扫描 7 学科 exam-signals + 50 章 cheatsheet，打印状态表并返回统计。

    dry-run：只 stat/read md，不写任何文件，不调 GLM API。

    返回 {"chapters": {status: count}, "exam_signals": {status: count}}。
    """
    # 延迟导入 glm_pipeline：避免顶层循环依赖与 fitz 加载
    from glm_pipeline import CHAPTERS

    # --- exam-signals（学科级）---
    print("=" * 72)
    print(f"[status] exam-signals 状态（use_skill={use_skill}）")
    print("=" * 72)
    es_stats: dict[str, int] = defaultdict(int)
    for subject in SUBJECT_QUESTION_PDF:
        status, es_path = classify_exam_signals(subject, CHAPTERS)
        es_stats[status] += 1
        print(f"  {subject:10s}  {status:8s}  {es_path}")
    print(
        f"  小计：OK={es_stats['OK']}  MISSING={es_stats['MISSING']}  "
        f"STALE={es_stats['STALE']}  / {len(SUBJECT_QUESTION_PDF)}"
    )

    # --- 章节级（按学科分组）---
    print("")
    print("=" * 72)
    print(f"[status] 章节状态（use_skill={use_skill}）")
    print("=" * 72)
    ch_stats: dict[str, int] = defaultdict(int)
    for subject in SUBJECT_QUESTION_PDF:
        chapters = [c for c in CHAPTERS if c.subject == subject]
        print(f"\n--- {subject}（{len(chapters)} 章）---")
        for ch in chapters:
            v = classify_chapter(ch, use_skill)
            ch_stats[v.status.value] += 1
            tag = f"第{ch.idx}章 {ch.title}"
            print(f"  [{v.status.value:13s}] {tag:34s}  {v.reason}")

    total = len(CHAPTERS)
    print("")
    print("=" * 72)
    print(
        f"[status] 章节：OK={ch_stats.get('OK', 0)}  "
        f"MISSING={ch_stats.get('MISSING', 0)}  "
        f"NEEDS-REPAIR={ch_stats.get('NEEDS-REPAIR', 0)}  "
        f"STALE={ch_stats.get('STALE', 0)}  / {total}"
    )
    print(
        f"[status] exam-signals：OK={es_stats['OK']}  "
        f"MISSING={es_stats['MISSING']}  STALE={es_stats['STALE']}  / "
        f"{len(SUBJECT_QUESTION_PDF)} 学科"
    )
    ready = ch_stats.get("OK", 0)
    print(
        f"[status] 就绪 {ready}/{total}；待处理 {total - ready} 章 "
        f"(MISSING={ch_stats.get('MISSING', 0)}, "
        f"NEEDS-REPAIR={ch_stats.get('NEEDS-REPAIR', 0)}, "
        f"STALE={ch_stats.get('STALE', 0)})"
    )
    print("=" * 72)
    return {"chapters": dict(ch_stats), "exam_signals": dict(es_stats)}


# ---------------------------------------------------------------------------
# --sync：智能同步执行
# ---------------------------------------------------------------------------
def _action_for(status: ChapterStatus, force: bool) -> str:
    """把章节状态映射成 sync 动作标签（用于日志）。"""
    if force:
        return "FORCE-REGEN"
    return {
        ChapterStatus.OK: "SKIP",
        ChapterStatus.MISSING: "GENERATE",
        ChapterStatus.NEEDS_REPAIR: "REPAIR",
        ChapterStatus.STALE: "REGEN-STALE",
    }[status]


def run_sync(use_skill: bool = False, force: bool = False) -> None:
    """执行智能同步。

    对每章：
      - OK（且非 force）           -> skip
      - MISSING / NEEDS-REPAIR / STALE / force -> 调 run_chapter_full
        （MISSING = 从零生成；其余 = 增量修复/重生；OCR 磁盘缓存命中即省 OCR token）

    use_skill=True 时，run_chapter_full 内部会 ensure_exam_signals（学科级缓存命中
    即 skip；MISSING/STALE 由 --mine-only 或本路径首次触发挖掘）。force=True
    会无条件重生所有章节（但仍走 run_chapter_full，OCR 缓存照旧复用）。

    复用 glm_pipeline._log_progress 写主进度文件，便于与 --all 进度统一查阅。
    """
    from glm_pipeline import (  # 延迟导入：避免顶层循环 + fitz 加载
        CHAPTERS,
        MAIN_GUIDE,
        _log_progress,
        load_api_key,
        run_chapter_full,
    )

    api_key = load_api_key()
    guide_text = MAIN_GUIDE.read_text(encoding="utf-8")
    total = len(CHAPTERS)
    generated = repaired = skipped = failed = 0

    _log_progress(
        f"\n===== sync 启动  skill={'ON' if use_skill else 'OFF'}  "
        f"force={'True' if force else 'False'}  共 {total} 章 ====="
    )

    for n, ch in enumerate(CHAPTERS, 1):
        tag = f"{ch.subject}·第{ch.idx}章 {ch.title}"
        v = classify_chapter(ch, use_skill)
        action = _action_for(v.status, force)
        print(f"\n========== [sync {n}/{total}] [{action}] {tag} ==========")

        if v.status == ChapterStatus.OK and not force:
            skipped += 1
            print(f"  -> skip（OK）")
            _log_progress(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | SYNC-SKIP OK | - | - | - |"
            )
            continue

        # 需要生成 / 修复 / 重生
        print(f"  -> {action}（{v.label()}）")
        _log_progress(
            f"| {ch.subject} | 第{ch.idx}章 {ch.title} | SYNC-{action} "
            f"{v.reason or '-'} | - | - | - |"
        )
        try:
            res = run_chapter_full(ch, api_key, guide_text, use_skill=use_skill)
            if v.status == ChapterStatus.MISSING:
                generated += 1
            else:
                repaired += 1
            _log_progress(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | SYNC-DONE | "
                f"{res.elapsed:.0f}s | tok={res.tokens['total_tokens']} | "
                f"{res.char_count}字 | react={res.repair_rounds} {res.final_verdict}"
            )
        except Exception as e:  # 单章异常不中断整批
            failed += 1
            import traceback

            traceback.print_exc()
            _log_progress(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | SYNC-FAILED "
                f"{type(e).__name__}: {str(e)[:120]} | - | - | - |"
            )
            print(f"  [FAILED] {tag}: {e} — 继续下一章")

    _log_progress(
        f"===== sync 结束  GENERATED={generated} REPAIRED={repaired} "
        f"SKIPPED={skipped} FAILED={failed} / {total} ====="
    )
    print(
        f"\nsync 结束：GENERATED={generated} REPAIRED={repaired} "
        f"SKIPPED={skipped} FAILED={failed} / {total}"
    )
