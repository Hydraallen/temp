# -*- coding: utf-8 -*-
"""
Skill 方法论 prompt 模板（迁移自 ~/.claude/skills/cheatsheet-creator/SKILL.md）。

本模块只负责 prompt 文本与 source-marker 处理：不调用任何 API、不读文件、不渲染。
保持无外部依赖，便于 dry-run 与 ast.parse 验证。

迁移自 skill 的步骤：
  - Step 1（lecture summary 模板）→ 部分结构已融入 build_writer_prompt_skill 的输出规范
  - Step 3（mine homework/exams）  → EXAM_MINING_PROMPT_TEMPLATE
  - Step 4（synthesize 双输出）    → build_writer_prompt_skill + source-marker 工具

source-marker 设计（skill Step 4「single source of truth」做法）：
  写稿模型只输出一份 expanded 版，所有出处以 HTML 注释 `<!-- src: ... -->` 内联；
  pipeline 再派生两份落盘文件：
    - *-expanded.md：把注释渲染成斜体括号引用 `*(src)*`
    - *.md（concise 主交付）：把注释直接剥离
  这样两版同源、零漂移。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# source-marker 处理工具
# ---------------------------------------------------------------------------
# 匹配 `<!-- src: ... -->`，允许前后有空白；非贪婪匹配注释内容。
_SRC_MARKER_RE = re.compile(r"[ \t]*<!--\s*src:\s*([^>]*?)\s*-->")


def strip_source_markers(expanded_md: str) -> str:
    """剥离所有 `<!-- src: ... -->` 标记，产出 concise 版（skill Step 4）。

    用于派生主交付文件 *.md（无出处引用）。
    """
    out = _SRC_MARKER_RE.sub("", expanded_md)
    # 清理剥离后留下的行尾多余空白与 3 个以上连续空行
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{4,}", "\n\n\n", out)
    return out


def convert_source_markers_to_italic(expanded_md: str) -> str:
    """把 `<!-- src: X -->` 渲染成 `*(X)*`，产出 expanded 版（skill Step 4）。

    用于派生 *-expanded.md（带斜体出处引用，视觉上次要但可追溯）。

    Bug 4 防护——避免重复引用：若同一行内**已有**相同出处（典型场景：写稿 prompt
    模板把 Caveat 写成 `*Caveat* (题目2): … <!-- src: 题目2 -->`，正文里已带 `(题目2)`，
    再渲染出 `*(题目2)*` 就是重复），则不再追加斜体引用。这样改在代码侧统一去重，
    不依赖模型遵守「不要重复」的指令，单一可信来源。
    """
    def _repl(m: "re.Match[str]") -> str:
        inner = m.group(1).strip()
        if not inner:
            return ""
        # 取 marker 所在行（从上一个换行到 marker 起点）的前文，判断是否已含同一引用。
        start = m.start()
        line_start = expanded_md.rfind("\n", 0, start) + 1
        preceding = expanded_md[line_start:start]
        # 归一化对比：去掉空白与常见包围符号（()（）[]【】），降低「题目2」vs「(题目2)」漏判。
        norm_preceding = re.sub(r"[\s()（）\[\]【】]", "", preceding)
        norm_inner = re.sub(r"[\s()（）\[\]【】]", "", inner)
        if norm_inner and norm_inner in norm_preceding:
            return ""  # 行内已引用过，丢弃重复的斜体出处
        return f"*({inner})*"

    return _SRC_MARKER_RE.sub(_repl, expanded_md)


# ---------------------------------------------------------------------------
# skill Step 3：考试信号挖掘 prompt
# ---------------------------------------------------------------------------
EXAM_MINING_PROMPT_TEMPLATE = """你是一名资深考试分析师。下面提供了一本「题目集」的整书 OCR 转写（含题干与选项，通常无标准答案）。请按下列方法论，挖掘出本学科后续编纂复习资料所需的「考试信号」。

======== 方法论（源自 cheatsheet-creator skill Step 3）========
1. 找出每道题考查的概念，记录出处（如「题目3」「P5-T2」）。
2. 关注"只有动手做过才会发现"的内容：
   - 讲义里一笔带过、但题目反复考的细节
   - 特定的技巧 / 捷径
   - 常见的错误思路（题干干扰项揭示的陷阱）
   - 反复出现的题型模式（"看到 X 就先尝试 Y"）
   - 反复用到的公式 vs 仅出现一次的公式
