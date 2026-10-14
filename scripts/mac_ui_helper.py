#!/usr/bin/env bash
""":"
if [ -f "$(dirname "$0")/../.venv-ui/bin/python" ]; then
    exec "$(dirname "$0")/../.venv-ui/bin/python" "$0" "$@"
fi
exec python3 "$0" "$@"
":"""

import sys
import subprocess
import os
import time

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_window_bounds(app_name="EasyPaper"):
    candidates = [app_name, "app", "EasyPaper", "HJPaper"] if app_name in ["EasyPaper", "app"] else [app_name]
    for name in candidates:
        script = f'''
        tell application "System Events"
            if exists (process "{name}") then
                tell process "{name}"
                    set frontmost to true
                    set win to front window
                    set {{x, y}} to position of win
                    set {{w, h}} to size of win
                    return (x as string) & "," & (y as string) & "," & (w as string) & "," & (h as string)
                end tell
            end if
        end tell
        '''
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            parts = [int(p.strip()) for p in res.stdout.strip().split(",")]
            return {"x": parts[0], "y": parts[1], "w": parts[2], "h": parts[3], "name": name}
    return None

def click(x, y):
    # 1. Try cliclick
    cliclick_path = "/opt/homebrew/bin/cliclick"
    if os.path.exists(cliclick_path):
        res = subprocess.run([cliclick_path, f"c:{x},{y}"], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[cliclick] Clicked at {x}, {y}")
            return True

    # 2. Try Quartz
    try:
        import Quartz
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (x, y), Quartz.kCGMouseButtonLeft)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        time.sleep(0.05)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        print(f"[Quartz] Clicked at {x}, {y}")
        return True
    except Exception:
        pass

    # 3. Try pyautogui
    try:
        import pyautogui
        pyautogui.click(x, y)
        print(f"[pyautogui] Clicked at {x}, {y}")
        return True
    except Exception:
        pass

    # 4. Fallback to osascript
    script = f'''
    tell application "System Events"
        click at {{{x}, {y}}}
    end tell
    '''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"[osascript] Clicked at {x}, {y}")
        return True
    print(f"Failed to click at {x}, {y}: {res.stderr}")
    return False

def screenshot(out_path):
    res = subprocess.run(["screencapture", "-x", out_path], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"Screenshot saved to {out_path}")
        return True
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: mac_ui_helper.py [window | click <x> <y> | screenshot <path>]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "window":
        app = sys.argv[2] if len(sys.argv) > 2 else "EasyPaper"
        bounds = get_window_bounds(app)
        if bounds:
            print(f"{app} Window: x={bounds['x']}, y={bounds['y']}, w={bounds['w']}, h={bounds['h']}")
        else:
            print(f"Could not find window for {app}")
    elif action == "click":
        if len(sys.argv) < 4:
            print("Usage: mac_ui_helper.py click <x> <y>")
            sys.exit(1)
        x = int(sys.argv[2])
        y = int(sys.argv[3])
        click(x, y)
    elif action == "screenshot":
        if len(sys.argv) < 3:
            print("Usage: mac_ui_helper.py screenshot <path>")
            sys.exit(1)
        screenshot(sys.argv[2])
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()
