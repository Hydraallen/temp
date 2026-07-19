# -*- coding: utf-8 -*-
"""
cheatsheet 自检模块：对刚生成的 md 做四维校验，并支持 react 自愈回路选稿。

四个维度：
  (a) 结构完整 ——「来源」行 + 多级标题 + 页码区间与 chapter.pages 对得上
  (b) 覆盖率   ——OCR 里的知识点/小节名在 md 正文里出现的比例（ocr_text 为 None 则跳过）
  (c) 公式保真 ——$...$ / $$...$$ 是否成对闭合 + 破损占位（[?] / ??? / 不配对的 \(）数量
  (d) 长度/非空——去空白后字符数下限

本模块刻意不依赖 fitz / glm_pipeline，避免循环导入；Chapter 通过 Protocol 描述形状。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# 阈值常量（集中放置，便于事后调参）
# ---------------------------------------------------------------------------
MIN_SECTIONS = 3          # (a) 至少识别出 3 个小节标题
COVERAGE_THRESHOLD = 0.50  # (b) 覆盖率下限
MIN_TOKENS_FOR_COVERAGE = 5  # (b) 抽到的知识点 token 少于此数 → 信号太弱，记 N/A
LATEX_BROKEN_MAX = 3       # (c) 未闭合/破损占位总数超过该值判 fail
MIN_CHARS_BASE = 800       # (d) 字符数下限基数
MIN_CHARS_PER_PAGE = 80    # (d) 每页追加字符数（按 chapter.pages 比例放大下限）

# skill 结构维度（可选，向后兼容：默认不启用，需显式调用 check_skill_structure）
MIN_TOPIC_GROUPS = 2       # (e) `## 主题组` 数量下限（skill Step 1+4 结构）
MIN_BOLD_HEADWORDS = 5     # (e) `**粗体头词**` 数量下限（skill Density tips）


class _ChapterLike(Protocol):
    """glm_pipeline.Chapter 的形状契约（结构子类型，无需运行时导入）。"""

    pdf: str
    pages: tuple[int, int]


@dataclass(frozen=True)
class CheckResult:
    """四维自检结果。passed = 所有「计入维度」全过（覆盖率 N/A 时不计入）。"""

    passed: bool
    failures: list[str] = field(default_factory=list)
    scores: dict[str, dict] = field(default_factory=dict)

    def score_tuple(self) -> tuple[int, int]:
        """用于「保留最优稿」的比较键：(通过维度数, 字符数)。越大越好。"""
        passed_dims = sum(
            1 for d in self.scores.values() if d.get("pass") and d.get("active", True)
        )
        length_val = self.scores.get("length", {}).get("value", 0)
        return (passed_dims, int(length_val))


# ---------------------------------------------------------------------------
# 维度 (a) 结构完整
# ---------------------------------------------------------------------------
_SOURCE_RE = re.compile(
    r"来源[：:]\s*[^\n]*?物理页\s*\[\s*(\d+)\s*[,，]\s*(\d+)\s*\]"
)
# 六段式模板里的小节标题：中文编号「一、二、」或 Markdown 「## 」/「### 」
_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"[一二三四五六七八九十百]+[、.]"            # 一、 / 二、
    r"|\d+\.\s+\S"                              # 1. xxx
    r"|#{2,4}\s+\S"                             # ## xxx / ### xxx
    r")"
)


def _check_structure(md_text: str, chapter: _ChapterLike) -> tuple[bool, dict]:
    failures: list[str] = []
    detail: dict[str, object] = {}

    # 必须含「来源：…」行
    has_source = bool(_SOURCE_RE.search(md_text))
    detail["has_source_line"] = has_source
    if not has_source:
        failures.append("缺少「来源：… 物理页 [起,止]」行")

    # 页码区间对得上 chapter.pages
    page_match = _SOURCE_RE.search(md_text)
    page_ok = False
    if page_match:
        s, e = int(page_match.group(1)), int(page_match.group(2))
        page_ok = (s, e) == tuple(chapter.pages)
        detail["source_pages"] = (s, e)
        detail["expected_pages"] = tuple(chapter.pages)
        if not page_ok:
            failures.append(
                f"来源行页码区间 [{s},{e}] 与 chapter.pages {tuple(chapter.pages)} 不一致"
            )
    else:
        detail["source_pages"] = None
        detail["expected_pages"] = tuple(chapter.pages)

    # 多级标题数 ≥ MIN_SECTIONS
    sections = _SECTION_RE.findall(md_text)
    n_sec = len(sections)
    detail["section_count"] = n_sec
    if n_sec < MIN_SECTIONS:
        failures.append(f"小节标题数 {n_sec} < {MIN_SECTIONS}（结构不完整）")

    passed = has_source and page_ok and n_sec >= MIN_SECTIONS
    return passed, {"failures": failures, "detail": detail, "value": n_sec}


# ---------------------------------------------------------------------------
# 维度 (b) 覆盖率（启发式：从 OCR 抽知识点/小节名）
# ---------------------------------------------------------------------------
# OCR 里典型的小节/知识点锚点
_KP_ANCHOR_RE = re.compile(
    r"(?m)^\s*(?:"
    r"知识点\s*\d*"                           # 知识点 / 知识点 3
    r"|第[一二三四五六七八九十百\d]+[节章]"      # 第一节 / 第3节
    r"|\d+\.\d+(?:\.\d+)*\s+[^\n]{2,30}"      # 1.2 xxx / 2.3.1 xxx
    r"|[•·\-]\s+[^\n]{2,40}"                  # • xxx 项目符号要点
    r")"
)


def _extract_kp_tokens(ocr_text: str) -> list[str]:
    """从 OCR 文本里抽知识点/小节关键词，用于覆盖率统计。"""
    tokens: list[str] = []
    for m in _KP_ANCHOR_RE.finditer(ocr_text):
        # 取锚点行剩余的非空白文本作为关键词（剥掉前缀符号）
        line = m.group(0).strip()
        body = re.sub(r"^\s*(?:知识点\s*\d*|第[一二三四五六七八九十百\d]+[节章]|\d+\.\d+(?:\.\d+)*|[•·\-])\s*", "", line)
        body = body.strip(" :：-·•\t")
        # 拒绝句片段噪音：含句末/嵌套标点说明 OCR 抓到的是整句而非关键词
        if (
            2 <= len(body) <= 30
            and not body.isdigit()
            and not re.search(r"[。，；,;（）()【】！？!?…]", body)
        ):
            tokens.append(body)
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _check_coverage(md_text: str, ocr_text: str | None) -> tuple[bool, dict]:
    if not ocr_text or not ocr_text.strip():
        return True, {
            "active": False,
            "pass": True,
            "value": None,
            "detail": "ocr_text=None → N/A",
        }
    tokens = _extract_kp_tokens(ocr_text)
    if len(tokens) < MIN_TOKENS_FOR_COVERAGE:
        return True, {
            "active": False,
            "pass": True,
            "value": None,
            "detail": f"OCR 抽到知识点 token 仅 {len(tokens)} < {MIN_TOKENS_FOR_COVERAGE}，信号太弱 → N/A",
        }
    hit = sum(1 for t in tokens if t in md_text)
    ratio = hit / len(tokens)
    failures: list[str] = []
    if ratio < COVERAGE_THRESHOLD:
        failures.append(
            f"OCR 知识点覆盖率 {ratio:.0%}（{hit}/{len(tokens)}）< {COVERAGE_THRESHOLD:.0%}"
        )
    passed = ratio >= COVERAGE_THRESHOLD
    return passed, {
        "active": True,
        "pass": passed,
        "value": ratio,
        "failures": failures,
        "detail": f"{hit}/{len(tokens)} 命中",
    }


# ---------------------------------------------------------------------------
# 维度 (c) LaTeX / 公式保真
# ---------------------------------------------------------------------------
_PLACEHOLDER_RE = re.compile(r"\[\?\]|\?\?|【\?】|［?］")


def _check_latex(md_text: str) -> tuple[bool, dict]:
    failures: list[str] = []
    # $$...$$: 计算成对出现的数量
    double_count = md_text.count("$$")
    double_pairs = double_count // 2
    double_unpaired = double_count % 2

    # 去掉已配对的 $$...$$ 后，统计单 $ 的配对情况
    body = re.sub(r"\$\$.*?\$\$", "", md_text, flags=re.DOTALL)
    single_count = body.count("$")
    single_unpaired = single_count % 2

    # 不配对的 \(  \)
    open_paren = md_text.count(r"\(")
    close_paren = md_text.count(r"\)")
    paren_unbalanced = abs(open_paren - close_paren)

    # 破损占位
    placeholders = len(_PLACEHOLDER_RE.findall(md_text))

    broken_total = single_unpaired + double_unpaired + paren_unbalanced + placeholders
    detail = {
        "single_unpaired": single_unpaired,
        "double_unpaired": double_unpaired,
        "paren_unbalanced": paren_unbalanced,
        "placeholders": placeholders,
        "broken_total": broken_total,
    }
    if broken_total > LATEX_BROKEN_MAX:
        failures.append(
            f"公式/占位破损总数 {broken_total} > {LATEX_BROKEN_MAX}"
            f"（单$未配对={single_unpaired}, $$未配对={double_unpaired},"
            f" \\(\\)不平衡={paren_unbalanced}, 占位={placeholders}）"
        )
    passed = broken_total <= LATEX_BROKEN_MAX
    return passed, {"failures": failures, "detail": detail, "value": broken_total}


# ---------------------------------------------------------------------------
# 维度 (d) 长度/非空
# ---------------------------------------------------------------------------
def _min_chars_for(chapter: _ChapterLike) -> int:
    start, end = chapter.pages
    pages = max(1, end - start + 1)
    return MIN_CHARS_BASE + pages * MIN_CHARS_PER_PAGE


def _check_length(md_text: str, chapter: _ChapterLike) -> tuple[bool, dict]:
    stripped = re.sub(r"\s+", "", md_text)
    n = len(stripped)
    threshold = _min_chars_for(chapter)
    failures: list[str] = []
    if n == 0:
        failures.append("正文为空")
    elif n < threshold:
        failures.append(f"正文 {n} 字 < 下限 {threshold}")
    passed = n >= threshold
    return passed, {"failures": failures, "detail": {"threshold": threshold}, "value": n}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def check_cheatsheet(
    md_text: str,
    chapter: _ChapterLike,
    ocr_text: str | None = None,
) -> CheckResult:
    """对一份刚生成的 cheatsheet md 跑四维校验。

    chapter 只要有 `.pdf` 与 `.pages` 属性即可（glm_pipeline.Chapter 满足）。
    ocr_text 为 None 时覆盖率维度记 N/A，不计入总判定。
    """
    scores: dict[str, dict] = {}
    failures: list[str] = []

    ok_a, scores["structure"] = _check_structure(md_text, chapter)
    ok_b, scores["coverage"] = _check_coverage(md_text, ocr_text)
    ok_c, scores["latex"] = _check_latex(md_text)
    ok_d, scores["length"] = _check_length(md_text, chapter)

    # 显式写入 pass / active 字段（coverage 的 active 已在内部按 ocr_text 是否提供设置）
    scores["structure"]["pass"] = ok_a
    scores["structure"]["active"] = True
    scores["coverage"]["pass"] = ok_b
    # coverage.active 已在 _check_coverage 内设置
    scores["latex"]["pass"] = ok_c
    scores["latex"]["active"] = True
    scores["length"]["pass"] = ok_d
    scores["length"]["active"] = True

    for dim, res in scores.items():
        if not res.get("active", True):
            continue
        failures.extend(res.get("failures", []))

    passed = all(
        res.get("pass", True) for res in scores.values() if res.get("active", True)
    )
    return CheckResult(passed=passed, failures=failures, scores=scores)


# ---------------------------------------------------------------------------
# 辅助：把判定结果格式化成一行进度日志字段
# ---------------------------------------------------------------------------
def format_score_line(result: CheckResult) -> str:
    """形如 `structure=P coverage=NA(0.50未启用) latex=P(0) length=P(4521)`。"""
    parts: list[str] = []
    for dim in ("structure", "coverage", "latex", "length"):
        res = result.scores.get(dim, {})
        if not res.get("active", True):
            parts.append(f"{dim}=NA")
            continue
        flag = "P" if res.get("pass") else "F"
        val = res.get("value")
        val_str = "" if val is None else f"({val})"
        parts.append(f"{dim}={flag}{val_str}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 维度 (e) skill 结构（可选；迁移自 cheatsheet-creator skill Step 1+4）
# ---------------------------------------------------------------------------
# `## 主题组` 标题（二级标题，skill 的 topic group）
_SKILL_TOPIC_RE = re.compile(r"(?m)^[ \t]*##\s+[^\n#]")
# 粗体头词 `**xxx**`（行首允许空白；长度 1-60，过滤 **注意** 这类强调）
_BOLD_HEADWORD_RE = re.compile(r"\*\*[^*\n]{1,60}\*\*")
# `## Worked Examples` 区块标题（skill Step 4 末尾区块）
_WORKED_EXAMPLES_RE = re.compile(r"(?m)^[ \t]*##\s*Worked Examples\b")


def check_skill_structure(
    md_text: str, exam_signals_present: bool
) -> tuple[bool, dict]:
    """skill 结构维度（可选第 5 维；不破坏 check_cheatsheet 的四维契约）。

    检查项（迁移自 skill Step 1+4 的结构要求）：
      - `## 主题组` 数量 ≥ MIN_TOPIC_GROUPS（topic-grouped 组织）
      - 粗体头词数量 ≥ MIN_BOLD_HEADWORDS（skill Density tips：粗体头词便于扫读）
      - 若 exam_signals_present：必须有 `## Worked Examples` 区块

    用法：在 skill 模式下，写稿完成后**额外**调用本函数做诊断检查。
    不计入 react 自愈主判定（避免改动 check_cheatsheet 的四维契约）。
    """
    failures: list[str] = []
    topic_groups = _SKILL_TOPIC_RE.findall(md_text)
    n_groups = len(topic_groups)
    bold_count = len(_BOLD_HEADWORD_RE.findall(md_text))
    has_worked = bool(_WORKED_EXAMPLES_RE.search(md_text))

    detail: dict[str, object] = {
        "topic_groups": n_groups,
        "bold_headwords": bold_count,
        "has_worked_examples": has_worked,
    }
    if n_groups < MIN_TOPIC_GROUPS:
        failures.append(f"主题组数 {n_groups} < {MIN_TOPIC_GROUPS}")
    if bold_count < MIN_BOLD_HEADWORDS:
        failures.append(f"粗体头词 {bold_count} < {MIN_BOLD_HEADWORDS}")
    if exam_signals_present and not has_worked:
        failures.append("exam-signals 非空但缺少 `## Worked Examples` 区块")

    passed = not failures
    return passed, {
        "failures": failures,
        "detail": detail,
        "value": n_groups,
        "pass": passed,
        "active": True,
    }


def format_skill_line(skill_res: dict) -> str:
    """把 check_skill_structure 返回的 dict 格式化成单行日志字段。

    形如 `skill=P(groups=8 bold=42 worked=Y)`。
    """
    if not skill_res:
        return "skill=NA"
    flag = "P" if skill_res.get("pass") else "F"
    d = skill_res.get("detail", {})
    worked = "Y" if d.get("has_worked_examples") else "N"
    return (
        f"skill={flag}"
        f"(groups={d.get('topic_groups', '?')} "
        f"bold={d.get('bold_headwords', '?')} worked={worked})"
    )
