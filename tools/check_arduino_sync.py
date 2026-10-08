#!/usr/bin/env python3
"""
check_arduino_sync.py — 检测开发副本与分发副本是否已经分叉

## 为什么需要它

Arduino 库必须发布在【独立仓库】（因为 Library Manager 要求 library.properties 在仓库根，
而本仓库是 monorepo）。于是同一个头文件存在两份：

    开发副本：erdilrf-drivers/arduino/src/ERDILRF_LRF.h
    分发副本：erdilrf-lrf-arduino/src/ERDILRF_LRF.h   ← Arduino Library Manager 索引的就是它

两份【手工】保持同步。**手工同步必然漂移** —— 而这正是本项目反复在打的那类失败：
静默不一致。测试里我已经修过一次同型问题（头文件移动后 6 个守卫静默 skip），
所以这里不重蹈覆辙：把不可见的漂移变成一条会响的检查。

## 用法

    python tools/check_arduino_sync.py            # 退出码 0 一致 / 1 已分叉 / 2 无法检查
    python tools/check_arduino_sync.py --diff     # 分叉时额外打印首个不同之处

## 设计取舍

* 需要网络（读分发仓库）。因此**不做成 pytest 测试** —— 测试套件应当离线可跑，
  用 skip 处理网络问题会重新引入「静默脱岗」的反模式。
* 只比较**内容哈希**，不比较 git 历史：两份副本的提交历史本就应该不同。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Windows 的中文控制台默认用 GBK 编码。本脚本输出 ✓ / ✗，在 GBK 下会抛
#   UnicodeEncodeError: 'gbk' codec can't encode character '\u2713'
# 并让**整个检查崩掉** —— 一个检查器因为自己的输出编码而失败，是最没价值的失败。
# 这里把标准输出/错误流强制为 UTF-8（errors=replace 保证再也不会因此中断）。
# 实测踩到：在未设 PYTHONIOENCODING 的中文 Windows 上运行即崩。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 旧解释器或已被重定向时忽略
        pass


DEV_HEADER = Path(__file__).resolve().parent.parent / "arduino" / "src" / "ERDILRF_LRF.h"
DEV_EXAMPLE = (Path(__file__).resolve().parent.parent / "arduino" / "examples"
               / "BasicRanging" / "BasicRanging.ino")

DIST_REPO = "erdilrf/erdilrf-lrf-arduino"
DIST_REF = "main"
PAIRS = [("src/ERDILRF_LRF.h", DEV_HEADER),
         ("examples/BasicRanging/BasicRanging.ino", DEV_EXAMPLE)]


def token() -> str | None:
    for p in (Path.home() / ".erdi" / "github_token",
              Path.home() / ".gtm-workbench" / "github_token"):
        if p.exists():
            return p.read_text().strip()
    return os.environ.get("GITHUB_TOKEN")


def fetch_dist(path: str) -> tuple[int, str]:
    t = token()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "erdi-sync-check"}
    if t:
        headers["Authorization"] = "token " + t
    url = f"https://api.github.com/repos/{DIST_REPO}/contents/{path}?ref={DIST_REF}"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
        d = json.loads(r.read().decode())
        return 200, base64.b64decode(d["content"]).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, f"__ERR_{type(e).__name__}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(prog="check_arduino_sync",
                                 description="检测 Arduino 库开发副本与分发副本是否分叉")
    ap.add_argument("--diff", action="store_true", help="分叉时打印首个不同之处")
    args = ap.parse_args()

    drift = 0
    unknown = 0
    for dist_path, dev_path in PAIRS:
        if not dev_path.exists():
            print(f"✗ 开发副本缺失: {dev_path}")
            drift += 1
            continue
        dev = dev_path.read_text(encoding="utf-8")
        st, dist = fetch_dist(dist_path)
        if st != 200:
            print(f"? {dist_path}: 无法读取分发副本（HTTP {st} {dist[:60]}）—— 未做比较")
            unknown += 1
            continue
        if sha(dev) == sha(dist):
            print(f"✓ {dist_path}: 一致  sha={sha(dev)[:12]}  ({len(dev)} 字符)")
            continue
        drift += 1
        print(f"✗ {dist_path}: **已分叉**")
        print(f"    开发副本 sha={sha(dev)[:12]}  {len(dev)} 字符")
        print(f"    分发副本 sha={sha(dist)[:12]}  {len(dist)} 字符")
        if args.diff:
            dl, sl = dev.splitlines(), dist.splitlines()
            for i in range(max(len(dl), len(sl))):
                a = dl[i] if i < len(dl) else "<EOF>"
                b = sl[i] if i < len(sl) else "<EOF>"
                if a != b:
                    print(f"    首个差异 L{i+1}:")
                    print(f"      开发: {a[:120]}")
                    print(f"      分发: {b[:120]}")
                    break

    print()
    if drift:
        print(f"结果: {drift} 个文件已分叉 -> 把开发副本同步到分发仓库后重新发布")
        return 1
    if unknown:
        print(f"结果: 无分叉，但 {unknown} 个文件未做比较（见上）")
        return 2
    print("结果: 全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
