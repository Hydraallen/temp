#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GLM 讲义 -> 逐章复习 cheatsheet 编排脚本。

阶段：
  1. 渲染：PyMuPDF 把扫描页渲染为 PNG（dpi=150）。
  2. OCR：视觉模型 glm-4.6v 逐字转写（走 OpenAI 兼容端点）。
  3. 写稿：文本模型 glm-5.2 依据主指导文档模板 + 三条铁律产出 cheatsheet。
        （OpenAI 兼容端点失败则退回 Anthropic 端点）

本次仅调用一次跑「操作系统第1章」原型。run_chapter 已参数化，便于以后循环 50 章。
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# 常量 / 路径
# ---------------------------------------------------------------------------
WORK_DIR = Path(
    "/Users/hydraallen/Desktop/Study/工作/找工/国家电网/天行/课本/temp/Study"
)
LECTURE_DIR = WORK_DIR / "讲义"  # 讲义源 PDF 目录
GUIDE_DIR = WORK_DIR / "复习资料生成指导"
MAIN_GUIDE = GUIDE_DIR / "00-主指导文档.md"
RENDER_DIR = Path("/private/tmp/cheatsheet-render")
CRED_FILE = Path.home() / ".claude" / "glm-env.json"

OPENAI_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
ANTHROPIC_ENDPOINT = "https://open.bigmodel.cn/api/anthropic/v1/messages"

VISION_MODEL = "glm-4.6v"
TEXT_MODEL = "glm-5.2"

RENDER_DPI = 150


# ---------------------------------------------------------------------------
# 凭证
# ---------------------------------------------------------------------------
def load_api_key() -> str:
    data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
    key = data.get("ANTHROPIC_AUTH_TOKEN")
    if not key:
        raise RuntimeError("ANTHROPIC_AUTH_TOKEN 未在 glm-env.json 中找到")
    return key


# ---------------------------------------------------------------------------
# HTTP （标准库，带一次重试）
# ---------------------------------------------------------------------------
def _post_json(url: str, headers: dict, payload: dict, timeout: int = 600, retries: int = 3) -> dict:
    body = json.dumps(payload).encode("utf-8")

    def _once() -> dict:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _once()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as e:
            last = e
            detail = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    detail = e.read().decode("utf-8", "ignore")[:500]
                except Exception:
                    pass
            if attempt < retries:
                wait = 5 * (attempt + 1)
                print(f"    [网络异常] {e} {detail} — {wait}s 后重试（{attempt + 1}/{retries}）")
                time.sleep(wait)
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def render_pages(
    pdf_path: Path, start: int, end: int, dpi: int = RENDER_DPI, pdf_id: str = ""
) -> list[Path]:
    """渲染物理页 [start, end]（从 1 开始）为 PNG，返回文件路径列表。

    pdf_id：PDF 命名空间前缀，避免不同 PDF 的同号页（每本都有 p003）互相覆盖，
    也让 OCR 磁盘缓存（键含 png.stem）天然按 PDF 隔离。
    """
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"{pdf_id}-" if pdf_id else ""
    doc = fitz.open(pdf_path)
    out: list[Path] = []
    for p in range(start - 1, end):  # fitz 页索引从 0 开始
        png = RENDER_DIR / f"{prefix}p{p + 1:03d}.png"
        doc[p].get_pixmap(dpi=dpi).save(png)
        out.append(png)
    doc.close()
    return out


# ---------------------------------------------------------------------------
# OCR （glm-4.6v）
# ---------------------------------------------------------------------------
OCR_PROMPT_FULL = (
    "请逐字完整转写这张扫描讲义页面上的全部文字内容。要求：\n"
    "1. 只输出页面文字本身，不要任何解释、说明、翻译或评论；\n"
    "2. 公式、符号、下标上标保留原样（可用 LaTeX 表示）；\n"
    "3. 表格尽量用文本还原其行列结构；\n"
    "4. 看不清的字用 [?] 标注，绝不猜测编造；\n"
    "5. 保持原有的标题层级、编号、分点结构。"
)

OCR_PROMPT_ROUGH = (
    "请粗略转写这张扫描讲义页面（专项练习/参考答案）的文字，用于判断考点。要求：\n"
    "1. 只输出文字，不要解释；\n"
    "2. 保留题号与知识点关键词、答案解析中点明的易错点/陷阱；\n"
    "3. 无需逐字精确，抓住考点信号即可；看不清用 [?] 标注。"
)


OCR_MIN_CHARS = 30  # 短于此视为失败（思考模型偶尔耗尽预算只吐几字），重试


def ocr_page(png_path: Path, api_key: str, prompt: str, max_tokens: int = 6000) -> tuple[str, dict]:
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # 最多两轮：若首轮输出异常短（多因思考耗尽预算），提高 max_tokens 再来一次
    for attempt in range(2):
        payload["max_tokens"] = max_tokens if attempt == 0 else max_tokens + 4000
        resp = _post_json(OPENAI_ENDPOINT, headers, payload)
        text = resp["choices"][0]["message"]["content"] or ""
        usage = resp.get("usage", {}) or {}
        if len(text.strip()) >= OCR_MIN_CHARS or attempt == 1:
            return text, usage
        print(f"    [OCR过短 {len(text.strip())}字] {png_path.name} 提高预算重试")
    return text, usage


OCR_CACHE_DIR = GUIDE_DIR / "_work" / "ocr-cache"


