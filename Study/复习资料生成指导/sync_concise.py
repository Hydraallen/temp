#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 *-expanded.md 重生对应的 *.md（concise 版）。

concise = expanded 去掉所有 `*(...)*` 斜体出处引用（保留其它斜体如 *Caveat*、*Tags:*）。
用于子 agent 手工补写 expanded 后，保持 concise/expanded 零漂移。

用法：
  python sync_concise.py <expanded.md>            # 写入同名 concise（去 -expanded）
  python sync_concise.py <expanded.md> --check    # 只比对，不写
"""
from __future__ import annotations

import argparse
import re
import sys
import pathlib

# 仅匹配真正的「来源引用」：`*(讲义 pXXX)*` / `*(题目XX)*`。
# 不误伤 *Caveat* / *Tags: a, b*（无外层括号），也不误伤描述性 `*(来自 exam-signals 候选 N)*`。
# 注意：题号类引用（如 `*(第五章-单选-8)*`）在原 pipeline 里来自 HTML 注释转换，
# 落盘后无法与描述性斜体区分，故保守地只剥「讲义/题目」前缀——与子 agent 约定
# 新增引用统一用 `*(讲义 pXX)*` / `*(题目XX)*` 形式，确保可被正确剥离。
_SRC_ITALIC_RE = re.compile(r"\*\((?:讲义|题目)[^)\n]*\)\*")


def strip_italic_refs(expanded_md: str) -> str:
    out = _SRC_ITALIC_RE.sub("", expanded_md)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{4,}", "\n\n\n", out)
    return out


def concise_path(expanded: pathlib.Path) -> pathlib.Path:
    name = expanded.name
    assert name.endswith("-expanded.md"), f"unexpected file: {name}"
    return expanded.with_name(name[: -len("-expanded.md")] + ".md")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("expanded", type=pathlib.Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    exp = args.expanded.read_text(encoding="utf-8")
    new_concise = strip_italic_refs(exp)
    target = concise_path(args.expanded)

    if args.check:
        cur = target.read_text(encoding="utf-8") if target.exists() else ""
        if cur == new_concise:
            print(f"[OK] {target.name} 已同步")
            return 0
        import difflib
        diff = list(difflib.unified_diff(
            cur.splitlines(keepends=True),
            new_concise.splitlines(keepends=True),
            fromfile=str(target), tofile="<expected>",
            lineterm="",
        ))
        print(f"[DRIFT] {target.name} 与期望差 {len(diff)} 行")
        for line in diff[:40]:
            sys.stdout.write(line if line.endswith("\n") else line + "\n")
        return 1

    target.write_text(new_concise, encoding="utf-8")
    print(f"[WRITE] {target.name}  {len(new_concise)} 字符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
