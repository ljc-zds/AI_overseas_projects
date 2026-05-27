#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股定时播报脚本：拉取指定股票实时行情，交易时段输出格式化播报。
非交易时段输出 NON_TRADING，供调度方判断是否推送。
数据源：腾讯免费行情 qt.gtimg.cn（GBK 编码）。
"""
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone, timedelta

# 监控标的（前缀 sz=深市, sh=沪市）
CODES = ["sz002155", "sz002716", "sh600111", "sh600584"]
CST = timezone(timedelta(hours=8))  # 北京时间
ALERT_PCT = 5.0  # 单日涨跌幅预警阈值（%）
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".stock_alert_state.json")


def in_trading_session(now):
    """A股交易时段：周一至周五 09:30-11:30, 13:00-15:00。"""
    if now.weekday() >= 5:  # 周六周日
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 30 <= t <= 11 * 60 + 30) or (13 * 60 <= t <= 15 * 60)


def fetch():
    url = "http://qt.gtimg.cn/q=" + ",".join(CODES)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", "ignore")
    rows = []
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        body = line.split("=", 1)[1].strip().strip('"')
        f = body.split("~")
        if len(f) < 35 or not f[3]:
            continue
        rows.append({
            "name": f[1],
            "code": f[2],
            "price": float(f[3]),
            "prev": float(f[4]),
            "open": float(f[5]),
            "change": float(f[31]),
            "pct": float(f[32]),
            "high": float(f[33]),
            "low": float(f[34]),
        })
    return rows


def load_state(today):
    """读取当天预警状态；跨天自动重置。"""
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            st = json.load(fh)
        if st.get("date") == today:
            return st
    except (OSError, ValueError):
        pass
    return {"date": today, "alerted": {}}


def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(st, fh, ensure_ascii=False)
    except OSError:
        pass


def alert_mode(now):
    """高频轮询：单日涨跌幅首次触及 ±阈值时推送，同票同方向当天只推一次。"""
    if not in_trading_session(now):
        print("NON_TRADING")
        return
    rows = fetch()
    if not rows:
        print("FETCH_FAILED")
        return
    today = now.strftime("%Y-%m-%d")
    st = load_state(today)
    fired = []
    for r in rows:
        direction = "up" if r["pct"] >= ALERT_PCT else ("down" if r["pct"] <= -ALERT_PCT else None)
        if direction and st["alerted"].get(r["code"]) != direction:
            st["alerted"][r["code"]] = direction
            mark = "🚨涨" if direction == "up" else "🚨跌"
            sign = "+" if r["change"] >= 0 else ""
            fired.append(
                f"{mark} {r['name']}({r['code']}) {r['price']:.2f}  "
                f"{sign}{r['pct']:.2f}%（触及±{ALERT_PCT:.0f}%）"
            )
    save_state(st)
    if fired:
        print(f"⚠️ 涨跌幅预警 {now.strftime('%m-%d %H:%M')}\n" + "\n".join(fired))
    else:
        print("NO_ALERT")


def summary_mode(now, kind):
    """开盘/收盘总结。kind 为 'open' 或 'close'。仅工作日运行。"""
    if now.weekday() >= 5:
        print("NON_TRADING")
        return
    rows = fetch()
    if not rows:
        print("FETCH_FAILED")
        return
    if kind == "open":
        header = f"🔔 开盘总结 {now.strftime('%m-%d %H:%M')}"
        lines = [header]
        for r in rows:
            gap = (r["open"] - r["prev"]) / r["prev"] * 100 if r["prev"] else 0.0
            tag = "高开" if gap > 0 else ("低开" if gap < 0 else "平开")
            sign = "+" if gap >= 0 else ""
            lines.append(
                f"{tag} {r['name']}({r['code']}) 开{r['open']:.2f} "
                f"昨收{r['prev']:.2f}（{sign}{gap:.2f}%）现价{r['price']:.2f}"
            )
    else:  # close
        header = f"🔚 收盘总结 {now.strftime('%m-%d %H:%M')}"
        lines = [header]
        for r in rows:
            arrow = "🔴" if r["pct"] > 0 else ("🟢" if r["pct"] < 0 else "⚪")
            sign = "+" if r["change"] >= 0 else ""
            amp = (r["high"] - r["low"]) / r["prev"] * 100 if r["prev"] else 0.0
            lines.append(
                f"{arrow} {r['name']}({r['code']}) 收{r['price']:.2f} "
                f"{sign}{r['change']:.2f}({sign}{r['pct']:.2f}%) 振幅{amp:.2f}% "
                f"高{r['high']:.2f}/低{r['low']:.2f}"
            )
    print("\n".join(lines))


def main():
    now = datetime.now(CST)
    if not in_trading_session(now):
        print("NON_TRADING")
        return
    rows = fetch()
    if not rows:
        print("FETCH_FAILED")
        return
    lines = [f"📊 A股播报 {now.strftime('%m-%d %H:%M')}"]
    for r in rows:
        arrow = "🔴" if r["pct"] > 0 else ("🟢" if r["pct"] < 0 else "⚪")
        sign = "+" if r["change"] >= 0 else ""
        lines.append(
            f"{arrow} {r['name']}({r['code']}) {r['price']:.2f}  "
            f"{sign}{r['change']:.2f} ({sign}{r['pct']:.2f}%)  "
            f"高{r['high']:.2f}/低{r['low']:.2f}"
        )
    print("\n".join(lines))


if __name__ == "__main__":
    if "--alert" in sys.argv:
        alert_mode(datetime.now(CST))
    elif "--summary" in sys.argv:
        i = sys.argv.index("--summary")
        kind = sys.argv[i + 1] if i + 1 < len(sys.argv) else "close"
        summary_mode(datetime.now(CST), kind)
    else:
        main()