3. 构建概念频次表（哪些概念在多题里出现）。
4. 给出适合做 Worked Example 的代表题候选；题目集无答案时，解法一律标 `[PROPOSED — verify]`。
======== 方法论结束 ========

【学科】{subject}

======== 【题目集 OCR 全文】（信号源）========
{exam_ocr}
======== 题目集 OCR 结束 ========

【输出要求（Markdown，按下列固定结构）】
# {subject} · 考试信号挖掘（exam-signals）

> 来源：{exam_pdf}（OCR 共 {n_pages} 页）
> 说明：仅作"考什么 / 怎么考"的考点信号，不作为知识点正文；后续写稿用作权重。

## 1. 被考到的概念（带出处）
- **<概念名>** × <出现次数>：题目<N>、题目<M>、… — <一句话考点方向>

## 2. 反复出现的题型模式
- **<模式名>**：常见题干特征 → 解题切入点（若给具体解法，标 `[PROPOSED — verify]`）

## 3. 技巧 / 易错点（Caveat callout）
- > Caveat (题目<N>): <陷阱或技巧一句话>

## 4. 概念频次表（frequency tally，按频次降序）
| 概念 | 出现次数 | 出处 |
|---|---|---|
| <概念> | N | 题目x, 题目y |

## 5. Worked Example 候选（适合放进最终 cheatsheet 末尾）
### 候选 1：<题号·一句话主题> `[PROPOSED — verify]`
- 概念 tag：<concept>, <concept>
- 题干（精简）：…
- 解题骨架（3-8 步）：…

## 6. lecture 出现但未被考的概念（写稿时可从简）
- <概念A>、<概念B>、…

【纪律】
A. 没有答案支持的具体结论一律标 `[PROPOSED — verify]`，禁止杜撰"答案指出…"这类无据断言。
B. 概念名尽量贴讲义术语；无法对齐讲义术语时用题目原词并注明。
C. 频次表给出整数次数（同一题里多次出现按一次计），不要"多次 / 若干"这种含糊表述。
D. 第 6 节只能写「明显未在题目集里出现」的概念；判不准的概念不要列入。
E. 直接输出 Markdown 正文，不要任何前言、解释、"好的"等套话。"""


# ---------------------------------------------------------------------------
# skill Step 1 + 4：写稿 prompt（topic 分组、bold headwords、Caveat callout、
# Worked Examples 末尾区块；以 source-marker 形式携带出处；产物为 expanded）
# ---------------------------------------------------------------------------
# 中文章号 → 阿拉伯数字映射（与 glm_pipeline.Chapter.idx 的「一/二/…」对齐），
# 用于 Bug 2 的「Worked Example 章节归属过滤」：把当前章号显式告诉模型。
_CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _chapter_label_info(chapter_idx: str) -> tuple[str, str, str]:
    """把 Chapter.idx（如「一」）展开为 prompt 用的章号提示三元组。

    返回 (chapter_label, chapter_label_hint, other_chapter_hint)：
      - chapter_label：形如「第一章」「第二章」，主约束里直接引用；
      - chapter_label_hint：补充说明（如「即阿拉伯数字 1」），消除歧义；
      - other_chapter_hint：举几个「其它章节」的例子，让模型一眼能识别该排除哪些候选。

    chapter_idx 为空或无法识别时，回退到「当前章」泛指（约束依然有效，只是不带数字）。
    """
    idx = (chapter_idx or "").strip()
    if not idx:
        return ("当前章", "（chapter_idx 未提供，按 OCR 章节标题判断本章归属）", "其它章节")
    label = f"第{idx}章"
    n = _CN_NUM.get(idx)
    if n is not None:
        hint = f"（即阿拉伯数字 {n}）"
        # 取相邻两章作为「其它章节」示例，便于模型识别排除项；
        # 邻居必须在 _CN_NUM 已覆盖范围内，否则跳过（章号超出映射的不举例子）。
        cn_map_inv = {v: k for k, v in _CN_NUM.items()}
        neighbors = [
            i for i in (n - 1, n + 1, n + 2)
            if i != n and i in cn_map_inv
        ]
        examples = "、".join(f"第{cn_map_inv[i]}章" for i in neighbors[:2])
        other_hint = f"如{examples}、其它各章" if examples else "其它各章"
    else:
        hint = "（按 OCR 章节标题判断）"
        other_hint = "其它各章"
    return (label, hint, other_hint)



def build_writer_prompt_skill(
    subject: str,
    chapter_title: str,
    pdf_name: str,
    pages: tuple[int, int],
    chapter_ocr: str,
    guide_text: str,
    exam_signals: str = "",
    answer_note: str = "",
    answer_key: str = "",
    chapter_idx: str = "",
) -> str:
    """skill 方法论版的写稿 prompt。

    与 glm_pipeline.build_writer_prompt_full 的差异（迁移自 skill Step 1+4）：
      - 主体按「主题组 ## 主题」组织（而非严格六段式），便于扫读；
      - 保留顶部 `> 来源：...` 行（pipeline 现有约束）；
      - 每条 substantive 内容后用 `<!-- src: 讲义 pN -->` / `<!-- src: 题目N -->`
        形式内联出处；pipeline 据此派生 expanded（斜体引用）与 concise（剥离）；
      - 把 exam_signals 作为「重点权重」显式注入 prompt：被反复考的详写、
        未被考的可简写——这是 skill 的核心信号 vs 噪声逻辑；
      - 末尾独立的 `## Worked Examples` 区块（exam_signals 非空时）；
      - Caveat 用 `> Caveat:` callout 形式（skill 反复强调的高价值项）。
    """
    # Bug 2：把当前章号显式告诉模型，约束 Worked Example 只选本章来源的候选，
    # 防止 exam-signals（学科级整本挖）里的其它章节候选被机械塞入本章。
    chapter_label, chapter_label_hint, other_chapter_hint = _chapter_label_info(
        chapter_idx
    )
    exam_block = ""
    if exam_signals.strip():
        exam_block = f"""
