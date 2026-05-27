#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run stock_monitor.py and push non-empty results to Feishu."""
import json
import os
import subprocess
import sys
import urllib.request


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = "/home/oclaw/.openclaw/openclaw.json"
RECEIVE_ID = "ou_f8e1b9d4daf33cc7a719b695861f5cb3"
SUPPRESS = {"", "NON_TRADING", "NO_ALERT", "FETCH_FAILED", "NO_REPLY"}


def load_feishu_app():
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    feishu = cfg["channels"]["feishu"]
    return feishu["appId"], feishu["appSecret"]


def post_json(url, payload, headers=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tenant_access_token():
    app_id, app_secret = load_feishu_app()
    res = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    if res.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {res}")
    return res["tenant_access_token"]


def send_feishu(text):
    token = tenant_access_token()
    res = post_json(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        {
            "receive_id": RECEIVE_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        {"Authorization": f"Bearer {token}"},
    )
    if res.get("code") != 0:
        raise RuntimeError(f"send message failed: {res}")


def main():
    args = [sys.executable, os.path.join(ROOT, "stock_monitor.py"), *sys.argv[1:]]
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"stock_monitor exited {result.returncode}")
    text = result.stdout.strip()
    if text in SUPPRESS:
        return
    send_feishu(text)


if __name__ == "__main__":
    main()
