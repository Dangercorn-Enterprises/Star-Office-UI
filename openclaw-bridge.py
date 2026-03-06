#!/usr/bin/env python3
"""OpenClaw Gateway → Star Office UI state bridge.

Polls the OpenClaw gateway status and maps agent states to Star Office UI states.
Updates state.json so the pixel office reflects what Calder is actually doing.

Usage: python3 openclaw-bridge.py [--interval 10] [--gateway ws://localhost:18789]
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
POLL_INTERVAL = int(os.environ.get("BRIDGE_INTERVAL", "10"))
GATEWAY_PORT = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")

def get_gateway_status():
    """Check OpenClaw gateway health via HTTP."""
    try:
        import urllib.request
        url = f"http://127.0.0.1:{GATEWAY_PORT}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data
    except Exception:
        return None

def check_systemctl_status():
    """Check if gateway service is running."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False

def check_active_tasks():
    """Check if Calder is actively processing by looking at recent log activity."""
    log_patterns = [
        "/tmp/openclaw/openclaw-*.log",
    ]
    try:
        import glob as g
        for pattern in log_patterns:
            files = g.glob(pattern)
            for f in sorted(files, key=os.path.getmtime, reverse=True)[:1]:
                mtime = os.path.getmtime(f)
                age = time.time() - mtime
                if age < 30:  # Active in last 30 seconds
                    # Read last few lines for context
                    with open(f, 'r') as fh:
                        lines = fh.readlines()[-5:]
                    last_line = lines[-1].strip() if lines else ""
                    if "error" in last_line.lower() or "exception" in last_line.lower():
                        return "error", last_line[:80]
                    elif any(k in last_line.lower() for k in ["generat", "respond", "reply", "complet"]):
                        return "writing", last_line[:80]
                    elif any(k in last_line.lower() for k in ["search", "fetch", "query", "research"]):
                        return "researching", last_line[:80]
                    elif any(k in last_line.lower() for k in ["exec", "run", "tool", "command"]):
                        return "executing", last_line[:80]
                    else:
                        return "writing", "Processing..."
    except Exception:
        pass
    return None, None

def update_state(state, detail, progress=0):
    """Write state to state.json for Star Office UI to pick up."""
    data = {
        "state": state,
        "detail": detail,
        "progress": progress,
        "updated_at": datetime.now().isoformat()
    }
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def main():
    print(f"OpenClaw → Star Office bridge starting")
    print(f"  Gateway port: {GATEWAY_PORT}")
    print(f"  State file: {STATE_FILE}")
    print(f"  Poll interval: {POLL_INTERVAL}s")

    last_state = None
    while True:
        try:
            gateway_running = check_systemctl_status()

            if not gateway_running:
                new_state = "error"
                detail = "Gateway DOWN"
            else:
                # Check for active tasks
                task_state, task_detail = check_active_tasks()
                if task_state:
                    new_state = task_state
                    detail = task_detail
                else:
                    new_state = "idle"
                    detail = "Calder standing by..."

            if new_state != last_state:
                print(f"  State: {last_state} → {new_state} | {detail}")
                last_state = new_state

            update_state(new_state, detail)

        except Exception as e:
            print(f"  Bridge error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