def ocr_pages(
    pngs: list[Path], api_key: str, prompt: str, label: str, mode: str
) -> tuple[str, dict]:
    """逐页 OCR。已缓存的页直接复用（缓存键含页名+mode），便于中断后续跑、省 token。"""
    OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for i, png in enumerate(pngs, 1):
        cache = OCR_CACHE_DIR / f"{png.stem}-{mode}.txt"
        if cache.exists() and len(cache.read_text(encoding="utf-8").strip()) >= OCR_MIN_CHARS:
            text = cache.read_text(encoding="utf-8")
            print(f"    [{label}] {png.name} ({i}/{len(pngs)})  [缓存复用] chars={len(text)}")
        else:
            t0 = time.time()
            text, usage = ocr_page(png, api_key, prompt)
            dt = time.time() - t0
            for k in total:
                total[k] += int(usage.get(k, 0) or 0)
            print(
                f"    [{label}] {png.name} ({i}/{len(pngs)})  "
                f"{dt:.1f}s  in={usage.get('prompt_tokens', '?')} "
                f"out={usage.get('completion_tokens', '?')}  chars={len(text)}"
            )
            cache.write_text(text, encoding="utf-8")
        parts.append(f"\n\n===== 物理页 {png.stem} =====\n\n{text}")
    return "".join(parts), total


# ---------------------------------------------------------------------------
# 写稿 （glm-5.2）
# ---------------------------------------------------------------------------
def build_writer_prompt(
    subject: str,
    chapter_title: str,
    pdf_name: str,
    kp_range: tuple[int, int],
    kp_ocr: str,
    ex_ocr: str,
    guide_text: str,
) -> str:
    return f"""你是一名资深考试复习资料编纂者。下面提供了「主指导文档」（含三条铁律、六段式模板、保真要求、自检清单），以及某一章讲义的 OCR 转写文本。请严格依据主指导文档，为本章产出一份详尽的复习 cheatsheet。

======== 主指导文档（规范，必须遵守）========
{guide_text}
======== 主指导文档结束 ========

【本章元信息】
- 专题：{subject}
- 章名：{chapter_title}
- 来源 PDF：{pdf_name}
- 知识点物理页范围：[{kp_range[0]}, {kp_range[1]}]

======== 【知识点】OCR 全文（复习资料正文的唯一来源，需完整覆盖）========
{kp_ocr}
======== 知识点 OCR 结束 ========

======== 【专项练习 + 参考答案】OCR（仅作考点信号，用于打 ⭐高频 / ⚠易错 标记，禁止把题目或例题解答抄进正文）========
{ex_ocr}
======== 练习/答案 OCR 结束 ========

【输出要求（务必遵守）】
1. 严格采用主指导文档第 3 节的六段式模板：一、本章概览；二、知识点详解；三、公式/算法/定理速查表；四、重点对比与易混辨析（无则省略）；五、高频考点与易错提醒；六、一句话记忆要点。
2. 遵守三条铁律：保真不改写（公式用 LaTeX、算法/代码用代码块、定义贴原文）；零编造（看不清用 [?] 或 [原文模糊] 标注）；只摘知识点，练习题只做考点信号、不收录题目与解答。
3. 覆盖本章全部知识点，逐个「知识点 N」提取定义/要点/公式/算法/对比。
4. 依据练习与答案信号，在知识点标题后标注 ⭐（高频）或 ⚠（易错）；判断不了就不标。
5. 目标篇幅：详尽复习版，正文约 3 页以上。
6. 顶部按模板写「来源」行：来源：{pdf_name} 物理页 [{kp_range[0]}, {kp_range[1]}]。
7. 直接输出最终 Markdown 正文，不要任何额外说明、前言或“好的”之类的话。

【纪律强化：严防练习内容渗入正文（必须逐条执行）】
A. 第三节「公式/算法/定理速查表」只允许收录在【知识点】OCR 正文里真实出现过的公式/算法/定理；凡是只在【专项练习/参考答案】里出现、需要从题目或答案反推出来的公式，一律禁止进第三节速查表——只能放到第五节，作为考点信号写出，并在其后注明「(练习N，反推)」以示其来源非正文。
B. 第五节「高频考点与易错提醒」采用信号式写法：写成「⚠<考点名>是高频易错点」这种指向式表述，禁止把练习答案里的具体结论抄进来当正文（例如禁止写“某某指令属于特权指令/非特权指令”这类答案结论），除非该结论在【知识点】OCR 正文本身就已出现过；若确实源自练习，只点出考点方向并注明 (练习N)。
C. 第四节对比表：每个单元格的内容都必须能回溯到【知识点】OCR 正文的原话或原意；OCR 正文没有讲到的某项优点/缺点/特征，不得自行补造或凭常识填充，该单元格留空或写「[原文未述]」。
D. 每一处 ⭐/⚠ 标注之后都追加极简来源标记 `(练习N)`（N 为对应练习/题目编号，无法定位具体编号时写 `(练习)`），以便审查一眼区分「正文知识点」与「练习派生考点」。
E.【结论必须有据，严禁臆断】任何一条考点结论，只有在【知识点】OCR 正文、章内答案或（若已提供）书末统一答案里能找到明确依据时，才允许作为事实断言写出；若三者都找不到依据，只能写成纯信号式表述（如「⚠ X 是考点方向/高频易错点」），绝不能臆断该考点的具体结论，更严禁凭常识杜撰或写出「答案指出…」「答案表明…」这类无依据的断言。"""


# 写稿输出预算：glm-5.2 官方最大输出 128K，取 32768 稳妥且足够长章一次写完。
WRITER_MAX_TOKENS = 32768
# finish_reason / stop_reason 表示"被 max_tokens 截断"的取值集合。
_TRUNCATED_FINISH = {"length", "max_tokens"}
# 续写指令：让模型从截断处紧接着写完，禁止重复与前言。
_CONTINUE_INSTRUCTION = (
    "上面的复习资料因长度限制被截断了，尚未写完。请从被截断处紧接着继续写完剩余的全部内容，"
    "直到第六节「六、一句话记忆要点」完整收尾为止。直接接着上次结尾续写即可，"
    "不要重复已经写过的任何内容，不要重新开头，也不要加入任何前言、说明或“好的”之类的话。"
)
# 单章最多续写轮数，防极端情况下无限循环。
_MAX_CONTINUATIONS = 6


