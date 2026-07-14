#!/usr/bin/env python3
"""Build and install the app on a connected device.

Actions:
  --list                          List connected devices as JSON
  --install --device <id>         Build + install on that device
  --install --platform <name>     Build + install on first matching device

Flags:
  --platform ios|android|web|macos|linux|windows|fuchsia
  --mode debug|profile|release    (default: debug)
  --lines N                       Keep only the last N lines of build output
                                   (default: 40 for install; 0 = full)

The LLM's "final step" flow:
  1. foreman deploy list                              (or --platform ios)
  2. If empty: ask user to connect device, re-run
  3. If multiple: ask user which
  4. foreman deploy install --device <id>
"""
import json, os, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log
from foreman.proc import run_command

_start = time.time()

# Map targetPlatform → human-friendly platform name.
PLATFORM_MAP = {
    "darwin": "macos", "darwin-arm64": "macos", "darwin-x64": "macos",
    "linux-x64": "linux", "linux-arm64": "linux",
    "windows-x64": "windows",
    "web-javascript": "web",
    "android-arm": "android", "android-arm64": "android",
    "android-x64": "android", "android-x86": "android",
    "ios": "ios", "ios-arm64": "ios",
    "fuchsia-x64": "fuchsia", "fuchsia-arm64": "fuchsia",
}


def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)


target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")


def _out(obj, code=0):
    from foreman import ui
    if obj.get("devices") is not None or (obj.get("ok") and "count" in obj and "--install" not in sys.argv):
        ui.deploy_list_view(obj)
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "deploy.py", code, int((time.time()-_start)*1000))
    sys.exit(code)


def _list_devices():
    """Return list of {id, name, platform, emulator, sdk} for connected devices."""
    r = subprocess.run(["flutter", "devices", "--machine"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None, r.stderr or r.stdout
    try:
        raw = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return None, f"Could not parse flutter devices output: {e}"
    out = []
    for d in raw:
        tp = d.get("targetPlatform", "")
        out.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "platform": PLATFORM_MAP.get(tp, tp),
            "target_platform": tp,
            "emulator": d.get("emulator", False),
            "sdk": d.get("sdk", ""),
        })
    return out, None


# ── list ──
if "--list" in sys.argv or (not any(f in sys.argv for f in ("--install", "--run"))):
    devices, err = _list_devices()
    if devices is None:
        _out({"ok": False, "message": err}, 1)
    plat = _arg("--platform")
    if plat:
        devices = [d for d in devices if d["platform"] == plat]
    if not devices:
        hint = (f"No {plat} devices connected." if plat
                else "No devices connected.")
        _out({"ok": True, "count": 0, "devices": [],
              "hint": hint + " Connect a physical device (USB + trust) or start a simulator, then re-run."}, 0)
    _out({"ok": True, "count": len(devices), "devices": devices,
          "hint": "Pick a device id and run: foreman deploy install --device <id>"})


# ── install ──
if "--install" in sys.argv:
    device_id = _arg("--device")
    plat = _arg("--platform")
    mode = _arg("--mode", "debug")
    if mode not in ("debug", "profile", "release"):
        _out({"ok": False, "message": f"Invalid --mode '{mode}'. Use debug|profile|release."}, 1)

    # Resolve device
    if not device_id:
        devices, err = _list_devices()
        if devices is None:
            _out({"ok": False, "message": err}, 1)
        if plat:
            devices = [d for d in devices if d["platform"] == plat]
        if not devices:
            _out({"ok": False, "message": "No device to install on.",
                  "hint": "foreman deploy list"}, 1)
        if len(devices) > 1:
            _out({"ok": False, "message": "Multiple devices matched. Specify --device <id>.",
                  "devices": devices}, 1)
        device_id = devices[0]["id"]

    # Verify device is still connected
    devices, err = _list_devices()
    if devices is None:
        _out({"ok": False, "message": err}, 1)
    found = next((d for d in devices if d["id"] == device_id), None)
    if not found:
        _out({"ok": False, "message": f"Device '{device_id}' not connected.",
              "available": [d["id"] for d in devices]}, 1)

    # Build first (flutter install expects a pre-built artefact),
    # then install / point at the built binary.
    steps: list[dict] = []
    plat_name = found["platform"]

    BUILD_TARGET = {
        "android": "apk", "ios": "ios", "macos": "macos",
        "linux": "linux", "windows": "windows", "web": "web",
    }
    if plat_name not in BUILD_TARGET:
        _out({"ok": False, "message": f"Unsupported target platform: {plat_name}"}, 1)

    build_cmd = ["flutter", "build", BUILD_TARGET[plat_name], f"--{mode}"]
    # iOS device builds without codesign need this flag to succeed offline.
    if plat_name == "ios":
        build_cmd.append("--no-codesign")
    build_res = run_command(build_cmd, cwd=target, timeout=900, heartbeat=False)
    steps.append({"step": "build", "cmd": " ".join(build_cmd),
                  "ok": build_res.ok, "duration_s": round(build_res.duration, 1)})

    def _tail_lines(text: str, n: int) -> str:
        lines_ = (text or "").splitlines()
        if n <= 0 or len(lines_) <= n:
            return "\n".join(lines_)
        omitted = len(lines_) - n
        return f"... ({omitted} earlier lines omitted)\n" + "\n".join(lines_[-n:])

    lines_arg = _arg("--lines")
    tail_n = int(lines_arg) if lines_arg else 40  # LINES not chars

    if not build_res.ok:
        _out({"ok": False, "device": found, "mode": mode, "steps": steps,
              "output": _tail_lines(build_res.combined, tail_n),
              "hint": "Build failed. See output."}, 1)

    # Install step (only for platforms where installing to a device is meaningful).
    if plat_name in ("android", "ios"):
        install_cmd = ["flutter", "install", "-d", device_id, f"--{mode}"]
        inst_res = run_command(install_cmd, cwd=target, timeout=300, heartbeat=False)
        steps.append({"step": "install", "cmd": " ".join(install_cmd),
                      "ok": inst_res.ok, "duration_s": round(inst_res.duration, 1)})
        ok = inst_res.ok
        tail = inst_res.combined
    else:
        # Desktop/web: build produced a binary; no separate install step.
        ok = True
        tail = build_res.combined

    _out({
        "ok": ok, "device": found, "mode": mode, "steps": steps,
        "output": _tail_lines(tail, tail_n),
        "hint": (f"Installed on {found['name']}. Launch the app on the device to test."
                 if ok else "Install failed. See output.")
    }, 0 if ok else 1)


_out({"ok": False, "message": "Use --list or --install"}, 1)
