#!/usr/bin/env python3
"""
游戏大站 Sitemap 监控脚本
监控 CrazyGames 等游戏站点的 sitemap 更新，提取新增 URL 和关键词
"""

import os
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, unquote

# ── 配置 ──────────────────────────────────────────────
TARGETS = [
    {
        "name": "CrazyGames",
        "sitemap": "https://www.crazygames.com/sitemap.xml",
    },
    {
        "name": "Miniclip",
        "sitemap": "https://www.miniclip.com/sitemap.xml",
    },
    {
        "name": "Poki",
        "sitemap": "https://poki.com/sitemap.xml",
    },
]

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "state", "sitemap_snapshots")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SitemapMonitorBot/1.0)"
}
REQUEST_TIMEOUT = 20


# ── 工具函数 ──────────────────────────────────────────
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def snapshot_path(name: str) -> str:
    safe = name.lower().replace(" ", "_")
    return os.path.join(SNAPSHOT_DIR, f"{safe}.json")


def load_snapshot(name: str) -> dict:
    path = snapshot_path(name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(name: str, data: dict):
    ensure_dir(SNAPSHOT_DIR)
    with open(snapshot_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_sitemap(url: str) -> list[dict]:
    """获取 sitemap，自动处理 sitemap index（多级 sitemap）"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [错误] 请求失败: {e}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  [错误] XML 解析失败: {e}")
        return []

    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    tag = lambda t: f"{{{ns}}}{t}" if ns else t

    # sitemap index → 递归抓取子 sitemap
    if root.tag == tag("sitemapindex"):
        urls = []
        children = root.findall(tag("sitemap"))
        print(f"  sitemap index，共 {len(children)} 个子 sitemap，抓取前 5 个...")
        for sm in children[:5]:
            loc = sm.findtext(tag("loc"), "").strip()
            if loc:
                urls.extend(fetch_sitemap(loc))
                time.sleep(0.5)
        return urls

    # 普通 urlset
    entries = []
    for url_el in root.findall(tag("url")):
        loc = url_el.findtext(tag("loc"), "").strip()
        lastmod = url_el.findtext(tag("lastmod"), "").strip()
        if loc:
            entries.append({"url": loc, "lastmod": lastmod})
    return entries


def extract_keyword(url: str) -> str:
    """从 URL 路径提取关键词（游戏名）"""
    path = urlparse(url).path
    # 取最后一段有意义的路径片段
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return ""
    slug = parts[-1]
    # slug 转可读关键词
    keyword = unquote(slug).replace("-", " ").replace("_", " ").strip()
    return keyword


def diff_urls(old: dict, new: list[dict]) -> dict:
    """比较新旧快照，返回新增 / 更新 / 消失的 URL"""
    new_map = {e["url"]: e["lastmod"] for e in new}
    old_map = old

    added = {u: lm for u, lm in new_map.items() if u not in old_map}
    updated = {
        u: lm
        for u, lm in new_map.items()
        if u in old_map and lm and lm != old_map[u]
    }
    removed = {u: lm for u, lm in old_map.items() if u not in new_map}

    return {"added": added, "updated": updated, "removed": removed}


def print_section(title: str, items: dict, limit: int = 20):
    if not items:
        return
    print(f"\n  [{title}] {len(items)} 条" + ("（仅展示前 " + str(limit) + " 条）" if len(items) > limit else ""))
    for i, (url, lm) in enumerate(list(items.items())[:limit]):
        kw = extract_keyword(url)
        print(f"    {i+1:3}. {kw:<35} | {lm or '—':12} | {url}")


# ── 主逻辑 ────────────────────────────────────────────
def monitor_once():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  Sitemap 监控运行时间: {now}")
    print(f"{'='*60}")

    all_new_keywords = []

    for target in TARGETS:
        name = target["name"]
        sitemap_url = target["sitemap"]
        print(f"\n>> {name}")
        print(f"   {sitemap_url}")

        entries = fetch_sitemap(sitemap_url)
        if not entries:
            print("  未获取到任何 URL，跳过。")
            continue

        print(f"  共 {len(entries)} 个 URL")

        old_snapshot = load_snapshot(name)
        diff = diff_urls(old_snapshot, entries)

        print_section("新增", diff["added"])
        print_section("更新", diff["updated"])
        print_section("消失", diff["removed"], limit=10)

        # 收集新增关键词
        for url in diff["added"]:
            kw = extract_keyword(url)
            if kw:
                all_new_keywords.append({"site": name, "keyword": kw, "url": url})

        # 更新快照
        new_snapshot = {e["url"]: e["lastmod"] for e in entries}
        save_snapshot(name, new_snapshot)

    # 汇总新关键词
    if all_new_keywords:
        print(f"\n{'─'*60}")
        print(f"  本次新增关键词汇总（共 {len(all_new_keywords)} 个）")
        print(f"{'─'*60}")
        for item in all_new_keywords[:50]:
            print(f"  [{item['site']}] {item['keyword']}")

        # 保存到文件
        output_file = os.path.join(SNAPSHOT_DIR, "new_keywords.jsonl")
        with open(output_file, "a", encoding="utf-8") as f:
            for item in all_new_keywords:
                item["date"] = datetime.now().strftime("%Y-%m-%d")
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"\n  关键词已追加到: {output_file}")
    else:
        print("\n  本次无新增关键词。")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="游戏站 Sitemap 监控")
    parser.add_argument("--loop", type=int, default=0,
                        help="循环间隔（秒），0 = 只运行一次")
    parser.add_argument("--reset", action="store_true",
                        help="清空所有快照，重新开始")
    args = parser.parse_args()

    if args.reset:
        import shutil
        if os.path.exists(SNAPSHOT_DIR):
            shutil.rmtree(SNAPSHOT_DIR)
            print("快照已清空。")

    if args.loop > 0:
        print(f"循环模式，每 {args.loop} 秒运行一次，Ctrl+C 停止。")
        while True:
            monitor_once()
            print(f"\n等待 {args.loop} 秒后再次运行...")
            time.sleep(args.loop)
    else:
        monitor_once()


if __name__ == "__main__":
    main()