def _call_text_openai(
    messages: list[dict], api_key: str, max_tokens: int
) -> tuple[str, dict, str | None]:
    payload = {
        "model": TEXT_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = _post_json(OPENAI_ENDPOINT, headers, payload)
    choice = resp["choices"][0]
    text = choice["message"]["content"] or ""
    finish = choice.get("finish_reason")
    return text, (resp.get("usage", {}) or {}), finish


def _call_text_anthropic(
    messages: list[dict], api_key: str, max_tokens: int
) -> tuple[str, dict, str | None]:
    payload = {
        "model": TEXT_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    resp = _post_json(ANTHROPIC_ENDPOINT, headers, payload)
    blocks = resp.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    u = resp.get("usage", {}) or {}
    usage = {
        "prompt_tokens": u.get("input_tokens", 0),
        "completion_tokens": u.get("output_tokens", 0),
        "total_tokens": (u.get("input_tokens", 0) + u.get("output_tokens", 0)),
    }
    stop = resp.get("stop_reason")
    finish = "length" if stop == "max_tokens" else stop
    return text, usage, finish


def _accumulate(dst: dict, src: dict) -> None:
    for k in dst:
        dst[k] += int(src.get(k, 0) or 0)


def write_cheatsheet(
    prompt: str, api_key: str, max_tokens: int = WRITER_MAX_TOKENS
) -> tuple[str, dict, str]:
    """优先 OpenAI 兼容端点，失败退回 Anthropic 端点。返回 (正文, usage, 使用端点)。

    截断处理：检查 finish_reason / stop_reason，若为 length/max_tokens（被 max_tokens
    截断），自动以"续写"请求（把已产出内容作为 assistant 上文 + 续写指令）继续，
    直至模型正常收尾或达到 _MAX_CONTINUATIONS 轮，最终拼接为完整产物。
    """
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    base_messages = [{"role": "user", "content": prompt}]

    # 首次调用：优先 OpenAI 兼容端点，失败退回 Anthropic，并锁定后续续写用同一端点。
    try:
        text, usage, finish = _call_text_openai(base_messages, api_key, max_tokens)
        if not (text and text.strip()):
            raise RuntimeError("OpenAI 端点返回空内容")
        endpoint, caller = "openai-compatible", _call_text_openai
    except Exception as e:
        print(f"    [写稿] OpenAI 兼容端点失败：{e} — 退回 Anthropic 端点")
        text, usage, finish = _call_text_anthropic(base_messages, api_key, max_tokens)
        endpoint, caller = "anthropic", _call_text_anthropic
    _accumulate(usage_total, usage)

    full = text
    rounds = 0
    while finish in _TRUNCATED_FINISH and rounds < _MAX_CONTINUATIONS:
        rounds += 1
        print(
            f"    [截断检测] finish_reason={finish}，已产出 {len(full)} 字 — "
            f"发起第 {rounds}/{_MAX_CONTINUATIONS} 次续写（端点={endpoint}）"
        )
        cont_messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": full},
            {"role": "user", "content": _CONTINUE_INSTRUCTION},
        ]
        text, usage, finish = caller(cont_messages, api_key, max_tokens)
        _accumulate(usage_total, usage)
        if not (text and text.strip()):
            print("    [续写] 本轮返回空内容，终止续写")
            break
        full += text

    if finish in _TRUNCATED_FINISH:
        print(
            f"    [警告] 续写 {rounds} 轮后 finish_reason 仍为 {finish}，"
            f"产物可能仍不完整（{len(full)} 字）"
        )
    return full, usage_total, endpoint


# ---------------------------------------------------------------------------
# 编排：单章
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChapterResult:
    out_path: Path
    ocr_path: Path
    char_count: int
    elapsed: float
    tokens: dict


def parse_ocr_dump(ocr_p: Path) -> tuple[str, str]:
    """从已有的 OCR 中间产物 md 中切分出 (知识点 OCR, 练习/答案 OCR)。

    用于 --write-only 模式：完全跳过渲染与 OCR，直接复用磁盘上的转写结果，
    保证不触发任何视觉模型调用。
    """
    text = ocr_p.read_text(encoding="utf-8")
    kp_marker = "# ========== 知识点（完整转写） =========="
    ex_marker = "# ========== 专项练习 + 参考答案（粗转写，考点信号） =========="
    if kp_marker not in text or ex_marker not in text:
        raise RuntimeError(f"OCR 中间产物缺少预期分节标记，无法切分：{ocr_p}")
    after_kp = text.split(kp_marker, 1)[1]
    kp_ocr, ex_ocr = after_kp.split(ex_marker, 1)
    return kp_ocr.strip(), ex_ocr.strip()


def run_chapter(
    pdf: str,
    kp_pages: tuple[int, int],
    exercise_pages: tuple[int, int],
    out_path: str,
    subject: str,
    chapter_title: str,
    ocr_dump: str | None = None,
    write_only: bool = False,
) -> ChapterResult:
    api_key = load_api_key()
    guide_text = MAIN_GUIDE.read_text(encoding="utf-8")
    pdf_path = LECTURE_DIR / pdf
    out_p = WORK_DIR / out_path
    out_p.parent.mkdir(parents=True, exist_ok=True)
    ocr_p = Path(ocr_dump) if ocr_dump else (GUIDE_DIR / "_work" / "ocr-dump.md")
    ocr_p.parent.mkdir(parents=True, exist_ok=True)

    grand = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    t_start = time.time()

    # --- write-only：跳过渲染 + OCR，直接复用已有 OCR 中间产物 ---
    if write_only:
        print(f"[write-only] 复用已有 OCR：{ocr_p}（跳过渲染与 OCR，不调用视觉模型）")
        kp_ocr, ex_ocr = parse_ocr_dump(ocr_p)
        print(f"    知识点 OCR {len(kp_ocr)} 字 + 练习 OCR {len(ex_ocr)} 字")

        print(f"[写稿] （{TEXT_MODEL}）...")
        t0 = time.time()
        prompt = build_writer_prompt(
            subject, chapter_title, pdf, kp_pages, kp_ocr, ex_ocr, guide_text
        )
        cheatsheet, u3, endpoint = write_cheatsheet(prompt, api_key)
        for k in grand:
            grand[k] += int(u3.get(k, 0) or 0)
        out_p.write_text(cheatsheet, encoding="utf-8")
        print(
            f"    写稿完成 {time.time() - t0:.1f}s，端点={endpoint}，"
            f"in={u3.get('prompt_tokens', '?')} out={u3.get('completion_tokens', '?')}，"
            f"{len(cheatsheet)} 字，写入 {out_p}"
        )
        return ChapterResult(out_p, ocr_p, len(cheatsheet), time.time() - t_start, grand)

    # --- Step 1: 渲染 ---
    print(f"[1/3] 渲染 {pdf}  知识点页{kp_pages}  练习页{exercise_pages} ...")
    t0 = time.time()
    kp_pngs = render_pages(pdf_path, kp_pages[0], kp_pages[1])
    ex_pngs = render_pages(pdf_path, exercise_pages[0], exercise_pages[1])
    print(f"    渲染完成：知识点 {len(kp_pngs)} 页 + 练习 {len(ex_pngs)} 页，{time.time() - t0:.1f}s")

    # --- Step 2: OCR ---
    print(f"[2/3] OCR （{VISION_MODEL}）...")
    t0 = time.time()
    kp_ocr, u1 = ocr_pages(kp_pngs, api_key, OCR_PROMPT_FULL, "知识点", "full")
    ex_ocr, u2 = ocr_pages(ex_pngs, api_key, OCR_PROMPT_ROUGH, "练习答案", "rough")
    for k in grand:
        grand[k] += u1.get(k, 0) + u2.get(k, 0)
    ocr_full = (
        f"# OCR 中间产物 — {subject} · {chapter_title}\n"
        f"> 来源：{pdf}  知识点页{kp_pages}  练习页{exercise_pages}\n\n"
        f"# ========== 知识点（完整转写） ==========\n{kp_ocr}\n\n"
        f"# ========== 专项练习 + 参考答案（粗转写，考点信号） ==========\n{ex_ocr}\n"
    )
    ocr_p.write_text(ocr_full, encoding="utf-8")
    print(f"    OCR 完成 {time.time() - t0:.1f}s，全文 {len(ocr_full)} 字，存 {ocr_p}")

    # --- Step 3: 写稿 ---
    print(f"[3/3] 写稿 （{TEXT_MODEL}）...")
    t0 = time.time()
    prompt = build_writer_prompt(
        subject, chapter_title, pdf, kp_pages, kp_ocr, ex_ocr, guide_text
    )
    cheatsheet, u3, endpoint = write_cheatsheet(prompt, api_key)
    for k in grand:
        grand[k] += int(u3.get(k, 0) or 0)
    out_p.write_text(cheatsheet, encoding="utf-8")
    print(
        f"    写稿完成 {time.time() - t0:.1f}s，端点={endpoint}，"
        f"in={u3.get('prompt_tokens', '?')} out={u3.get('completion_tokens', '?')}，"
        f"{len(cheatsheet)} 字，写入 {out_p}"
    )

    elapsed = time.time() - t_start
    return ChapterResult(out_p, ocr_p, len(cheatsheet), elapsed, grand)


# ---------------------------------------------------------------------------
# 全书 50 章：整章范围 OCR + 让写稿模型自行区分知识点/练习
# （页码与 复习资料生成指导/01-章节任务表.md 完全一致，已逐行核对）
# ---------------------------------------------------------------------------
def build_writer_prompt_full(
    subject: str,
    chapter_title: str,
    pdf_name: str,
    pages: tuple[int, int],
    chapter_ocr: str,
    guide_text: str,
    answer_note: str = "",
    answer_key: str = "",
) -> str:
    """整章模式写稿 prompt：OCR 全文里同时含『知识点』与『专项练习/答案』，
    由写稿模型依据小标题（知识点 / 专项练习 / 参考答案(及解析) / 习题答案）自行区分。

    answer_key：若提供（计网重生模式），则为书末统一答案全文（题号→答案字母），
    作为课后习题的权威结论来源，用于给第五节考点信号标注正确结论。"""
    answer_block = ""
    if answer_key.strip():
        answer_block = f"""
======== 【书末统一答案】（题号 → 正确答案字母，权威，仅用于给考点标注正确结论）========
说明：本册习题答案统一印在全书末尾，下面是其 OCR 全文（按「第X章」分节，形如「1.C 2.A ...」，个别题带简短解析）。
用法与铁律：
- 仅当你要在第五节点出某道课后习题对应的考点时，才据此答案标注正确结论（例如「⚠ 因特网核心技术是 TCP/IP（练习3，答案 C）」）；
- **严禁编造答案**：凡本答案表里没有列出、或你无法把题号对上的结论，一律不得断言，只能写成纯信号式「X 是考点方向」；
- 答案只服务于第五节的考点信号与结论校正，**不得**把习题题干、选项或答案抄进第二/三/四节正文；
- 若答案与你从题目常识推测的结论冲突，**以本答案表为准**。
--- 书末答案开始 ---
{answer_key}
--- 书末答案结束 ---
"""
    return f"""你是一名资深考试复习资料编纂者。下面提供了「主指导文档」（含三条铁律、六段式模板、保真要求、自检清单），以及某一章讲义**整章**的 OCR 转写文本。请严格依据主指导文档，为本章产出一份详尽的复习 cheatsheet。

======== 主指导文档（规范，必须遵守）========
{guide_text}
======== 主指导文档结束 ========

【本章元信息】
- 专题：{subject}
- 章名：{chapter_title}
- 来源 PDF：{pdf_name}
- 整章物理页范围：[{pages[0]}, {pages[1]}]

======== 【整章 OCR 全文】========
说明：以下 OCR 全文同时包含本章的「知识点」正文与「专项练习 / 参考答案（及解析）/ 习题答案」。
请你依据 OCR 文本里出现的小标题（如「知识点」「专项练习」「参考答案」「答案解析」「习题答案」等）**自行区分**：
- 只把『知识点』部分作为复习资料**正文的唯一来源**，需完整覆盖每一个知识点；
- 『专项练习 / 答案』部分**只作考点信号**，用于打 ⭐高频 / ⚠易错 标记，禁止把题目或例题解答抄进正文。
{answer_note}
--- OCR 全文开始 ---
{chapter_ocr}
--- OCR 全文结束 ---
{answer_block}
【输出要求（务必遵守）】
1. 严格采用主指导文档第 3 节的六段式模板：一、本章概览；二、知识点详解；三、公式/算法/定理速查表；四、重点对比与易混辨析（无则省略）；五、高频考点与易错提醒；六、一句话记忆要点。
2. 遵守三条铁律：保真不改写（公式用 LaTeX、算法/代码用代码块、定义贴原文）；零编造（看不清用 [?] 或 [原文模糊] 标注）；只摘知识点，练习题只做考点信号、不收录题目与解答。
3. 覆盖本章全部知识点，逐个「知识点 N」提取定义/要点/公式/算法/对比。
4. 依据练习与答案信号，在知识点标题后标注 ⭐（高频）或 ⚠（易错）；判断不了就不标。
5. 目标篇幅：详尽复习版，正文约 3 页以上。
6. 顶部按模板写「来源」行：来源：{pdf_name} 物理页 [{pages[0]}, {pages[1]}]。
7. 直接输出最终 Markdown 正文，不要任何额外说明、前言或“好的”之类的话。

【纪律强化：严防练习内容渗入正文（必须逐条执行）】
A. 第三节「公式/算法/定理速查表」只允许收录在【知识点】正文里真实出现过的公式/算法/定理；凡是只在【专项练习/参考答案】里出现、需要从题目或答案反推出来的公式，一律禁止进第三节速查表——只能放到第五节，作为考点信号写出，并在其后注明「(练习N，反推)」以示其来源非正文。
B. 第五节「高频考点与易错提醒」采用信号式写法：写成「⚠<考点名>是高频易错点」这种指向式表述，禁止把练习答案里的具体结论抄进来当正文，除非该结论在【知识点】正文本身就已出现过；若确实源自练习，只点出考点方向并注明 (练习N)。
C. 第四节对比表：每个单元格的内容都必须能回溯到【知识点】正文的原话或原意；正文没有讲到的某项特征，不得自行补造或凭常识填充，该单元格留空或写「[原文未述]」。
D. 每一处 ⭐/⚠ 标注之后都追加极简来源标记 `(练习N)`（N 为对应练习/题目编号，无法定位具体编号时写 `(练习)`），以便审查一眼区分「正文知识点」与「练习派生考点」。
E.【结论必须有据，严禁臆断】任何一条考点结论，只有在【知识点】正文、章内答案或（若已提供）书末统一答案里能找到明确依据时，才允许作为事实断言写出；若三者都找不到依据，只能写成纯信号式表述（如「⚠ X 是考点方向/高频易错点」），绝不能臆断该考点的具体结论，更严禁凭常识杜撰或写出「答案指出…」「答案表明…」这类无依据的断言。"""


@dataclass(frozen=True)
class Chapter:
    subject: str          # 专题名（如「操作系统」）
    pdf: str              # PDF 文件名
    idx: str              # 章号（中文，如「一」）
    title: str            # 章名
    pages: tuple[int, int]  # 整章物理页 [起, 止]
    out_path: str         # 输出相对路径 cheatsheets/<文件夹>/<文件名>


# 与 01-章节任务表.md 完全一致（已逐行核对页码）。
CHAPTERS: list[Chapter] = [
    # ---- 专题 02 操作系统（7 章）----
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "一", "操作系统基础", (3, 22), "cheatsheets/04-操作系统/第01章-操作系统基础.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "二", "进程管理", (23, 45), "cheatsheets/04-操作系统/第02章-进程管理.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "三", "处理机调度", (46, 69), "cheatsheets/04-操作系统/第03章-处理机调度.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "四", "内存管理", (70, 93), "cheatsheets/04-操作系统/第04章-内存管理.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "五", "设备管理", (94, 116), "cheatsheets/04-操作系统/第05章-设备管理.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "六", "文件管理", (117, 139), "cheatsheets/04-操作系统/第06章-文件管理.md"),
    Chapter("操作系统", "4-3-操作系统-讲义.pdf", "七", "操作系统的安全和保护", (140, 163), "cheatsheets/04-操作系统/第07章-操作系统的安全和保护.md"),
    # ---- 专题 03 计算机网络（8 章；答案统一在全书末尾 [151,152]，各章仅用课后习题作信号）----
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "一", "计算机网络概述", (3, 24), "cheatsheets/05-计算机网络/第01章-计算机网络概述.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "二", "物理层", (25, 50), "cheatsheets/05-计算机网络/第02章-物理层.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "三", "数据链路层", (51, 65), "cheatsheets/05-计算机网络/第03章-数据链路层.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "四", "网络层", (66, 89), "cheatsheets/05-计算机网络/第04章-网络层.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "五", "传输层", (90, 107), "cheatsheets/05-计算机网络/第05章-传输层.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "六", "应用层协议", (108, 124), "cheatsheets/05-计算机网络/第06章-应用层协议.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "七", "网络安全", (125, 140), "cheatsheets/05-计算机网络/第07章-网络安全.md"),
    Chapter("计算机网络", "5-5-计算机网络讲义.pdf", "八", "无线通信及组网通用配置", (141, 150), "cheatsheets/05-计算机网络/第08章-无线通信及组网通用配置.md"),
    # ---- 专题 04 软件设计与开发（6 章）----
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "一", "软件工程学概述及软件开发过程管理", (6, 27), "cheatsheets/06-软件设计与开发/第01章-软件工程学概述及软件开发过程管理.md"),
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "二", "可行性及需求分析", (28, 52), "cheatsheets/06-软件设计与开发/第02章-可行性及需求分析.md"),
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "三", "系统设计", (53, 82), "cheatsheets/06-软件设计与开发/第03章-系统设计.md"),
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "四", "系统开发及测试", (83, 112), "cheatsheets/06-软件设计与开发/第04章-系统开发及测试.md"),
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "五", "系统维护", (113, 124), "cheatsheets/06-软件设计与开发/第05章-系统维护.md"),
    Chapter("软件设计与开发", "6-3-软件设计与开发计算机类讲义.pdf", "六", "软件项目管理", (125, 146), "cheatsheets/06-软件设计与开发/第06章-软件项目管理.md"),
    # ---- 专题 05 数据结构（9 章）----
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "一", "数据结构基本概念与算法评价", (3, 17), "cheatsheets/07-数据结构/第01章-数据结构基本概念与算法评价.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "二", "线性表", (18, 34), "cheatsheets/07-数据结构/第02章-线性表.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "三", "栈和队列", (35, 46), "cheatsheets/07-数据结构/第03章-栈和队列.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "四", "数组与矩阵的压缩存储", (47, 57), "cheatsheets/07-数据结构/第04章-数组与矩阵的压缩存储.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "五", "树和二叉树", (58, 73), "cheatsheets/07-数据结构/第05章-树和二叉树.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "六", "图", (74, 87), "cheatsheets/07-数据结构/第06章-图.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "七", "查找", (88, 100), "cheatsheets/07-数据结构/第07章-查找.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "八", "内部排序", (101, 112), "cheatsheets/07-数据结构/第08章-内部排序.md"),
    Chapter("数据结构", "7-3-数据结构计算机类讲义.pdf", "九", "算法设计与分析", (113, 120), "cheatsheets/07-数据结构/第09章-算法设计与分析.md"),
    # ---- 专题 06 数据库（10 章）----
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "一", "数据库基本概念", (3, 13), "cheatsheets/08-数据库/第01章-数据库基本概念.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "二", "关系数据库", (14, 22), "cheatsheets/08-数据库/第02章-关系数据库.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "三", "关系数据理论", (23, 32), "cheatsheets/08-数据库/第03章-关系数据理论.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "四", "关系数据库标准语言SQL", (33, 46), "cheatsheets/08-数据库/第04章-关系数据库标准语言SQL.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "五", "关系查询处理和查询优化", (47, 55), "cheatsheets/08-数据库/第05章-关系查询处理和查询优化.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "六", "数据库安全性", (56, 67), "cheatsheets/08-数据库/第06章-数据库安全性.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "七", "数据库完整性", (68, 76), "cheatsheets/08-数据库/第07章-数据库完整性.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "八", "数据库恢复技术", (77, 87), "cheatsheets/08-数据库/第08章-数据库恢复技术.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "九", "并发控制", (88, 98), "cheatsheets/08-数据库/第09章-并发控制.md"),
    Chapter("数据库", "8-3-数据库计算机类讲义.pdf", "十", "关系数据库设计理论", (99, 110), "cheatsheets/08-数据库/第10章-关系数据库设计理论.md"),
    # ---- 专题 07 计算机组成（7 章）----
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "一", "计算机系统概述", (3, 17), "cheatsheets/02-计算机组成/第01章-计算机系统概述.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "二", "数据的机器级表示与运算", (18, 35), "cheatsheets/02-计算机组成/第02章-数据的机器级表示与运算.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "三", "指令系统", (36, 48), "cheatsheets/02-计算机组成/第03章-指令系统.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "四", "中央处理器", (49, 64), "cheatsheets/02-计算机组成/第04章-中央处理器.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "五", "存储器分层体系结构", (65, 79), "cheatsheets/02-计算机组成/第05章-存储器分层体系结构.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "六", "互连与输入输出系统", (80, 103), "cheatsheets/02-计算机组成/第06章-互连与输入输出系统.md"),
    Chapter("计算机组成", "2-3-计算机组成计算机类讲义.pdf", "七", "并行处理系统", (104, 121), "cheatsheets/02-计算机组成/第07章-并行处理系统.md"),
    # ---- 专题 08 信息技术（3 章）----
    Chapter("信息技术", "3-2-信息技术计算机类讲义.pdf", "一", "物联网基础", (3, 17), "cheatsheets/03-信息技术/第01章-物联网基础.md"),
    Chapter("信息技术", "3-2-信息技术计算机类讲义.pdf", "二", "大数据基础", (18, 43), "cheatsheets/03-信息技术/第02章-大数据基础.md"),
    Chapter("信息技术", "3-2-信息技术计算机类讲义.pdf", "三", "人工智能基础", (44, 57), "cheatsheets/03-信息技术/第03章-人工智能基础.md"),
]

