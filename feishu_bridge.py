#!/usr/bin/env python3
"""
Feishu ↔ AI Bridge
Listens for IM messages via lark-cli WebSocket, replies via DeepSeek API.

Usage:
    python feishu_bridge.py

Requires:
    lark-cli (npm install -g @larksuite/cli)
    ANTHROPIC_BASE_URL, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_MODEL env vars
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# lark-cli path (npm global)
def _find_lark_cli():
    """Find lark-cli executable."""
    for path in [
        os.environ.get("LARK_CLI_PATH", ""),
        "/c/Program Files/nodejs/lark-cli",
        "/c/Program Files/nodejs/lark-cli.cmd",
        "lark-cli",
        "lark-cli.cmd",
    ]:
        if not path:
            continue
        try:
            subprocess.run([path, "--version"], capture_output=True, timeout=5)
            return path
        except (FileNotFoundError, OSError):
            continue
    return "lark-cli"

LARK_CLI = _find_lark_cli()

MY_OPEN_ID = "ou_1539f65fb11c13d5cf2277646d2ef182"  # 瞿宏权
TZ = timezone(timedelta(hours=8))

# DeepSeek API config (from settings.json)
API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
API_MODEL = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]")

# Chat context: {chat_id: [{"role": "user"/"assistant", "content": "..."}]}
CHAT_HISTORY = {}
MAX_HISTORY = 20


def call_ai(user_message, chat_id):
    """Send message to DeepSeek API and return response."""
    if chat_id not in CHAT_HISTORY:
        CHAT_HISTORY[chat_id] = []

    history = CHAT_HISTORY[chat_id]
    history.append({"role": "user", "content": user_message})

    messages = [
        {"role": "system", "content": "你是蟠恒若，一个AI助手。用户叫蟠渊。用中文回复，简洁友好。"},
        *history[-MAX_HISTORY:],
    ]

    body = json.dumps({
        "model": API_MODEL,
        "messages": messages,
        "max_tokens": 2000,
    }).encode()

    url = f"{API_BASE}/messages"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        reply = data["content"][0]["text"]
        history.append({"role": "assistant", "content": reply})
        # Trim history
        if len(history) > MAX_HISTORY + 10:
            CHAT_HISTORY[chat_id] = history[-MAX_HISTORY:]
        return reply
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[AI error] HTTP {e.code}: {body[:200]}", file=sys.stderr)
        return f"AI 调用失败: {e.code}"
    except Exception as e:
        print(f"[AI error] {e}", file=sys.stderr)
        return f"AI 调用失败: {e}"


def send_reply(msg_id, text):
    """Send a reply via lark-cli."""
    result = subprocess.run(
        [LARK_CLI, "im", "+messages-reply",
         "--message-id", msg_id, "--text", text, "--as", "bot"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            if data.get("ok"):
                return data["data"]["message_id"]
        except json.JSONDecodeError:
            pass
    print(f"[reply failed] {result.stderr[:200]}", file=sys.stderr)
    return None


def process_event(event):
    """Handle a single incoming message event."""
    chat_id = event.get("chat_id", "")
    sender_id = event.get("sender_id", "")
    message_id = event.get("message_id", "")
    content = (event.get("content", "") or "").strip()
    message_type = event.get("message_type", "text")
    chat_type = event.get("chat_type", "")

    if not content:
        return
    if sender_id == MY_OPEN_ID:
        return  # skip own messages

    now = datetime.now(TZ).strftime("%H:%M:%S")
    print(f"\n[{now}] {sender_id} ({chat_type}): {content[:100]}")

    # Get AI response
    reply = call_ai(content, chat_id)
    print(f"  -> AI: {reply[:80]}...")

    # Send reply
    msg_id = send_reply(message_id, reply)
    if msg_id:
        print(f"  [OK] Sent: {msg_id}")


def main():
    print("=" * 60)
    print("Feishu <-> AI Bridge (DeepSeek)")
    print(f"Model: {API_MODEL}")
    print("=" * 60)

    # Start lark-cli event consumer (long-running)
    proc = subprocess.Popen(
        [LARK_CLI, "event", "consume", "im.message.receive_v1",
         "--as", "bot"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    # Wait for ready signal on stderr
    for line in proc.stderr:
        line = line.strip()
        if line:
            print(f"[lark] {line}", file=sys.stderr)
        if "[event] ready" in line:
            break

    print("[OK] Bridge ready - waiting for messages...")

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "im.message.receive_v1":
                    process_event(event)
            except json.JSONDecodeError:
                print(f"[warn] non-JSON: {line[:80]}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)

    print("Bridge stopped.")


if __name__ == "__main__":
    main()