======== 【本学科考试信号】（用作"重点权重"，并非知识点正文来源）========
说明：这是从本学科题目集里挖掘出的考点信号（被考概念、反复题型、易错点、频次表、Worked Example 候选）。
请据此决定详写 / 简写：
- 凡「被考到的概念」「频次表里 ≥2 次的概念」→ **优先详写**（公式 + 算法 + 标准解题套路 + Caveat 全写）；
- 凡「lecture 出现但未被考的概念」（exam-signals 第 6 节）→ 可一句带过，仅保留定义；
- 易错点（exam-signals 第 3 节的 `> Caveat (题目N): …`）→ 在对应概念下以 `> Caveat:` 形式呈现，并保留出处；
- Worked Example 候选（exam-signals 第 5 节）→ 末尾 `## Worked Examples` 区块至少收录 1 条代表题；
  候选含具体解法且源自题目集（无书内答案）的，必须标 `[PROPOSED — verify]`。
--- 考试信号开始 ---
{exam_signals}
--- 考试信号结束 ---
"""
    answer_block = ""
    if answer_key.strip():
        answer_block = f"""
======== 【书末统一答案】（题号 → 正确答案字母，权威，仅用于给考点标注正确结论）========
- 仅当你要在 Worked Examples 或 Caveat 里点出某道课后习题的正确结论时，才据此标注；
- **严禁编造答案**：本答案表里没有列出、或题号对不上的结论，一律不得断言；
- 若答案与你的常识推测冲突，**以本答案表为准**。
--- 书末答案开始 ---
{answer_key}
--- 书末答案结束 ---
"""
    return f"""你是一名资深考试复习资料编纂者。下面提供了「主指导文档」（含三条铁律、保真要求、自检清单）、本章讲义**整章**的 OCR 转写，以及（若提供）本学科的「考试信号」与「书末统一答案」。请严格依据 cheatsheet-creator skill 的方法论（已迁移到本 prompt）产出本章复习 cheatsheet 的 **expanded 版**（带 `<!-- src: ... -->` 出处标记；pipeline 会据此派生 concise 版）。

======== 主指导文档（铁律与保真要求必须遵守）========
{guide_text}
======== 主指导文档结束 ========

【本章元信息】
- 专题：{subject}
- 章名：{chapter_title}
- 来源 PDF：{pdf_name}
- 整章物理页范围：[{pages[0]}, {pages[1]}]