PROGRESS_FILE = WORK_DIR / "cheatsheets" / "_progress.md"


def _log_progress(line: str) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PROGRESS_FILE.exists():
        PROGRESS_FILE.write_text(
            "# 量产进度\n\n"
            "> 每章 START/DONE/FAILED 各记一行。\n"
            "> 已完成章数： `grep -c ' DONE ' cheatsheets/_progress.md`\n\n",
            encoding="utf-8",
        )
    with PROGRESS_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_chapter_full(
    ch: Chapter, api_key: str, guide_text: str, answer_key: str = ""
) -> ChapterResult:
    """整章模式：渲染 [start,end] 全部页 → 整章 full OCR → 写稿模型自行区分知识点/练习。

    answer_key：计网重生模式下传入书末统一答案全文，用于给第五节考点信号标注正确结论。"""
    pdf_path = LECTURE_DIR / ch.pdf
    out_p = WORK_DIR / ch.out_path
    out_p.parent.mkdir(parents=True, exist_ok=True)
    pdf_id = Path(ch.pdf).stem
    ocr_p = GUIDE_DIR / "_work" / f"ocr-{pdf_id}-p{ch.pages[0]:03d}-{ch.pages[1]:03d}.md"

    grand = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    t_start = time.time()

    # Step 1: 渲染整章
    print(f"[1/3] 渲染 {ch.pdf}  整章页{ch.pages} ...")
    pngs = render_pages(pdf_path, ch.pages[0], ch.pages[1], pdf_id=pdf_id)
    print(f"    渲染完成：{len(pngs)} 页")

    # Step 2: 整章 full OCR（含知识点 + 练习/答案）
    print(f"[2/3] OCR （{VISION_MODEL}）整章 {len(pngs)} 页 ...")
    t0 = time.time()
    ocr_text, u1 = ocr_pages(pngs, api_key, OCR_PROMPT_FULL, "整章", "full")
    for k in grand:
        grand[k] += int(u1.get(k, 0) or 0)
    ocr_full = (
        f"# OCR 中间产物 — {ch.subject} · 第 {ch.idx} 章 {ch.title}\n"
        f"> 来源：{ch.pdf}  整章物理页{ch.pages}\n\n"
        f"# ========== 整章完整转写（含知识点 + 专项练习/答案） ==========\n{ocr_text}\n"
    )
    ocr_p.write_text(ocr_full, encoding="utf-8")
    print(f"    OCR 完成 {time.time() - t0:.1f}s，全文 {len(ocr_full)} 字，存 {ocr_p}")

    # Step 3: 写稿
    print(f"[3/3] 写稿 （{TEXT_MODEL}）...")
    t0 = time.time()
    answer_note = ""
    if ch.subject == "计算机网络":
        if answer_key.strip():
            answer_note = (
                "注意：本册习题答案统一印在全书末尾，已在下方【书末统一答案】区块单独提供。"
                "请据该权威答案给第五节课后习题考点标注正确结论；严禁编造答案里没有的结论。\n"
            )
        else:
            answer_note = (
                "注意：本册答案统一在全书末尾（不在本章范围内）。若本章 OCR 内没有答案文本，"
                "就仅用课后习题作为考点信号，不要回溯末尾答案，也不要编造答案结论。\n"
            )
    prompt = build_writer_prompt_full(
        ch.subject, ch.title, ch.pdf, ch.pages, ocr_text, guide_text, answer_note, answer_key
    )
    cheatsheet, u3, endpoint = write_cheatsheet(prompt, api_key)
    for k in grand:
        grand[k] += int(u3.get(k, 0) or 0)
    out_p.write_text(cheatsheet, encoding="utf-8")
    print(
        f"    写稿完成 {time.time() - t0:.1f}s，端点={endpoint}，"
        f"in={u3.get('prompt_tokens', '?')} out={u3.get('completion_tokens', '?')}，"
        f"{len(cheatsheet)} 字，写入 {out_p}"
    )
    return ChapterResult(out_p, ocr_p, len(cheatsheet), time.time() - t_start, grand)


