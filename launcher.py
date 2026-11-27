#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlDawli Downloads Launcher
يشغّل ملف aldawli.py الخارجي باستخدام بيئة Python والمكتبات المدمجة داخل AlDawli.exe
بحيث تعمل التحديثات التلقائية عبر تحديث aldawli.py فقط بدون الحاجة لإعادة بناء الـ EXE.
"""
import os, re, sys, ssl, json, time, hmac, site, glob, base64, ctypes, shutil, socket, secrets
import tempfile, argparse, platform, importlib, threading, subprocess, webbrowser, mimetypes
import http.client, http.cookiejar, http.server, runpy
import urllib.request, urllib.parse, urllib.error
from pathlib import Path

try:
    import winreg  # noqa: F401
except Exception:
    pass

try:
    import tkinter  # noqa: F401
    from tkinter import filedialog  # noqa: F401
except Exception:
    pass

try:
    import webview  # noqa: F401
except Exception:
    pass

try:
    import yt_dlp  # noqa: F401
except Exception:
    pass

try:
    import yt_dlp_ejs  # noqa: F401
except Exception:
    pass


def _pick_script():
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    app_script = base_dir / "aldawli.py"
    user_script = Path.home() / ".aldawli" / "aldawli.py"
    if user_script.exists():
        if not app_script.exists() or user_script.stat().st_mtime > app_script.stat().st_mtime:
            return user_script
    if app_script.exists():
        return app_script
    return None


def main():
    script = _pick_script()
    if not script:
        if platform.system() == "Windows":
            ctypes.windll.user32.MessageBoxW(
                None,
                "لم يتم العثور على ملف aldawli.py بجانب البرنامج.\nأعد تثبيت الدولي للتحميلات.",
                "الدولي للتحميلات",
                0x10,
            )
        raise SystemExit(1)
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