======== 【整章 OCR 全文】（知识点正文唯一来源；练习/答案仅作考点信号）========
说明：OCR 全文同时含『知识点』正文与『专项练习 / 参考答案 / 习题答案』。请按小标题自行区分：
- 只把『知识点』部分作为**正文唯一来源**，需完整覆盖每一个知识点；
- 『练习/答案』只作考点信号；题目题干与答案解析**禁止**抄进正文，仅用于打 ⭐/⚠ 标记或 Caveat 方向。
{answer_note}
--- OCR 全文开始 ---
{chapter_ocr}
--- OCR 全文结束 ---
{exam_block}{answer_block}
【输出结构（skill 方法论版，必须遵守）】
顶部 3 行（保留现 pipeline 的「来源」行约束）：
```
# {subject} · {chapter_title} — 复习资料

> 来源：{pdf_name} 物理页 [{pages[0]}, {pages[1]}]
> 说明：⭐=高频考点，⚠=易错点；> Caveat: 为陷阱/技巧；末尾 Worked Examples 为代表性题目（无书内答案的标 [PROPOSED — verify]）。
```

主体按「主题组」组织（粗体头词便于扫读；公式用 LaTeX、算法用代码块保真）：

```
## <主题组 1>
**<概念>**：<一句话定义> <!-- src: 讲义 p<物理页号> -->
$$<公式>$$ <!-- src: 讲义 p<物理页号> -->
- *Caveat* (题目<N>): <陷阱 / 技巧一句话> <!-- src: 题目N -->

**<标准解题套路>**（for <题型>）<!-- src: 讲义 p<物理页号> -->
1. <步骤>
2. <步骤>
3. <步骤>

## <主题组 2>
...

## 记号约定（可选，无则省略）
- <符号> = <含义>

---

## Worked Examples

### 例 1：<主题> *(来自 exam-signals 候选 N)*
*Tags: <concept>, <concept>*
**问题**：<精简题干> <!-- src: 题目N -->
**解答**：`[PROPOSED — verify]`（若该题在书内 / OCR 答案里无明确解法）
1. <key step>
2. <key step>
```

【纪律强化（必须逐条执行）】
1. **保真**：公式用 `$...$` / `$$...$$`，算法/代码用 fenced 代码块并标注语言，定义贴原文；看不清用 `[?]` 或 `[原文模糊]`。
2. **零编造**：知识点正文里没有的结论一律不得断言；Caveat 必须能回溯到 OCR 或 exam-signals；无答案支持的具体解法一律标 `[PROPOSED — verify]`。
3. **source-marker 规范**：每一条 substantive 内容（概念定义、公式、标准解题套路、Caveat、Worked Example 题干/解答步骤）后面**必须**带一个 `<!-- src: 讲义 pN -->` 或 `<!-- src: 题目N -->` 形式的标记；纯过渡句、章节标题、表头不需要。
4. **考试信号权重**：被考到 ≥2 次的概念务必详写（公式 + 套路 + Caveat）；lecture 出现但未被考的概念可一句带过（仅定义）。
5. **Worked Examples**：若上方【本学科考试信号】非空，本区块**必须存在**且至少收录 1 条代表题；若无考试信号，省略整个 Worked Examples 区块。
6. **不要使用斜体引用**：concise 版由 pipeline 自动派生，你只需输出 expanded 版（带 `<!-- src: ... -->`）；不要在 expanded 里手写 `*(...)*` 形式的斜体出处——用 HTML 注释标记即可。
7. 直接输出 Markdown 正文，不要任何额外说明、前言或"好的"之类的话。
8. **Worked Example 章节归属过滤（关键，防跨章污染）**：当前正在写的是「{chapter_label}」{chapter_label_hint}。exam-signals 第 5 节的 Worked Example 候选**只允许**选取来源标注为本章的题目（标注形如「{chapter_label}-单选-1」「{chapter_label}-多选-4」「本章-…」等）；**严禁**把来源标注为其它章节（{other_chapter_hint}）的题目塞入本章 cheatsheet。若本章无任何候选，宁可省略 Worked Examples 区块，也不要凑数塞其它章节的题。
9. **对比项 ≥3 强制表格（防对比表退化为 bullet）**：凡涉及 **3 个及以上**同类项的对比（如多种技术标准 / 多种协议 / 多个分类 / 多个并列方案的特性对比），**必须**用 Markdown 表格呈现（`| 列 | 列 |` 形式），不要压成 bullet 列表；列名贴讲义术语，某项特征原文未述时该单元格写「[原文未述]」，不得凭常识补造。"""