# ---------------------------------------------------------------------------
# 计网重生（netfix）：独立进度文件、强制覆盖 8 章、喂书末答案
# ---------------------------------------------------------------------------
NETFIX_PROGRESS_FILE = WORK_DIR / "cheatsheets" / "_progress-netfix.md"
NETFIX_ANSWER_FILE = (
    GUIDE_DIR / "_work" / "ocr-5-5-计算机网络讲义-答案-p149-152.md"
)


def _log_netfix(line: str) -> None:
    """独立进度文件，避免与主量产进程交错写入 _progress.md。"""
    NETFIX_PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not NETFIX_PROGRESS_FILE.exists():
        NETFIX_PROGRESS_FILE.write_text(
            "# 计网重生（netfix）进度\n\n"
            "> 独立于主量产进程；强制覆盖计网 8 章，喂入书末统一答案。\n"
            "> 每章 START/DONE/FAILED 各记一行。\n\n",
            encoding="utf-8",
        )
    with NETFIX_PROGRESS_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_netfix_answer() -> str:
    """载入书末统一答案全文（题号→答案字母）。缺失即报错，避免重生时无据可依。"""
    if not NETFIX_ANSWER_FILE.exists():
        raise RuntimeError(f"书末答案文件不存在：{NETFIX_ANSWER_FILE}")
    text = NETFIX_ANSWER_FILE.read_text(encoding="utf-8").strip()
    if len(text) < OCR_MIN_CHARS:
        raise RuntimeError(f"书末答案文件内容异常短：{NETFIX_ANSWER_FILE}")
    return text


def run_netfix() -> None:
    """重生计算机网络 8 章：强制覆盖已存在文件，并把书末统一答案作为上下文喂给写稿模型。"""
    api_key = load_api_key()
    guide_text = MAIN_GUIDE.read_text(encoding="utf-8")
    answer_key = load_netfix_answer()
    chapters = [c for c in CHAPTERS if c.subject == "计算机网络"]
    total = len(chapters)
    done = failed = 0
    _log_netfix(
        f"\n===== 计网重生启动 {_ts()}  共 {total} 章  "
        f"书末答案 {len(answer_key)} 字（强制覆盖）====="
    )
    print(f"[netfix] 书末答案已载入 {len(answer_key)} 字，将喂给写稿模型")
    for n, ch in enumerate(chapters, 1):
        tag = f"{ch.subject}·第{ch.idx}章 {ch.title}"
        print(f"\n========== [netfix {n}/{total}] {tag} 页{ch.pages}（强制覆盖）==========")
        _log_netfix(f"| {ch.subject} | 第{ch.idx}章 {ch.title} | START 页{ch.pages} | - | - | - | {_ts()} |")
        try:
            res = run_chapter_full(ch, api_key, guide_text, answer_key=answer_key)
            done += 1
            _log_netfix(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | DONE | "
                f"{res.elapsed:.0f}s | tok={res.tokens['total_tokens']} | {res.char_count}字 | {_ts()} |"
            )
        except Exception as e:  # 单章异常不中断整批
            failed += 1
            import traceback
            traceback.print_exc()
            _log_netfix(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | FAILED {type(e).__name__}: {str(e)[:120]} | - | - | - | {_ts()} |"
            )
            print(f"    [FAILED] {tag}: {e} — 继续下一章")
    _log_netfix(f"===== 计网重生结束 {_ts()}  DONE={done} FAILED={failed} / {total} =====")
    print(f"\n计网重生结束：DONE={done} FAILED={failed} / {total}")


def run_all() -> None:
    api_key = load_api_key()
    guide_text = MAIN_GUIDE.read_text(encoding="utf-8")
    total = len(CHAPTERS)
    done = skipped = failed = 0
    _log_progress(f"\n===== 批次启动 {_ts()}  共 {total} 章 =====")
    for n, ch in enumerate(CHAPTERS, 1):
        tag = f"{ch.subject}·第{ch.idx}章 {ch.title}"
        out_p = WORK_DIR / ch.out_path
        if out_p.exists():
            skipped += 1
            print(f"\n[{n}/{total}] 跳过（已存在）：{tag}")
            _log_progress(f"| {ch.subject} | 第{ch.idx}章 {ch.title} | SKIP 已存在 | - | - | - | {_ts()} |")
            continue
        print(f"\n========== [{n}/{total}] {tag} 页{ch.pages} ==========")
        _log_progress(f"| {ch.subject} | 第{ch.idx}章 {ch.title} | START 页{ch.pages} | - | - | - | {_ts()} |")
        try:
            res = run_chapter_full(ch, api_key, guide_text)
            done += 1
            _log_progress(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | DONE | "
                f"{res.elapsed:.0f}s | tok={res.tokens['total_tokens']} | {res.char_count}字 | {_ts()} |"
            )
        except Exception as e:  # 单章异常不中断整批
            failed += 1
            import traceback
            traceback.print_exc()
            _log_progress(
                f"| {ch.subject} | 第{ch.idx}章 {ch.title} | FAILED {type(e).__name__}: {str(e)[:120]} | - | - | - | {_ts()} |"
            )
            print(f"    [FAILED] {tag}: {e} — 继续下一章")
    _log_progress(
        f"===== 批次结束 {_ts()}  DONE={done} SKIP={skipped} FAILED={failed} / {total} ====="
    )
    print(f"\n批次结束：DONE={done} SKIP={skipped} FAILED={failed} / {total}")


# ---------------------------------------------------------------------------
# 入口：--all 量产全书；否则跑操作系统第 1 章原型（保留）
# ---------------------------------------------------------------------------
def main() -> None:
    import sys

    if "--netfix" in sys.argv:
        run_netfix()
        return

    if "--all" in sys.argv:
        run_all()
        return

    write_only = "--write-only" in sys.argv
    res = run_chapter(
        pdf="4-3-操作系统-讲义.pdf",
        kp_pages=(3, 11),
        exercise_pages=(12, 22),
        out_path="cheatsheets/04-操作系统/第01章-操作系统基础.md",
        subject="操作系统",
        chapter_title="操作系统基础",
        ocr_dump=str(GUIDE_DIR / "_work" / "os-ch01-ocr.md"),
        write_only=write_only,
    )
    print("\n================ 汇总 ================")
    print(f"cheatsheet : {res.out_path}  ({res.char_count} 字)")
    print(f"OCR 中间件 : {res.ocr_path}")
    print(f"总耗时     : {res.elapsed:.1f}s")
    print(
        f"总 token   : in={res.tokens['prompt_tokens']} "
        f"out={res.tokens['completion_tokens']} "
        f"total={res.tokens['total_tokens']}"
    )


if __name__ == "__main__":
    main()
