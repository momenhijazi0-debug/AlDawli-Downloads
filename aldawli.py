#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الدولي للتحميلات — مدير تنزيلات سريع + محمّل فيديوهات (يوتيوب، إنستغرام، تيك توك، فيسبوك...)
تنزيل مجزّأ ديناميكي + استئناف + تحديد سرعة + تحديث الرابط + ربط مع المتصفح + تحميل الفيديو والصوت
التشغيل:  python aldawli.py
إنشاء اختصار سطح المكتب:  python aldawli.py --shortcut
"""
import os, re, sys, ssl, json, time, hmac, site, glob, base64, ctypes, shutil, socket, secrets, tempfile, argparse, platform, importlib, threading, subprocess, webbrowser, mimetypes, http.client, http.cookiejar
import urllib.request as rq, urllib.parse as up, urllib.error as ue
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

APP_TITLE = "الدولي للتحميلات"
APP_VERSION = "10.10"
UPDATE_REPO = "momenhijazi0-debug/AlDawli-Downloads"
UPDATE_MANIFEST_URL = f"https://raw.githubusercontent.com/{UPDATE_REPO}/main/version.json"
UPDATE_SCRIPT_URL = f"https://raw.githubusercontent.com/{UPDATE_REPO}/main/aldawli.py"
UPDATE_SETUP_URL = f"https://github.com/{UPDATE_REPO}/releases/latest/download/AlDawli_Setup.exe"
CURRENT_PORT = 8765
APP = Path.home() / ".aldawli"
LEGACY_STATE = Path.home() / ".tahmeeli" / "state.json"
STATE = APP / "state.json"
UPLOAD_TMP = APP / "upload_tmp"
ARIA2_SESSION = APP / "aria2.session"
CATBOX_MAX = 200 * 1024 * 1024
LITTERBOX_MAX = 1024 * 1024 * 1024
UPLOAD_UA = "AlDawli-Uploader/2.0"
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".ts")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MINSEG = 1 << 20          # أصغر جزء: 1 م.ب
TOKEN = secrets.token_urlsafe(24)
ACTIVE = ("connecting", "downloading")

VIDEO_HOSTS = (
    "youtube.com", "youtu.be", "music.youtube.com",
    "instagram.com", "instagr.am",
    "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "facebook.com", "fb.watch", "m.facebook.com",
    "twitter.com", "x.com",
    "reddit.com", "v.redd.it",
    "vimeo.com", "dailymotion.com", "twitch.tv", "kick.com", "soundcloud.com", "pinterest.com", "pin.it"
)

_YTDLP_CACHE = {"checked": False, "mod": None}
_FFMPEG_CACHE = {"checked": False, "path": None}


class _MediaStopped(Exception):
    pass


class _CaptureLogger:
    def __init__(self):
        self.warnings = []
        self.errors = []
    def debug(self, msg):
        pass
    def info(self, msg):
        pass
    def warning(self, msg):
        self.warnings.append(str(msg))
    def error(self, msg):
        self.errors.append(str(msg))



def _ver_tuple(v):
    nums = re.findall(r"\d+", str(v or "0"))
    return tuple(int(x) for x in nums) if nums else (0,)

def app_dir():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def ensure_icon_file():
    here_ico = app_dir() / "icon.ico"
    if here_ico.exists():
        return here_ico
    APP.mkdir(parents=True, exist_ok=True)
    cached_ico = APP / "icon.ico"
    if not cached_ico.exists():
        cached_ico.write_bytes(base64.b64decode(ICON_ICO_B64))
    return cached_ico


def apply_windows_taskbar_icon():
    """تطبيق أيقونة الدولي للتحميلات مباشرة على نافذة التطبيق في شريط مهام ويندوز."""
    if platform.system() != "Windows":
        return
    try:
        ico_path = str(ensure_icon_file())
        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_long

        hicon_big = user32.LoadImageW(None, ico_path, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        if not hicon_big and not hicon_small:
            return

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def set_on_matching():
            found = []
            def cb(hwnd, _lp):
                if user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(hwnd, buf, n + 1)
                        if APP_TITLE in buf.value:
                            if hicon_big:
                                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                            if hicon_small:
                                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
                            found.append(hwnd)
                return True
            user32.EnumWindows(WNDENUMPROC(cb), 0)
            return bool(found)

        # نحاول لعدة ثوانٍ حتى تكتمل النافذة ويُعاد تثبيت الأيقونة بعد تحميل الصفحة
        hits = 0
        for _ in range(25):
            if set_on_matching():
                hits += 1
                if hits >= 4:
                    break
            time.sleep(0.5)
    except Exception:
        pass


def _get_windows_desktop():
    try:
        buf = ctypes.create_unicode_buffer(32768)
        # CSIDL_DESKTOPDIRECTORY = 0x0010 (يدعم مجلد OneDrive Desktop تلقائيًا إن وُجد)
        hr = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        if hr == 0 and buf.value:
            return Path(buf.value)
    except Exception:
        pass
    return Path.home() / "Desktop"


def _save_lnk_unicode(lnk_path, target_path, arguments, working_dir, icon_path, description):
    """إنشاء ملف .lnk باستخدام واجهة Windows COM Unicode (IShellLinkW + IPersistFile) مباشرة."""
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def make_guid(s):
        g = GUID()
        hr = ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        if hr < 0:
            raise OSError(f"CLSIDFromString failed: {hr:#x}")
        return g

    CLSID_ShellLink = make_guid("{00021401-0000-0000-C000-000000000046}")
    IID_IShellLinkW = make_guid("{000214F9-0000-0000-C000-000000000046}")
    IID_IPersistFile = make_guid("{0000010b-0000-0000-C000-000000000046}")

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    co_hr = ole32.CoInitialize(None)
    shell_link = ctypes.c_void_p()
    persist_file = ctypes.c_void_p()

    def vcall(obj_ptr, idx, restype, argtypes, *args):
        vtable = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[idx])
        return fn(obj_ptr, *args)

    try:
        # CLSCTX_INPROC_SERVER = 1
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_ShellLink), None, 1,
            ctypes.byref(IID_IShellLinkW), ctypes.byref(shell_link)
        )
        if hr < 0 or not shell_link.value:
            raise OSError(f"CoCreateInstance failed: {hr:#x}")

        # IShellLinkW vtable: 20=SetPath, 11=SetArguments, 9=SetWorkingDirectory, 17=SetIconLocation, 7=SetDescription
        vcall(shell_link, 20, ctypes.c_long, [ctypes.c_wchar_p], str(target_path))
        if arguments:
            vcall(shell_link, 11, ctypes.c_long, [ctypes.c_wchar_p], str(arguments))
        if working_dir:
            vcall(shell_link, 9, ctypes.c_long, [ctypes.c_wchar_p], str(working_dir))
        if icon_path:
            vcall(shell_link, 17, ctypes.c_long, [ctypes.c_wchar_p, ctypes.c_int], str(icon_path), 0)
        if description:
            vcall(shell_link, 7, ctypes.c_long, [ctypes.c_wchar_p], str(description))

        # IUnknown::QueryInterface (index 0) -> IPersistFile
        hr = vcall(
            shell_link, 0, ctypes.c_long,
            [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
            ctypes.byref(IID_IPersistFile), ctypes.byref(persist_file)
        )
        if hr < 0 or not persist_file.value:
            raise OSError(f"QueryInterface(IPersistFile) failed: {hr:#x}")

        # IPersistFile::Save (index 6): Save(LPCOLESTR pszFileName, BOOL fRemember)
        hr = vcall(persist_file, 6, ctypes.c_long, [ctypes.c_wchar_p, ctypes.c_int], str(lnk_path), 1)
        if hr < 0:
            raise OSError(f"IPersistFile::Save failed: {hr:#x}")
    finally:
        if persist_file.value:
            vcall(persist_file, 2, ctypes.c_ulong, [])
        if shell_link.value:
            vcall(shell_link, 2, ctypes.c_ulong, [])
        if co_hr in (0, 1):
            ole32.CoUninitialize()



def register_magnet_protocol():
    """تسجيل الدولي للتحميلات كبرنامج افتراضي لروابط magnet: في ويندوز."""
    if platform.system() != "Windows":
        raise RuntimeError("تسجيل بروتوكول Magnet مدعوم على نظام Windows فقط")
    import winreg
    ico_path = str(ensure_icon_file())
    if getattr(sys, "frozen", False):
        cmd_str = f'"{Path(sys.executable).resolve()}" --magnet "%1"'
    else:
        py_exe = Path(sys.executable).resolve()
        pyw_exe = py_exe.with_name("pythonw.exe")
        runner = pyw_exe if pyw_exe.exists() else py_exe
        script_path = Path(__file__).resolve()
        cmd_str = f'"{runner}" "{script_path}" --magnet "%1"'

    for base in (r"Software\Classes\magnet", r"Software\Classes\AlDawli.Magnet"):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"URL:{APP_TITLE}")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\DefaultIcon") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{ico_path}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd_str)

    # تسجيل التطبيق في قائمة التطبيقات الافتراضية في ويندوز (Default Apps)
    cap_key = r"Software\AlDawli\Capabilities"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cap_key) as k:
        winreg.SetValueEx(k, "ApplicationName", 0, winreg.REG_SZ, APP_TITLE)
        winreg.SetValueEx(k, "ApplicationDescription", 0, winreg.REG_SZ, "مدير تنزيلات وتورنت")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cap_key + r"\URLAssociations") as k:
        winreg.SetValueEx(k, "magnet", 0, winreg.REG_SZ, "AlDawli.Magnet")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as k:
        winreg.SetValueEx(k, "AlDawliDownloads", 0, winreg.REG_SZ, cap_key)

    # فحص ما إذا كان uTorrent أو برنامج آخر مقفل UserChoice في ويندوز
    locked_by_other = False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\magnet\UserChoice") as uk:
            prog, _ = winreg.QueryValueEx(uk, "ProgId")
            if prog and "aldawli" not in str(prog).lower():
                locked_by_other = True
    except Exception:
        pass

    if locked_by_other:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:defaultapps"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    return {"ok": True, "locked_by_other": locked_by_other}


def set_windows_autostart(enable=True):
    """تفعيل أو تعطيل التشغيل التلقائي مع بدء الويندوز (في الخلفية بصينية النظام)."""
    if platform.system() != "Windows":
        return False
    import winreg
    run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key) as k:
        if enable:
            if getattr(sys, "frozen", False):
                cmd_str = f'"{Path(sys.executable).resolve()}" --no-window'
            else:
                py_exe = Path(sys.executable).resolve()
                pyw_exe = py_exe.with_name("pythonw.exe")
                runner = pyw_exe if pyw_exe.exists() else py_exe
                cmd_str = f'"{runner}" "{Path(__file__).resolve()}" --no-window'
            winreg.SetValueEx(k, "AlDawliDownloads", 0, winreg.REG_SZ, cmd_str)
        else:
            try:
                winreg.DeleteValue(k, "AlDawliDownloads")
            except FileNotFoundError:
                pass
    return True


def is_windows_autostart_enabled():
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "AlDawliDownloads")
            return True
    except Exception:
        return False


def show_or_open_main_window():
    """إظهار نافذة الدولي للتحميلات في المقدمة إن كانت مفتوحة، أو فتحها تلقائيًا إن كانت مغلقة."""
    if platform.system() == "Windows":
        try:
            user32 = ctypes.windll.user32
            SW_RESTORE = 9
            found = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def cb(hwnd, _lp):
                if user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(hwnd, buf, n + 1)
                        if APP_TITLE in buf.value and "معلومات ملف التحميل" not in buf.value:
                            if user32.IsIconic(hwnd):
                                user32.ShowWindow(hwnd, SW_RESTORE)
                            user32.SetForegroundWindow(hwnd)
                            found.append(hwnd)
                            return False
                return True
            user32.EnumWindows(WNDENUMPROC(cb), 0)
            if found:
                return True
        except Exception:
            pass
    open_window(f"http://127.0.0.1:{CURRENT_PORT}/")
    return True


def start_windows_tray():
    """إضافة أيقونة الدولي للتحميلات في صينية النظام (System Tray) بويندوز بدون أي مكتبات خارجية."""
    if platform.system() != "Windows":
        return

    def _tray_thread():
        try:
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            kernel32 = ctypes.windll.kernel32

            WM_DESTROY = 0x0002
            WM_COMMAND = 0x0111
            WM_USER = 0x0400
            WM_TRAY = WM_USER + 20
            WM_LBUTTONUP = 0x0202
            WM_LBUTTONDBLCLK = 0x0203
            WM_RBUTTONUP = 0x0205
            NIM_ADD = 0x00000000
            NIM_DELETE = 0x00000002
            NIF_MESSAGE = 0x00000001
            NIF_ICON = 0x00000002
            NIF_TIP = 0x00000004
            MF_STRING = 0x00000000
            TPM_LEFTALIGN = 0x0000
            TPM_BOTTOMALIGN = 0x0020
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010

            ID_OPEN = 1001
            ID_QUIT = 1002

            LRESULT = ctypes.c_ssize_t
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [
                    ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                    ("hCursor", wt.HCURSOR), ("hbrBackground", wt.HBRUSH),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR),
                ]

            class NOTIFYICONDATAW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                    ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
                    ("szTip", wt.WCHAR * 128),
                ]

            user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            user32.DefWindowProcW.restype = LRESULT
            user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
            user32.LoadImageW.restype = wt.HICON

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_TRAY:
                    if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                        threading.Thread(target=show_or_open_main_window, daemon=True).start()
                    elif lparam == WM_RBUTTONUP:
                        menu = user32.CreatePopupMenu()
                        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "فتح الدولي للتحميلات")
                        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "إنهاء التطبيق")
                        pt = wt.POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        user32.SetForegroundWindow(hwnd)
                        user32.TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_BOTTOMALIGN, pt.x, pt.y, 0, hwnd, None)
                        user32.DestroyMenu(menu)
                    return 0
                elif msg == WM_COMMAND:
                    cmd_id = wparam & 0xFFFF
                    if cmd_id == ID_OPEN:
                        threading.Thread(target=show_or_open_main_window, daemon=True).start()
                    elif cmd_id == ID_QUIT:
                        def bye():
                            time.sleep(0.15)
                            if MGR:
                                MGR.shutdown()
                            os._exit(0)
                        threading.Thread(target=bye, daemon=True).start()
                    return 0
                elif msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            hinst = kernel32.GetModuleHandleW(None)
            cls_name = f"AlDawliTray_{os.getpid()}"
            wc = WNDCLASSW()
            wc.lpfnWndProc = WNDPROC(wnd_proc)
            wc.hInstance = hinst
            wc.lpszClassName = cls_name
            user32.RegisterClassW(ctypes.byref(wc))

            hwnd = user32.CreateWindowExW(0, cls_name, APP_TITLE, 0, 0, 0, 0, 0, None, None, hinst, None)
            if not hwnd:
                return

            ico_path = str(ensure_icon_file())
            hicon = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)

            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = hicon
            nid.szTip = f"{APP_TITLE} (v{APP_VERSION})"
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

            msg_s = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg_s), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg_s))
                user32.DispatchMessageW(ctypes.byref(msg_s))
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass

    threading.Thread(target=_tray_thread, daemon=True).start()


def _find_chromium_exe():
    s, c = platform.system(), []
    if s == "Darwin":
        c = [f"/Applications/{a}.app/Contents/MacOS/{b}" for a, b in
             (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"), ("Brave Browser", "Brave Browser"))]
    elif s == "Windows":
        for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            b = os.environ.get(k)
            if b:
                c += [
                    os.path.join(b, r"Google\Chrome\Application\chrome.exe"),
                    os.path.join(b, r"Microsoft\Edge\Application\msedge.exe"),
                ]
    else:
        c = [shutil.which(x) for x in ("google-chrome", "chromium", "microsoft-edge", "chromium-browser")]
    for x in c:
        if x and os.path.exists(x):
            return x
    return None


def bring_title_to_front(title_substr, topmost=False):
    if platform.system() != "Windows":
        return
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        for _ in range(16):
            found = []
            def cb(hwnd, _lp):
                if user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(hwnd, buf, n + 1)
                        if title_substr in buf.value:
                            if user32.IsIconic(hwnd):
                                user32.ShowWindow(hwnd, SW_RESTORE)
                            if topmost:
                                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                            user32.SetForegroundWindow(hwnd)
                            found.append(hwnd)
                            return False
                return True
            user32.EnumWindows(WNDENUMPROC(cb), 0)
            if found:
                return
            time.sleep(0.2)
    except Exception:
        pass


def open_popup_window(pid):
    """فتح نافذة منبثقة صغيرة ومستقلة أمام المتصفح مباشرة لاختيار مكان الحفظ."""
    url = f"http://127.0.0.1:{CURRENT_PORT}/popup?pid={pid}"
    exe = _find_chromium_exe()
    if not exe:
        bring_window_to_front()
        return False
    profile_dir = APP / "app_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        exe,
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=630,570",
    ])
    if platform.system() == "Windows":
        threading.Thread(target=bring_title_to_front, args=("معلومات ملف التحميل", True), daemon=True).start()
    return True


def open_video_popup_window(vid):
    """فتح نافذة منبثقة صغيرة أمام المتصفح مباشرة لاختيار جودة الفيديو ومكان الحفظ."""
    url = f"http://127.0.0.1:{CURRENT_PORT}/vpopup?vid={vid}"
    exe = _find_chromium_exe()
    if not exe:
        return False
    profile_dir = APP / "app_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        exe,
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=680,580",
    ])
    if platform.system() == "Windows":
        threading.Thread(target=bring_title_to_front, args=("تحميل فيديو — الدولي", True), daemon=True).start()
    return True


def _send_magnet_to_running(uri, base_port=8765):
    payload = json.dumps({"uri": uri, "inspect": True}).encode("utf-8")
    for port in range(base_port, base_port + 30):
        try:
            req = rq.Request(
                f"http://127.0.0.1:{port}/api/ext/torrent",
                data=payload,
                headers={"Content-Type": "application/json", "Origin": "chrome-extension://local"},
            )
            with rq.urlopen(req, timeout=2.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False

def create_desktop_shortcut():
    """إنشاء اختصار لسطح المكتب في ويندوز بأيقونة الدولي للتحميلات (يدعم الأسماء والمسارات العربية 100%)."""
    if platform.system() != "Windows":
        raise RuntimeError("إنشاء الاختصار التلقائي مدعوم على نظام Windows فقط")
    here = app_dir()
    ico_path = str(ensure_icon_file())
    if getattr(sys, "frozen", False):
        target_path = str(Path(sys.executable).resolve())
        arguments = ""
    else:
        py_exe = Path(sys.executable).resolve()
        pyw_exe = py_exe.with_name("pythonw.exe")
        target_path = str(pyw_exe if pyw_exe.exists() else py_exe)
        script_path = str(Path(__file__).resolve())
        arguments = f'"{script_path}"'

    desk = _get_windows_desktop()
    desk.mkdir(parents=True, exist_ok=True)
    lnk_path = desk / f"{APP_TITLE}.lnk"
    _save_lnk_unicode(lnk_path, target_path, arguments, str(here), ico_path, APP_TITLE)
    return str(lnk_path)


def is_video_url(url):
    try:
        host = (up.urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in VIDEO_HOSTS)
    except Exception:
        return False


def is_youtube_url(url):
    try:
        host = (up.urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in ("youtube.com", "youtu.be", "music.youtube.com"))
    except Exception:
        return False


def get_ytdlp(force=False):
    if not force and _YTDLP_CACHE["checked"]:
        return _YTDLP_CACHE["mod"]
    try:
        if force:
            importlib.invalidate_caches()
            try:
                site.main()
            except Exception:
                pass
        import yt_dlp
        _YTDLP_CACHE["mod"] = yt_dlp
    except Exception:
        _YTDLP_CACHE["mod"] = None
    _YTDLP_CACHE["checked"] = True
    return _YTDLP_CACHE["mod"]


def has_ytdlp_ejs():
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:
        return False


def find_ffmpeg(force=False):
    if not force and _FFMPEG_CACHE["checked"]:
        return _FFMPEG_CACHE["path"]
    p = shutil.which("ffmpeg")
    if not p:
        here = app_dir()
        cands = [here / "ffmpeg.exe", here / "ffmpeg", APP / "ffmpeg.exe", APP / "ffmpeg"]
        if platform.system() == "Windows":
            la = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            cands.append(Path(la) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe")
            for m in glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "**", "ffmpeg.exe"), recursive=True):
                cands.append(Path(m))
            for m in (Path("C:/ffmpeg/bin/ffmpeg.exe"), Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe")):
                cands.append(m)
        for cand in cands:
            if cand.exists():
                p = str(cand)
                break
    _FFMPEG_CACHE["path"] = p
    _FFMPEG_CACHE["checked"] = True
    return p


def detect_js_runtimes():
    rts = {}
    is_win = platform.system() == "Windows"
    la = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    home = Path.home()
    here = app_dir()
    extra_cands = {
        "deno": [
            here / ("deno.exe" if is_win else "deno"),
            APP / ("deno.exe" if is_win else "deno"),
            home / ".deno" / "bin" / ("deno.exe" if is_win else "deno"),
            Path(la) / "Microsoft" / "WinGet" / "Links" / "deno.exe",
        ] + ([Path(m) for m in glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*Deno*", "**", "deno.exe"), recursive=True)] if is_win else []),
        "node": [
            Path(r"C:\Program Files\nodejs\node.exe"),
            Path(r"C:\Program Files (x86)\nodejs\node.exe"),
            Path(la) / "Programs" / "nodejs" / "node.exe",
        ] if is_win else [],
        "bun": [home / ".bun" / "bin" / ("bun.exe" if is_win else "bun")],
        "quickjs": [],
    }
    for name in ("deno", "node", "bun", "quickjs"):
        p = shutil.which(name)
        if not p:
            for cand in extra_cands.get(name, []):
                if cand.exists():
                    p = str(cand)
                    break
        if p:
            rts[name] = {"path": p}
    return rts


def build_ytdlp_base_opts(url, headers=None, yt_clients=None, logger=None):
    opts = {
        "quiet": True,
        "no_warnings": False if logger else True,
        "noplaylist": True,
        "socket_timeout": 25,
        "retries": 3,
    }
    if logger:
        opts["logger"] = logger
    js_rts = detect_js_runtimes()
    if js_rts:
        opts["js_runtimes"] = js_rts
        opts["remote_components"] = {"ejs:github"}
    if yt_clients and is_youtube_url(url):
        opts["extractor_args"] = {"youtube": {"player_client": list(yt_clients)}}
    if isinstance(headers, dict) and not is_youtube_url(url):
        clean = {}
        for k, v in headers.items():
            if isinstance(k, str) and isinstance(v, str) and k.lower() in ("cookie", "referer"):
                clean[k] = v
        if clean:
            opts["http_headers"] = clean
    return opts


def explain(e):
    if isinstance(e, ue.HTTPError): return f"رفض الخادم الطلب (رمز {e.code})"
    if isinstance(e, ue.URLError): return "تعذّر الاتصال بالخادم"
    msg = str(e) or "خطأ غير معروف"
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
    return msg[:260]


def explain_media_error(e, logger=None):
    raw = explain(e)
    joined = " ".join((logger.warnings if logger else []) + (logger.errors if logger else []) + [raw]).lower()
    if "requested format is not available" in raw.lower():
        if "javascript runtime" in joined or "ejs" in joined or "n challenge" in joined or not detect_js_runtimes():
            return "يوتيوب يطلب مشغّل JavaScript (Deno) + مكتبة yt-dlp-ejs. شغّل setup.bat لتثبيتهما تلقائيًا."
        return raw
    return raw


def safe_name(n):
    n = up.unquote(n or "")
    try:
        n = n.encode("latin-1").decode("utf-8")
    except Exception:
        pass
    n = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", n).strip(" .")
    return n[:180] or "download"


def filename_from(h, url):
    cd = h.get("Content-Disposition", "") or ""
    m = re.search(r"filename\*\s*=\s*[\w-]*'[^']*'([^;]+)", cd, re.I)
    if m: return safe_name(m.group(1).strip())
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I) or re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    if m: return safe_name(m.group(1).strip())
    name = safe_name(os.path.basename(up.urlparse(url).path))
    if "." not in name:
        ext = mimetypes.guess_extension((h.get("Content-Type", "") or "").split(";")[0].strip())
        if ext: name += ext
    return name


def _extract_playable_formats(info, has_ff, is_yt):
    raw_fmts = info.get("formats") or []
    best_audio_size = 0
    best_audio_fmt = None
    for f in raw_fmts:
        ext_f = (f.get("ext") or "").lower()
        if ext_f == "mhtml" or f.get("protocol") == "mhtml":
            continue
        if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none"):
            sz = f.get("filesize") or f.get("filesize_approx") or 0
            abr = f.get("abr") or 0
            if not best_audio_fmt or abr > (best_audio_fmt.get("abr") or 0):
                best_audio_fmt = f
                best_audio_size = sz

    by_height = {}
    for f in raw_fmts:
        ext = (f.get("ext") or "mp4").lower()
        if ext == "mhtml" or f.get("protocol") == "mhtml":
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        h = f.get("height")
        if not h or h < 144 or vcodec in (None, "none"):
            continue
        has_audio = (acodec not in (None, "none")) if is_yt else (acodec != "none")
        if not has_audio and not has_ff:
            continue
        fid = str(f.get("format_id") or "")
        if not fid:
            continue
        sz = f.get("filesize") or f.get("filesize_approx") or 0
        if not has_audio and best_audio_size:
            sz = sz + best_audio_size if sz else 0
        is_direct = (f.get("protocol") or "").startswith("http")
        score = (
            1 if has_audio else 0,
            1 if ext == "mp4" else 0,
            1 if is_direct else 0,
            f.get("fps") or 0,
            f.get("tbr") or 0,
        )
        prev = by_height.get(int(h))
        if not prev or score > prev["score"]:
            if has_audio:
                fmt_sel = f"{fid}/b[height<={int(h)}][ext=mp4]/b[height<={int(h)}]/b"
            else:
                fmt_sel = (
                    f"{fid}+ba[ext=m4a]/{fid}+ba/"
                    f"bv*[height<={int(h)}]+ba/b[height<={int(h)}]/bv*+ba/b"
                )
            by_height[int(h)] = {
                "height": int(h),
                "ext": "mp4" if (not has_audio or ext == "mp4") else ext,
                "fps": int(f["fps"]) if f.get("fps") else 0,
                "size": int(sz) if sz else -1,
                "format_id": fmt_sel,
                "audio_only": False,
                "merged": has_audio,
                "score": score,
            }
    return by_height, best_audio_fmt, best_audio_size


def probe_media(url, headers=None):
    yt_dlp = get_ytdlp()
    if not yt_dlp:
        raise RuntimeError("محرك الفيديو (yt-dlp) غير مثبّت بعد. اضغط على زر «تثبيت تلقائي الآن» أعلاه.")
    url = (url or "").strip()
    p = up.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("الرابط غير صالح (يلزم http أو https)")

    has_ff = bool(find_ffmpeg(force=True))
    client_plans = [None, ["android_vr", "ios", "tv"]] if is_youtube_url(url) else [None]

    info = None
    used_clients = None
    by_height = {}
    best_audio_fmt = None
    best_audio_size = 0
    last_logger = None

    for plan in client_plans:
        logger = _CaptureLogger()
        last_logger = logger
        opts = build_ytdlp_base_opts(url, headers, yt_clients=plan, logger=logger)
        opts["skip_download"] = True
        opts["ignore_no_formats_error"] = True
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                cand = ydl.extract_info(url, download=False)
                if not cand:
                    continue
                if cand.get("_type") == "playlist" and cand.get("entries"):
                    entries = [e for e in cand["entries"] if e]
                    if not entries:
                        continue
                    cand = entries[0]
            is_yt = "youtube" in (cand.get("extractor_key") or "").lower()
            bh, baf, bas = _extract_playable_formats(cand, has_ff, is_yt)
            info = cand
            if bh or baf:
                by_height, best_audio_fmt, best_audio_size = bh, baf, bas
                used_clients = plan
                break
        except Exception:
            if plan is client_plans[-1] and info is None:
                raise

    if not info:
        raise RuntimeError("تعذّر استخراج بيانات الفيديو من هذا الرابط")

    choices = []
    for h in sorted(by_height.keys(), reverse=True):
        c = by_height[h]
        tag = "4K" if h >= 2160 else "2K" if h >= 1440 else "Full HD" if h >= 1080 else "HD" if h >= 720 else ""
        fps_txt = f" {c['fps']}fps" if c["fps"] and c["fps"] >= 50 else ""
        label = f"{h}p" + (f" {tag}" if tag else "") + fps_txt
        choices.append({
            "label": label,
            "ext": c["ext"].upper(),
            "size": c["size"],
            "format_id": c["format_id"],
            "audio_only": False,
            "quality_hint": h,
            "yt_clients": used_clients,
        })

    if not choices and is_youtube_url(url) and not best_audio_fmt:
        warn_txt = " ".join(last_logger.warnings if last_logger else []).lower()
        if not detect_js_runtimes() or "javascript runtime" in warn_txt or "ejs" in warn_txt:
            raise RuntimeError(
                "يوتيوب حجب الجودات لأن مشغّل JavaScript (Deno) أو yt-dlp-ejs غير مثبّت. "
                "شغّل ملف setup.bat المرفق لتثبيتهما تلقائيًا ثم أعد فتح التطبيق."
            )

    if not choices:
        choices.append({
            "label": "أفضل جودة متاحة تلقائيًا",
            "ext": "MP4",
            "size": int(info.get("filesize") or info.get("filesize_approx") or -1),
            "format_id": "bv*+ba/b" if has_ff else "b[ext=mp4]/b/bv*+ba",
            "audio_only": False,
            "quality_hint": 720,
            "yt_clients": used_clients,
        })

    if has_ff:
        choices.append({
            "label": "صوت فقط (MP3 — 192kbps)",
            "ext": "MP3",
            "size": int(best_audio_size) if best_audio_size else -1,
            "format_id": "ba/b",
            "audio_only": True,
            "quality_hint": 0,
            "yt_clients": used_clients,
        })
    elif best_audio_fmt:
        a_ext = (best_audio_fmt.get("ext") or "m4a").lower()
        choices.append({
            "label": f"صوت فقط ({a_ext.upper()})",
            "ext": a_ext.upper(),
            "size": int(best_audio_size) if best_audio_size else -1,
            "format_id": "ba[ext=m4a]/ba/b",
            "audio_only": True,
            "quality_hint": 0,
            "yt_clients": used_clients,
        })

    return {
        "url": info.get("webpage_url") or url,
        "title": info.get("title") or "فيديو",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": int(info["duration"]) if info.get("duration") else 0,
        "thumbnail": info.get("thumbnail") or "",
        "site": info.get("extractor_key") or info.get("extractor") or "",
        "has_ffmpeg": has_ff,
        "formats": choices,
    }


class Item:
    def __init__(self, mgr, d):
        self.mgr, self.id, self.url, self.dir = mgr, d["id"], d["url"], d["dir"]
        self.filename, self.size = d["filename"], d.get("size", -1)
        self.custom_name = bool(d.get("custom_name", False))
        self.desc = d.get("desc", "")
        self.kind = d.get("kind", "direct")
        self.format_id = d.get("format_id", "")
        self.audio_only = bool(d.get("audio_only", False))
        self.yt_clients = d.get("yt_clients")
        self.resumable, self.segments = d.get("resumable", False), d.get("segments", [])
        self.headers = d.get("headers") or {}
        self.status, self.error = d.get("status", "queued"), d.get("error", "")
        self.added, self.finished = d.get("added", time.time()), d.get("finished", 0)
        self._media_down = int(d.get("media_down", 0))
        self.prepared = bool(self.segments)
        self.speed, self.thread, self.fail_msg = 0.0, None, None
        self.stop = threading.Event()
        self._seglock = threading.Lock()

    @property
    def final_path(self): return Path(self.dir) / self.filename
    @property
    def part_path(self): return Path(self.dir) / (self.filename + ".part")
    @property
    def downloaded(self):
        if self.kind == "media":
            return self.size if self.status == "completed" and self.size > 0 else self._media_down
        with self._seglock:
            return sum(s[2] - s[0] for s in self.segments)
    @staticmethod
    def seg_done(s): return s[1] is not None and s[2] > s[1]

    def _build_headers(self):
        h = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        for k, v in (self.headers or {}).items():
            if isinstance(k, str) and isinstance(v, str) and k.lower() not in (
                "host", "range", "accept-encoding", "content-length"
            ):
                h[k] = v
        return h

    def meta(self):
        with self._seglock:
            segs = [list(s) for s in self.segments]
        return dict(id=self.id, url=self.url, dir=self.dir, filename=self.filename, size=self.size,
                    custom_name=self.custom_name, desc=self.desc,
                    kind=self.kind, format_id=self.format_id, audio_only=self.audio_only,
                    yt_clients=self.yt_clients, media_down=self._media_down, resumable=self.resumable,
                    segments=segs, headers=self.headers, status=self.status, error=self.error,
                    added=self.added, finished=self.finished)

    def api(self):
        if self.kind == "media":
            segs = []
            d = self.downloaded
        else:
            with self._seglock:
                segs = [list(s) for s in self.segments]
                d = sum(s[2] - s[0] for s in segs)
        eta = (self.size - d) / self.speed if self.speed > 1 and self.size > 0 and self.status == "downloading" else None
        return dict(id=self.id, url=self.url, filename=self.filename, size=self.size, downloaded=d,
                    kind=self.kind, status=self.status, speed=self.speed, eta=eta, error=self.error,
                    added=self.added, finished=self.finished,
                    segments=segs if self.resumable and len(segs) > 1 else [])

    def prepare(self):
        self.url = normalize_gdrive_url(self.url)
        h = self._build_headers()
        with _open_direct_smart(self.url, h, timeout=20, want_range_probe=True) as r:
            m = re.match(r"bytes\s+\d+-\d+/(\d+)", r.headers.get("Content-Range", ""))
            if r.status == 206 and m:
                size, resumable = int(m.group(1)), True
            else:
                cl = r.headers.get("Content-Length", "")
                size = int(cl) if cl.isdigit() else -1
                resumable = (r.headers.get("Accept-Ranges", "").lower() == "bytes") and size > 0
            self.url = r.geturl()
            name = filename_from(r.headers, self.url)
        self.size, self.resumable = size, resumable
        chosen_name = self.filename if (self.custom_name and self.filename) else name
        self.filename = self.mgr.unique(self.dir, chosen_name, self)
        os.makedirs(self.dir, exist_ok=True)
        with self._seglock:
            if resumable and size > 0:
                n = max(1, min(self.mgr.settings["segments"], size // MINSEG))
                p = size // n
                self.segments = [[i * p, (i + 1) * p - 1 if i < n - 1 else size - 1, i * p] for i in range(n)]
            else:
                self.segments = [[0, size - 1 if size > 0 else None, 0]]
        with open(self.part_path, "wb") as f:
            if size > 0: f.truncate(size)
        self.prepared = True

    def steal_segment(self):
        if not self.resumable:
            return None
        with self._seglock:
            best_idx, best_rem = -1, 0
            for idx, s in enumerate(self.segments):
                if s[1] is not None:
                    rem = s[1] - s[2] + 1
                    if rem > best_rem:
                        best_rem, best_idx = rem, idx
            if best_idx < 0 or best_rem < 2 * MINSEG:
                return None
            b = self.segments[best_idx]
            mid = b[2] + best_rem // 2
            new_seg = [mid, b[1], mid]
            b[1] = mid - 1
            self.segments.insert(best_idx + 1, new_seg)
            return new_seg

    def worker(self, seg, stop):
        while seg is not None and not stop.is_set():
            tries = 0
            while not stop.is_set():
                with self._seglock:
                    if self.seg_done(seg):
                        break
                    start_pos, end_pos = seg[2], seg[1]
                try:
                    h = self._build_headers()
                    if self.resumable:
                        h["Range"] = f"bytes={start_pos}-{end_pos}"
                    else:
                        with self._seglock:
                            seg[2] = 0
                            start_pos = 0
                    with _open_with_cookies(self.url, h, timeout=20) as r:
                        if self.resumable and r.status != 206:
                            raise IOError("الخادم لا يدعم التنزيل المجزّأ")
                        with open(self.part_path, "r+b") as f:
                            f.seek(start_pos)
                            while not stop.is_set():
                                kb = self.mgr.settings.get("max_speed", 0)
                                chunk_sz = min(65536, max(4096, (kb * 1024) // 8)) if kb > 0 else 65536
                                c = r.read(chunk_sz)
                                if stop.is_set(): return
                                if not c: break
                                with self._seglock:
                                    if seg[1] is not None:
                                        rem = seg[1] + 1 - seg[2]
                                        if rem <= 0:
                                            break
                                        if len(c) > rem:
                                            c = c[:rem]
                                    f.write(c)
                                    wrote = len(c)
                                    seg[2] += wrote
                                    tries = 0
                                    done_now = seg[1] is not None and seg[2] > seg[1]
                                self.mgr.throttle(wrote, stop)
                                if done_now:
                                    break
                    with self._seglock:
                        if seg[1] is None:
                            seg[1] = seg[2] - 1
                        elif seg[2] <= seg[1]:
                            raise IOError("انقطع الاتصال قبل اكتمال الجزء")
                except Exception as e:
                    if stop.is_set(): return
                    tries += 1
                    if tries > 5 or (isinstance(e, ue.HTTPError) and e.code in (400, 401, 403, 404, 410)):
                        self.fail_msg = self.fail_msg or explain(e); stop.set(); return
                    stop.wait(min(2 * tries, 8))
            seg = self.steal_segment() if not stop.is_set() else None

    def _run_media(self, stop):
        yt_dlp = get_ytdlp()
        if not yt_dlp:
            raise RuntimeError("محرك الفيديو (yt-dlp) غير مثبّت. ثبّته من قسم «تحميل فيديو».")
        os.makedirs(self.dir, exist_ok=True)
        ffmpeg = find_ffmpeg(force=True)
        final_holder = {"path": None}
        last_save = [time.monotonic()]

        def phook(d):
            if stop.is_set() or self.stop is not stop:
                raise _MediaStopped()
            st = d.get("status")
            if st == "downloading":
                self.status = "downloading"
                tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                if tot > 0:
                    self.size = int(tot)
                self._media_down = int(d.get("downloaded_bytes") or 0)
                spd = d.get("speed") or 0
                if spd:
                    self.speed = float(spd)
                fn = d.get("filename")
                if fn:
                    self.filename = Path(fn).name
                now = time.monotonic()
                if now - last_save[0] > 3:
                    self.mgr.save()
                    last_save[0] = now
            elif st == "finished":
                fn = d.get("filename")
                if fn:
                    final_holder["path"] = fn
                    self.filename = Path(fn).name
                self.speed = 0

        def pphook(d):
            if d.get("status") == "finished":
                fp = (d.get("info_dict") or {}).get("filepath")
                if fp:
                    final_holder["path"] = fp

        def make_opts(fmt_str, yt_clients, logger):
            opts = build_ytdlp_base_opts(self.url, self.headers, yt_clients=yt_clients, logger=logger)
            opts.update({
                "outtmpl": str(Path(self.dir) / "%(title).140B.%(ext)s"),
                "windowsfilenames": True,
                "continuedl": True,
                "progress_hooks": [phook],
                "postprocessor_hooks": [pphook],
                "format": fmt_str,
            })
            kb = self.mgr.settings.get("max_speed", 0)
            if kb > 0:
                opts["ratelimit"] = kb * 1024
            if ffmpeg:
                opts["ffmpeg_location"] = ffmpeg
                if self.audio_only:
                    opts["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }]
                else:
                    opts["merge_output_format"] = "mp4"
                    opts["postprocessor_args"] = {"merger": ["-movflags", "+faststart"]}
            return opts

        primary_fmt = self.format_id or ("ba/b" if self.audio_only else ("bv*+ba/b" if ffmpeg else "b[ext=mp4]/b"))
        fallback_fmt = "ba/b" if self.audio_only else ("bv*+ba/b" if ffmpeg else "b[ext=mp4]/b")

        attempts = [(primary_fmt, self.yt_clients)]
        if primary_fmt != fallback_fmt:
            attempts.append((fallback_fmt, self.yt_clients))
        if is_youtube_url(self.url):
            attempts.append((fallback_fmt, ["android_vr", "ios", "tv"]))

        last_err = None
        last_logger = None
        succeeded = False
        try:
            for fmt_try, clients_try in attempts:
                logger = _CaptureLogger()
                last_logger = logger
                try:
                    with yt_dlp.YoutubeDL(make_opts(fmt_try, clients_try, logger)) as ydl:
                        info = ydl.extract_info(self.url, download=True)
                        if not final_holder["path"] and info:
                            reqs = info.get("requested_downloads") or []
                            final_holder["path"] = reqs[0].get("filepath") if (reqs and reqs[0].get("filepath")) else ydl.prepare_filename(info)
                    succeeded = True
                    break
                except _MediaStopped:
                    raise
                except Exception as e:
                    if stop.is_set():
                        raise _MediaStopped()
                    last_err = e
                    if "format is not available" not in str(e).lower():
                        break
        except _MediaStopped:
            self.speed = 0
            return

        if not succeeded:
            raise RuntimeError(explain_media_error(last_err, last_logger))

        if stop.is_set() or self.stop is not stop:
            self.speed = 0
            return

        fp = Path(final_holder["path"]) if final_holder["path"] else self.final_path
        if self.audio_only and ffmpeg and not fp.exists():
            alt = fp.with_suffix(".mp3")
            if alt.exists():
                fp = alt
        if not fp.exists() and not self.audio_only:
            alt = fp.with_suffix(".mp4")
            if alt.exists():
                fp = alt

        self.filename = fp.name
        self.dir = str(fp.parent)
        if fp.exists():
            self.size = fp.stat().st_size
            self._media_down = self.size
        self.speed = 0
        self.status, self.finished = "completed", time.time()

    def start(self):
        prev, self.stop, self.fail_msg, self.error = self.thread, threading.Event(), None, ""
        self.status = "connecting"
        self.thread = threading.Thread(target=self._run, args=(prev, self.stop), daemon=True)
        self.thread.start()


    def _run_curl_fallback(self, stop):
        """تحميل بديل عبر curl بهيدرات المتصفح الكاملة لتجاوز حمايات 403/Cloudflare."""
        curl = shutil.which("curl")
        if not curl:
            raise RuntimeError("رفض الخادم الطلب (رمز 403) ولم يتم العثور على curl كمحرك بديل.")
        os.makedirs(self.dir, exist_ok=True)
        h = self._build_headers()
        target_part = self.part_path
        self.status = "downloading"
        self.error = ""
        self.fail_msg = None
        self.resumable = False
        self.prepared = True
        self.mgr.save()

        # فحص الحجم عبر curl -I إن لم يكن معروفًا
        if self.size <= 0:
            try:
                head_cmd = [curl, "-sSIL", "--max-time", "12"]
                for k, v in h.items():
                    if k.lower() != "accept-encoding":
                        head_cmd += ["-H", f"{k}: {v}"]
                head_cmd.append(self.url)
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
                hres = subprocess.run(head_cmd, capture_output=True, text=True, errors="replace", timeout=15, creationflags=creationflags)
                cls = re.findall(r"(?i)^content-length:\s*(\d+)", hres.stdout or "", re.M)
                if cls:
                    self.size = int(cls[-1])
            except Exception:
                pass

        cmd = [curl, "-sSL", "-f", "-C", "-", "--retry", "3", "--retry-delay", "2", "-o", str(target_part)]
        kb = int(self.mgr.settings.get("max_speed", 0) or 0)
        if kb > 0:
            cmd += ["--limit-rate", f"{kb}k"]
        for k, v in h.items():
            if k.lower() != "accept-encoding":
                cmd += ["-H", f"{k}: {v}"]
        cmd.append(self.url)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=creationflags)
        last_sz = target_part.stat().st_size if target_part.exists() else 0
        with self._seglock:
            self.segments = [[0, (self.size - 1) if self.size > 0 else None, last_sz]]
        t0 = time.monotonic()
        ts = t0
        try:
            while proc.poll() is None:
                if stop.is_set() or self.stop is not stop:
                    proc.terminate()
                    return
                time.sleep(0.45)
                cur = target_part.stat().st_size if target_part.exists() else 0
                now = time.monotonic()
                v = (cur - last_sz) / max(now - t0, 1e-3)
                self.speed = v if self.speed == 0 else 0.6 * self.speed + 0.4 * v
                last_sz, t0 = cur, now
                with self._seglock:
                    self.segments = [[0, (self.size - 1) if self.size > 0 else None, cur]]
                if now - ts > 3:
                    self.mgr.save()
                    ts = now
            _, err_b = proc.communicate()
            if stop.is_set() or self.stop is not stop:
                self.speed = 0
                return
            self.speed = 0
            if proc.returncode == 0 and target_part.exists() and target_part.stat().st_size > 0:
                cur = target_part.stat().st_size
                with self._seglock:
                    self.segments = [[0, cur - 1, cur]]
                self.finish()
            else:
                err_txt = (err_b or b"").decode("utf-8", errors="replace").strip()
                m = re.search(r"error:\s*(\d{3})", err_txt)
                if m:
                    self.status, self.error = "error", f"رفض الخادم الطلب (رمز {m.group(1)}) حتى عبر المحرك البديل"
                else:
                    self.status, self.error = "error", "فشل التحميل عبر المحرك البديل: " + (err_txt[-120:] or f"رمز {proc.returncode}")
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def _run(self, prev, stop):
        try:
            if prev and prev.is_alive(): prev.join()
            if stop.is_set() or self.stop is not stop: return
            if self.kind == "media":
                self._run_media(stop)
                return
            if not self.prepared or not self.part_path.exists():
                self.prepared = False
                try:
                    self.prepare()
                except ue.HTTPError as he:
                    if he.code in (403, 406, 429):
                        self._run_curl_fallback(stop)
                        return
                    raise
            if stop.is_set() or self.stop is not stop: return
            self.status = "downloading"; self.mgr.save()
            with self._seglock:
                todo = [s for s in self.segments if not self.seg_done(s)]
            ws = [threading.Thread(target=self.worker, args=(s, stop), daemon=True) for s in todo]
            for w in ws: w.start()
            last, t0, ts = self.downloaded, time.monotonic(), time.monotonic()
            while any(w.is_alive() for w in ws):
                time.sleep(0.5)
                now, cur = time.monotonic(), self.downloaded
                v = (cur - last) / max(now - t0, 1e-3)
                self.speed = v if self.speed == 0 else 0.6 * self.speed + 0.4 * v
                last, t0 = cur, now
                if now - ts > 3: self.mgr.save(); ts = now
            if self.stop is not stop: return
            self.speed = 0
            if self.fail_msg:
                if "403" in self.fail_msg and not stop.is_set():
                    self._run_curl_fallback(stop)
                    return
                self.status, self.error = "error", self.fail_msg
            elif stop.is_set(): pass
            elif all(self.seg_done(s) for s in self.segments): self.finish()
            else: self.status, self.error = "error", "لم يكتمل التنزيل"
        except Exception as e:
            if self.stop is stop: self.status, self.error, self.speed = "error", explain(e), 0
        finally:
            self.mgr.save()

    def finish(self):
        self.size = self.downloaded
        with open(self.part_path, "r+b") as f: f.truncate(self.size)
        if self.final_path.exists(): self.filename = self.mgr.unique(self.dir, self.filename, self)
        os.replace(self.part_path, self.final_path)
        self.status, self.finished = "completed", time.time()



def _parse_time_sec(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if re.match(r"^\d+(\.\d+)?$", s):
        return float(s)
    parts = s.split(":")
    if len(parts) in (2, 3) and all(re.match(r"^\d+(\.\d+)?$", p) for p in parts):
        nums = [float(p) for p in parts]
        return nums[0] * 60 + nums[1] if len(nums) == 2 else nums[0] * 3600 + nums[1] * 60 + nums[2]
    raise ValueError("صيغة الوقت غير صحيحة (استخدم ثوانٍ مثل 15 أو 01:30)")


class UploadItem:
    def __init__(self, mgr, d):
        self.mgr = mgr
        self.id = d["id"]
        self.filename = d["filename"]
        self.size = int(d.get("size", 0))
        self.uploaded = int(d.get("uploaded", 0))
        self.status = d.get("status", "uploading")   # processing | uploading | completed | error | cancelled
        self.stage = d.get("stage", "")
        self.url = d.get("url", "")
        self.service = d.get("service", "catbox")    # catbox | litterbox
        self.expiry = d.get("expiry", "")
        self.userhash = d.get("userhash", "")
        self.video_mode = d.get("video_mode", "faststart")  # faststart | streamable | original
        self.trim_start = d.get("trim_start", "")
        self.trim_end = d.get("trim_end", "")
        self.mute = bool(d.get("mute", False))
        self.local_path = d.get("local_path", "")
        self.is_temp = bool(d.get("is_temp", False))
        self.error = d.get("error", "")
        self.added = d.get("added", time.time())
        self.finished = d.get("finished", 0)
        self.speed = 0.0
        self.thread = None
        self._conn = None
        self._proc = None
        self.stop = threading.Event()

    def meta(self):
        return dict(
            id=self.id, filename=self.filename, size=self.size, uploaded=self.uploaded,
            status=self.status, stage=self.stage, url=self.url, service=self.service,
            expiry=self.expiry, userhash=self.userhash, video_mode=self.video_mode,
            trim_start=self.trim_start, trim_end=self.trim_end, mute=self.mute,
            local_path=self.local_path if self.status != "completed" else "",
            is_temp=self.is_temp if self.status != "completed" else False,
            error=self.error, added=self.added, finished=self.finished,
        )

    def api(self):
        eta = (self.size - self.uploaded) / self.speed if self.speed > 1 and self.size > 0 and self.status == "uploading" else None
        can_retry = self.status in ("error", "cancelled") and bool(self.local_path) and Path(self.local_path).exists()
        can_del_remote = self.status == "completed" and self.service == "catbox" and bool(self.userhash) and bool(self.url)
        return dict(
            id=self.id, filename=self.filename, size=self.size, uploaded=self.uploaded,
            status=self.status, stage=self.stage, url=self.url, service=self.service,
            expiry=self.expiry, video_mode=self.video_mode, error=self.error,
            added=self.added, finished=self.finished,
            speed=self.speed, eta=eta, can_retry=can_retry, can_del_remote=can_del_remote,
        )

    def cleanup_temp(self):
        if self.is_temp and self.local_path:
            try:
                Path(self.local_path).unlink(missing_ok=True)
            except Exception:
                pass
            self.local_path = ""
            self.is_temp = False

    def cancel(self):
        self.stop.set()
        proc = self._proc
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        c = self._conn
        if c:
            try:
                c.close()
            except Exception:
                pass
        if self.status in ("processing", "uploading"):
            self.status = "cancelled"
            self.stage = ""
            self.speed = 0.0
            self.error = "تم إلغاء الرفع"
            self.mgr.save()

    def start(self):
        self.stop = threading.Event()
        self.error = ""
        self.stage = ""
        self.uploaded = 0
        self.speed = 0.0
        self.status = "processing"
        self.mgr.save()
        self.thread = threading.Thread(target=self._run, args=(self.stop,), daemon=True)
        self.thread.start()

    def _translate_server_error(self, status_code, body):
        clean = re.sub(r"<[^>]+>", " ", body or "")
        clean = re.sub(r"\s+", " ", clean).strip()
        low = clean.lower()
        if "file type" in low or ("not allowed" in low and status_code != 405):
            return "نوع هذا الملف غير مسموح به على السيرفر (مثل .exe أو .jar). اضغطه بصيغة ZIP ثم ارفعه."
        if "too large" in low or "200mb" in low or status_code == 413:
            return "حجم الملف يتجاوز الحد الأقصى (200 م.ب لـ Catbox الدائم). اختر وضع «ضغط ذكي 720p» أو Litterbox المؤقت."
        if status_code == 403 or "cloudflare" in low or "just a moment" in low:
            return "حجب جدار الحماية الطلب مؤقتًا (403) — جرّب الرفع على Catbox الدائم أو أعد المحاولة بعد ثوانٍ."
        if clean:
            return f"رفض السيرفر الرفع ({status_code}): {clean[:140]}"
        return f"فشل الرفع إلى السيرفر (رمز {status_code})"

    def _prepare_video_if_needed(self, src_path, stop):
        ext = Path(self.filename).suffix.lower()
        if ext not in VIDEO_EXTS:
            return src_path, None

        t_start = _parse_time_sec(self.trim_start)
        t_end = _parse_time_sec(self.trim_end)
        if t_start is not None and t_end is not None and t_end <= t_start:
            raise ValueError("وقت النهاية في القص يجب أن يكون أكبر من وقت البداية")

        has_edits = (t_start is not None) or (t_end is not None) or self.mute
        mode = self.video_mode if self.video_mode in ("faststart", "streamable", "original") else "faststart"
        if mode == "original" and not has_edits:
            return src_path, None

        ffmpeg = find_ffmpeg(force=True)
        if not ffmpeg:
            if has_edits or mode == "streamable":
                raise RuntimeError("يلزم وجود FFmpeg لقص أو ضغط الفيديو (شغّل setup.bat ثم أعد فتح التطبيق).")
            return src_path, None

        UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
        out_path = UPLOAD_TMP / f"{self.id}_web.mp4"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        if t_start is not None and t_start > 0:
            cmd += ["-ss", f"{t_start:.3f}"]
        cmd += ["-i", str(src_path)]
        if t_end is not None:
            dur = (t_end - (t_start or 0.0))
            if dur > 0:
                cmd += ["-t", f"{dur:.3f}"]

        if mode == "streamable":
            self.stage = "جارٍ ضغط وتجهيز الفيديو للبث الفوري (720p H.264)..."
            cmd += [
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
            ]
            if self.mute:
                cmd += ["-an"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
            cmd += ["-movflags", "+faststart", str(out_path)]
        else:
            # FastStart (نسخ فوري بدون إعادة ترميز للملفات MP4/MOV/M4V — يضع بيانات الفهرس بأول الملف)
            self.stage = "جارٍ تجهيز الفيديو للبث السريع (FastStart)..."
            if ext in (".mp4", ".mov", ".m4v") and not has_edits:
                cmd += ["-c", "copy", "-movflags", "+faststart", str(out_path)]
            elif ext in (".mp4", ".mov", ".m4v") and has_edits:
                cmd += ["-c:v", "copy"]
                cmd += ["-an"] if self.mute else ["-c:a", "copy"]
                cmd += ["-movflags", "+faststart", str(out_path)]
            else:
                cmd += [
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                ]
                cmd += ["-an"] if self.mute else ["-c:a", "aac", "-b:a", "128k"]
                cmd += ["-movflags", "+faststart", str(out_path)]

        self.status = "processing"
        self.mgr.save()

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags
        )
        self._proc = proc
        try:
            while proc.poll() is None:
                if stop.is_set():
                    proc.terminate()
                    return None, out_path
                time.sleep(0.25)
            _, err_b = proc.communicate()
            if stop.is_set():
                return None, out_path
            if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size <= 0:
                if not has_edits and mode == "faststart":
                    # إن تعذّر النسخ المباشر لبعض الترميزات، ارفع الملف الأصلي بدل الفشل
                    out_path.unlink(missing_ok=True)
                    return src_path, None
                err_txt = (err_b or b"").decode("utf-8", errors="replace").strip()
                raise RuntimeError("فشل تجهيز الفيديو عبر FFmpeg: " + (err_txt[-160:] or f"رمز {proc.returncode}"))
        finally:
            self._proc = None

        if not self.filename.lower().endswith(".mp4"):
            self.filename = str(Path(self.filename).with_suffix(".mp4"))
        return out_path, out_path

    def _upload_via_http(self, fp, fsize, host, endpoint, is_litter, stop):
        boundary = "----AldawliUpload" + secrets.token_hex(12)
        ext = re.sub(r"[^a-zA-Z0-9.]", "", Path(self.filename).suffix.lower())[:16]
        if ext and not ext.startswith("."):
            ext = "." + ext
        ascii_fname = "file" + (ext or ".bin")
        ctype = mimetypes.guess_type(self.filename)[0] or "application/octet-stream"

        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"reqtype\"\r\n\r\nfileupload\r\n"]
        if is_litter:
            exp = self.expiry if self.expiry in ("1h", "12h", "24h", "72h") else "24h"
            self.expiry = exp
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"time\"\r\n\r\n{exp}\r\n")
        elif self.userhash:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"userhash\"\r\n\r\n{self.userhash}\r\n")
        parts.append(
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"fileToUpload\"; filename=\"{ascii_fname}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n"
        )
        prefix = "".join(parts).encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        total_len = len(prefix) + fsize + len(suffix)

        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, 443, timeout=300, context=ctx)
        self._conn = conn
        try:
            conn.putrequest("POST", endpoint)
            conn.putheader("User-Agent", UPLOAD_UA)
            conn.putheader("Accept", "*/*")
            conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            conn.putheader("Content-Length", str(total_len))
            conn.putheader("Connection", "close")
            conn.endheaders()

            conn.send(prefix)
            sent = 0
            last_sent = 0
            t0 = time.monotonic()
            with open(fp, "rb") as f:
                while True:
                    if stop.is_set():
                        return None, ""
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    conn.send(chunk)
                    sent += len(chunk)
                    self.uploaded = sent
                    now = time.monotonic()
                    dt = now - t0
                    if dt >= 0.35:
                        v = (sent - last_sent) / max(dt, 1e-3)
                        self.speed = v if self.speed == 0 else 0.6 * self.speed + 0.4 * v
                        last_sent = sent
                        t0 = now

            if stop.is_set():
                return None, ""
            conn.send(suffix)
            self.speed = 0.0
            resp = conn.getresponse()
            body = resp.read().decode("utf-8", errors="replace").strip()
            return resp.status, body
        finally:
            self._conn = None
            try:
                conn.close()
            except Exception:
                pass

    def _upload_via_curl(self, fp, host, endpoint, is_litter, stop):
        curl = shutil.which("curl")
        if not curl:
            return None, ""
        url = f"https://{host}{endpoint}"
        cmd = [curl, "-sS", "-w", "\n%{http_code}", "-F", "reqtype=fileupload"]
        if is_litter:
            exp = self.expiry if self.expiry in ("1h", "12h", "24h", "72h") else "24h"
            cmd += ["-F", f"time={exp}"]
        elif self.userhash:
            cmd += ["-F", f"userhash={self.userhash}"]
        cmd += ["-F", f"fileToUpload=@{fp}", url]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
        self._proc = proc
        try:
            while proc.poll() is None:
                if stop.is_set():
                    proc.terminate()
                    return None, ""
                time.sleep(0.25)
            out_b, _ = proc.communicate()
            txt = (out_b or b"").decode("utf-8", errors="replace").strip()
            lines = txt.splitlines()
            if lines and lines[-1].isdigit():
                code = int(lines[-1])
                body = "\n".join(lines[:-1]).strip()
                return code, body
            return None, txt
        finally:
            self._proc = None

    def _run(self, stop):
        proc_tmp = None
        try:
            src_fp = Path(self.local_path)
            if not src_fp.exists():
                raise IOError("الملف غير موجود على الجهاز")
            if src_fp.stat().st_size <= 0:
                raise IOError("الملف فارغ (0 بايت)")

            upload_fp, proc_tmp = self._prepare_video_if_needed(src_fp, stop)
            if stop.is_set() or upload_fp is None:
                return

            fsize = upload_fp.stat().st_size
            self.size = fsize
            is_litter = self.service == "litterbox"
            max_allowed = LITTERBOX_MAX if is_litter else CATBOX_MAX
            if fsize > max_allowed:
                raise IOError(
                    "حجم الملف بعد التجهيز أكبر من 200 م.ب (حد Catbox الدائم). اختر «ضغط ذكي 720p» أو Litterbox المؤقت."
                    if not is_litter else "حجم الملف يتجاوز الحد الأقصى (1 ج.ب)."
                )

            self.status = "uploading"
            self.stage = ""
            self.uploaded = 0
            self.mgr.save()

            host = "litterbox.catbox.moe" if is_litter else "catbox.moe"
            endpoint = "/resources/internals/api.php" if is_litter else "/user/api.php"

            status_code, body = self._upload_via_http(upload_fp, fsize, host, endpoint, is_litter, stop)
            if stop.is_set():
                return

            # إن رفض جدار الحماية (403) الاتصال المباشر، نعيد المحاولة تلقائيًا عبر curl المثبّت بالنظام
            if status_code == 403 and not stop.is_set():
                self.stage = "إعادة المحاولة عبر الاتصال البديل..."
                self.uploaded = 0
                c_code, c_body = self._upload_via_curl(upload_fp, host, endpoint, is_litter, stop)
                if c_code is not None:
                    status_code, body = c_code, c_body

            if stop.is_set():
                return

            if status_code == 200 and re.match(r"^https?://", body, re.I):
                self.url = body
                self.uploaded = self.size
                self.stage = ""
                self.status = "completed"
                self.finished = time.time()
                self.cleanup_temp()
            else:
                self.status = "error"
                self.stage = ""
                self.error = self._translate_server_error(status_code or 0, body)
        except Exception as e:
            if stop.is_set() or self.status == "cancelled":
                return
            self.status = "error"
            self.stage = ""
            self.error = explain(e)
        finally:
            self.speed = 0.0
            if proc_tmp and proc_tmp.exists():
                try:
                    proc_tmp.unlink(missing_ok=True)
                except Exception:
                    pass
            self.mgr.save()

    def delete_remote(self):
        if self.service != "catbox" or not self.userhash or not self.url:
            return False
        fname = os.path.basename(up.urlparse(self.url).path)
        if not fname:
            return False
        data = up.urlencode({
            "reqtype": "deletefiles",
            "userhash": self.userhash,
            "files": fname,
        }).encode("utf-8")
        req = rq.Request(
            "https://catbox.moe/user/api.php",
            data=data,
            headers={"User-Agent": UPLOAD_UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with rq.urlopen(req, timeout=20) as r:
            r.read()
        return True




TORRENT_META_TMP = APP / "torrent_meta"

PUBLIC_TRACKERS = ",".join([
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://public.popcorn-tracker.org:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "udp://retracker01-msk-virt.corbina.net:80/announce",
    "http://tracker.opentrackr.org:1337/announce",
    "https://tracker.tamersunion.org:443/announce",
    "https://tracker.gbitt.info:443/announce",
])


def bring_window_to_front():
    """إظهار نافذة الدولي للتحميلات في المقدمة عند وصول تنزيل جديد من المتصفح."""
    if platform.system() != "Windows":
        return
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _lp):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    if APP_TITLE in buf.value:
                        if user32.IsIconic(hwnd):
                            user32.ShowWindow(hwnd, SW_RESTORE)
                        user32.SetForegroundWindow(hwnd)
                        return False
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception:
        pass


def browse_folder_dialog(initial_dir=""):
    """فتح نافذة اختيار مجلد أصلية على ويندوز."""
    if platform.system() != "Windows":
        raise RuntimeError("اختيار المجلد التلقائي مدعوم على ويندوز فقط")
    init = str(initial_dir or "")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(initialdir=init if os.path.isdir(init) else str(Path.home()), title="اختر مجلد الحفظ")
        root.destroy()
        return chosen or ""
    except Exception:
        pass

    ps_code = (
        "Add-Type -AssemblyName System.Windows.Forms\r\n"
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog\r\n"
        "$f.Description = 'Select Download Folder'\r\n"
        + (f"$f.SelectedPath = '{init.replace(chr(39), chr(39)*2)}'\r\n" if os.path.isdir(init) else "")
        + "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }\r\n"
    )
    fd, tmp_ps1 = tempfile.mkstemp(suffix=".ps1", prefix="aldawli_dir_")
    os.close(fd)
    try:
        Path(tmp_ps1).write_text(ps_code, encoding="utf-8-sig")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File", tmp_ps1],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        return (res.stdout or "").strip()
    finally:
        try:
            os.unlink(tmp_ps1)
        except Exception:
            pass


def _bdecode_at(data, i):
    c = data[i:i + 1]
    if c == b"i":
        j = data.index(b"e", i + 1)
        return int(data[i + 1:j]), j + 1
    if c == b"l":
        out, i = [], i + 1
        while data[i:i + 1] != b"e":
            v, i = _bdecode_at(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        out, i = {}, i + 1
        while data[i:i + 1] != b"e":
            k, i = _bdecode_at(data, i)
            v, i = _bdecode_at(data, i)
            out[k] = v
        return out, i + 1
    if c.isdigit():
        j = data.index(b":", i)
        n = int(data[i:j])
        start = j + 1
        return data[start:start + n], start + n
    raise ValueError("ملف التورنت غير صالح (Bencode error)")


def parse_torrent_bytes(raw_bytes):
    """قراءة محتويات ملف .torrent (الاسم + قائمة الملفات وأحجامها) بدون أي مكتبات خارجية."""
    meta, _ = _bdecode_at(raw_bytes, 0)
    info = meta.get(b"info")
    if not isinstance(info, dict):
        raise ValueError("ملف التورنت لا يحتوي على بيانات صالحة")
    name_b = info.get(b"name.utf-8") or info.get(b"name") or b"torrent"
    name = name_b.decode("utf-8", errors="replace") if isinstance(name_b, bytes) else str(name_b)
    files = []
    if b"files" in info and isinstance(info[b"files"], list):
        for idx, f in enumerate(info[b"files"], start=1):
            plen = int(f.get(b"length", 0))
            parts = f.get(b"path.utf-8") or f.get(b"path") or [b"file"]
            rel = "/".join(p.decode("utf-8", errors="replace") if isinstance(p, bytes) else str(p) for p in parts)
            files.append({"index": idx, "path": rel, "size": plen})
    else:
        plen = int(info.get(b"length", 0))
        files.append({"index": 1, "path": name, "size": plen})
    total = sum(f["size"] for f in files)
    comment_b = meta.get(b"comment.utf-8") or meta.get(b"comment") or b""
    comment = comment_b.decode("utf-8", errors="replace") if isinstance(comment_b, bytes) else ""
    return {"name": name, "total_size": total, "files": files, "comment": comment[:200]}


def disk_free_bytes(path_str):
    try:
        p = Path(path_str or Path.home()).expanduser()
        while not p.exists() and p != p.parent:
            p = p.parent
        return shutil.disk_usage(str(p)).free
    except Exception:
        return -1



def _is_gdrive_url(url):
    try:
        host = (up.urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in (
            "drive.google.com", "drive.usercontent.google.com", "docs.google.com", "googleusercontent.com"
        ))
    except Exception:
        return False


def normalize_gdrive_url(url):
    """تحويل روابط Google Drive العادية (/file/d/ID/view أو /open?id=ID) إلى رابط تحميل مباشر مع confirm=t."""
    url = (url or "").strip()
    if not _is_gdrive_url(url):
        return url
    p = up.urlparse(url)
    host = (p.hostname or "").lower()
    qs = up.parse_qs(p.query, keep_blank_values=True)

    # /file/d/<ID>/view أو /file/u/0/d/<ID>/view
    m = re.search(r"/file/(?:u/\d+/)?d/([a-zA-Z0-9_-]{10,})", p.path)
    if m and host == "drive.google.com":
        fid = m.group(1)
        params = {"id": fid, "export": "download", "confirm": "t"}
        if "authuser" in qs and qs["authuser"]:
            params["authuser"] = qs["authuser"][0]
        if "resourcekey" in qs and qs["resourcekey"]:
            params["resourcekey"] = qs["resourcekey"][0]
        return "https://drive.usercontent.google.com/download?" + up.urlencode(params)

    # /open?id=<ID>
    if host == "drive.google.com" and p.path.rstrip("/") == "/open" and qs.get("id"):
        params = {"id": qs["id"][0], "export": "download", "confirm": "t"}
        if "authuser" in qs and qs["authuser"]:
            params["authuser"] = qs["authuser"][0]
        return "https://drive.usercontent.google.com/download?" + up.urlencode(params)

    # drive.usercontent.google.com/download أو drive.google.com/uc
    if (host == "drive.usercontent.google.com" and p.path.startswith("/download")) or (
        host == "drive.google.com" and p.path.startswith("/uc")
    ):
        flat = {k: v[0] for k, v in qs.items() if v}
        if "confirm" not in flat:
            flat["confirm"] = "t"
        return up.urlunparse((p.scheme, p.netloc, p.path, p.params, up.urlencode(flat), ""))

    return url


def _open_with_cookies(url, headers, timeout=15):
    cj = http.cookiejar.CookieJar()
    opener = rq.build_opener(rq.HTTPCookieProcessor(cj))
    return opener.open(rq.Request(url, headers=headers), timeout=timeout)


def _inspect_gdrive_html_response(final_url, html_bytes):
    """فحص رد HTML القادم من Google Drive: إما استخراج رابط التحميل الحقيقي من صفحة التحذير أو اكتشاف صفحة تسجيل الدخول."""
    fhost = (up.urlparse(final_url).hostname or "").lower()
    text = (html_bytes or b"").decode("utf-8", errors="replace")
    low = text.lower()

    if "accounts.google.com" in fhost or "accounts.google.com/servicelogin" in low or "accounts.google.com/v3/signin" in low:
        raise RuntimeError(
            "ملف Google Drive محمي ويتطلب تسجيل الدخول بحساب Google. "
            "حدّث إضافة المتصفح (aldawli-ext) وحمّله من المتصفح، أو اجعل الرابط عامًا (Anyone with the link)."
        )

    # صفحة تحذير فحص الفيروسات للملفات الكبيرة (>100MB) تحتوي على form id="download-form"
    fm = re.search(r'<form[^>]+id=["\']download-form["\'][^>]+action=["\']([^"\']+)["\']', text, re.I)
    if not fm:
        fm = re.search(r'<form[^>]+action=["\'](https://drive\.usercontent\.google\.com/download[^"\']*)["\']', text, re.I)
    if fm:
        action = fm.group(1).replace("&amp;", "&")
        inputs = dict(re.findall(r'<input[^>]+type=["\']hidden["\'][^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', text, re.I))
        if not inputs:
            inputs = dict(re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', text, re.I))
        if inputs:
            sep = "&" if "?" in action else "?"
            return action + sep + up.urlencode(inputs)
        return action

    return None


def _open_direct_smart(url, headers, timeout=15, want_range_probe=False):
    """فتح رابط تحميل مباشر مع معالجة ذكية لروابط Google Drive وصفحات تأكيد التحميل وتسجيل الدخول."""
    url = normalize_gdrive_url(url)
    is_gd = _is_gdrive_url(url)
    h = dict(headers or {})
    if want_range_probe and not is_gd:
        h["Range"] = "bytes=0-0"

    def do_open(u, hdrs):
        try:
            return _open_with_cookies(u, hdrs, timeout=timeout)
        except ue.HTTPError as e:
            if e.code in (416, 501) and "Range" in hdrs:
                h2 = dict(hdrs)
                h2.pop("Range", None)
                return _open_with_cookies(u, h2, timeout=timeout)
            raise

    r = do_open(url, h)
    ctype = (r.headers.get("Content-Type", "") or "").lower()
    final_url = r.geturl()
    fhost = (up.urlparse(final_url).hostname or "").lower()

    if "text/html" in ctype and (is_gd or "accounts.google.com" in fhost):
        html_chunk = r.read(262144)
        r.close()
        next_url = _inspect_gdrive_html_response(final_url, html_chunk)
        if next_url:
            h2 = dict(h)
            h2.pop("Range", None)
            r = do_open(next_url, h2)
            ctype2 = (r.headers.get("Content-Type", "") or "").lower()
            if "text/html" in ctype2:
                html_chunk2 = r.read(131072)
                r.close()
                _inspect_gdrive_html_response(r.geturl(), html_chunk2)
                raise RuntimeError("أعاد Google Drive صفحة ويب (HTML) بدل الملف — تأكد من صلاحيات مشاركة الملف.")
            return r
        raise RuntimeError("أعاد Google Drive صفحة ويب (HTML) بدل الملف — تأكد من صلاحيات مشاركة الملف أو تسجيل الدخول.")

    return r

def probe_direct_url(url, headers=None):
    url = normalize_gdrive_url((url or "").strip())
    p = up.urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValueError("الرابط غير صالح (يلزم http أو https)")
    h = {"User-Agent": UA, "Accept-Encoding": "identity"}
    if isinstance(headers, dict):
        for k, v in headers.items():
            if isinstance(k, str) and isinstance(v, str) and k.lower() not in ("host", "range", "accept-encoding", "content-length"):
                h[k] = v
    size = -1
    final_url = url
    fname = safe_name(os.path.basename(p.path)) or "download"
    warn = ""
    try:
        with _open_direct_smart(url, h, timeout=12, want_range_probe=True) as r:
            m = re.match(r"bytes\s+\d+-\d+/(\d+)", r.headers.get("Content-Range", ""))
            if r.status == 206 and m:
                size = int(m.group(1))
            else:
                cl = r.headers.get("Content-Length", "")
                size = int(cl) if cl.isdigit() else -1
            final_url = r.geturl()
            fname = filename_from(r.headers, final_url)
    except RuntimeError as e:
        warn = str(e)
    except Exception:
        pass
    return {"url": final_url, "filename": fname, "size": size, "warning": warn}

_ARIA2_CACHE = {"checked": False, "path": None}


def find_aria2(force=False):
    if not force and _ARIA2_CACHE["checked"]:
        return _ARIA2_CACHE["path"]
    p = shutil.which("aria2c")
    if not p:
        here = app_dir()
        cands = [here / "aria2c.exe", here / "aria2c", APP / "aria2c.exe", APP / "aria2c"]
        if platform.system() == "Windows":
            la = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            cands.append(Path(la) / "Microsoft" / "WinGet" / "Links" / "aria2c.exe")
            for m in glob.glob(os.path.join(la, "Microsoft", "WinGet", "Packages", "*aria2*", "**", "aria2c.exe"), recursive=True):
                cands.append(Path(m))
            for m in (Path("C:/aria2/aria2c.exe"), Path("C:/Program Files/aria2/aria2c.exe")):
                cands.append(m)
        for cand in cands:
            if cand.exists():
                p = str(cand)
                break
    _ARIA2_CACHE["path"] = p
    _ARIA2_CACHE["checked"] = True
    return p


class Aria2Engine:
    def __init__(self, mgr):
        self.mgr = mgr
        self.proc = None
        self.port = None
        self.secret = secrets.token_hex(12)
        self.lock = threading.Lock()
        self.installing = False
        self.install_msg = ""

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def _free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def ensure_started(self):
        with self.lock:
            if self.is_running():
                return True
            exe = find_aria2(force=True)
            if not exe:
                return False
            self.port = self._free_port()
            APP.mkdir(parents=True, exist_ok=True)
            TORRENT_META_TMP.mkdir(parents=True, exist_ok=True)
            if not ARIA2_SESSION.exists():
                ARIA2_SESSION.write_text("", encoding="utf-8")
            dl_dir = self.mgr.settings.get("last_dir") or self.mgr.settings.get("dir") or str(Path.home() / "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            kb = int(self.mgr.settings.get("max_speed", 0) or 0)
            cmd = [
                exe,
                "--enable-rpc=true",
                "--rpc-listen-all=false",
                f"--rpc-listen-port={self.port}",
                f"--rpc-secret={self.secret}",
                f"--dir={dl_dir}",
                f"--input-file={ARIA2_SESSION}",
                f"--save-session={ARIA2_SESSION}",
                "--save-session-interval=15",
                "--continue=true",
                "--max-concurrent-downloads=5",
                "--disk-cache=64M",
                "--file-allocation=none",
                "--enable-dht=true",
                "--enable-dht6=true",
                f"--dht-file-path={APP / 'dht.dat'}",
                f"--dht-file-path6={APP / 'dht6.dat'}",
                "--dht-entry-point=dht.transmissionbt.com:6881",
                "--dht-entry-point6=dht.transmissionbt.com:6881",
                "--bt-enable-lpd=true",
                "--enable-peer-exchange=true",
                "--bt-max-peers=200",
                "--bt-request-peer-speed-limit=20M",
                "--bt-min-crypto-level=plain",
                "--bt-require-crypto=false",
                "--bt-tracker-connect-timeout=10",
                "--bt-tracker-timeout=10",
                "--listen-port=6881-6999",
                "--dht-listen-port=6881-6999",
                "--seed-time=0",
                "--follow-torrent=mem",
                f"--bt-tracker={PUBLIC_TRACKERS}",
                f"--max-overall-download-limit={kb}K" if kb > 0 else "--max-overall-download-limit=0",
                "--quiet=true",
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags
            )
            for _ in range(25):
                if self.proc.poll() is not None:
                    self.proc = None
                    return False
                try:
                    self._rpc("aria2.getVersion", [], timeout=1.5)
                    return True
                except Exception:
                    time.sleep(0.15)
            return self.is_running()

    def _rpc(self, method, params=None, timeout=8):
        if not self.port:
            raise RuntimeError("محرك التورنت غير شغّال")
        full_params = [f"token:{self.secret}"] + list(params or [])
        payload = json.dumps({"jsonrpc": "2.0", "id": "aldawli", "method": method, "params": full_params}).encode("utf-8")
        req = rq.Request(
            f"http://127.0.0.1:{self.port}/jsonrpc",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with rq.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8", errors="replace"))
        if "error" in res and res["error"]:
            raise RuntimeError(res["error"].get("message") or "خطأ في محرك التورنت")
        return res.get("result")

    def rpc(self, method, params=None):
        if not self.ensure_started():
            raise RuntimeError("محرك التورنت (aria2) غير مثبّت بعد. اضغط «تثبيت aria2 تلقائيًا».")
        return self._rpc(method, params)

    def apply_settings(self):
        if not self.is_running():
            return
        try:
            kb = int(self.mgr.settings.get("max_speed", 0) or 0)
            self._rpc("aria2.changeGlobalOption", [{
                "dir": self.mgr.settings.get("dir") or str(Path.home() / "Downloads"),
                "max-overall-download-limit": f"{kb}K" if kb > 0 else "0",
            }])
        except Exception:
            pass

    def inspect_torrent_b64(self, b64_data):
        raw = base64.b64decode(b64_data)
        info = parse_torrent_bytes(raw)
        dl_dir = self.mgr.settings.get("dir") or str(Path.home() / "Downloads")
        info["torrent_b64"] = b64_data
        info["default_dir"] = dl_dir
        info["disk_free"] = disk_free_bytes(dl_dir)
        return info

    @staticmethod
    def _extract_infohash_hex(uri):
        m = re.search(r"xt=urn:btih:([a-zA-Z0-9]+)", uri or "", re.I)
        if not m:
            return None
        h = m.group(1)
        if len(h) == 40 and re.match(r"^[0-9a-fA-F]{40}$", h):
            return h.upper()
        if len(h) == 32:
            try:
                return base64.b32decode(h.upper()).hex().upper()
            except Exception:
                return None
        return None

    def _fetch_cached_torrent(self, uri):
        ih = self._extract_infohash_hex(uri)
        if not ih:
            return None
        for cache_url in (
            f"https://itorrents.org/torrent/{ih}.torrent",
            f"https://btcache.me/torrent/{ih}",
        ):
            try:
                req = rq.Request(cache_url, headers={"User-Agent": UA})
                with rq.urlopen(req, timeout=5) as r:
                    data = r.read(4 * 1024 * 1024)
                if data and data.startswith(b"d"):
                    parse_torrent_bytes(data)
                    return base64.b64encode(data).decode("ascii")
            except Exception:
                continue
        return None

    def inspect_magnet(self, uri, wait_sec=45):
        uri = (uri or "").strip()
        if not uri.lower().startswith("magnet:?"):
            raise ValueError("رابط الماجنت غير صالح (يجب أن يبدأ بـ magnet:?)")
        # محاولة فورية لجلب ملف .torrent من كاش التورنت العام (خلال ثانية واحدة)
        cached_b64 = self._fetch_cached_torrent(uri)
        if cached_b64:
            return self.inspect_torrent_b64(cached_b64)
        if not self.ensure_started():
            raise RuntimeError("محرك التورنت (aria2) غير مثبّت بعد. اضغط «تثبيت aria2 تلقائيًا».")
        sub = TORRENT_META_TMP / secrets.token_hex(6)
        sub.mkdir(parents=True, exist_ok=True)
        gid = None
        try:
            gid = self._rpc("aria2.addUri", [[uri], {
                "dir": str(sub),
                "bt-metadata-only": "true",
                "bt-save-metadata": "true",
                "bt-tracker": PUBLIC_TRACKERS,
            }])
            deadline = time.monotonic() + wait_sec
            tfile = None
            while time.monotonic() < deadline:
                found = list(sub.glob("*.torrent"))
                if found:
                    tfile = found[0]
                    break
                try:
                    st = self._rpc("aria2.tellStatus", [gid, ["status", "errorMessage"]], timeout=3)
                    if st.get("status") == "error":
                        raise RuntimeError(st.get("errorMessage") or "فشل جلب بيانات التورنت")
                    if st.get("status") == "complete":
                        found = list(sub.glob("*.torrent"))
                        if found:
                            tfile = found[0]
                        break
                except RuntimeError:
                    raise
                except Exception:
                    pass
                time.sleep(0.5)
            if not tfile or not tfile.exists():
                raise RuntimeError("تأخر جلب قائمة الملفات من الـ Peers (يمكنك إعادة المحاولة أو الضغط على «تحميل مباشر بدون فحص»).")
            raw = tfile.read_bytes()
            b64_data = base64.b64encode(raw).decode("ascii")
            return self.inspect_torrent_b64(b64_data)
        finally:
            if gid:
                try:
                    self._rpc("aria2.forceRemove", [gid], timeout=2)
                except Exception:
                    pass
                try:
                    self._rpc("aria2.removeDownloadResult", [gid], timeout=2)
                except Exception:
                    pass
            shutil.rmtree(sub, ignore_errors=True)

    def add_magnet(self, uri, save_dir=None, paused=False):
        uri = (uri or "").strip()
        if not uri.lower().startswith("magnet:?"):
            raise ValueError("رابط الماجنت غير صالح (يجب أن يبدأ بـ magnet:?)")
        target_dir = (save_dir or self.mgr.settings.get("last_dir") or self.mgr.settings.get("dir") or str(Path.home() / "Downloads")).strip()
        if save_dir:
            self.mgr.settings["last_dir"] = target_dir
            self.mgr.save()
        os.makedirs(target_dir, exist_ok=True)
        opts = {"dir": target_dir, "bt-tracker": PUBLIC_TRACKERS}
        if paused:
            opts["pause"] = "true"
        gid = self.rpc("aria2.addUri", [[uri], opts])
        return {"ok": True, "gid": gid}

    def add_torrent_b64(self, b64_data, save_dir=None, select_files=None, subfolder="", paused=False):
        if not b64_data:
            raise ValueError("ملف التورنت فارغ")
        target_dir = (save_dir or self.mgr.settings.get("last_dir") or self.mgr.settings.get("dir") or str(Path.home() / "Downloads")).strip()
        if save_dir:
            self.mgr.settings["last_dir"] = target_dir
            self.mgr.save()
        if subfolder:
            target_dir = str(Path(target_dir) / safe_name(subfolder))
        os.makedirs(target_dir, exist_ok=True)
        opts = {"dir": target_dir, "bt-tracker": PUBLIC_TRACKERS}
        if select_files:
            if isinstance(select_files, list):
                sel_str = ",".join(str(int(x)) for x in select_files)
            else:
                sel_str = str(select_files).strip()
            if sel_str:
                opts["select-file"] = sel_str
        if paused:
            opts["pause"] = "true"
        gid = self.rpc("aria2.addTorrent", [b64_data, [], opts])
        return {"ok": True, "gid": gid}

    def pause(self, gid):
        self.rpc("aria2.forcePause", [gid])

    def resume(self, gid):
        self.rpc("aria2.unpause", [gid])

    def remove(self, gid):
        try:
            self.rpc("aria2.forceRemove", [gid])
        except Exception:
            pass
        try:
            self.rpc("aria2.removeDownloadResult", [gid])
        except Exception:
            pass

    def clear_done(self):
        if self.is_running():
            try:
                self._rpc("aria2.purgeDownloadResult", [])
            except Exception:
                pass

    def open_folder(self, gid):
        info = self.rpc("aria2.tellStatus", [gid, ["dir", "files"]])
        files = info.get("files") or []
        target = None
        for f in files:
            if f.get("selected", "true") == "true" and f.get("path") and Path(f["path"]).exists():
                target = Path(f["path"])
                break
        if not target and info.get("dir") and Path(info["dir"]).exists():
            target = Path(info["dir"])
        if not target:
            raise IOError("المجلد غير موجود بعد")
        s = platform.system()
        if s == "Windows":
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                os.startfile(str(target))
        elif s == "Darwin":
            subprocess.Popen(["open", "-R" if target.is_file() else "", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])

    def list_items(self):
        if not self.is_running():
            if not find_aria2():
                return []
            if not self.ensure_started():
                return []
        keys = [
            "gid", "status", "totalLength", "completedLength", "downloadSpeed",
            "uploadSpeed", "connections", "numSeeders", "dir", "files",
            "bittorrent", "errorMessage"
        ]
        try:
            active = self._rpc("aria2.tellActive", [keys]) or []
            waiting = self._rpc("aria2.tellWaiting", [0, 100, keys]) or []
            stopped = self._rpc("aria2.tellStopped", [0, 100, keys]) or []
        except Exception:
            return []

        st_map = {
            "active": "downloading",
            "waiting": "queued",
            "paused": "paused",
            "complete": "completed",
            "error": "error",
            "removed": "removed",
        }
        out = []
        for t in active + waiting + stopped:
            if t.get("status") == "removed":
                continue
            bt = t.get("bittorrent") or {}
            info = bt.get("info") or {}
            files = t.get("files") or []
            # Skip temporary metadata-only probes
            tdir = t.get("dir") or ""
            if str(TORRENT_META_TMP) in tdir:
                continue
            name = info.get("name")
            if not name and files and files[0].get("path"):
                name = Path(files[0]["path"]).name
            if not name:
                name = f"تورنت ({t.get('gid', '')[:6]})"
            tot = int(t.get("totalLength") or 0)
            done = int(t.get("completedLength") or 0)
            dspd = int(t.get("downloadSpeed") or 0)
            uspd = int(t.get("uploadSpeed") or 0)
            eta = (tot - done) / dspd if dspd > 1 and tot > done else None
            out.append({
                "id": t.get("gid", ""),
                "name": name,
                "status": st_map.get(t.get("status"), t.get("status", "queued")),
                "size": tot if tot > 0 else -1,
                "downloaded": done,
                "speed": dspd,
                "up_speed": uspd,
                "peers": int(t.get("connections") or 0),
                "seeders": int(t.get("numSeeders") or 0),
                "eta": eta,
                "error": t.get("errorMessage") or "",
            })
        return out

    def install(self):
        if self.installing:
            return {"ok": True, "msg": "جارٍ التثبيت بالفعل..."}
        self.installing = True
        self.install_msg = "جارٍ تثبيت محرك التورنت (aria2) عبر winget..."

        def run():
            try:
                res = subprocess.run(
                    ["winget", "install", "-e", "--id", "aria2.aria2",
                     "--accept-package-agreements", "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=180
                )
                if find_aria2(force=True):
                    self.install_msg = "تم تثبيت aria2 بنجاح!"
                    self.ensure_started()
                else:
                    err = (res.stderr or res.stdout or "").strip().splitlines()
                    self.install_msg = "فشل التثبيت: " + (err[-1][:120] if err else "نفّذ winget install aria2.aria2")
            except Exception as e:
                self.install_msg = "فشل التثبيت: " + explain(e)
            finally:
                self.installing = False

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def shutdown(self):
        if self.is_running():
            try:
                self._rpc("aria2.saveSession", [], timeout=2)
                self._rpc("aria2.shutdown", [], timeout=2)
            except Exception:
                pass
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None


class Manager:
    def __init__(self):
        APP.mkdir(parents=True, exist_ok=True)
        UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
        dl = Path.home() / "Downloads"
        self.settings = {
            "dir": str(dl if dl.exists() else Path.home()),
            "segments": 8, "max_active": 3, "max_speed": 0,
            "catbox_userhash": "", "confirm_dialog": True, "show_video_btn": True, "ext_updated_notice": False, "category_dirs": {}, "last_dir": ""
        }
        self.items, self.uploads, self.lock, self.slock = {}, {}, threading.RLock(), threading.Lock()
        self._rlock, self._next_time = threading.Lock(), 0.0
        self.installing_ytdlp = False
        self.install_msg = ""
        self.pending_video = None
        self.pending_download = None
        self.pending_magnet = None
        self.popups = {}
        self.vpopups = {}
        self.aria2 = Aria2Engine(self)
        self.update_info = {
            "current": APP_VERSION,
            "latest": APP_VERSION,
            "available": False,
            "notes": "",
            "url": UPDATE_SCRIPT_URL,
            "setup_url": UPDATE_SETUP_URL,
            "checking": False,
            "applying": False,
            "msg": "",
        }
        state_src = STATE if STATE.exists() else (LEGACY_STATE if LEGACY_STATE.exists() else None)
        if state_src:
            try:
                d = json.loads(state_src.read_text("utf-8"))
                self.settings.update(d.get("settings", {}))
                for m in d.get("items", []):
                    it = Item(self, m)
                    if it.status in ("queued", "connecting", "downloading"): it.status = "paused"
                    self.items[it.id] = it
                for u in d.get("uploads", []):
                    ui = UploadItem(self, u)
                    if ui.status in ("uploading", "processing"):
                        ui.status = "error"
                        ui.error = "انقطع الرفع عند إغلاق التطبيق"
                    self.uploads[ui.id] = ui
            except Exception:
                pass
        referenced = {str(Path(u.local_path).resolve()) for u in self.uploads.values() if u.local_path}
        for tf in UPLOAD_TMP.glob("*"):
            try:
                if str(tf.resolve()) not in referenced:
                    tf.unlink(missing_ok=True)
            except Exception:
                pass
        threading.Thread(target=self.scheduler, daemon=True).start()
        threading.Thread(target=self._auto_check_update, daemon=True).start()

    def throttle(self, nbytes, stop):
        kb = self.settings.get("max_speed", 0)
        if kb <= 0 or nbytes <= 0:
            return
        rate = kb * 1024
        with self._rlock:
            now = time.monotonic()
            if self._next_time < now:
                self._next_time = now
            wait = self._next_time - now
            self._next_time = min(self._next_time + nbytes / rate, now + 2.0)
        if wait > 0:
            stop.wait(min(wait, 2.0))

    def save(self):
        with self.slock:
            try:
                data = {"settings": self.settings, "items": [i.meta() for i in list(self.items.values())], "uploads": [u.meta() for u in list(self.uploads.values())]}
                tmp = STATE.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8"); os.replace(tmp, STATE)
            except Exception:
                pass

    def unique(self, d, name, me):
        base, ext = os.path.splitext(name); cand, n = name, 0
        while (Path(d) / cand).exists() or any(o is not me and o.prepared and o.dir == d and o.filename == cand
                                               for o in list(self.items.values())):
            n += 1; cand = f"{base} ({n}){ext}"
        return cand

    def scheduler(self):
        while True:
            time.sleep(0.4)
            with self.lock:
                free = self.settings["max_active"] - sum(i.status in ACTIVE for i in self.items.values())
                q = sorted((i for i in self.items.values() if i.status == "queued"), key=lambda i: i.added)
                for it in q[:max(free, 0)]: it.start()

    def add(self, urls, headers=None):
        added, errs = 0, []
        hdrs = headers if isinstance(headers, dict) else {}
        for u in urls:
            u = u.strip()
            if not u: continue
            p = up.urlparse(u)
            if p.scheme not in ("http", "https") or not p.netloc: errs.append(u); continue
            i = secrets.token_hex(4)
            with self.lock:
                self.items[i] = Item(self, dict(id=i, url=u, dir=self.settings["dir"], headers=dict(hdrs),
                                                filename=safe_name(os.path.basename(p.path)) or "download"))
            added += 1
        self.save()
        return {"added": added, "errors": errs}

    def add_single(self, url, save_dir=None, filename=None, headers=None, start_now=True,
                   category="", remember_cat=False, desc=""):
        url = (url or "").strip()
        p = up.urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("الرابط غير صالح (يلزم http أو https)")
        target_dir = str(Path(save_dir or self.settings.get("last_dir") or self.settings["dir"]).expanduser())
        os.makedirs(target_dir, exist_ok=True)
        self.settings["last_dir"] = target_dir
        if remember_cat and category:
            cdirs = self.settings.setdefault("category_dirs", {})
            cdirs[category] = target_dir
        fname = safe_name(filename or os.path.basename(p.path) or "download")
        i = secrets.token_hex(4)
        with self.lock:
            self.items[i] = Item(self, dict(
                id=i, url=url, dir=target_dir, filename=fname,
                custom_name=bool(filename), desc=str(desc or "").strip()[:300],
                headers=dict(headers) if isinstance(headers, dict) else {},
                status="queued" if start_now else "paused",
            ))
        self.save()
        return {"ok": True, "id": i}

    def add_media(self, url, title, format_id, audio_only=False, ext="mp4", size=-1, headers=None, yt_clients=None, save_dir=None):
        url = (url or "").strip()
        p = up.urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("الرابط غير صالح")
        ext = (ext or ("mp3" if audio_only else "mp4")).lower().lstrip(".")
        fname = safe_name(title or "video")
        if not fname.lower().endswith("." + ext):
            fname = f"{fname}.{ext}"
        target_dir = str(Path(save_dir or self.settings.get("last_dir") or self.settings["dir"]).expanduser())
        os.makedirs(target_dir, exist_ok=True)
        self.settings["last_dir"] = target_dir
        i = secrets.token_hex(4)
        with self.lock:
            self.items[i] = Item(self, dict(
                id=i, url=url, dir=target_dir, filename=fname,
                size=int(size) if size else -1, kind="media",
                format_id=format_id or "", audio_only=bool(audio_only),
                yt_clients=yt_clients,
                headers=headers if isinstance(headers, dict) else {},
            ))
        self.save()
        return {"id": i, "ok": True}

    def install_ytdlp(self):
        if self.installing_ytdlp:
            return {"ok": True, "msg": "جاري التثبيت بالفعل..."}
        self.installing_ytdlp = True
        self.install_msg = "جارٍ تثبيت محرك الفيديو (yt-dlp[default])..."

        def run():
            try:
                res = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-U", "yt-dlp[default]"],
                    capture_output=True, text=True, timeout=180
                )
                if res.returncode == 0 and get_ytdlp(force=True):
                    self.install_msg = "تم تثبيت محرك الفيديو بنجاح!"
                else:
                    err = (res.stderr or res.stdout or "").strip().splitlines()
                    self.install_msg = "فشل التثبيت: " + (err[-1][:120] if err else "جرّب تشغيل setup.bat")
            except Exception as e:
                self.install_msg = "فشل التثبيت: " + explain(e)
            finally:
                self.installing_ytdlp = False

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def refresh_url(self, i, new_url, headers=None):
        new_url = (new_url or "").strip()
        p = up.urlparse(new_url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError("الرابط غير صالح (يلزم http أو https)")
        with self.lock:
            it = self.items.get(i)
            if not it: raise ValueError("التنزيل غير موجود")
            if it.status == "completed": raise ValueError("لا يمكن تحديث رابط تنزيل مكتمل")
            it.stop.set()
            it.stop = threading.Event()
            it.url = new_url
            if isinstance(headers, dict):
                it.headers = headers
            it.error, it.fail_msg, it.speed = "", None, 0
            it.status = "queued"
        self.save()

    def pause(self, i):
        it = self.items.get(i)
        if it and it.status in ("queued",) + ACTIVE: it.stop.set(); it.status, it.speed = "paused", 0; self.save()

    def resume(self, i):
        it = self.items.get(i)
        if it and it.status in ("paused", "error"): it.status = "queued"; self.save()

    def remove(self, i, delete_file=False):
        with self.lock: it = self.items.pop(i, None)
        if not it: return
        it.stop.set()
        def cleanup():
            if it.thread and it.thread.is_alive(): it.thread.join(timeout=20)
            try:
                if it.status != "completed": it.part_path.unlink(missing_ok=True)
                elif delete_file: it.final_path.unlink(missing_ok=True)
            except Exception: pass
        threading.Thread(target=cleanup, daemon=True).start(); self.save()

    def add_upload(self, filepath, filename, is_temp=False, service="catbox", expiry="24h", uid=None,
                   video_mode="faststart", trim_start="", trim_end="", mute=False):
        p = Path(filepath)
        if not p.exists():
            raise ValueError("الملف غير موجود")
        fsize = p.stat().st_size
        service = "litterbox" if service == "litterbox" else "catbox"
        expiry = expiry if expiry in ("1h", "12h", "24h", "72h") else "24h"
        video_mode = video_mode if video_mode in ("faststart", "streamable", "original") else "faststart"
        is_vid = Path(filename or p.name).suffix.lower() in VIDEO_EXTS
        # في وضع الضغط الذكي نسمح بدخول ملفات فيديو أكبر من 200 م.ب لأنها ستصغر قبل الرفع
        if service == "catbox" and fsize > CATBOX_MAX and not (is_vid and video_mode == "streamable"):
            if is_temp:
                p.unlink(missing_ok=True)
            raise ValueError("حجم الملف أكبر من 200 م.ب (الحد الأقصى لـ Catbox الدائم). اختر «ضغط ذكي 720p» أو Litterbox المؤقت.")
        if service == "litterbox" and fsize > LITTERBOX_MAX and not (is_vid and video_mode == "streamable"):
            if is_temp:
                p.unlink(missing_ok=True)
            raise ValueError("حجم الملف يتجاوز 1 ج.ب (الحد الأقصى).")
        uid = uid or secrets.token_hex(4)
        uh = (self.settings.get("catbox_userhash") or "").strip() if service == "catbox" else ""
        ui = UploadItem(self, dict(
            id=uid, filename=safe_name(filename or p.name), size=fsize,
            service=service, expiry="" if service == "catbox" else expiry,
            userhash=uh, video_mode=video_mode, trim_start=str(trim_start or "").strip(),
            trim_end=str(trim_end or "").strip(), mute=bool(mute),
            local_path=str(p), is_temp=is_temp,
        ))
        with self.lock:
            self.uploads[uid] = ui
        ui.start()
        return {"ok": True, "id": uid}

    def upload_from_download(self, dl_id, service="catbox", expiry="72h"):
        it = self.items.get(dl_id)
        if not it or it.status != "completed":
            raise ValueError("الملف غير مكتمل أو غير موجود")
        if not it.final_path.exists():
            raise ValueError("الملف غير موجود على القرص")
        fsize = it.final_path.stat().st_size
        if service == "catbox" and fsize > CATBOX_MAX:
            if fsize <= LITTERBOX_MAX:
                service = "litterbox"
                expiry = "72h"
            else:
                raise ValueError("حجم الملف أكبر من 1 ج.ب ولا يمكن رفعه على Catbox أو Litterbox")
        return self.add_upload(it.final_path, it.filename, is_temp=False, service=service, expiry=expiry)

    def cancel_upload(self, uid):
        u = self.uploads.get(uid)
        if u:
            u.cancel()

    def retry_upload(self, uid):
        u = self.uploads.get(uid)
        if not u:
            raise ValueError("عنصر الرفع غير موجود")
        if not u.local_path or not Path(u.local_path).exists():
            raise ValueError("الملف المؤقت غير موجود، أعد اختيار الملف للرفع")
        if u.service == "catbox":
            u.userhash = (self.settings.get("catbox_userhash") or "").strip()
        u.start()

    def remove_upload(self, uid, delete_remote=False):
        with self.lock:
            u = self.uploads.pop(uid, None)
        if not u:
            return
        u.cancel()
        if delete_remote:
            try:
                u.delete_remote()
            except Exception as e:
                with self.lock:
                    self.uploads[uid] = u
                raise RuntimeError("تعذّر حذف الملف من سيرفر Catbox: " + explain(e))
        u.cleanup_temp()
        self.save()

    def clear_done_uploads(self):
        for uid, u in list(self.uploads.items()):
            if u.status == "completed":
                with self.lock:
                    self.uploads.pop(uid, None)
                u.cleanup_temp()
        self.save()

    def set_settings(self, d):
        s = self.settings
        if d.get("dir"):
            p = Path(d["dir"]).expanduser(); p.mkdir(parents=True, exist_ok=True); s["dir"] = str(p)
        s["segments"] = min(16, max(1, int(d.get("segments", s["segments"]))))
        s["max_active"] = min(8, max(1, int(d.get("max_active", s["max_active"]))))
        s["max_speed"] = max(0, int(d.get("max_speed", s.get("max_speed", 0))))
        if "catbox_userhash" in d:
            s["catbox_userhash"] = str(d.get("catbox_userhash") or "").strip()[:80]
        if "confirm_dialog" in d:
            s["confirm_dialog"] = bool(d.get("confirm_dialog"))
        if "autostart" in d:
            s["autostart"] = bool(d.get("autostart"))
            set_windows_autostart(s["autostart"])
        if "show_video_btn" in d:
            s["show_video_btn"] = bool(d.get("show_video_btn"))
        self.save()
        self.aria2.apply_settings()


    def _auto_check_update(self):
        time.sleep(3.5)
        self.check_update(manual=False)

    def check_update(self, manual=False):
        if self.update_info.get("checking") or self.update_info.get("applying"):
            return self.update_info
        self.update_info["checking"] = True
        if manual:
            self.update_info["msg"] = "جارٍ التحقق من وجود تحديثات..."

        def run():
            try:
                url = f"{UPDATE_MANIFEST_URL}?t={int(time.time())}"
                req = rq.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
                with rq.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8", errors="replace"))
                latest = str(data.get("version") or APP_VERSION).strip()
                notes = str(data.get("notes") or "").strip()[:300]
                dl_url = str(data.get("url") or UPDATE_SCRIPT_URL).strip()
                setup_url = str(data.get("setup_url") or UPDATE_SETUP_URL).strip()
                avail = _ver_tuple(latest) > _ver_tuple(APP_VERSION)
                self.update_info.update({
                    "latest": latest,
                    "available": avail,
                    "notes": notes,
                    "url": dl_url,
                    "setup_url": setup_url,
                    "msg": f"يتوفر تحديث جديد (v{latest})" if avail else ("أنت تستخدم أحدث إصدار بالفعل!" if manual else ""),
                })
            except Exception as e:
                if manual:
                    self.update_info["msg"] = "تعذّر الاتصال بـ GitHub للتحقق من التحديث: " + explain(e)
            finally:
                self.update_info["checking"] = False

        threading.Thread(target=run, daemon=True).start()
        return self.update_info

    def apply_update(self):
        if self.update_info.get("applying"):
            return {"ok": True, "msg": "جارٍ التحديث بالفعل..."}
        self.update_info["applying"] = True
        self.update_info["msg"] = "جارٍ تنزيل التحديث الجديد..."

        def run():
            try:
                dl_url = self.update_info.get("url") or UPDATE_SCRIPT_URL
                sep = "&" if "?" in dl_url else "?"
                req = rq.Request(f"{dl_url}{sep}t={int(time.time())}", headers={"User-Agent": UA, "Cache-Control": "no-cache"})
                with rq.urlopen(req, timeout=30) as r:
                    new_bytes = r.read()
                new_text = new_bytes.decode("utf-8")
                if "APP_TITLE" not in new_text or "class Manager:" not in new_text:
                    raise RuntimeError("الملف المُنزّل غير صالح.")
                compile(new_text, "aldawli_update.py", "exec")

                if getattr(sys, "frozen", False):
                    base_target = app_dir() / "aldawli.py"
                    try:
                        tmp = base_target.with_suffix(".py.new")
                        tmp.write_bytes(new_bytes)
                        os.replace(tmp, base_target)
                        target = base_target
                        # حذف أي نسخة قديمة في مجلد المستخدم إن نجح التحديث في مجلد التطبيق
                        (APP / "aldawli.py").unlink(missing_ok=True)
                    except PermissionError:
                        APP.mkdir(parents=True, exist_ok=True)
                        target = APP / "aldawli.py"
                        tmp = target.with_suffix(".py.new")
                        tmp.write_bytes(new_bytes)
                        os.replace(tmp, target)
                    ext_dir = app_dir() / "aldawli-ext"
                else:
                    target = Path(__file__).resolve()
                    tmp = target.with_suffix(".py.new")
                    tmp.write_bytes(new_bytes)
                    os.replace(tmp, target)
                    ext_dir = target.parent / "aldawli-ext"
                ext_dir.mkdir(parents=True, exist_ok=True)
                ext_updated = False
                for ef in ("manifest.json", "background.js", "video_btn.js"):
                    try:
                        eurl = f"https://raw.githubusercontent.com/{UPDATE_REPO}/main/aldawli-ext/{ef}?t={int(time.time())}"
                        ereq = rq.Request(eurl, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
                        with rq.urlopen(ereq, timeout=15) as er:
                            ebytes = er.read()
                        if ebytes:
                            epath = ext_dir / ef
                            if not epath.exists() or epath.read_bytes() != ebytes:
                                epath.write_bytes(ebytes)
                                ext_updated = True
                    except Exception:
                        pass
                if ext_updated:
                    self.settings["ext_updated_notice"] = True
                    self.save()

                self.update_info["msg"] = "تم التحديث بنجاح! جارٍ إعادة التشغيل..."

                # إغلاق المحركات وحفظ الحالة ثم إعادة تشغيل السكربت تلقائيًا
                self.shutdown()
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform.system() == "Windows" else 0
                if getattr(sys, "frozen", False):
                    subprocess.Popen(
                        [sys.executable, "--port", str(CURRENT_PORT), "--no-window"],
                        cwd=str(app_dir()),
                        creationflags=creationflags,
                    )
                else:
                    subprocess.Popen(
                        [sys.executable, str(target), "--port", str(CURRENT_PORT), "--no-window"],
                        cwd=str(target.parent),
                        creationflags=creationflags,
                    )
                time.sleep(0.4)
                os._exit(0)
            except Exception as e:
                self.update_info["applying"] = False
                self.update_info["msg"] = "فشل التحديث: " + explain(e)

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def state(self):
        its = sorted(self.items.values(), key=lambda i: -i.added)
        ups = sorted(self.uploads.values(), key=lambda u: -u.added)
        pv = self.pending_video
        self.pending_video = None
        pd = self.pending_download
        self.pending_download = None
        pm = self.pending_magnet
        self.pending_magnet = None
        js_rts = list(detect_js_runtimes().keys())
        tors = self.aria2.list_items() if self.aria2.is_running() else []
        tor_spd = sum(t["speed"] for t in tors if t["status"] == "downloading")
        return {
            "items": [i.api() for i in its],
            "uploads": [u.api() for u in ups],
            "torrents": tors,
            "torrent_engine": {
                "ready": bool(find_aria2()),
                "running": self.aria2.is_running(),
                "installing": self.aria2.installing,
                "install_msg": self.aria2.install_msg,
            },
            "settings": self.settings,
            "speed": sum(i.speed for i in its if i.status == "downloading") + tor_spd,
            "upload_speed": sum(u.speed for u in ups if u.status == "uploading"),
            "media_engine": {
                "ytdlp": bool(get_ytdlp()),
                "ffmpeg": bool(find_ffmpeg()),
                "ejs": has_ytdlp_ejs(),
                "js_runtimes": js_rts,
                "installing": self.installing_ytdlp,
                "install_msg": self.install_msg,
            },
            "pending_video": pv,
            "pending_download": pd,
            "pending_magnet": pm,
            "update": self.update_info,
        }

    def shutdown(self):
        for i in list(self.items.values()): i.stop.set()
        for u in list(self.uploads.values()): u.cancel()
        self.aria2.shutdown()
        time.sleep(0.3); self.save()


MGR = None


def open_path(it, what):
    p = it.final_path if it.status == "completed" else it.part_path
    if not p.exists(): raise IOError("الملف غير موجود")
    s = platform.system()
    if what == "file":
        if s == "Windows": os.startfile(str(p))
        else: subprocess.Popen(["open" if s == "Darwin" else "xdg-open", str(p)])
    elif s == "Windows": subprocess.Popen(["explorer", "/select,", str(p)])
    elif s == "Darwin": subprocess.Popen(["open", "-R", str(p)])
    else: subprocess.Popen(["xdg-open", str(p.parent)])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def is_ext_origin(self):
        o = self.headers.get("Origin") or ""
        return o.startswith("chrome-extension://") or o.startswith("moz-extension://")

    def send_any(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, str)): body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
        if self.is_ext_origin():
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; manifest-src 'self'; img-src 'self' data: https: http:; media-src 'self' blob: https: http:"
        )
        self.end_headers(); self.wfile.write(body)

    def guard(self, need_token=True):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in ("127.0.0.1", "localhost") or (
                need_token and not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN)):
            self.send_any(403, {"error": "forbidden"}); return False
        return True

    def do_OPTIONS(self):
        if self.path in ("/api/ext/add", "/api/ext/video", "/api/ext/torrent") and self.is_ext_origin():
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
        else:
            self.send_any(403, {"error": "forbidden"})

    def do_GET(self):
        clean_path = self.path.split("?", 1)[0]
        if clean_path == "/":
            if self.guard(False): self.send_any(200, PAGE.replace("__TOKEN__", TOKEN), "text/html; charset=utf-8")
        elif clean_path == "/favicon.ico":
            if self.guard(False):
                self.send_any(200, ensure_icon_file().read_bytes(), "image/x-icon")
        elif clean_path == "/icon.png":
            if self.guard(False):
                png_file = app_dir() / "icon.png"
                data = png_file.read_bytes() if png_file.exists() else base64.b64decode(ICON_PNG_B64)
                self.send_any(200, data, "image/png")
        elif clean_path == "/manifest.webmanifest":
            if self.guard(False):
                manifest = {
                    "name": APP_TITLE,
                    "short_name": APP_TITLE,
                    "start_url": "/",
                    "display": "standalone",
                    "background_color": "#0d1218",
                    "theme_color": "#2447d6",
                    "icons": [
                        {"src": "/icon.png?v=3", "sizes": "256x256", "type": "image/png"}
                    ]
                }
                self.send_any(200, manifest, "application/manifest+json; charset=utf-8")
        elif clean_path == "/popup":
            if self.guard(False):
                qs = up.parse_qs(up.urlparse(self.path).query)
                pid = (qs.get("pid") or [""])[0]
                html = POPUP_PAGE.replace("__TOKEN__", TOKEN).replace("__PID__", pid)
                self.send_any(200, html, "text/html; charset=utf-8")
        elif clean_path == "/api/popup_data":
            if self.guard():
                qs = up.parse_qs(up.urlparse(self.path).query)
                pid = (qs.get("pid") or [""])[0]
                data = MGR.popups.get(pid)
                if not data:
                    self.send_any(404, {"error": "الطلب منتهي الصلاحية"})
                else:
                    self.send_any(200, {
                        "url": data["url"],
                        "headers": data.get("headers") or {},
                        "settings": MGR.settings,
                    })
        elif clean_path == "/vpopup":
            if self.guard(False):
                qs = up.parse_qs(up.urlparse(self.path).query)
                vid = (qs.get("vid") or [""])[0]
                html = VPOPUP_PAGE.replace("__TOKEN__", TOKEN).replace("__VID__", vid)
                self.send_any(200, html, "text/html; charset=utf-8")
        elif clean_path == "/api/vpopup_data":
            if self.guard():
                qs = up.parse_qs(up.urlparse(self.path).query)
                vid = (qs.get("vid") or [""])[0]
                data = MGR.vpopups.get(vid)
                if not data:
                    self.send_any(404, {"error": "الطلب منتهي الصلاحية"})
                else:
                    self.send_any(200, {
                        "url": data["url"],
                        "headers": data.get("headers") or {},
                        "settings": MGR.settings,
                    })
        elif clean_path == "/api/ext/config":
            if self.guard(need_token=not self.is_ext_origin()):
                self.send_any(200, {"show_video_btn": bool(MGR.settings.get("show_video_btn", True))})
        elif clean_path == "/api/state":
            if self.guard(): self.send_any(200, MGR.state())
        else:
            self.send_any(404, {"error": "not found"})

    def _handle_raw_upload(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            service = (self.headers.get("X-Service") or "catbox").strip().lower()
            expiry = (self.headers.get("X-Expiry") or "24h").strip().lower()
            vmode = (self.headers.get("X-Video-Mode") or "faststart").strip().lower()
            t_start = (self.headers.get("X-Trim-Start") or "").strip()
            t_end = (self.headers.get("X-Trim-End") or "").strip()
            mute = (self.headers.get("X-Mute") or "0").strip() == "1"
            raw_name = up.unquote(self.headers.get("X-Filename") or "file.bin")
            fname = safe_name(raw_name)
            is_vid = Path(fname).suffix.lower() in VIDEO_EXTS
            max_sz = LITTERBOX_MAX if (service == "litterbox" or (is_vid and vmode == "streamable")) else CATBOX_MAX
            if n <= 0:
                return self.send_any(400, {"error": "الملف فارغ"})
            if n > max_sz:
                return self.send_any(400, {"error": "حجم الملف أكبر من الحد المسموح (200 م.ب لـ Catbox الدائم، أو اختر ضغط ذكي 720p)"})
            UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
            uid = secrets.token_hex(4)
            ext = re.sub(r"[^a-zA-Z0-9.]", "", Path(fname).suffix.lower())[:16]
            tmp_path = UPLOAD_TMP / f"{uid}{ext or '.bin'}"
            rem = n
            with open(tmp_path, "wb") as f:
                while rem > 0:
                    chunk = self.rfile.read(min(65536, rem))
                    if not chunk:
                        break
                    f.write(chunk)
                    rem -= len(chunk)
            if rem > 0:
                tmp_path.unlink(missing_ok=True)
                return self.send_any(400, {"error": "انقطع إرسال الملف قبل اكتماله"})
            r = MGR.add_upload(
                tmp_path, fname, is_temp=True, service=service, expiry=expiry, uid=uid,
                video_mode=vmode, trim_start=t_start, trim_end=t_end, mute=mute
            )
            self.send_any(200, r)
        except Exception as e:
            self.send_any(400, {"error": explain(e)})

    def do_POST(self):
        is_ext = self.path in ("/api/ext/add", "/api/ext/video", "/api/ext/torrent") and self.is_ext_origin()
        if not self.guard(need_token=not is_ext): return
        if self.path == "/api/upload/raw":
            return self._handle_raw_upload()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(min(n, 1 << 20)) or b"{}")
            p, r = self.path, {"ok": True}
            if p == "/api/add": r = MGR.add(d.get("urls", []))
            elif p == "/api/add_single":
                r = MGR.add_single(
                    d.get("url"), d.get("dir"), d.get("filename"), d.get("headers"),
                    bool(d.get("start_now", True)), d.get("category", ""),
                    bool(d.get("remember_cat", False)), d.get("desc", "")
                )
            elif p == "/api/probe_direct":
                r = probe_direct_url(d.get("url", ""), d.get("headers"))
            elif p == "/api/browse_dir":
                r = {"dir": browse_folder_dialog(d.get("initial", ""))}
            elif p == "/api/disk_free":
                r = {"free": disk_free_bytes(d.get("dir", ""))}
            elif p == "/api/upload/from_item":
                r = MGR.upload_from_download(d["id"], d.get("service", "catbox"), d.get("expiry", "72h"))
            elif p == "/api/upload/cancel": MGR.cancel_upload(d["id"])
            elif p == "/api/upload/retry": MGR.retry_upload(d["id"])
            elif p == "/api/upload/remove": MGR.remove_upload(d["id"], bool(d.get("delete_remote")))
            elif p == "/api/upload/clear_done": MGR.clear_done_uploads()
            elif p == "/api/torrent/inspect_file": r = MGR.aria2.inspect_torrent_b64(d.get("data", ""))
            elif p == "/api/torrent/inspect_magnet": r = MGR.aria2.inspect_magnet(d.get("uri", ""))
            elif p == "/api/torrent/magnet":
                r = MGR.aria2.add_magnet(d.get("uri", ""), d.get("dir"), bool(d.get("paused", False)))
            elif p == "/api/ext/torrent":
                uri = (d.get("uri") or "").strip()
                if d.get("inspect", True):
                    MGR.pending_magnet = uri
                    threading.Thread(target=show_or_open_main_window, daemon=True).start()
                    r = {"ok": True, "inspect": True}
                else:
                    r = MGR.aria2.add_magnet(uri)
            elif p == "/api/torrent/file":
                r = MGR.aria2.add_torrent_b64(
                    d.get("data", ""), d.get("dir"), d.get("select_files"),
                    d.get("subfolder", ""), bool(d.get("paused", False))
                )
            elif p == "/api/torrent/pause": MGR.aria2.pause(d["id"])
            elif p == "/api/torrent/resume": MGR.aria2.resume(d["id"])
            elif p == "/api/torrent/remove": MGR.aria2.remove(d["id"])
            elif p == "/api/torrent/clear_done": MGR.aria2.clear_done()
            elif p == "/api/torrent/open": MGR.aria2.open_folder(d["id"])
            elif p == "/api/torrent/install": r = MGR.aria2.install()
            elif p == "/api/torrent/start_engine":
                ok = MGR.aria2.ensure_started()
                r = {"ok": ok}
            elif p == "/api/ext/add":
                urls = [u.strip() for u in (d.get("urls") or []) if u and u.strip()]
                if len(urls) == 1 and MGR.settings.get("confirm_dialog", True):
                    pid = secrets.token_hex(6)
                    MGR.popups[pid] = {"url": urls[0], "headers": d.get("headers") or {}, "ts": time.time()}
                    # تنظيف الطلبات القديمة
                    for k in list(MGR.popups.keys()):
                        if time.time() - MGR.popups[k]["ts"] > 600:
                            MGR.popups.pop(k, None)
                    opened = open_popup_window(pid)
                    if not opened:
                        MGR.pending_download = {"url": urls[0], "headers": d.get("headers") or {}}
                        threading.Thread(target=bring_window_to_front, daemon=True).start()
                    r = {"ok": True, "added": 1, "popup": opened}
                else:
                    r = MGR.add(urls, d.get("headers"))
            elif p == "/api/ext/video":
                vurl = (d.get("url") or "").strip()
                vhdrs = d.get("headers") or {}
                vid = secrets.token_hex(6)
                MGR.vpopups[vid] = {"url": vurl, "headers": vhdrs, "ts": time.time()}
                for k in list(MGR.vpopups.keys()):
                    if time.time() - MGR.vpopups[k]["ts"] > 600:
                        MGR.vpopups.pop(k, None)
                opened = open_video_popup_window(vid)
                if not opened:
                    MGR.pending_video = {"url": vurl, "headers": vhdrs}
                    threading.Thread(target=show_or_open_main_window, daemon=True).start()
                r = {"ok": True, "popup": opened}
            elif p == "/api/media/probe": r = probe_media(d.get("url", ""), d.get("headers"))
            elif p == "/api/media/add":
                r = MGR.add_media(d.get("url"), d.get("title"), d.get("format_id"),
                                  d.get("audio_only", False), d.get("ext", "mp4"),
                                  d.get("size", -1), d.get("headers"), d.get("yt_clients"),
                                  d.get("dir"))
            elif p == "/api/media/install": r = MGR.install_ytdlp()
            elif p == "/api/create_shortcut":
                lnk = create_desktop_shortcut()
                r = {"ok": True, "path": lnk}
            elif p == "/api/register_magnet":
                r = register_magnet_protocol()
            elif p == "/api/refresh_url": MGR.refresh_url(d["id"], d.get("url", ""), d.get("headers"))
            elif p == "/api/pause": MGR.pause(d["id"])
            elif p == "/api/resume": MGR.resume(d["id"])
            elif p == "/api/pause_all": [MGR.pause(i) for i in list(MGR.items)]
            elif p == "/api/resume_all": [MGR.resume(i) for i in list(MGR.items)]
            elif p == "/api/remove": MGR.remove(d["id"], bool(d.get("delete_file")))
            elif p == "/api/clear_done":
                [MGR.remove(i) for i, it in list(MGR.items.items()) if it.status == "completed"]
            elif p == "/api/open": open_path(MGR.items[d["id"]], d.get("what", "folder"))
            elif p == "/api/settings": MGR.set_settings(d)
            elif p == "/api/dismiss_ext_notice":
                MGR.settings["ext_updated_notice"] = False
                MGR.save()
            elif p == "/api/update/check": r = MGR.check_update(manual=True)
            elif p == "/api/update/apply": r = MGR.apply_update()
            elif p == "/api/quit":
                def bye(): time.sleep(0.3); MGR.shutdown(); os._exit(0)
                threading.Thread(target=bye, daemon=True).start()
            else: return self.send_any(404, {"error": "not found"})
            self.send_any(200, r)
        except Exception as e:
            self.send_any(400, {"error": explain(e)})


def open_window(url):
    s, c = platform.system(), []
    if s == "Darwin":
        c = [f"/Applications/{a}.app/Contents/MacOS/{b}" for a, b in
             (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"), ("Brave Browser", "Brave Browser"))]
    elif s == "Windows":
        for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            b = os.environ.get(k)
            if b: c += [os.path.join(b, r"Google\Chrome\Application\chrome.exe"), os.path.join(b, r"Microsoft\Edge\Application\msedge.exe")]
    else:
        c = [shutil.which(x) for x in ("google-chrome", "chromium", "microsoft-edge", "chromium-browser")]
    profile_dir = APP / "app_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    for x in c:
        if x and os.path.exists(x):
            subprocess.Popen([
                x,
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1140,760",
            ])
            if s == "Windows":
                threading.Thread(target=apply_windows_taskbar_icon, daemon=True).start()
            return
    webbrowser.open(url)


def main():
    global MGR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--shortcut", action="store_true")
    ap.add_argument("--register-magnet", action="store_true")
    ap.add_argument("--magnet", type=str, default="")
    a = ap.parse_args()
    if a.shortcut:
        try:
            lnk = create_desktop_shortcut()
            print("Desktop shortcut created successfully:")
            print(lnk)
            return
        except Exception as e:
            print("Failed to create shortcut:", e)
            raise SystemExit(1)
    if a.register_magnet:
        try:
            register_magnet_protocol()
            print("Magnet protocol registered successfully!")
            return
        except Exception as e:
            print("Failed to register magnet protocol:", e)
            raise SystemExit(1)
    if a.magnet:
        if _send_magnet_to_running(a.magnet, a.port):
            return
    MGR = Manager()
    if a.magnet:
        MGR.pending_magnet = a.magnet
    srv = None
    for port in range(a.port, a.port + 30):
        try: srv = ThreadingHTTPServer(("127.0.0.1", port), Handler); break
        except OSError: continue
    if not srv: raise SystemExit("تعذّر العثور على منفذ متاح")
    global CURRENT_PORT
    CURRENT_PORT = port
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP_TITLE} يعمل على {url}  (اضغط Ctrl+C للإنهاء)")
    start_windows_tray()
    if not a.no_window: open_window(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: MGR.shutdown()


ICON_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAABFDklEQVR42u29ebgk11Un+Dv3RuSeb696tUkllRZblmQLeaHB0CW7PQPdTBvs7tLYMI3NYhobsAFBgw24VMZmxwyGARr8DbjxDP6qjIFmGTAGVRkaGVvGtmxJ1lKqkkq1vnpL7pkRce+ZP+6NiBuRke/lK5UMNM768qt8mRGRkffs5/zOucCXH19+fPnxL/dB//i3wAT+l7z6xP9CGIDp8GHQcUDcBQD3Qr+LSPOXhRCHD7M4DggA2PnwMT527JD+UjEGPddEP3TU/LBjd5MqPOTQ09Xbb7imArS2vlzr6t/hZpecnfYrW7krTXHi7OwsPv/EIMBf7u4VLstRlmbd8Jwyw3PDAMx08F7IE0coSt57wRdKr3zjTc9frOiXliTfUZK4SRDvBXhOCqqDmdk1BwSAObUO+SXgxIAAzLn37d+6+Fxyzx+7ps5eHzz2nQCDGGBzk2O3RTx+K3Zd4uVhIiKteKBYtzSL85HCE/2AP9fu41MffzR4CH+ytx+fdvDwfd4JHNc4ckT/E2cAI/GptD/gf8Mv3PrK2Rq9tlLCK8uCb6zWKwABUQiEISOKIkSRKuChAgqN0aLomM3Pyx+WHDB2PBcwR/Y45gmCyfnvcM5z3vOkgOd58H0PnicBAMN+D8NQPz0Y6L9pddVHPnY8+nN82jDDoaMsr7ZGuGoMYG7OEP7APZ2dL9wn3zBXozc065Vb/RIw7Ct0ewP0Ao5GIRBGTJqZmI1AJaLDRZKTl/r8gnLBcbn3CAXXHidMIVGd95KXhcchp7G4mDnNj7U/nFgIZk8Qlz1CtUKyUa9QrVqFihTa3f6pdo8/+NiZ3m8/9sHrTgHAoUMsjx2bYFK/9AzgSP2hLzRe/ZXXvW1xRr51bq6yMxwprLf6uj2AHoUsNEMQCATAdf3JkTdm56a4iE5c8DlvKqn5t6ngOEZqcghFattV8TyRR1ITUKxVxs+xTM+A1oYBiViXfHCzKrE4W5aVah0bG9325Xb0W5998OzPXvjzO1cOH2Zx5Aj42WqDZ8UA5iZIA8C/eXf7G3cveD+3tFC9edQfYqUVRJ0hC6VJEBEExQLOBSqZswLFRSp/WnV/JZI52dbnGWRrdb+JT7KpObG+BQGszVMxQ4J1o0p6ad736vVZrK61z55fGb7z47927f99NbQBPWuV/798tv6NX3fDL+1eqr3JFxEurg2i9R5LzURSEIjs1xRK5gTCj2lw3kLii6V+24QvMB+8KRFzH026rykIP4lBNANKMQDNczVSu5YqHkQV5y52/uAfHjz13Rf/8uWXDh68zztx4hXRl4wBDh5m78QRiu645/QLbrp28f/ds7PxovZ6S53f0BQoITwBw8n28lToiP1TlHouIO40Ur+1up+K+LnrcWISNbQGoojhCc27FqRaXJj3Ll7unD55uv2fHvy95/9tTJPnnAHiL/rKHzlz143XLHxkYbY0f36lHa12yRMESCJD/fjSlLdSX5Z63uTa2QgoXSvWxlHQWiNSjPkGRfuW616ro4JTT6+/4YEPvuBDL/6uB/xP/+ZLwueMATLE3zf3p7N1UXvqYl91R0L60hKdAEKs+mFdvn+iUr+JM/ill/r8/XO6XmyYgrU2/zMjjBi1klbX7a6IwUjS46dWX/+Z37v9Q9vVBFMzQOxsvOSHnz540zVzfzZbpdqpC309CIXwPWFITTnCE0BsfXwqJvhzI/Xpm+RI1Rj/cDHBqCBsfO6lvujanNwng8GaLSMYbRBGGr7Q+oZ9VQwCIU4+efn1nzl6x4e24xNMxwCHWeAI6dvf9uTzbrlu4e8Xmt7sk+e6hviSABIJ8cnRAs46bpHUuXpST1Zq0mdKeGFuDUSAcHMOALROz9Ocfm/MDJQkJ/k5lvrsgrHLBAwwa8MImgHWCCMNT7C+YV8FvQHh0VOXX/HIR1788UOHjspjx+5WV4EBmA4dgjiGM6VX31n51N6dzVufPLuheiMhPc9E9WSje8MElvREyATVz6HUx4QxcbT5ak8AJQ8o+4SyT/Al4EuCFCbUkoIy6l5ZBlAKCBUjCIFRyBgGRt2GESc5ipiR+DmR+qy5ZMcbTDSAfa21BrNGGGhUfNY37W/SpdXhpU9/Ye2OS8dfdpHuvZe2Sh97W4d7Jsnzqp945lf2Li/cevbCStQewCt56WI7ia1cfp6yDuBVlHokkmuI7wmgUSHUy4RamVApETzpECuJswkMMhKvDUWJDKPECZmYa2ONECrGYMToDxm9gcYg0IiUZQbhMMNVkfpcGponnc+JVpAS6A9ZPHW2ra6/Zmn5lutHHyCirzt0iMUxHLlyDRDb/Zf9yJlvuGX/4p8Eg050ekV5UhKElXZBwtEARvJjM2AMgcsVz1LqHaJrDUjBqJUJszVCs2IkXQrzPWHEiLS5tqUzIsXojxi9ISOITGgFS8SyJFQt80hJYGbYS0EKoCQNmSPNGAWMzoDR6mr0hwylzLGCYmF9FlKf15KxPUocQYZOzIC2jKzBWiMINPbt9KK5uUXvkcee+Z7PfvjOX9sqUSS3UP048bzvqt65TH/arHmzT54fEINIjKn8LPGJqIDD6NlJvSW8UoAvgcUmYc+CwPKcwExVQBIwioBWn3FxQ2GjpyGEOS9SwFpX48K6wkbHSHCoDOGiiBFEhjHafY12n6G0+Q7WwCgALq1rtHoKWjMEEaolQrMmMFcXaFYFpCAEERCEnDDUFUv9FnWKjKax5gCaE43T6UY032Que+Jft+rf+juf/NO93SOAwIkTvC0TcOgoxJG7Sf3rt5/5/uUdO687e+FyFETwfI9NxTRmd4pvnFLvOWOdn53UE+JsGFDxgYU5gfk6oVIy3zkMGKsDhXaf0R9pDEOg6gO7FyRKHjAcMVZaCoPAVJykyPlucYqaYmbRuLyh0RsQlmYkqiXCXINwblVjZUOjUlKolQkzNUP8Zk2gURNYmtVY7yqstTWGI/M9sVXcrtTnY+XC0DTxct2EERAq0DMX+urA/p0zB3aPfpKI3rSZKaBJ9XwQsOd7zi585T75eK1amn3ibB9EJIQw6t+oflgtIFJNINzY33UQrszWRzqWeIGlJqHsG03QGzLWOkZiR1FaIKqVgV3zEp4AWj3GpVZkJTct9pi6RGwiUjuuNJLYRbM5buecwGxNIFLA+TWF3lAnPkXJI8zUCfNNgXqFIARhFDAubyisthTCyNUGz0Lq44JUEgbqxBRoFZsCDa3M+1Gk+YZ9VdZM+jOPtG47d9/LHsNhJti6jfsQhQmfe49LgPiGJr5tYX5hfmW1r5VikQi3dUJiJkzZ3GiHlDl5PItSEOrkiU+xutfAQkPgxl0SexcEfAm0e4xTFxWeOB9hpW1UuSdjRw5YnpOQAljtaFxYjwDNEM7iCWh0eyE2OiFUFEHrCO1ugFY3BLG23raGsPd1YU1htaMhBbBrXqDiG/b2BBBGGisbCifPhjh1PkKrq+FLYO+Shxv3+liYEYmzSWNSz+O5hVz1M6PuNY9LvXbMgHsuM52/PNTN5oy3b2fprQD40K3Fwl70JjEY9F2f9v79Nbu/MDdTu+nRp9sMCCv9xtab10byhXkTwqaByQmgaRMPfpKtjxRQ9oyNn6sbR7I/YlzaYKx3TTZMxPUGuyaCGHsWjMre6GlcXI8sd8cSxGCl0R0ovPy2Cv7tSxu4cW8JQgCnzwf42Kd7+Kt/6KHkS3hSmEq9DRG0ZizPS8w1BAYjxjMrxh+Is95smVUQMFsXWJ6XqFUEWDPWuwrnVhRGoYlUeAqpdzOmScLKCQM1p1LPyjiC2dcMpTTftL+B4TDc+Pv72ze2H/7qNWPosol5r8DzF3SM1IsbT901O9O8eXWjrSMF4XtW/UAkoR875UsSlNTKmWz4R8iagC08fOZY6gm75wUqvvHmV1oaKy2TAxfCqFVmKwFW6yzNGeJ3B4yVjciqfOuRs1msMFR4++sX8Nqvncl87/W7fLziK+p41Wd6eNd/u4Qw4gwTCCJc2lDwBKFeJeyYJVxYt4Awq1Q9e09rHY12T2PHnMCOWYnFpkS9LHDucoTVjoIUW/hB+bA5Jn6cDeSs1LNznOtvaA1aWeura/bsnN9/U/Dazz+M9x88eFyeOIFoUxNw6QXHCQAWGvJu3y/xRlfr5Idm4k/OqK0kQeHeBXNqMopUXU7lMwN7FwT2L0mUPWPDnzivcG5VQzNDyjg0Sk2O1kCzJjBTIwQhY6UVOV9v4kWCRrsb4s3/fg6v/doZKCuxOi63ahMivuIr6vixb1nCcBiAWAGs04XWwKWNCEHEmKmb79Mq5XFtf5YnzDqcv6zwxDMhWl2Fsg/s3yWxb0maWj+zEx6PI5kSs5r5EAlmMVH5CRNox7rGJofR7iiwVjxfl4cA4K677trSB6ATR14R4cUP+FWfXjUY9GkQaEHkmvliwmccAvfmEl+AJ+TejcqXArh+p8DyrInBL6xpPHlBoT/U8CS79ZE0rmDAk0ZjMDMutxWCyDh8cb4cYPQGEW65xsM3v2o2UdVSIIndpQA8SYgU41UvaeKrX1BBpxeawNU6W4IYQci4vGEWe7Ep4Xsp4VNJNbfnSWAw0jh5LsS5VcOUywsSB/Z4kMJENTQxhczZ9WPkNECqBYxTmH0PbMLVIGDR6XSpWhEvb9zx8R0GvMM0mQEOmw9ve9nyLZWyv7/dGbDWllkzCQmbYHFTkzlnML5pl8uZx1WdUsZ5u2FZYq5m4umnLimcXVMAjMp31ZzjIUFrYL4uUPKAzsAkZySlGkIzA9AYDkN87e1V46NYs1XoEFmf4pUvbiAMI7BWRovEGTcBdPoa3T6j5ANzDWGSSTwuzbGfAgBnVxROn48QhMBcXeCGPSWUfUqZgCcUGN01Zef6zponGirWVhpuBZFa7aGu1uv1a3ZVX2pM/DExkQEO4rgAgPkGv6xSnaHuQCtK4DxZD1+7miBvl3JSkVX7aVijtIntDyxL1MpAfwQ8eV5hravhCWwK1tD23JkaIVTAeicNzzj+jjhlqCPs3+VPVRkjAvbt8CFJQWuV2L54wQnAalsjCIGZmkClBMsE4x5+zBe+ZKx3Ipx8JkBvyKhXCDfs9VEpWSYgNx/gCJkrOclTZ00tsyW+q3wN8xMBvYHWnvTRrMuvAoBLl3bQlmFguSy/AgCGQerosHNxIxWOanJuULOz+Hm17YAulWZUfOD6ZePs9YaMk+cj9Ecanpws9eyYnbm6Sf22exqj+F4dDWUqZ4aQ/f52wDIMsEqkijVnqo2jgNHuaUhBmKuL8aRO/jcz4AnCYMg4+UyI3oBR8QkH9violMlCvjJhXCoorkW1aW3OmQDkMAPmDaO6RyNFSkUolfEVALBz5wpPZIC7YJyEsiduiqIIodJEmcSTK+VZZzAto+ZjfcckWMSs0ibMM8QndPqMkxcUQmUzdVyM0nHLopUyoVEVCCNGq28yOK5z5DIlK4W1TliQiJlAfgY0q4zkpSoXIGK0ugphyGhUBSploxE3jeutCYkixsmzITp9jUqZcGCP55iDNNWbVf9ZM8su8TUyFcJY+8VMGylNo9EIJZ8OAMCHTYmYihiA3mUzRVLw7jCMoJU1UTmvP8OBOubKWD1lHRdk1JVZKE8w9u8wxO8NGKcvRSbEIxeokZV614FgBuZqVvr7Rh3TWIrUVY/GiduWBtA6UX15bUQAwhBo90xYN1sXhjG4IOuXYwIhTMRx+nyAXl+jUiLs3+3DkwaTkGUgJ+5PntqpAaQFItYa7NpoxFGSplEQQhKWsPi3Tc5JgRhzRN9wqiII81GkwLZxgzOmiB1wQlbduprBtVXMWYTLtUse6mVCf8R48mKEUME4b5tIvUvfsk+oV6z09+IsW0GWMYlddarGp+YB4+Rq9/c4TElkNE+oGPWqQNknS8AtOpqYIYkRRsDJsyH6Q0a9Srh22XO8eWTWOFkIG7cagsOkgrVOvQ7N2ejAMm8YRhACzfnr1dzkMNDe+Exf1qSgehgph3CUUWsxIiWReq1zzMFJeBQfA2Yozdg9J03Mbr39MIyJv7nUJ5UFber+niRT1g11pskktb06WzHbTg86ZwmfcXZTZwBBaPABngQaVUqbWtxIp6AFjW2dIQw1njofIAwYsw2B3UselGInrndUe87zj/GBJu43zm6i/t3fzGwZgCozC17dRHvFJsAsss9p1ZFpPOzQSFQ+OzCqlDPt4rm5a1uLn6sJ7JgxTs8zlyP0h7HN31zq4SRbhADqFZNj7/RVLmuWFTfO+yTbeegsQ2Z9/PS9Tl+BNaNRodR/KSj65KHezOa39waMMxdDaMXYOe9hrikQRew4kHHYFaOeYqm3RLeooJQeOq+yk2I8heMLIaZyiK0W4FwmMMOdWjsRAGcYRGtGSQK7F0wFcaWtsdbRkMQZtVok9WOhX4lQ9oDhSGMwMoWeyVmzKyT+WJGKUzXrfI0AYzBkDEeMsm9QSNmQEFmtlvNvYsdwrRVhZd34E3uWPJQ8MlU+dy05JXZs0pLY3/EP2AGQZv0mRjAa/5ViAhYkW8jOZ6QyfoHjCOqc/bEHKsVYnhco+0C7p3H2cgRBWXDDRJQuZ6PBRoUgyKB6klRsnvCuOZnAU9PQf9N6PRvfQyugN9AQZKKS7MFZqR/XKIZoRMCZiwE2OhEqJcKeJQnl2nOdS7ppFyKuk88yTYZII4LNhEAU1wVjDqWsLc8XKBypZ7dipVMTEEYas3XCfN2kWpVmzNcJJWmkJVJxxs4pmTrM4DKalIyqT1AWDwDiLMpoWmDmlfHBmIdvYY/oDQyTV0sCUiIXm2cZ0kUXR5GGUgZXsDAjLUJJY74pMd8QCENXsnUC/Yr/1hYXYHwGnQqgk09gbK4JvUkagIt+vAaYKIPxMdllQwxNIkl/agCkGZIEds2ZKk5/qCEIWJ6XBoY1ZPSGGoOAESlTQSRKU7XMKdqUGah4ZFA+gXH+BBVJZjZvcWUDiMbz7o77n3HyBIwzOAoZlRLZpFaaVk7GSCTCaa7tSaBek6hXBWoVg1oOI43ewEQVy4seNtphgvzNEz8GhTCnVS0XKJppg95EBY4zQCsVJOIE4muZQoOceoUhlLY/kWzxxDCEEAJKAbsXCLWSKYycOh+h5BNmahL1CmGmRpitSQQRMAgY/QFjGDJClTrxRKmdr5YMHmEQaAsKzalWuJGHo9r4WYp+Ebzd6RtQ2vy+WlmiUhboDpRTKEvXypdAuUqoVSSqZVPDAJsi01pPodVRCAKNG68toV4FFucEzl8MIURWC2hH/adSrwHLC7HZojG6j7YPC4cdhUI2NHFhI4maEDZ0IkswImjW8D2BxRkBzYyL6xFGIRtk7tB81qgQ6hVTx5+tmWcYCYwCxjDUVtJNtRDMqJZMIqk/yqZm83Xxq/ZgHoO8x68pt0j9gcZ8w/wWMENbjEDJOoeVskEte9JoulBptHsKvb5Gt68RhMZuq0jj4uUA+3f72DErcXkVCCLj8WuX+Npx+GwCTufL8Im25vGWuM1NQFIayTBBCgKxJUhyQiZy0b+mpXl5jlDxCd2BxmpbQSYdQ4QoYqx3DLTa9wm1slGFFZ9QrxCaFQENIIpMg0aoAN8zKdM4baq0K/zWj+BxJ3LbwUC++OQ6kzTuVxAMdjFUGiUPWF6U8CWh5FMCV2NtRuJ0Bgq9oUJvoBEEcW8C244mDSEYqxsBFmYIzRphYVbgmQsBZEYLOIm3xA/IF5KytYhtNoZQYXjtmhQXFcQABKc8o4nhScJcQ0ApjUtrEaJIw/fSbiEC2/IsTBdOoNDqmjp62ReolgSqJcD3gFrFnKesWdi9IBApQhQBQWS0ShSZz5ViwyRO8kzpTeb5YHLvAevUTRYECGkkWNr/PUHwPNNx5Mm0jWy2LkEw3UT9gWkqGQw1RoFp5dIa6ZQUyoZ5YEYUKVxaHaFWKWF+RuLCCiNScdyfSn8SGSDbPpZXYKDJPRbeptqPXRvKTqaLkriY4MCqmUGCESlgvuGjWiL0BhrrnQgCFkFj+/KYbOaMjO8QO35RRAhDjU5fQ5JhCN8zyNtKiRLkbsUnUCnxPBKnz2gIjSgEglCDlQIigWqZpm6Gkx5hx6zE7IyE9CQ8T8L3fEhPGLh33Pzi1EkiZZhNCqA/iFHBtqXMEopsv0yc+dRJipozTh0RY60VYGleoF4RmG1IXLwcWp8nR/xMAcxJuScd2hbGvx0TwPl8ABzgvIUgxRqBc2cZAJkBS4AZa+0IQahR8oS5WSJouxIUQ7VtFzFZkD6RdSsAhBFhFGjM1AiSCJc2NHpDjYpvmUMSPM9IYILyEUDJNyVYYsKobuzwtA9PAjN1gUbV9j1KStBBgTLhbKQ0IkvgKDI9hPUKYfeih0gxurYxhWKTSchW7thN5KTE1zaOD0KFtfUA9eUy5mckLl12Mq06V+10Zw2NJaC4KCe9OQPQmKikvdIaTsu32+9jVbvSpkTaqBCGgcZaOwKZqpTty0MS7sWwWrIaJVVV9jgyq+ZJsiVTxig0C9+N0h8aaxBBViMRQ0CBtYKEwtq6xmDIU5eDowhYWY/QDxQYkWFaMDRTmhvR47mRkTDMUfYFfA9QWiejBzkBbWonwaOdimWa5oUNX1fXA+yYl2hUjQbr9pRhpkxBjpO611izKtFE6P0WTiDnnKBsW1dmGCJlTYxWGjM1D54AVtsKg6GCZ5M+BICEE0PGSsVKPbtawAmj/BJBEhBGJlYWjsPpMqBKumjjRgkFwRqtrsIwmN4HiBSj1dPQUICQEEJDSAIgDONaAyAoWx8IrDaQEhDCVPzI7evLlHOz+ft8aAfW6A812p0Qi3M+ZhoSrXZggLEZ4tvQexLs3qkKbisKIEcSjcqngs4eGxlQymGCCM2qgGZgo2O6crRIS6ik4v4B24FgEytpW3lqboiMSTEt3UbdqogTvyGFm9KYx25bFSCQ4ve38xBkMX0WOJrOMaRMadcdL6cjE7LVJcETwFCZ+9ZOdS6V+mLCu8UdrTTWWwHmZyRmGxJnhZtuTxtfiwGFMXkKq1NTRAFMTtxDjh+QjDvNfClZgGe9TKiVBIYjE+eCAW0XIqZCnC+gBKQZIw85M2TCqFuGLwUIJvunNZuQCO4QKi4ovNiytNtUeYW1IDu7z6o7B4iZW3TTe6CBiuli0loBAlnJ17nCjWv/XQbQBta10QkxHJVQLRsnuDdQcdplQruZm7vKjzYJthEFIJ9Ncwss6XAFcvACWjPqFQFPAu2OqdZJgTRnkFP5cXdxEl4QpYmn+FhtnD9mRhgqs0DkjBTO8KWDAtJ5JO12c0BWakknVTnX1rnMkSChNSMIlLlnYaSbkC3TMvJo6mxaN/XwLaZvqNDrR1iY9VGvSrQ7IchD8TArRvF4W7qSKMASOhnumCSC4AxVjkEQqQTWqqbTsjtQ0Eob4sWhI8WSlKr8OPdP1umLI09BlIRcvhTQysTRsTM5pq1ihzSDVoqRSfrKpJ/jTmhkMmrsAGTYxfBrxmikwIrgS4YUOknwxGghzXq8eMY62/fvIKyUYnS6MQOINC1fUDllFKSvaXNMxORUcNJ4R07Wl7L233JXrBwECVRKEkoBvb5lEJ1Kfer7Wc+R0pIagwBKHbzuSCOMzHc1KyV45EFFNheOdA4BOwUadhYn7goqAnVMVQxySqzMOvvbcw5WjMs3XjxhONLo9iKsrg0AMHyPUC2LRPpRhPSxDOCaifheOr0QYVRCtWLyEFpzAeHzQFzKIKKyJvDeKVLBzE70R+ORgTv9EwTFBupc8U2LVn/ICX3ZTdHGKcT0DWgyP1xKYDA0sfCdN9dwx801NOsSw5HGQ6eGeOTUACVfQkBYJhDWf3B/sGNDmR1njbelAWJCEGlT7iLnnjNhmE7UNSuFldUIN+5r4KtfNItKeR6dXoR/eLiDTz/UghBApSQdxA+s1CMzBSyDAgajP4wQhhqVkoDvCwxHKu19nJTCThxkJxceTK0BUkePBSWSlM7IT7siTehmYuSSLXZ0+1Z6CRjDYiaM5eSvYbJ+vV6EfTt9vPM7rsXX3JFt4OwPFf7bn13Gr//+RVDJgxAC2upnIpGEjgkw1SZMCFlmmJ7+qeRQbP+hcxA1o5EIGpGKMAoifM/r9uAN37Qb9Wp2+MrHH1jD4fc9jjPnB6hWLPaP00YZ1gWzACzxwtCYlkbNQ6UkMBhEgKTxiSM5H47gNHUAQGlqRFABPIsJ7tAntvY/LQAAJd90Dgch2/x7fAnKQcm1bdph4ylrjcEwxM5Zwu/eexO+5o4Zm8M3ABKtGbWKxHe/dhlH3rQX6xsDKGVat7RS0CoyrdEqBknohDhIPOvtmYAEbKGdvEI8mEFpKBVBRxHAEaIoQKc7wHveeh3e8vp9qFcNokfZMTSagX/9kgX83nvvwM4FiX5/BGbTsJLcs+MbxGjk2LyoyDSjCGGETHMxbC2r7h0cQFwXDqZkAAbl6t6UTRBlqoWcnFP2BAhmbAtra+tjh0VbjRKDhZz+dtYKw0GAH/+Oa7C8WEJoGzylMNh/Icx5kWJ8012LeOeb9mF1vY8oDAGOoJUyBFHaMoRlhngxp9QAmXV1hi9pB5ChlLLPCIQIo+EI/d4Q73vHzfimf7MTURT3EZqikRmoZRDAu5bKuPf7bsZwODJ9h1o5EUA2RMxC2hjDkcEYlEsC2f67XBo42x6Vc35G2zMB+RCKHecvjYhsIoeNswOYjJ1m11RYZ007WeUELaPRG4R43v4yXvnSeWhGcp28T+pJgtKM/+PfLaNeEfixXz0F3/dQKvlgLcCkk5A1RsowtAOhns4XNNM3bFqWGBQ7gU5rnBSMXm+Ess/4zXe9AAdfugClGJ5XnHHyfYOLeNVX78TzD9Tw2Kk+qhXfrFOMwMrhBpP5CzYENg6lcErenClTj2sE5Dq0t2ECise6Zwc9kHPzsARipmSGXsZEsDOY0alaERjDYYhbrq8aSd+igUPafPtrXrkD773nBqgoxHAQGE0QKbBSqeTq9DVvsy8gUf+xRonNjY4goNDtDlApKbz/3bfi4EsXECmGlJunG1kDQhBuu6mJ4TBuP9epxNsiW2amMafp6bgdnijXmkf59mtOx8sm191uGJiBltN4QYGzGEJBIlHVYWgGN2iipF+QMhXGONGhwWS4u+TR1HY67uX/+pcvYnHWw5uOfBGdToRatWQGP8XRgNbQwtbgFW+H/ogijSgy+HsiBUAlAyDW2iPs2enhd37mDtx8XQORMviHaa/te4QoChFFJUQ6t4dKpguKbTqcEQTGVEhBWRQU5WHxnNsZZbuYQCfBUdTP736rm4wgGHsdq/BGVdpJci4iNu20YSfMmqkLnLvU31bO3pOmOvjS22bx//zMrfje93wRlzcCNOs+IpVWyAQBlZIpG09fBzDnVHy2yStjAnwBtDoj3HpDBb96+HZcv69m1P6U145/37kLXTTrEtUKQbMAQdhEmas5XbQRW+fPTkmhnL130pM8BonmVLtsCxJWOMQoT/hsiphsuXR5wcfinDZ767hsagc2GDuqrBcP6LkKLqz0cPbSAHt2VKEsp28J3LBMcOsNDfzuT9+Gn3jfYzi7EmCmUTI5eRtx+uShVqUt8SDxZ6USYdeiRKPhgUiCSML3COutEV70vBn83H+5DbNN39znlMRXdsjk2Qs9nL/Uwc3XNyCFBxKeYQBydlfBuI2PO6h4bJpEAfGzqN7CsTwTfYBWPhlUNL8G41AB955HAWM4BAYjJHCowdDUBvojoD9iDIecvBeEjPVWiPf+zmO2rj+9OZDWMdy3XMF7f+QW7NtZwjPnugiDEP1+iP4gxGAQQUXTmwCtGINhhMHAXCMIQpx+po0XPb+BX3z77Zht+rYoNa3aZztaF/j5//pZrG2MEAQa/aEy3zMyZfPBUGEwiDAY2P+HCoOBQn8QYTjSOfANZ2sfmSKFznTzpO7vNopB43mBcU2QUIkoiWEFCBfXFFpdBU+kk0RS8ERsAhTACtAKrEIQCB/842dQ8oB3f/8LjTnRbEfQYUvHUGvG/IyPX/wvt+At7/oC/ur+y9ixUAKrCCurQ7R70ZZRQPzZKNQ4c36ARoPhSQ+X1wK8+lW78VP33IZqRU59X3GBTAjDpG//6fvxgQ8/jtmZOjY6fRB5AASYbDIL48IEMpjHuaaPhXm/oOuIMb5hAidlelMPnewECkxUAdmy6tiefDlTY/a0MfbTl5QwYYwrQL6Ak+QICEwCShNmmxX8+u+dxLfc87cm3WkJO5Xddpjgt9/zQrz6FTuwstKDIBsN8PaiAGgFSRrnL3bwum/Yg/f/1IsN8Xn7xB+OIvzvb/n/8Ku/8wXMNis2kRP3WpLTEcVjflj82vdsPiFSyRwBhp5AfHY+29wJFJtHADrX6pzvuaNM7KotDEkSsmANywjk1IQpKQAJgCUAD0oLLC818NG/vYjXff8JrKwNE+nZDhNUyhLvf/cdeP3/tgcXV3p2c4htMAABYIULl7p42xtvwvsO35lsKCGm9FKVMsRfWR3gP3zXn+LP73sau3Y0bH5E2N9OOS8e4y1dialLzZNR+TqX/9eTM4HYNgOw05aVk3rOJnJgCWuSFaYo4nkEjXyDKdmB0sKp/glzCyTNa/IQKYmlhSZOfGoVh956HBdWBpAiN0dnCyaIW7B++cfvwA+88SZcvtTdFgNopbG20cfb33wr7n3bC+1UUJo6QlE2J3BxpY/Xvum/48QnzmHHUhOhIjCkqV84WjAFPxQheGwrmQcLilG25S0X/k2U+pRuo+2jgsdVE0/ajImR7Krhe1QwA88tAMWMYKeKWuKb9WCEmrG00MRDj3Xx6v/8MRx93124bl9z6ng79qa1ZrzjLbei1x9iMJx+SFQYafzsj74Ub/v22xNJ3i7xT59p4dB3/wkeP93FjsUmoogA8uxvtYyfqP/MfqjIz40jNj0VDCNknMv2cS4HkG+r5k06g4o1gMZ4zz0XEJ+zcegwMK/KvhscUJb47IJNBAjSPMkzmkD4EMJHpD3MzDRw7lKIN73jb/C5R1aTBND0MbfRBu/5oRfj2w/dlOQPNnMmAeDlL9mFt3377cbTl9MTP1IaUhIeevQyvvOH/wJPn+1jtllHpAyDk5AAZBr2ubWXTTx8EFAuC7N/wUgleMjNpT6XCQQX1gLE5mnAXC6ZizdtNpVhAwNXylQFZeIIWv6kbKtZ3F5ELMBkF4Y8CPJAVIIQJWj2UKvXsNHR+J53/g/83acvXgETmK/auVSdWgP4todhWmfPQMk1PCnwyc+cx3f80J9jdSNEvV5DpAUgvMTjNxrAcYAzof94UkfDMGHZl1BaYxhEY+XisYRPoR+gr8AJdGp9k5zBmCcEGKPANDmWfULZc8qWeR8kZoYYZ8l25zF4APkmOUIehCghUj6qlSqYPLzubR/HH33sacME24jribbfM0rbgBFHSsPzBP77R0/i7jf/GTRLVCsVhEpACN/+LgEiY//BIm6Rcm5O5+J6nSCTyj6hXCIEgcJoaHsDJkn9JCfQVQBHttQAbpv1BKnPTQMlAqLQ7NDhSaBajkM4SjOGmVlAlMMexkwgjGsiSuYJYw6qlQoqlQq+80c/gQ985Al43vSOYeoXXP1HpIzkH/uTx/DGH/hLEHmoVytG7cNkEmGzibCqP/X+eUIqNzWerBn1qmk2HQ4jBJGyuMotpD7DVNheFMBupy1jDAvABdMyyMa9vYEZ2VqvityoGUr7CNzxGs6ixEwAxy9g+GAugaiUMMHbjjyA/+t3H0lSwVezI3w7qQJlif+bH3wQ33bPx1CulFGrVQDyoFmCWQLCEp+EMYNjoV9RNi+bx6/XJIgY3X4IrXTqA0yU+nwm8Erawws2dth07xtr6zt9Ba09NCrCtjQXpa5p3GNFDD9La9txC5nSgJQS0lMQQmNhXuJHfuazWF0f4Z1vvSPRNM+VlBcR34ysEfjZX/sU3v3LD2B+tg7NEtLzIT0fSitAMARJExLHG1AUzhAan6wad/xIATTqJvvY6QZjtQAu8v7zmcAEFja1E4jMLKBJUu8SP95jpzcwvkCtAlPtyu0z4JaQ0+uQHUlnHUM4XjNJRFqCpIdyqQSQD2YPO5dm8Au/9UX8wLs+mYRp+kugCpKUtyC88xfux+Ff/CTm5+oAeWAy9yiEh0g5CZ+0lzgnuSjO4dun0hrVqkC94mE0Uuj1QytUm0i9EwE8u0xgZuwCJkzizA4lIgBBYCZeeB5hznLupk4kyMHZU9LUSBybBw+hkgB8lEolSOkD5EOzhx2LTfzmh07iP7/j7zAKlJlMop87JjATuA1E7c1v/2v83G98Bss7Z8AwxJfSQ7lkvP0wSp1dKiy3A4UdvM46a9aYa/rwPaDTCzAKlLN9bbETmBLfmRdImL4amFEv+UQQFyR1nAkSZHHvGx0F1sBMQ2SHP/M4VGkMZ8gCaR+KSRKFkQBDolTy4XklkDDPSHvYtXMGH/zDp/D67zuObj/aVv1gW8S35dz+IMK3fv9f4Hc+/EUs75iB0qmT53ke/JIHxWaE/VgkUTi5S49l89gihTwBzM/4YGast0YJRG0zqZ8UHWxbA0wr9W5IwAxIIrS6CoORRr1KqFdFMtJly7l5yYCjWCsICFsoCiNCyffh+UYjaBsyKi2xd9cM/uZTl/H67/trrK7b+oG6ekygbFGn1w/xnT/0UfzhX5zCnuVZaG0Yk1kiUsIwgO8hjAAVxXUDJ+RN1kBvGr6RVf+NuodG3cNgFGGjPbJ7JU0p9c/GCcz2nFGx1BflB2CctuGI0eoo7FrysDQr0e6o8WwiUBheun5B3CmjFSEIzQyhmUYJJR8o+x4kmSchxDW7fJw518Wb33ECv3T45di7q5GkZZ8V8e01NlpDvPntf4mHHlvHnbftRBiZvL7WApEWGAZApWz6FYIgRBCZvkh3hxJCfm4xj1X9UpXN2DFfgicJFy+PMBxFFnOpc+cChdux2MEbqUaYGhHUAnh+fIuSAq+/SGPEtb7L6wpLsxLzTYlqmTAccTqyJL9pFHEydEFbhLHJJZiO2HJJoFoxwMj5WR+SJFgrKBVCKYEwJAyCEWq1Gj73aAd3v+Vj+O1fuAs3H5gzGTpPXBHx49rDqTMtfPePfgwnT7extNjEcARrjjxIz4OQ0mgqO8CqXvVw7e4qhhboMQqVwRcymyEWlA6LLPLilWJUywLzc2UEkcLK6mA8qYPic93PxqaobwsUmht+sOnulrmxrJKATk+h3dVYmJVYmvfw1LkAvufM/0O6A4a22L2yT6hWCLWK6aUr+8KqPW2aLLTpFt7oaYwChVGgEATKAjhNw4aAj0dPDfDv3vgX+OD/eRf+1Z3LV8QEcYLn0ZPreM2b/gTPnB9gbraGMxcCSOlBSkB6GiVfoVTyUCkZdU1kIOCLFQGGD60Yo8Agf/oD8xyNFCKtQSK/FT0n01R2LtVQLhFW14dodwJnAunmUp/feiYDDdsWIigBgtCWUp+3HTFxL61FmG0K7JiTuLRKCALT8BF3/cTbtjeqZv/dqh0DD9sEMhgpMxR6qBFGCruWfEgBXN4wC0qJiTJZN2HHpzSbVbR7A9z9lr/Cb/3s1+LrDl6zLeRuzDD3f/o8vuX7/hytrsLCXB2RJgjhgVkiVIRQMYYjDa0DVCsaMw3fTEK/0IfvCVQrZtpZqSRQnSthYbaEMDL33umF6PVCDEcKinWyg5nSjEpFYMdiGUppXLzctwhqmqgxJmqEK5oUmhAfm+7yzQUlYdfJE4Kw3o7Q7krMNSV2LXp48pkAUhjEUL0hMVMXqFUEPC/eqVuj09Xo9RUGQ1NXUDre+YIx1xSYbZrxqqMRQUhh+/6k+V8Y6LRSGrVqGaPRCN/81r/G+3/2a/Garz8wlSaI8/r3/d0ZfOvbPopBwGjUK2aUbVyxJAEBafP7BtrSqEl4HqHbD9HqhGbrWQvkKPmESlmiXpWoViUaNQ/NhkQUldAfRGh3AnS6IYJQQSmN/XubqJQE1lpDrK+PTEcw85RSn/uMNXBFTiCyHv5WUj+mdcj09Z27FKJZE1ia89DuKvgeYa4hUfJNfXs00mh1NLo9MxPHYArYThw1s3YEgJBNmnm2YZzBNUKmRY1IgOGZTh5hQJulUglSAG+85zhWVgf4rm+5FVGkIaUozBqGkZlg+kcfPYlv+8G/RKlUQr1ahlKmohcTnyCz6F0CqlUJEKPXN5rJk+kk9cGQ0RuEWNswjR21ikSz4aFe89Csm2cQKmy0RggChR0LZSilcO58D1prSI+QDgKawg9wBjllQsPtpYI5mQ8wjdRnwCK2ROxJwkZbYW0jwtKch+v2lDAKbK6gHaHVVegPNKIobYMSxAYl5uQI4uayfj9CpCRqVTOFJN53jyGSKWMkpPUkPZuu9THTrOGed9+PUaDwfd/2wkTS4zg9Ru36nsAHP/IIvvfHj6NWq8DzTJjp5vPjWn6c2mWLGahVBaJQoz8wo/C14zwTAR7FcwwZ7a5CuzOC5xGqVQ+zTQ/Nuo+lhbJpAfcMlGytPTKMlNmEYAqpz3+2bScwhyOfVuqLkEJEwDMXQjRrBlvfGik8fT5AFHIycVSI7D55nKsjx8cNQ43hUNkJ2wLtbpjMGYpr7AQTm5OwLeJ2eOXcbB0/9vOfRLsT4Iff/BUo+XLM4/2N330QP/7z96NWrcCTPrRLfMTEd5A8ZDqgGhWBsifQG0QYjSIH5TOO3k2aX9gwYas9QqczhOcRrtvbQLNWRhAoPH2+a8PGbUo9CsLKZD7ANM2hrfGix7RSP57QsfWBoca5SyGu2+ejWTejX0JrH7ObHWTTjez8ADOESqPbV2jUBRo1iVYnNPPqyY6ttzhDEgzWBmtoXhvtMDdTx8/82mfxFx9/Gq/5+uvxoluWIKXAw4+t4o8++iT+xwMXMNOsQggJjRzxYyhXHKbH4/FYo1k3u5B3eyGUMiqbeWt7HZsKpUyPQbPhm80jLnTR74cGBpaz/VNLvZNPuAIncBNg6BRSj1zo6EnChcshZhuExTkPB/aV8MjJoZOyzf0gcA73FjMTo9uLEM5L1GsE3zfAEIJlAneUTVxWdvZzYwALCw089HgbD3z+U2ZcO0zrdqnkYX6ubrN7lnkS+JZw9gkws45izGHJJzRqHsJQo90NrPkqQOROqNwZ8wPcsH8G1arE5dUBLlzsWR9Cj+MEtiX1zvdsb0ycMyWZtyf1eWvh/nH6bIhqWWCmLrF/j48nz4wSZ6lI6vM/iAgYjEynzExDolkjrG44DpctKBm/3IyWY5KZDRmVBuq1Khr1cmJbDXaQDGRbkHXyLIKHXPSuA9QkhrLSX/YFNroBBqN42/oJmb6cF28GSmvcsL+J2aaPfj/Aqadb2VE025V692/Clk7g5jERU7YkvGUOP79NfMokUthNI86OoJTGzgUPu3cYySFKhzEBm1e6NGu0OhGYGTMNz26m4NwXOVDUeAxdjMoREiQ8MHvQWpoqHntQWkKzPQZecizcXD7lfqvdjHK24UGD0WoHptmVt0LppAmfIFTYs6uG5R1VKKVx6uk2hqPI9FVMLO5oh/jFbeGTz90WJjALJOSCxpD8buHYBDOgNcOTjLVWhDMXRiAwrtnlY8eCNI2cKKpeZZsdGGZ38G7X9MrVq2ZvAaU0inaIMibBOm0x8BQGZ0DkWyi6bdAUnvmMpG3TckCslNOEYGjFqFUlalWJ4TBCt2tn+m+F0ol3Ho0UdixVcO2eOogZT59tY3V9mOT7pyeuHlu3iedurxzMuShi+1LvAihie+dL4NzFAOdXTHrz+mvKWJiTtqkkq/Izi2iraESMUCm02gGIgPlZL9lwIb9pHzuaIM4VkBAJTs/A0C3hEUt9itnPcT/c7dOZGAtzxvnbaI8QKlXg/Y9X5wiMURhhYb6MG69twhPAuUs9nL3QNanyZIfSK5X63PaxmesE0zuBHHfvFOb/N7H1uW1Si5wVKYGnzo0gJWPnoocbrimBwLi8HiSeL3OxH8B2o6a1VojZGYlGXaJRERYL4BaudLq9S+K8mbRxvIlCAtGaal/hlMGU1iabV5cYjiJstEZ23+M8gbK4P7PbqMLOhQoOXNu0lb4+Tp9p29kKfGW2Hij+3rzDOK0G0AWQsCuV+sIeNZvpO/n0AJdWTZHohmtL2LngmXGwbDtaYzxb/DreZ09ohFGEjY0AkhgLc9LGgTrthi1crNiRd207OX9Pwse7Zshce2HOg5SM9dYQQRhDtXVO6h1ptJNQdi5WcON1TZR8gYuX+3ji1MYEmPezkPoM4+jCCuzWYWAGuVsADN2G1Bd7+KY0evKpAViXsWPBw3X7SvA8xrmLIzOtm7LncJze1KbDbr0VYLYp0KwJzNQENjqhjQgwxnTsbKGabajl8SRY6kBkQiiC2ShiruljpuFh0I+wvjGEIJ37zuxrzWZEzTW7a9i3uwEhCBdWejj51AbirvCrJ/XZQZHJFrg0bRioBBFnB3CjCAGUKxxwkcobi+tzdsmOZD95po8gKmP3Th/X7imhWgZOnx3YVquch29VKREj1BqrGyPs2VnGjkUP/WEI1gwhCmLvsTbq3OZKRUSg/GZMjLIPLO8oQwpgvTWE0so6bu5EDiSjcKNIw5eE6/bP2O4kxtkLXTz1TDvZMp4L1PZmcT1PELCsxoATkcRrPl4OHWcALxppjYEnxRw5W8VemdS7qUztmAydbJakRyFYaZx6fID+mod9u8pYqhJqewROnx2h1YmSrWWKuP1yb4AaV9BoSJSlwpnLwwQ5W7x37GaxeZZpOLOIRpL3LtcwGIxw/uIIZ852bX6ogFh2XWYaPq7d04TvMS5cauOpsx1cWOmbTackoV71bZOLnpB6521KPWe1GBieFNBKBb32YLAJA5j8Nj94R0+97OR6qSx3A2kn8pVJPQqaFCzxRxEgNErXN+EtlgFmdCKNczMSC7MeBBH23crwLo8wHOkUTZS7F82Mjk+4ZrmEV84JDDoBWkNl4VhjNmtiCzYw4fh4YZkN0GOuDAawvjE0jZq574mROFozqhWJ5R01u20cY3V9iI22KQIxA8+c6+ATnzmHVifAbKNsdgajojL8lFJf9BkzfE9CMbeHFy6tmw/u5bg/zNUA/M7DLI4cIR0pXKx53guEyOV0r9DWZ4mvoQcBvOUK5l57I0r7m6CYWnYk2oaz22ZdEupTNGqcBVBvEA7fJrD/yhBg/yiPRx5fxQ+96z4cv/8M5mcqRhNQdhL0tqQ+gxI2DUl+yaNgNFwD3tch+pUUhp+PAo7juACAIOQnPM+DL4n1Nj38wmweazDMrD09CiAXfSx+x60oH5gFjxR0PzTPXggMI4hRBBFEoFEE3Qu3fHI/hBqE+NS5AHf/9RCfX1dQym4xo56Dp76C45NztH2a9265aREf/q1vwstfvBvt7sD4L87mEpvBvBl6Iko4NllSgEu+jyCMTgPE73wnC1eUs7Jy/C4AwGCoPwsA5ZJp1SLOS/142FHMGNnwjVmDoxAzX38dvMUKdDdAgoUSTres+xRTPokwXyEMNOG9TyiQSDd5vOpPcQXHJ+cI+zTvhZFGteLhF+99pd1mJg5n2QmDx5M6XBheO9vG2ynp5ZJkz5MYDIPPAcDx4/eKiXmAEzuPMQCsr48+NRp00agKmW53tk2pd2r72sbyHIaQcz7KB2ahBxFSQ311HqEGmj7wUJtxum+nbPI/bRMQzyK4/ZaduP35i+j3h2YbVq2vQOpTxjB+s0a95pGKQnS7o/sNjW/lyYmgY4c0AJx6ovH5wWB0rtmokPGz9DakPpV8drUAa7CKIKoCVJLZHbmv8iPUwOUR/7PxA2Lcxc6lKsIospGH3r7U5xJJzJpnmxXZH3RGq8+s/b2h8UObMACIDx1iiaeuH/YH+nitVuVKGVpzUXi3idSPMYZhABIaqjcEB2rTfrVnLVUCWCrTPxsGiMfZXFzpwBMwU1STsWt6aqmHMw5GK0bJF7rZbHCvF3xysPrz5w4fPiyAI3rTVPClS8cJAFbb0VGlFM02iVjFJVu9udTzhIRPzASSEK12MTp5GaJaSneDvoqE74TArTOE62pkx7r90yZ+GBls4ucfuYAHHz6PalUmfgCgtyn1acFJa4WZZpmFkNRqD37f2P9xeo8lgk6cuEsBTI89eOajexbXn1mar+1dudzSzFowT4ngKRpdHufpJWH9jz+P0v55eIt16F4wXSFmik/WAqAugR+8sWR34bj6DHA1lBblfIDBMMQP/MQfIwwjVMoG0ZzZkmmsKsm5HV1yOQGbwdqx2JDt9nrv0tOdo4a244OCCmoBxAcP3uedOPGKQavz0G8vLdV+otlsq/UNLTyvqDkRmbEm+dElSYXMeBMgXyJa6eLirx3H4utegvL1O0EZrD5tezXjHblvbwA/8QLg2n8+2h8PP3oRP3j4j/G3f38a83MNKG33QYpBhxhPNGHTBByglEK9VlLNmaZ3+vTZP+hf/qnzhw4dlceO3a02Y0bncVgA9/LCyx7ce8cLyo+WfFF59MlOumPrRKnHeAEmzgFoBeYQrEMAEdRwACBC+foFeIv1tHLF02XnUmCl+XhXBbhjTqAmgYGyhaQklYvsRtdjsly4/VbhPfCkY3jCdfN4SgcQdubcBj7xwNPodEPMztQRaVgwikh2T3Wvu6nUO1C1KNK46cCSLpV8+vwjZ1/aOvmT/wAcFcDUDAAcOsTy2DFSL3r1537hxhuW7zl1+kK0uh55pouHN5F6jDmAZuSsArPZZElbJmAVQg8H4Cg0w6Pj48cYqqgKls2XK2b0I4Zi2NGwubRoURq44BgurB1gwt+58ya0bGXu2Um8e55EvVaB53lQDDsgK54hSFPVBjKhHxmo+WyjpJ7/vGvkk0+e/chjn3z7fzh06JA8duyY2gYoFDh2DPrw4cPiyLHeT802V7913+76YruzoZVi4Uw3LhhXijEn0IAzzTg4HXfxaIPMEdUqgLKzw2exWuMiQjiM4AGoUkFVr5C4KPyOScQeY/Yc8JOLBjaPgTqRECnGWzLiPkmkMLTMNoica9UvuG4eLEPM1+6bx/p6e/TUudaPgJmO0b0TXZdNxsUTP/wwCzxMa+f3feqH5uZmPrBvVyl68sxQxFpgcv4fWWy6M9eYSIDZEN+oaLKj4+1IGOgxpipC5RRpBs28NfFyJouxCUNY6Je7abYzFTst/eRBl5zdTS0pYY/V02KoWm6IJlDMVJvk/2Oc4TV7ZlSlWveefOr0u0bP/MwTh+6+Ux7DETWNQ7qpKbjzGx/4owPXL7/6ydMXo5W10PM9Z/96nlwRNCodKVpHawDKMQvx3zmA41SwaGxpLvK9csVmZCszM83n7qy/YvOT9wMoQ4Z0RxMey5HwRKlPgCqRwuxMRT3/eXvlU09f+vQjf/dn/+rQoZ187NgxvVnwIrf0Uh8GHT58F33oxI0fnW9E37xvV32u0xmqYaCFJEyuu+dr7rFDloFtx2PzrOND8XawIjNUmexAaSKZfA77dI8nEnZPYaeZw2nsIHJsbNLZm32dnEfp1rTJ98PWHeCcK0SyjzEgbF+Bc01yt7jN9hW6cDSaFGxuUfWLO6bKZU8/76ZlWlvr9b/48Nn/VQ8+tPLQQ4cIOLFp5DpFMv6IPvLwrYQvfuXqqafbd7faUXjj/gaVfehIcTq1Mu/4FcG8KeVzTggczwkWyf48CY4fMnkvJj6cyZvZz23XrtPBS+51EU/qtMcgN6oedmZxwljSNC2SSI7n+H7jexciYTB2p4BnJoI7n+cGY8Ybc1NhdJH18IsTPgagKj3wzTfu1KMA4umnLrwxuPzex/g/HpX5rN8VMgCAY3ergwfv88793dfcf/Lplf/UH5F43oEmyiXoKHJHvxTg4QtavGJGIHaAmRDpIk9YSHYkKLOQyefuHgTuZ+Y1u3h/V6qRlc6sJ04pohjZJ3F6PbKhW/KPs+fHf6f/YnVP4yaD8+GdHssEEjGUUpAC/PybdinA85548swPrjzx0x8+ePCwh4KY/4pMQPx46qkP6IMH7/M+d+Kuz6vZ1z06O1M9tHvJR6c74lGgSIjN5tbz+N72GROA5AXFcLpUUSbqMbekybEuoqn4XEoQUu5n4OyodgKsynbsM6U7nLiTXpM43d3pi7LZKS7YJSej6GkSKHXzmJ/s1jHlktTPv2mZiUreY0+cuefCw+/+pYMHD3snThyZenOEqRkgZoIXv/gB/5H7v+pBNXv3o41G9TX7dtXkMAiiXl+JuL9/U1+gqMk0r/0oXXjO/e0u9MTP8ucWfJYQgLZI+TIKEz6F413HkjbFCSEeSw5Ng/BBAh8PI4W5mYp6/s3LMlRCPHHy7D0XHv7J926X+NtmAAA4f/43rSZ4xYNB/T/+TalcetU1e+bmPC+Iup2QIsUkBLITLSf8oE3n3GIy5Gyrc7OoWmB6VO2052KTcyd/NjnRtLnUx7MIVKQAMO/bPasOXL/bW2/1WycfP/eGS4+95/1XQvwrSLynD1sviHDT0b13vmDfb+3dNf9vVdTFmXOdaKMVSg0D9RubjbdJt+zEuXnP6tyCRb6q3TecS1ZtguadcN3NPHxmMzSSmTHTLKn9+xZkpdrAubMrn3j8i2e+I1j7lYevlPjPigFMkuCojJ2Nm1513/fu2VE7sjDfXGi11nF+pR91u6HUGiTsODTejMCbSj1vQ+p5G1J/FXH4Ez7bOoefZYY4qjLb3muAmBu1kt613BQLC/O0sd7unzu/9vNnPn/kPQBClwZfegawhaPDh4EjR45oHDh67Qtv2fOOpXn5bTPNRqnX7WBltadanRBBoASDKXWkOIP354kJnM0/myiZY0yz1bnTZdymZbhixsgPhwDcJliz07kJAXxf6JlGhXfsaHjNZhO9XheXL3ePPvr4hXux9suPmJkG7xTThHrPMQNkM4YAMP/CP77tmmua3z0/490902zsYFbodLtotwe62490MFIUKU2smXiahZogmVckfdsi0IRqZ5IiHs8wJh1Fub8z7XaUbVUjAktBXC55XK97NDNTk81GHVJKdNqt9np79Afnnl79jc7Zn/uEWeuj8tixu/XVgCdcbbgEHTp0TCR1511Hd9x029w3zTf919Sq4qtrlcqs9DwoFSEYBQiCEGEUIQyiTZyx4oVk5BcVBQRCNg1caJOBSa1V2AQAU3ReYcFp7DtTqfd9Cd+TKJU8lEo+pCehlMKg3+v3+8GnNjaGf/jUo2d/H8NfPwMAhw+zOHLkXjxbqX8OGSA1C4cO3UuxRgAAXP9Hyweuqdw526CvKpfoRSWfDkjJy4LQkAIVgwVwB9TmJDPPGNvytPM4hcnlXd609OvmMLJ78xmpRrHUZ3oRDQKUCFBaB1qprtK8MgrU6eEwfLDbCT/xzNm1B7D+3jOpdj0qjx17iK8m4Z9jBkg1wsGDx+Vdd92ljxyh8Zuf/6+z1cWl5vycrMfDC7KDzEaFL7d4s+CxBewsGD3rawQASvn7GZlKd3L2KL1GqVzCaqs1xIXLLeADrbHyDzPddde90sC4rj7h/xEeTIcOHZUHD97nHTp0VBLhyw8n2Xj4MIuDBw97OHRUGkTWl+i7/7GZAriXcHiKQ4/8z0r+e52pzl9+fPnx5ceXH1/Kx/8PgJAofmd2oYUAAAAASUVORK5CYII="
ICON_ICO_B64 = "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"

PAGE = r'''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>الدولي للتحميلات</title>
<link rel="icon" type="image/png" sizes="256x256" href="/icon.png?v=3">
<link rel="shortcut icon" type="image/x-icon" href="/favicon.ico?v=3">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef0f3;--sf:#fff;--tx:#121b26;--mu:#667386;--ln:#dde2e8;--ac:#2447d6;--ac2:#e6ebfc;--ok:#13874f;--er:#cf3a3a;--wa:#8b97a8;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0d1218;--sf:#151c24;--tx:#e7ecf2;--mu:#8995a6;--ln:#252f3b;--ac:#7c9bff;--ac2:#1b2748;--ok:#3ccf86;--er:#ff7878;--wa:#6b788a}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 "SF Arabic","Segoe UI",Tahoma,"Geeza Pro","Noto Sans Arabic",system-ui,sans-serif}
button,input,select,textarea{font:inherit;color:inherit}
.app{display:grid;grid-template-columns:244px 1fr;height:100%}
aside{background:var(--sf);border-inline-end:1px solid var(--ln);padding:22px 14px;display:flex;flex-direction:column;gap:6px}
.brand{display:flex;align-items:center;gap:12px;padding:0 6px 18px}
.logo-img{width:44px;height:44px;border-radius:12px;display:block;flex-shrink:0}
.brand b{font-size:17px;display:block;line-height:1.25}.brand small{color:var(--mu);font-size:12px}
.nav{display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;border:0;border-radius:10px;background:none;cursor:pointer;text-align:start}
.nav:hover{background:var(--bg)}.nav.on{background:var(--ac2);color:var(--ac);font-weight:600}
.nav em{margin-inline-start:auto;font-style:normal;font-size:12px;color:var(--mu)}.nav.on em{color:var(--ac)}
.sep{height:1px;background:var(--ln);margin:6px 8px}
.sp{flex:1}
.speed{padding:12px;border-radius:12px;background:var(--bg);margin-bottom:6px}
.speed small{color:var(--mu);display:block;font-size:12px}.speed b{font-size:20px;direction:rtl}
.speed .cap{font-size:11.5px;color:var(--ac);margin-top:2px;display:block}
main{display:flex;flex-direction:column;min-width:0}
header{display:flex;align-items:center;gap:8px;padding:18px 24px 6px}
header h1{font-size:22px;margin:0;margin-inline-end:auto}
#updBar{margin:8px 24px 0;padding:11px 16px;border-radius:12px;background:var(--ac2);border:1px solid var(--ac);display:none;align-items:center;gap:12px;flex-wrap:wrap}
#updBar b{color:var(--ac);font-size:14px}#updBar small{color:var(--tx);font-size:13px;display:block}
.btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--ln);background:var(--sf);border-radius:10px;padding:8px 14px;cursor:pointer}
.btn:hover{border-color:var(--ac)}.btn:disabled{opacity:.55;cursor:not-allowed}
.btn.pri{background:var(--ac);border-color:var(--ac);color:#fff;font-weight:600}
@media(prefers-color-scheme:dark){.btn.pri{color:#0b1020}}
.btn.dng{color:var(--er)}.ib{width:38px;height:38px;padding:0;justify-content:center}
#list{padding:12px 24px 24px;overflow:auto;display:flex;flex-direction:column;gap:10px;flex:1}
.item{background:var(--sf);border:1px solid var(--ln);border-radius:14px;padding:14px 16px;display:grid;grid-template-columns:46px 1fr auto;gap:14px;align-items:center}
.fi{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;font-size:11px;font-weight:700;direction:ltr;color:var(--c);background:color-mix(in srgb,var(--c) 14%,transparent)}
.top{display:flex;align-items:center;gap:10px;min-width:0}
.name{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;unicode-bidi:plaintext;text-align:start}
.chip{font-size:12px;padding:1px 10px;border-radius:99px;background:var(--bg);color:var(--mu);white-space:nowrap}
.s-downloading .chip{background:var(--ac2);color:var(--ac)}.s-completed .chip{color:var(--ok)}.s-error .chip{color:var(--er)}
.bar{display:flex;gap:3px;height:8px;margin:9px 0 7px;direction:ltr}
.seg{background:var(--ln);border-radius:4px;overflow:hidden;min-width:3px}
.seg i{display:block;height:100%;background:var(--ac);transition:width .5s linear}
.s-paused .seg i,.s-queued .seg i{background:var(--wa)}.s-completed .seg i{background:var(--ok)}.s-error .seg i{background:var(--er)}
.ind .seg i{width:35%!important;animation:ind 1.3s ease-in-out infinite alternate}
@keyframes ind{to{transform:translateX(185%)}}
.meta{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--mu)}.meta span:empty{display:none}.meta .er{color:var(--er)}
.acts{display:flex;gap:4px}.acts .btn{border-color:transparent;background:none}.acts .btn:hover{background:var(--bg)}.hid{display:none!important}
#empty{margin:auto;text-align:center;color:var(--mu);padding:40px}#empty h2{color:var(--tx);margin:0 0 6px}

#videoView{padding:16px 24px 28px;overflow:auto;flex:1;display:none;flex-direction:column;gap:16px}
.vcard{background:var(--sf);border:1px solid var(--ln);border-radius:16px;padding:22px;max-width:780px;width:100%;margin:0 auto}
.vcard h2{margin:0 0 4px;font-size:19px}.vcard p{margin:0 0 14px;color:var(--mu);font-size:13.5px}
.vbar{display:flex;gap:8px;flex-wrap:wrap}.vbar input{flex:1;min-width:220px}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.badge{font-size:12px;padding:3px 10px;border-radius:99px;background:var(--bg);color:var(--mu)}
.eng-warn{background:color-mix(in srgb,var(--er) 12%,var(--sf));border:1px solid color-mix(in srgb,var(--er) 40%,transparent);border-radius:12px;padding:14px 16px;margin-top:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.eng-note{background:var(--ac2);color:var(--ac);border-radius:12px;padding:10px 14px;margin-top:12px;font-size:13px}
.vinfo{display:grid;grid-template-columns:220px 1fr;gap:18px;align-items:start}
.vthumb{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:12px;background:var(--bg);border:1px solid var(--ln)}
.vtitle{font-size:17px;font-weight:700;margin:0 0 6px;line-height:1.45}
.vsub{color:var(--mu);font-size:13px;display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.fmts{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:16px}
.fbtn{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 14px;border-radius:12px;border:1px solid var(--ln);background:var(--bg);cursor:pointer;text-align:start;transition:border-color .15s,transform .1s}
.fbtn:hover{border-color:var(--ac);transform:translateY(-1px)}
.fbtn b{display:block;font-size:14px}.fbtn small{color:var(--mu);font-size:12px}
.fext{font-size:11px;font-weight:700;padding:3px 8px;border-radius:8px;background:var(--ac2);color:var(--ac);direction:ltr}
.fbtn.aud .fext{background:color-mix(in srgb,#8f4fe0 18%,transparent);color:#8f4fe0}
@media(max-width:680px){.vinfo{grid-template-columns:1fr}}

#uploadView{padding:16px 24px 28px;overflow:auto;flex:1;display:none;flex-direction:column;gap:16px}
.ucard{background:var(--sf);border:1px solid var(--ln);border-radius:16px;padding:22px;max-width:860px;width:100%;margin:0 auto}
.ucard h2{margin:0 0 4px;font-size:19px}.ucard p{margin:0 0 14px;color:var(--mu);font-size:13.5px}
.umodes{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.umode{border:1px solid var(--ln);background:var(--bg);border-radius:99px;padding:7px 14px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;transition:all .15s}
.umode:hover{border-color:var(--ac)}.umode.on{background:var(--ac2);border-color:var(--ac);color:var(--ac);font-weight:600}
.dropzone{border:2px dashed var(--ln);border-radius:16px;background:var(--bg);padding:34px 20px;text-align:center;cursor:pointer;transition:border-color .15s,background .15s}
.dropzone:hover,.dropzone.drag{border-color:var(--ac);background:var(--ac2)}
.dropzone .dz-ic{width:54px;height:54px;border-radius:16px;background:var(--ac2);color:var(--ac);display:grid;place-items:center;margin:0 auto 10px}
.dropzone b{display:block;font-size:16px;margin-bottom:4px}.dropzone small{color:var(--mu);font-size:13px}
.uhead{display:flex;align-items:center;justify-content:space-between;gap:10px;max-width:860px;width:100%;margin:0 auto}
.uhead h3{margin:0;font-size:16px}
#uList{display:flex;flex-direction:column;gap:10px;max-width:860px;width:100%;margin:0 auto}
.uitem{background:var(--sf);border:1px solid var(--ln);border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.utop{display:grid;grid-template-columns:46px 1fr auto;gap:12px;align-items:center}
.uthumb{width:46px;height:46px;border-radius:12px;object-fit:cover;border:1px solid var(--ln);background:var(--bg)}
.ubadge{font-size:11.5px;padding:1px 9px;border-radius:99px;background:var(--ac2);color:var(--ac);white-space:nowrap}
.ubadge.tmp{background:color-mix(in srgb,#d98a00 16%,transparent);color:#d98a00}
.s-uploading .chip{background:var(--ac2);color:var(--ac)}.s-cancelled .chip{color:var(--wa)}.s-cancelled .seg i{background:var(--wa)}
.ulink-box{display:flex;gap:6px;align-items:center;flex-wrap:wrap;background:var(--bg);border:1px solid var(--ln);border-radius:10px;padding:6px 8px}
.ulink-box input{flex:1;min-width:180px;border:0;background:transparent;padding:4px 6px;direction:ltr;text-align:left;font-size:13.5px;outline:none}
.ucodes{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.cbtn{font-size:12px;padding:5px 10px;border-radius:8px;border:1px solid var(--ln);background:var(--bg);cursor:pointer;display:inline-flex;align-items:center;gap:5px}
.cbtn:hover{border-color:var(--ac);color:var(--ac)}.cbtn.dng:hover{border-color:var(--er);color:var(--er)}
.s-processing .chip{background:color-mix(in srgb,#8f4fe0 18%,transparent);color:#8f4fe0}
.s-processing .seg i{width:35%!important;background:#8f4fe0;animation:ind 1.3s ease-in-out infinite alternate}
.ustudio{margin-top:16px;border:1px solid var(--ln);border-radius:14px;background:var(--bg);padding:16px;display:flex;flex-direction:column;gap:14px}
.ustudio video{width:100%;max-height:320px;border-radius:12px;background:#000;display:block}
.uopts{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px;align-items:end}
.uopts label{margin:0 0 4px;font-size:12.5px}
.ucheck{display:flex;align-items:center;gap:8px;padding:9px 12px;border:1px solid var(--ln);background:var(--sf);border-radius:10px;cursor:pointer;font-size:13.5px;user-select:none}
.ucheck input{width:auto;margin:0}
.uplayer{margin-top:10px;border-radius:12px;overflow:hidden;background:#000;border:1px solid var(--ln)}
.uplayer video{width:100%;max-height:360px;display:block}
#torrentView{padding:16px 24px 28px;overflow:auto;flex:1;display:none;flex-direction:column;gap:16px}
#soonView{padding:16px 24px 28px;overflow:auto;flex:1;display:none;flex-direction:column;gap:16px}
#tList{display:flex;flex-direction:column;gap:10px;max-width:860px;width:100%;margin:0 auto}

dialog{border:1px solid var(--ln);border-radius:16px;background:var(--sf);color:var(--tx);padding:22px;width:min(540px,92vw)}
dialog.wide{width:min(820px,95vw)}
.fgrid{display:grid;grid-template-columns:1fr 90px;gap:16px;align-items:start}
.fbox{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:12px 8px;border-radius:12px;background:var(--bg);border:1px solid var(--ln);text-align:center}
.fbox .fi{width:54px;height:54px;font-size:13px}
.fbox small{font-size:12px;color:var(--mu);direction:rtl}
.inrow{display:flex;gap:6px;align-items:center}.inrow input{flex:1}
.tfiles{max-height:280px;overflow:auto;border:1px solid var(--ln);border-radius:12px;background:var(--bg);margin-top:8px}
.tfile{display:grid;grid-template-columns:24px 1fr auto;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--ln);font-size:13px;cursor:pointer}
.tfile:last-child{border-bottom:0}.tfile:hover{background:var(--sf)}
.tfile input{width:auto;margin:0;cursor:pointer}
.tfile .tfn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;direction:ltr;text-align:left}
.tfile .tfs{color:var(--mu);font-size:12px;white-space:nowrap}
.tbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}
.tbar input{flex:1;min-width:160px;padding:6px 10px;font-size:13px}
.tmeta{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--mu);margin-top:6px}
@media(max-width:620px){.fgrid{grid-template-columns:1fr}}
dialog::backdrop{background:rgba(8,12,18,.5)}dialog h3{margin:0 0 14px}
label{display:block;font-size:13px;color:var(--mu);margin:12px 0 4px}
input,select,textarea{width:100%;border:1px solid var(--ln);background:var(--bg);border-radius:10px;padding:9px 12px}
textarea{min-height:120px;resize:vertical;direction:ltr;text-align:left}input.l{direction:ltr;text-align:left}
.row{display:flex;gap:8px;justify-content:flex-start;margin-top:18px;flex-wrap:wrap}
#toast{position:fixed;bottom:22px;inset-inline:0;margin:auto;width:fit-content;max-width:90vw;background:var(--tx);color:var(--bg);padding:10px 18px;border-radius:12px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:99}
#toast.on{opacity:1}
#bye{position:fixed;inset:0;background:var(--bg);display:none;place-items:center;text-align:center}
:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
@media(max-width:720px){.app{grid-template-columns:1fr}aside{display:none}}
</style></head><body>
<div class="app">
<aside>
 <div class="brand"><img class="logo-img" src="/icon.png?v=3" alt="الدولي للتحميلات"><div><b>الدولي للتحميلات</b><small>الإصدار <span id="appVer">10.10</span></small></div></div>
 <button class="nav" data-f="video"><span data-ic="video"></span>تحميل فيديو</button>
 <button class="nav" data-f="upload"><span data-ic="upload"></span>مركز الرفع<em id="c-upload">0</em></button>
 <button class="nav" data-f="torrent"><span data-ic="magnet"></span>التورنت<em id="c-torrent">0</em></button>
 <button class="nav" data-f="soon"><span data-ic="spark"></span>قريبا</button>
 <div class="sep"></div>
 <button class="nav on" data-f="all"><span data-ic="all"></span>كل التنزيلات<em id="c-all">0</em></button>
 <button class="nav" data-f="active"><span data-ic="down"></span>قيد التنزيل<em id="c-active">0</em></button>
 <button class="nav" data-f="stopped"><span data-ic="pause"></span>المتوقفة والفاشلة<em id="c-stopped">0</em></button>
 <div class="sp"></div>
 <div class="speed"><small>السرعة الإجمالية</small><b id="spd">0 بايت/ث</b><span class="cap" id="spdCap"></span></div>
 <button class="nav" id="bSet"><span data-ic="set"></span>الإعدادات</button>
 <button class="nav" id="bQuit"><span data-ic="power"></span>إنهاء التطبيق</button>
</aside>
<main>
 <header><h1 id="ttl">كل التنزيلات</h1>
  <button class="btn ib" id="bResAll" title="استئناف الكل" data-ic="play"></button>
  <button class="btn ib" id="bPauAll" title="إيقاف الكل مؤقتًا" data-ic="pause"></button>
  <button class="btn ib" id="bClear" title="مسح المكتملة من القائمة" data-ic="trash"></button>
  <button class="btn" id="bGoTorrent"><span data-ic="magnet"></span>تورنت</button>
  <button class="btn" id="bGoUpload"><span data-ic="upload"></span>رفع ملف</button>
  <button class="btn" id="bGoVideo"><span data-ic="video"></span>فيديو</button>
  <button class="btn pri" id="bAdd"><span data-ic="plus"></span>إضافة رابط</button></header>
 <div id="updBar"><div style="flex:1"><b id="updTtl">يتوفر تحديث جديد!</b><small id="updNotes"></small></div><button class="btn pri" id="bDoUpd">تحديث وإعادة التشغيل الآن</button></div>
 <div id="extBar" style="margin:8px 24px 0;padding:11px 16px;border-radius:12px;background:color-mix(in srgb,#d98a00 14%,var(--sf));border:1px solid #d98a00;display:none;align-items:center;gap:12px;flex-wrap:wrap"><div style="flex:1"><b style="color:#d98a00;font-size:14px">تم تحديث ملفات إضافة المتصفح (aldawli-ext) تلقائيًا!</b><small style="color:var(--tx);font-size:13px;display:block">افتح صفحة الإضافات في متصفحك (edge://extensions أو chrome://extensions) واضغط زر التحديث (↻) على إضافة الدولي لتفعيل التحديث الجديد.</small></div><button class="btn" id="bDisExt">فهمت، إخفاء</button></div>
 <div id="list"></div>
 <div id="empty"><h2>لا توجد تنزيلات هنا</h2><p>الصق رابطًا (Ctrl+V) أو اضغط «إضافة رابط» أو افتح قسم «تحميل فيديو» ليوتيوب وإنستغرام.</p></div>

 <section id="videoView">
  <div class="vcard">
   <h2>تحميل فيديوهات يوتيوب وإنستغرام</h2>
   <p>الصق رابط فيديو من YouTube أو Instagram أو TikTok أو Facebook أو X، واضغط «فحص الرابط» لاختيار الجودة وتحميله فورًا.</p>
   <div class="vbar">
    <input class="l" id="vUrl" placeholder="https://www.youtube.com/watch?v=... أو رابط ريلز إنستغرام">
    <button class="btn" id="vPaste"><span data-ic="clip"></span>لصق</button>
    <button class="btn pri" id="vProbe"><span data-ic="search"></span>فحص الرابط</button>
   </div>
   <div style="margin-top:10px">
    <label for="vDir" style="margin:0 0 4px">مجلد حفظ الفيديو</label>
    <div class="inrow">
     <input class="l" id="vDir" placeholder="نفس مجلد الحفظ الافتراضي">
     <button class="btn" id="vBrowse" type="button" title="اختيار مجلد">...</button>
    </div>
   </div>
   <div class="badges">
    <span class="badge">YouTube</span><span class="badge">Instagram Reels</span><span class="badge">TikTok</span><span class="badge">Facebook</span><span class="badge">X / Twitter</span><span class="badge">MP3 صوت</span>
   </div>
   <div id="engBox"></div>
  </div>
  <div class="vcard hid" id="vResult"></div>
 </section>

 <section id="uploadView">
  <div class="ucard">
   <h2>مركز الرفع والبث السريع</h2>
   <p>ارفع فيديوهاتك وصورك وملفاتك مع تجهيز تلقائي للفيديو (FastStart أو ضغط ذكي 720p) حتى يفتح ويشغّل فورًا عند أي شخص بدون انتظار.</p>
   <div class="umodes" id="uModes">
    <button class="umode on" data-svc="catbox" data-exp="">دائم — Catbox (حتى 200 م.ب)</button>
    <button class="umode" data-svc="litterbox" data-exp="24h">مؤقت 24 ساعة — Litterbox (حتى 1 ج.ب)</button>
    <button class="umode" data-svc="litterbox" data-exp="72h">مؤقت 72 ساعة — Litterbox (حتى 1 ج.ب)</button>
   </div>
   <div class="dropzone" id="dropZone">
    <div class="dz-ic" data-ic="upload"></div>
    <b>اسحب الفيديو أو الملف وأفلته هنا، أو اضغط للاختيار</b>
    <small id="dzHint">عند اختيار فيديو سيفتح لك استوديو المعاينة والقص والضغط الفوري، وباقي الملفات تُرفع مباشرة.</small>
    <input type="file" id="uFile" multiple hidden>
   </div>

   <div class="ustudio hid" id="uStudio">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
     <b id="stName" dir="auto" style="font-size:15px"></b>
     <span id="stMeta" style="font-size:12.5px;color:var(--mu)"></span>
    </div>
    <video id="stPrev" controls preload="metadata"></video>
    <div class="uopts">
     <div>
      <label for="stMode">تحسين تشغيل الفيديو</label>
      <select id="stMode">
       <option value="faststart">فتح فوري FastStart (ثانية واحدة — نفس الجودة)</option>
       <option value="streamable" selected>بث سريع 720p H.264 (أسرع فتح + أصغر حجم)</option>
       <option value="original">بدون معالجة (الملف الأصلي كما هو)</option>
      </select>
     </div>
     <div>
      <label for="stFrom">قص من (اختياري — مثال 00:05)</label>
      <input class="l" id="stFrom" placeholder="00:00">
     </div>
     <div>
      <label for="stTo">إلى (اختياري — مثال 00:30)</label>
      <input class="l" id="stTo" placeholder="نهاية الفيديو">
     </div>
     <div>
      <label>&nbsp;</label>
      <label class="ucheck"><input type="checkbox" id="stMute"><span>كتم الصوت</span></label>
     </div>
    </div>
    <div class="row" style="margin-top:4px">
     <button class="btn pri" id="stStart"><span data-ic="upload"></span>تجهيز ورفع الفيديو الآن</button>
     <button class="btn" id="stSetFrom">تعيين البداية من موضع المشغّل</button>
     <button class="btn" id="stSetTo">تعيين النهاية من موضع المشغّل</button>
     <button class="btn" id="stCancel">إلغاء</button>
    </div>
   </div>
  </div>
  <div class="uhead hid" id="uHead">
   <h3>سجل المرفوعات والروابط</h3>
   <button class="btn" id="bClearUp" style="padding:6px 12px;font-size:13px"><span data-ic="trash"></span>مسح السجل المكتمل</button>
  </div>
  <div id="uList"></div>
 </section>

 <section id="torrentView">
  <div class="ucard">
   <h2>تحميل التورنت (Magnet و .torrent)</h2>
   <p>الصق رابط Magnet أو اسحب ملف .torrent ليبدأ التحميل مباشرة عبر محرك aria2 مع إيقاف الـ Seeding تلقائيًا بعد الاكتمال.</p>
   <div class="vbar">
    <input class="l" id="tMagnet" placeholder="magnet:?xt=urn:btih:...">
    <button class="btn" id="tPaste"><span data-ic="clip"></span>لصق</button>
    <button class="btn pri" id="tAddBtn"><span data-ic="search"></span>فحص واختيار الملفات</button>
    <button class="btn" id="tFastBtn" title="بدء التحميل فورًا بدون انتظار جلب قائمة الملفات">تحميل مباشر</button>
   </div>
   <div class="dropzone" id="tDrop" style="margin-top:12px;padding:22px 16px">
    <b>أو اسحب ملف .torrent وأفلته هنا، أو اضغط للاختيار</b>
    <small>يُحفظ تلقائيًا في نفس مجلد الحفظ ويلتزم بحد السرعة من الإعدادات</small>
    <input type="file" id="tFile" accept=".torrent" multiple hidden>
   </div>
   <div id="torEngBox"></div>
  </div>
  <div class="uhead hid" id="tHead">
   <h3>قائمة التورنت</h3>
   <button class="btn" id="bClearTor" style="padding:6px 12px;font-size:13px"><span data-ic="trash"></span>مسح المكتملة</button>
  </div>
  <div id="tList"></div>
 </section>

 <section id="soonView">
  <div class="ucard" style="text-align:center;padding:48px 24px">
   <h2 style="font-size:24px;margin-bottom:8px">قريبًا...</h2>
   <p style="margin:0">ميزات جديدة قيد التطوير! تم الوصول لهذا القسم بنجاح عبر نظام التحديث التلقائي (الإصدار 10.1).</p>
  </div>
 </section>
</main></div>

<dialog id="dAdd"><h3>إضافة روابط مباشرة</h3>
 <label for="urls">رابط في كل سطر (روابط يوتيوب وإنستغرام ستُفتح تلقائيًا في محمّل الفيديو)</label><textarea id="urls" placeholder="https://example.com/file.zip"></textarea>
 <div class="row"><button class="btn pri" id="okAdd">بدء التنزيل</button><button class="btn" id="bPaste"><span data-ic="clip"></span>لصق من الحافظة</button><button class="btn" data-close>إلغاء</button></div></dialog>

<dialog id="dUrl"><h3>تحديث رابط التنزيل</h3>
 <label for="uNew">الرابط الجديد (سيستكمل التنزيل من نفس النقطة)</label>
 <input class="l" id="uNew" placeholder="https://example.com/new-link">
 <div class="row"><button class="btn pri" id="okUrl">تحديث واستئناف</button><button class="btn" data-close>إلغاء</button></div></dialog>

<dialog id="dSet"><h3>الإعدادات</h3>
 <label for="sDir">مجلد الحفظ</label><input class="l" id="sDir">
 <label for="sSeg">عدد الاتصالات لكل ملف</label><select id="sSeg"></select>
 <label for="sAct">أقصى عدد من التنزيلات المتزامنة</label><select id="sAct"></select>
 <label for="sSpd">حد السرعة الإجمالية (ك.ب/ث — 0 بدون حد)</label><input class="l" id="sSpd" type="number" min="0" step="50" placeholder="0">
 <label for="sHash">رمز حساب Catbox (Userhash — اختياري لحذف مرفوعاتك من السيرفر لاحقًا)</label><input class="l" id="sHash" placeholder="اتركه فارغًا للرفع المجهول المباشر">
 <label class="ucheck" style="margin-top:12px"><input type="checkbox" id="sConf"><span>إظهار نافذة «معلومات ملف التحميل» قبل بدء التنزيل</span></label>
 <label class="ucheck" style="margin-top:8px"><input type="checkbox" id="sAuto"><span>تشغيل الدولي تلقائيًا مع بدء الويندوز (في صينية النظام)</span></label>
 <label class="ucheck" style="margin-top:8px"><input type="checkbox" id="sVidBtn"><span>إظهار زر التحميل العائم على زاوية الفيديوهات في المتصفح</span></label>
 <div class="row">
  <button class="btn pri" id="okSet">حفظ</button>
  <button class="btn" id="bDeskSc">إنشاء اختصار على سطح المكتب</button>
  <button class="btn" id="bRegMag">تعيين كبرنامج افتراضي للـ Magnet</button>
  <button class="btn" id="bChkUpd">التحقق من التحديثات</button>
  <button class="btn" data-close>إلغاء</button>
 </div></dialog>

<dialog id="dDel"><h3>إزالة التنزيل</h3><p>هل تريد حذف الملف من جهازك أيضًا؟</p>
 <div class="row"><button class="btn" data-del="0">إزالة من القائمة فقط</button><button class="btn dng" data-del="1">حذف مع الملف</button><button class="btn" data-close>تراجع</button></div></dialog>

<dialog id="dInfo" style="width:min(600px,94vw)">
 <h3>معلومات ملف التحميل</h3>
 <div class="fgrid">
  <div>
   <label for="iUrl" style="margin-top:0">الرابط (URL)</label>
   <input class="l" id="iUrl" readonly>
   <label for="iCat">الفئة</label>
   <select id="iCat">
    <option value="عام">عام</option>
    <option value="مستندات">مستندات (PDF / Office)</option>
    <option value="مضغوط">ملفات مضغوطة (ZIP / RAR)</option>
    <option value="فيديو">فيديو</option>
    <option value="صوت">صوت</option>
    <option value="برامج">برامج (EXE / MSI)</option>
    <option value="صور">صور</option>
   </select>
   <label for="iDir">مجلد الحفظ</label>
   <div class="inrow">
    <input class="l" id="iDir">
    <button class="btn" id="iBrowse" type="button" title="اختيار مجلد">...</button>
   </div>
   <label class="ucheck" style="margin-top:8px;padding:6px 10px"><input type="checkbox" id="iRemCat"><span id="iRemTxt" style="font-size:12.5px">تذكر هذا المسار لهذه الفئة</span></label>
   <label for="iName">اسم الملف</label>
   <input id="iName" dir="auto">
   <label for="iDesc">الوصف (اختياري)</label>
   <input id="iDesc" placeholder="ملاحظة عن الملف...">
  </div>
  <div class="fbox">
   <div class="fi" id="iIcon" style="--c:#2447d6">FILE</div>
   <b id="iSize" style="font-size:13px">جارٍ الفحص...</b>
   <small id="iExt"></small>
  </div>
 </div>
 <div class="row">
  <button class="btn pri" id="iStart">بدء التحميل</button>
  <button class="btn" id="iLater">التحميل لاحقًا</button>
  <button class="btn" data-close>إلغاء الأمر</button>
 </div>
</dialog>

<dialog id="dTorAdd" class="wide">
 <h3>إضافة تورنت جديد — اختيار الملفات</h3>
 <div class="inrow" style="gap:12px;flex-wrap:wrap">
  <div style="flex:1;min-width:240px">
   <label for="taDir" style="margin-top:0">حفظ في</label>
   <div class="inrow">
    <input class="l" id="taDir">
    <button class="btn" id="taBrowse" type="button" title="اختيار مجلد">...</button>
   </div>
  </div>
  <div style="flex:1;min-width:220px">
   <label for="taSub" style="margin-top:0">اسم المجلد الفرعي</label>
   <input id="taSub" dir="auto">
  </div>
 </div>
 <div class="tmeta">
  <label class="ucheck" style="padding:4px 10px"><input type="checkbox" id="taMkSub" checked><span>إنشاء مجلد فرعي</span></label>
  <span id="taStats" style="align-self:center;font-weight:600;color:var(--tx)"></span>
  <span id="taDisk" style="align-self:center"></span>
 </div>
 <div class="tbar">
  <input id="taSearch" placeholder="بحث داخل ملفات التورنت...">
  <button class="btn" id="taAll" type="button" style="padding:6px 10px;font-size:12.5px">تحديد الكل</button>
  <button class="btn" id="taNone" type="button" style="padding:6px 10px;font-size:12.5px">إلغاء الكل</button>
  <button class="btn" id="taNoOpt" type="button" style="padding:6px 10px;font-size:12.5px" title="إزالة اللغات الاختيارية الإضافية مثل الروسية والفرنسية والألمانية...">إزالة اللغات الإضافية</button>
 </div>
 <div class="tfiles" id="taFiles"></div>
 <div class="row">
  <button class="btn pri" id="taStart">بدء التحميل</button>
  <button class="btn" id="taLater">إضافة متوقفًا</button>
  <button class="btn" data-close>إلغاء</button>
 </div>
</dialog>


<div id="toast"></div><div id="bye"><div><h2>تم إنهاء الدولي للتحميلات</h2><p>يمكنك إغلاق هذه النافذة.</p></div></div>
<script>
const T="__TOKEN__",$=s=>document.querySelector(s);
const api=async(p,b)=>{const r=await fetch(p,{method:b===undefined?'GET':'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'حدث خطأ');return j};
const sv=p=>`<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const I={down:'<path d="M12 3v12m0 0l-4-4m4 4l4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
all:'<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
ok:'<path d="M22 11v1a10 10 0 1 1-6-9"/><path d="M22 4L12 14l-3-3"/>',
pause:'<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
play:'<path d="M7 4l13 8-13 8z"/>',folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
link:'<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
video:'<rect x="2" y="5" width="15" height="14" rx="2"/><path d="M17 9l5-3v12l-5-3z"/>',
search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>',
trash:'<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4h6v2"/>',
plus:'<path d="M12 5v14M5 12h14"/>',power:'<path d="M18.4 6.6a9 9 0 1 1-12.8 0M12 2v10"/>',
set:'<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
clip:'<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
upload:'<path d="M12 15V3m0 0l-4 4m4-4l4 4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
copy:'<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
ext:'<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/>',
retry:'<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
x:'<path d="M18 6L6 18M6 6l12 12"/>',
magnet:'<path d="M6 15V6a2 2 0 0 1 2-2h1v6H8v5a4 4 0 0 0 8 0v-5h-1V4h1a2 2 0 0 1 2 2v9a6 6 0 0 1-12 0z"/>',
spark:'<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/>'};
document.querySelectorAll('[data-ic]').forEach(e=>e.insertAdjacentHTML('afterbegin',sv(I[e.dataset.ic])));
const B=n=>{if(n<0||n===undefined||n===null)return'—';const u=['بايت','ك.ب','م.ب','ج.ب','ت.ب'];let i=0;while(n>=1024&&i<4){n/=1024;i++}return(i?n.toFixed(n<10?2:1):Math.round(n))+' '+u[i]};
const D=s=>{s=Math.round(s);const h=s/3600|0,m=s%3600/60|0,x=s%60,p=v=>String(v).padStart(2,'0');return h?`${h}:${p(m)}:${p(x)}`:`${p(m)}:${p(x)}`};
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ST={queued:'في الانتظار',connecting:'جارٍ الاتصال',downloading:'قيد التنزيل',paused:'متوقف مؤقتًا',completed:'مكتمل',error:'فشل'};
const F={all:()=>1,active:i=>['queued','connecting','downloading'].includes(i.status),stopped:i=>['paused','error'].includes(i.status)};
const TT={all:'كل التنزيلات',active:'قيد التنزيل',stopped:'المتوقفة والفاشلة',video:'تحميل فيديو',upload:'مركز الرفع',torrent:'التورنت',soon:'قريبا'};
const UST={processing:'جارٍ تجهيز الفيديو',uploading:'جارٍ الرفع',completed:'تم الرفع',error:'فشل',cancelled:'ملغى'};
const CAT=[['#d98a00','zip rar 7z tar gz bz2 xz iso'],['#d6336c','mp4 mkv avi mov webm flv'],['#8f4fe0','mp3 flac wav aac ogg m4a'],['#1c9a5a','jpg jpeg png gif webp svg bmp'],['#2447d6','pdf doc docx xls xlsx ppt pptx txt epub'],['#0d9488','exe msi dmg pkg apk deb']];
const col=e=>(CAT.find(c=>c[1].split(' ').includes(e))||['#667386'])[0];
const isVidUrl=u=>/^https?:\/\/([\w-]+\.)*(youtube\.com|youtu\.be|instagram\.com|instagr\.am|tiktok\.com|facebook\.com|fb\.watch|x\.com|twitter\.com|vimeo\.com|twitch\.tv|kick\.com|reddit\.com|soundcloud\.com)\//i.test(u||'');
let S={items:[],uploads:[],torrents:[],torrent_engine:{},settings:{},speed:0,upload_speed:0,media_engine:{}},flt='all',lastProbe=null,lastVidHeaders=null,lastEngKey='',lastTorEngKey='',uSvc='catbox',uExp='';const els=new Map(),uels=new Map(),tels=new Map();
const toast=m=>{const t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(toast.h);toast.h=setTimeout(()=>t.classList.remove('on'),3500)};
const act=async(p,b)=>{try{await api(p,b||{});await tick(true)}catch(e){toast(e.message)}};

function setTab(name){
 flt=name;
 document.querySelectorAll('.nav[data-f]').forEach(x=>x.classList.toggle('on',x.dataset.f===name));
 const isV=name==='video',isU=name==='upload',isT=name==='torrent',isS=name==='soon';
 $('#videoView').style.display=isV?'flex':'none';
 $('#uploadView').style.display=isU?'flex':'none';
 $('#torrentView').style.display=isT?'flex':'none';
 $('#soonView').style.display=isS?'flex':'none';
 $('#list').style.display=(isV||isU||isT||isS)?'none':'flex';
 if(isV||isU||isT||isS)$('#empty').style.display='none';
 if(isV && !$('#vDir').value && S.settings)$('#vDir').value=S.settings.last_dir||S.settings.dir||'';
 if(isT && S.torrent_engine && S.torrent_engine.ready && !S.torrent_engine.running){api('/api/torrent/start_engine',{}).then(()=>tick(true)).catch(()=>{})}
 render();
}

function make(it){const el=document.createElement('article');el.className='item';el.dataset.id=it.id;
 el.innerHTML=`<div class="fi"></div><div style="min-width:0"><div class="top"><div class="name" dir="auto"></div><span class="chip"></span></div><div class="bar"></div><div class="meta"><span class="m1"></span><span class="m2"></span><span class="m3"></span></div></div>
 <div class="acts"><button class="btn ib" data-a="tog"></button><button class="btn ib" data-a="url" title="تحديث الرابط">${sv(I.link)}</button><button class="btn ib" data-a="up" title="رفع على Catbox ومشاركة الرابط">${sv(I.upload)}</button><button class="btn ib" data-a="file" title="فتح الملف">${sv(I.file)}</button><button class="btn ib" data-a="dir" title="إظهار في المجلد">${sv(I.folder)}</button><button class="btn ib" data-a="rm" title="إزالة">${sv(I.trash)}</button></div>`;
 el._r={fi:el.querySelector('.fi'),nm:el.querySelector('.name'),ch:el.querySelector('.chip'),bar:el.querySelector('.bar'),m:[...el.querySelectorAll('.meta span')],tog:el.querySelector('[data-a=tog]'),url:el.querySelector('[data-a=url]'),up:el.querySelector('[data-a=up]'),file:el.querySelector('[data-a=file]')};return el}
function upd(el,it){const r=el._r,done=it.status==='completed',run=['queued','connecting','downloading'].includes(it.status);
 el.className='item s-'+it.status;
 if(r.nm.textContent!==it.filename){r.nm.textContent=it.filename;r.nm.title=it.url;const x=it.filename.includes('.')?it.filename.split('.').pop():'';r.fi.style.setProperty('--c',col(x.toLowerCase()));r.fi.textContent=(x||'•').slice(0,4).toUpperCase()}
 r.ch.textContent=ST[it.status];
 const segs=it.segments,n=segs.length||1;if(r.bar.children.length!==n)r.bar.innerHTML='<div class="seg"><i></i></div>'.repeat(n);
 r.bar.classList.toggle('ind',it.size<0&&it.status==='downloading');
 if(segs.length)segs.forEach((s,k)=>{const L=s[1]-s[0]+1,c=r.bar.children[k];c.style.flex=L;c.firstChild.style.width=(done?100:(s[2]-s[0])/L*100)+'%'});
 else{const c=r.bar.children[0];c.style.flex=1;c.firstChild.style.width=(done?100:it.size>0?it.downloaded/it.size*100:0)+'%'}
 const pct=it.size>0?Math.floor(it.downloaded/it.size*100):0;
 if(done){r.m[0].textContent=B(it.size);r.m[1].textContent='اكتمل '+new Date(it.finished*1000).toLocaleString('ar-u-nu-latn',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});r.m[2].textContent=''}
 else if(it.status==='error'){r.m[0].innerHTML='<b class="er"></b>';r.m[0].firstChild.textContent=it.error;r.m[1].textContent=B(it.downloaded);r.m[2].textContent=''}
 else{r.m[0].textContent=`${B(it.downloaded)} من ${it.size>0?B(it.size):'حجم غير معروف'}`+(it.size>0?` (${pct}%)`:'');
  r.m[1].textContent=it.status==='downloading'&&it.speed>0?B(it.speed)+'/ث':'';r.m[2].textContent=it.eta?'متبقي '+D(it.eta):''}
 r.tog.classList.toggle('hid',done);r.url.classList.toggle('hid',done||it.kind==='media');r.up.classList.toggle('hid',!done);r.file.classList.toggle('hid',!done);
 r.tog.innerHTML=sv(run?I.pause:I.play);r.tog.title=run?'إيقاف مؤقت':'استئناف'}

function renderEngine(){
 const e=S.media_engine||{},key=JSON.stringify(e);
 if(key===lastEngKey)return;
 lastEngKey=key;
 const box=$('#engBox');
 const rts=e.js_runtimes||[];
 if(!e.ytdlp){
  box.innerHTML=`<div class="eng-warn"><div style="flex:1"><b>محرك تحميل الفيديو (yt-dlp) غير مثبّت</b><div style="font-size:13px;color:var(--mu)">${esc(e.install_msg||'شغّل setup.bat أو اضغط الزر للتثبيت تلقائيًا.')}</div></div><button class="btn pri" id="bInstYtdlp" ${e.installing?'disabled':''}>${e.installing?'جارٍ التثبيت...':'تثبيت تلقائي الآن'}</button></div>`;
  const bi=$('#bInstYtdlp');if(bi)bi.onclick=async()=>{try{await api('/api/media/install',{});toast('بدأ تثبيت محرك الفيديو...');tick(true)}catch(err){toast(err.message)}};
 } else if(!rts.length || !e.ejs){
  box.innerHTML=`<div class="eng-warn"><div style="flex:1"><b>تنبيه لتحميل يوتيوب</b><div style="font-size:13px;color:var(--mu)">${!rts.length?'لم يتم العثور على Deno — شغّل ملف setup.bat المرفق لتثبيته تلقائيًا.':'مكتبة yt-dlp-ejs غير مثبّتة — اضغط التحديث لتثبيتها.'}</div></div><button class="btn pri" id="bInstYtdlp" ${e.installing?'disabled':''}>${e.installing?'جارٍ التحديث...':'تثبيت yt-dlp-ejs'}</button></div>`;
  const bi=$('#bInstYtdlp');if(bi)bi.onclick=async()=>{try{await api('/api/media/install',{});toast('بدأ تحديث المحرك...');tick(true)}catch(err){toast(err.message)}};
 } else if(!e.ffmpeg){
  box.innerHTML=`<div class="eng-note">محرك الفيديو جاهز (${esc(rts.join(', '))}). لتحميل 1080p/4K وMP3 شغّل setup.bat لتثبيت FFmpeg ثم أعد فتح التطبيق.</div>`;
 } else {
  box.innerHTML='';
 }
}


const copyTxt=async(t,msg)=>{try{await navigator.clipboard.writeText(t);toast(msg||'تم النسخ إلى الحافظة!')}catch(e){const ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();toast(msg||'تم النسخ إلى الحافظة!')}};
const imgExts=['jpg','jpeg','png','gif','webp','bmp','svg'];
const vidExts=['mp4','mkv','webm','mov','avi','flv','m4v'];
const audExts=['mp3','wav','ogg','flac','m4a','aac'];
function buildHtmlCode(u){
 const ext=(u.filename.split('.').pop()||'').toLowerCase();
 if(imgExts.includes(ext))return `<img src="${u.url}" alt="${u.filename}">`;
 if(vidExts.includes(ext))return `<video src="${u.url}" controls width="640"></video>`;
 if(audExts.includes(ext))return `<audio src="${u.url}" controls></audio>`;
 return `<a href="${u.url}" target="_blank">${u.filename}</a>`;
}
function buildBbCode(u){
 const ext=(u.filename.split('.').pop()||'').toLowerCase();
 if(imgExts.includes(ext))return `[img]${u.url}[/img]`;
 return `[url=${u.url}]${u.filename}[/url]`;
}

let stagedFile=null,stagedUrl=null;
function closeStudio(){
 stagedFile=null;
 if(stagedUrl){URL.revokeObjectURL(stagedUrl);stagedUrl=null}
 const pv=$('#stPrev');pv.pause();pv.removeAttribute('src');pv.load();
 $('#uStudio').classList.add('hid');
}
function openStudio(f){
 closeStudio();
 stagedFile=f;
 stagedUrl=URL.createObjectURL(f);
 $('#stName').textContent=f.name;
 $('#stMeta').textContent=B(f.size);
 $('#stFrom').value='';$('#stTo').value='';$('#stMute').checked=false;
 $('#stMode').value=f.size>(30*1024*1024)?'streamable':'faststart';
 const pv=$('#stPrev');pv.src=stagedUrl;
 $('#uStudio').classList.remove('hid');
}

function makeUp(u){
 const el=document.createElement('article');el.className='uitem';el.dataset.id=u.id;
 el.innerHTML=`<div class="utop"><div class="fi"></div><div style="min-width:0"><div class="top"><div class="name" dir="auto"></div><span class="ubadge"></span><span class="chip"></span></div><div class="bar"><div class="seg" style="flex:1"><i></i></div></div><div class="meta"><span class="m1"></span><span class="m2"></span><span class="m3"></span></div></div><div class="acts"><button class="btn ib" data-ua="cancel" title="إلغاء الرفع">${sv(I.x)}</button><button class="btn ib" data-ua="retry" title="إعادة المحاولة">${sv(I.retry)}</button><button class="btn ib" data-ua="rm" title="إزالة من السجل">${sv(I.trash)}</button></div></div>
 <div class="ushare hid"><div class="ulink-box"><input readonly><button class="btn pri" style="padding:6px 12px;font-size:13px" data-ua="copy">${sv(I.copy)}نسخ الرابط</button><button class="btn hid" style="padding:6px 10px;font-size:13px" data-ua="play">${sv(I.play)}تشغيل</button><a class="btn" style="padding:6px 10px;font-size:13px;text-decoration:none" target="_blank" rel="noopener" data-ua="open">${sv(I.ext)}فتح</a></div>
 <div class="uplayer hid"></div>
 <div class="ucodes" style="margin-top:8px"><button class="cbtn" data-ua="html">${sv(I.copy)}نسخ كود HTML</button><button class="cbtn" data-ua="bb">${sv(I.copy)}نسخ كود منتديات (BBCode)</button><button class="cbtn dng hid" data-ua="rm_srv">${sv(I.trash)}حذف من سيرفر Catbox</button></div></div>`;
 el._r={fi:el.querySelector('.fi'),nm:el.querySelector('.name'),bd:el.querySelector('.ubadge'),ch:el.querySelector('.chip'),bar:el.querySelector('.bar'),fill:el.querySelector('.seg i'),m:[...el.querySelectorAll('.meta span')],cancel:el.querySelector('[data-ua=cancel]'),retry:el.querySelector('[data-ua=retry]'),share:el.querySelector('.ushare'),inp:el.querySelector('.ulink-box input'),play:el.querySelector('[data-ua=play]'),player:el.querySelector('.uplayer'),open:el.querySelector('[data-ua=open]'),rmSrv:el.querySelector('[data-ua=rm_srv]')};
 return el;
}

function updUp(el,u){
 const r=el._r,done=u.status==='completed',busy=u.status==='uploading'||u.status==='processing',ext=(u.filename.split('.').pop()||'').toLowerCase();
 el.className='uitem s-'+u.status;
 if(r.nm.textContent!==u.filename){
  r.nm.textContent=u.filename;r.nm.title=u.filename;
  r.fi.style.setProperty('--c',col(ext));r.fi.textContent=(ext||'•').slice(0,4).toUpperCase();
 }
 if(done && imgExts.includes(ext) && u.url && !el._imgSet){
  el._imgSet=true;
  r.fi.innerHTML=`<img class="uthumb" src="${esc(u.url)}" alt="">`;
  r.fi.style.background='none';
 }
 const isLit=u.service==='litterbox';
 r.bd.textContent=isLit?('مؤقت '+(u.expiry||'24h')+' — Litterbox'):'دائم — Catbox';
 r.bd.classList.toggle('tmp',isLit);
 r.ch.textContent=UST[u.status]||u.status;
 r.bar.classList.toggle('hid',done);
 const pct=u.size>0?Math.min(100,Math.floor(u.uploaded/u.size*100)):0;
 if(u.status==='uploading')r.fill.style.width=pct+'%';
 else if(done)r.fill.style.width='100%';
 if(done){
  r.m[0].textContent=B(u.size);
  r.m[1].textContent='رُفع '+new Date(u.finished*1000).toLocaleString('ar-u-nu-latn',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  r.m[2].textContent=u.video_mode==='streamable'?'بث سريع 720p':(u.video_mode==='faststart'&&vidExts.includes(ext)?'FastStart':'');
 } else if(u.status==='processing'){
  r.m[0].textContent=u.stage||'جارٍ تجهيز الفيديو للبث السريع...';
  r.m[1].textContent=B(u.size);r.m[2].textContent='';
 } else if(u.status==='error'||u.status==='cancelled'){
  r.m[0].innerHTML='<b class="er"></b>';r.m[0].firstChild.textContent=u.error||'فشل الرفع';
  r.m[1].textContent=B(u.size);r.m[2].textContent='';
 } else {
  r.m[0].textContent=`${B(u.uploaded)} من ${B(u.size)} (${pct}%)`;
  r.m[1].textContent=u.stage||(u.speed>0?B(u.speed)+'/ث':'جارٍ الاتصال بالسيرفر...');
  r.m[2].textContent=u.eta?'متبقي '+D(u.eta):'';
 }
 r.cancel.classList.toggle('hid',!busy);
 r.retry.classList.toggle('hid',!u.can_retry);
 r.share.classList.toggle('hid',!done);
 if(done){
  if(r.inp.value!==u.url)r.inp.value=u.url;
  r.open.href=u.url;
  r.play.classList.toggle('hid',!vidExts.includes(ext));
  r.rmSrv.classList.toggle('hid',!u.can_del_remote);
 }
}

function renderUploads(){
 const ups=S.uploads||[];
 $('#c-upload').textContent=ups.length;
 $('#uHead').classList.toggle('hid',!ups.length);
 if(flt!=='upload')return;
 const ids=new Set(ups.map(u=>u.id)),list=$('#uList');
 for(const[id,el]of uels)if(!ids.has(id)){el.remove();uels.delete(id)}
 ups.forEach((u,k)=>{let el=uels.get(u.id);if(!el){el=makeUp(u);uels.set(u.id,el)}updUp(el,u);if(list.children[k]!==el)list.insertBefore(el,list.children[k]||null)});
}

async function sendSingleFile(f, opts){
 opts=opts||{};
 const vmode=opts.video_mode||'faststart';
 const ext=(f.name.split('.').pop()||'').toLowerCase();
 const isVid=vidExts.includes(ext);
 const maxBytes=(uSvc==='litterbox'||(isVid&&vmode==='streamable'))?(1024*1024*1024):(200*1024*1024);
 if(f.size<=0){toast('الملف فارغ: '+f.name);return}
 if(f.size>maxBytes){
  toast(uSvc==='catbox'
   ?`الملف «${f.name}» أكبر من 200 م.ب! اختر «بث سريع 720p» لضغطه أو Litterbox المؤقت.`
   :`الملف «${f.name}» أكبر من الحد الأقصى (1 ج.ب).`);
  return;
 }
 toast('جارٍ إرسال: '+f.name);
 try{
  const r=await fetch('/api/upload/raw',{
   method:'POST',
   headers:{
    'X-Token':T,
    'X-Filename':encodeURIComponent(f.name),
    'X-Service':uSvc,
    'X-Expiry':uExp,
    'X-Video-Mode':vmode,
    'X-Trim-Start':opts.trim_start||'',
    'X-Trim-End':opts.trim_end||'',
    'X-Mute':opts.mute?'1':'0'
   },
   body:f
  });
  const j=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(j.error||'فشل بدء الرفع');
  await tick(true);
 }catch(e){toast(e.message)}
}

async function uploadFiles(fileList){
 const files=[...fileList];
 if(!files.length)return;
 if(files.length===1){
  const ext=(files[0].name.split('.').pop()||'').toLowerCase();
  if(vidExts.includes(ext)){openStudio(files[0]);return}
 }
 for(const f of files)await sendSingleFile(f,{video_mode:'faststart'});
}


function renderTorEngine(){
 const e=S.torrent_engine||{},key=JSON.stringify(e);
 if(key===lastTorEngKey)return;
 lastTorEngKey=key;
 const box=$('#torEngBox');
 if(!e.ready){
  box.innerHTML=`<div class="eng-warn"><div style="flex:1"><b>محرك التورنت (aria2) غير مثبّت</b><div style="font-size:13px;color:var(--mu)">${esc(e.install_msg||'يلزم تثبيته مرة واحدة فقط لتشغيل روابط Magnet وملفات .torrent.')}</div></div><button class="btn pri" id="bInstAria" ${e.installing?'disabled':''}>${e.installing?'جارٍ التثبيت...':'تثبيت aria2 تلقائيًا'}</button></div>`;
  const bi=$('#bInstAria');if(bi)bi.onclick=async()=>{try{await api('/api/torrent/install',{});toast('بدأ تثبيت محرك التورنت (aria2)...');tick(true)}catch(err){toast(err.message)}};
 } else {
  box.innerHTML='';
 }
}

function makeTor(t){
 const el=document.createElement('article');el.className='item';el.dataset.id=t.id;
 el.innerHTML=`<div class="fi" style="--c:#8f4fe0">TOR</div><div style="min-width:0"><div class="top"><div class="name" dir="auto"></div><span class="chip"></span></div><div class="bar"><div class="seg" style="flex:1"><i></i></div></div><div class="meta"><span class="m1"></span><span class="m2"></span><span class="m3"></span></div></div>
 <div class="acts"><button class="btn ib" data-ta="tog"></button><button class="btn ib" data-ta="dir" title="فتح المجلد">${sv(I.folder)}</button><button class="btn ib" data-ta="rm" title="إزالة">${sv(I.trash)}</button></div>`;
 el._r={nm:el.querySelector('.name'),ch:el.querySelector('.chip'),bar:el.querySelector('.bar'),fill:el.querySelector('.seg i'),m:[...el.querySelectorAll('.meta span')],tog:el.querySelector('[data-ta=tog]')};
 return el;
}

function updTor(el,t){
 const r=el._r,done=t.status==='completed',run=['queued','downloading'].includes(t.status);
 el.className='item s-'+t.status;
 if(r.nm.textContent!==t.name){r.nm.textContent=t.name;r.nm.title=t.name}
 r.ch.textContent=ST[t.status]||t.status;
 r.bar.classList.toggle('ind',t.size<0&&t.status==='downloading');
 const pct=t.size>0?Math.min(100,Math.floor(t.downloaded/t.size*100)):0;
 r.fill.style.width=(done?100:pct)+'%';
 if(done){r.m[0].textContent=B(t.size);r.m[1].textContent='اكتمل التحميل';r.m[2].textContent=''}
 else if(t.status==='error'){r.m[0].innerHTML='<b class="er"></b>';r.m[0].firstChild.textContent=t.error||'فشل التورنت';r.m[1].textContent=B(t.downloaded);r.m[2].textContent=''}
 else{
  r.m[0].textContent=`${B(t.downloaded)} من ${t.size>0?B(t.size):'جارٍ جلب البيانات'}`+(t.size>0?` (${pct}%)`:'');
  r.m[1].textContent=`↓ ${B(t.speed)}/ث  |  Peers: ${t.peers} (Seeds: ${t.seeders})`;
  r.m[2].textContent=t.eta?'متبقي '+D(t.eta):'';
 }
 r.tog.classList.toggle('hid',done);
 r.tog.innerHTML=sv(run?I.pause:I.play);r.tog.title=run?'إيقاف مؤقت':'استئناف';
}

function renderTorrents(){
 renderTorEngine();
 const tors=S.torrents||[];
 $('#c-torrent').textContent=tors.length;
 $('#tHead').classList.toggle('hid',!tors.length);
 if(flt!=='torrent')return;
 const ids=new Set(tors.map(t=>t.id)),list=$('#tList');
 for(const[id,el]of tels)if(!ids.has(id)){el.remove();tels.delete(id)}
 tors.forEach((t,k)=>{let el=tels.get(t.id);if(!el){el=makeTor(t);tels.set(t.id,el)}updTor(el,t);if(list.children[k]!==el)list.insertBefore(el,list.children[k]||null)});
}

let curTorInfo=null,curInfoHdrs=null;
const CAT_MAP=[
 ['مضغوط',['zip','rar','7z','tar','gz','bz2','xz','iso']],
 ['فيديو',['mp4','mkv','avi','mov','webm','flv','m4v']],
 ['صوت',['mp3','flac','wav','aac','ogg','m4a']],
 ['صور',['jpg','jpeg','png','gif','webp','svg','bmp']],
 ['مستندات',['pdf','doc','docx','xls','xlsx','ppt','pptx','txt','epub']],
 ['برامج',['exe','msi','dmg','pkg','apk','deb']]
];
function guessCat(fn){
 const x=(fn&&fn.includes('.')?fn.split('.').pop().toLowerCase():'');
 const found=CAT_MAP.find(c=>c[1].includes(x));
 return found?found[0]:'عام';
}
function updateInfoIcon(fn){
 const x=(fn&&fn.includes('.')?fn.split('.').pop().toLowerCase():'');
 $('#iIcon').style.setProperty('--c',col(x));
 $('#iIcon').textContent=(x||'FILE').slice(0,4).toUpperCase();
 $('#iExt').textContent=x?x.toUpperCase():'';
}
async function openDownloadInfo(url, headers){
 curInfoHdrs=headers||null;
 $('#iUrl').value=url;
 $('#iDesc').value='';
 $('#iRemCat').checked=false;
 $('#iSize').textContent='جارٍ فحص الرابط...';
 const initName=decodeURIComponent((url.split('?')[0].split('/').pop()||'download')).slice(0,180);
 $('#iName').value=initName;
 updateInfoIcon(initName);
 const applyCatDir=(cat)=>{
  const cdirs=(S.settings&&S.settings.category_dirs)||{};
  $('#iDir').value=cdirs[cat]||(S.settings&&(S.settings.last_dir||S.settings.dir))||'';
  $('#iRemTxt').textContent=`تذكر هذا المسار لفئة «${cat}»`;
 };
 const c0=guessCat(initName);
 $('#iCat').value=c0;
 applyCatDir(c0);
 if(!$('#dInfo').open)$('#dInfo').showModal();
 try{
  const info=await api('/api/probe_direct',{url,headers:curInfoHdrs});
  if($('#iUrl').value!==url)return;
  if(info.filename){
   $('#iName').value=info.filename;
   updateInfoIcon(info.filename);
   const c1=guessCat(info.filename);
   $('#iCat').value=c1;
   applyCatDir(c1);
  }
  if(info.warning){toast(info.warning);$('#iSize').textContent='يتطلب صلاحية'}
  else{$('#iSize').textContent=info.size>0?B(info.size):'حجم غير معروف';}
 }catch(e){
  $('#iSize').textContent='حجم غير معروف';
 }
}

function updateTorStats(){
 if(!curTorInfo)return;
 const cbs=[...$('#taFiles').querySelectorAll('input[type=checkbox]')];
 let selCnt=0,selSz=0;
 cbs.forEach(cb=>{if(cb.checked){selCnt++;selSz+=+cb.dataset.sz}});
 $('#taStats').textContent=`المحدد: ${selCnt} من ${cbs.length} ملف (${B(selSz)} من ${B(curTorInfo.total_size)})`;
}
function openTorDialog(info){
 curTorInfo=info;
 $('#taDir').value=info.default_dir||(S.settings&&S.settings.dir)||'';
 $('#taSub').value=info.name||'';
 $('#taMkSub').checked=(info.files&&info.files.length>1);
 $('#taSearch').value='';
 $('#taDisk').textContent=info.disk_free>0?('المساحة المتاحة: '+B(info.disk_free)):'';
 $('#taFiles').innerHTML=(info.files||[]).map(f=>`
  <label class="tfile" data-p="${esc(f.path.toLowerCase())}">
   <input type="checkbox" checked data-idx="${f.index}" data-sz="${f.size}">
   <span class="tfn" title="${esc(f.path)}">${esc(f.path)}</span>
   <span class="tfs">${B(f.size)}</span>
  </label>`).join('');
 updateTorStats();
 $('#dTorAdd').showModal();
}

async function addMagnetUri(uri, direct){
 uri=(uri||$('#tMagnet').value||'').trim();
 if(!uri.toLowerCase().startsWith('magnet:?')){toast('الصق رابط magnet:? صالح');return}
 if(direct){
  try{await api('/api/torrent/magnet',{uri});$('#tMagnet').value='';toast('تمت إضافة التورنت للتحميل المباشر!');setTab('torrent');tick(true)}
  catch(e){toast(e.message)}
  return;
 }
 const btn=$('#tAddBtn');
 btn.disabled=true;btn.textContent='جارٍ جلب قائمة الملفات...';
 toast('جارٍ الاتصال بالـ Peers لجلب قائمة الملفات (قد يستغرق بضع ثوانٍ)...');
 try{
  const info=await api('/api/torrent/inspect_magnet',{uri});
  $('#tMagnet').value='';
  openTorDialog(info);
 }catch(e){
  toast(e.message);
 }finally{
  btn.disabled=false;btn.innerHTML=sv(I.search)+'فحص واختيار الملفات';
 }
}

async function addTorrentFiles(fileList){
 const files=[...fileList].filter(f=>f.name.toLowerCase().endsWith('.torrent'));
 if(!files.length){toast('اختر ملف .torrent صالح');return}
 const toB64=async(f)=>{
  const buf=await f.arrayBuffer(),bytes=new Uint8Array(buf);
  let bin='';for(let i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]);
  return btoa(bin);
 };
 if(files.length===1){
  try{
   const b64=await toB64(files[0]);
   const info=await api('/api/torrent/inspect_file',{data:b64});
   openTorDialog(info);
  }catch(e){toast(e.message)}
  return;
 }
 for(const f of files){
  try{await api('/api/torrent/file',{data:await toB64(f)});toast('تمت إضافة: '+f.name);setTab('torrent');tick(true)}
  catch(e){toast(e.message)}
 }
}


let lastUpdMsg='';
function renderUpdate(){
 const u=S.update||{};
 if(u.current)$('#appVer').textContent=u.current;
 const bar=$('#updBar');
 if(u.available){
  bar.style.display='flex';
  $('#updTtl').textContent=`يتوفر تحديث جديد (الإصدار ${u.latest})!`;
  $('#updNotes').textContent=u.notes||'تحسينات وإصلاحات جديدة لبرنامج الدولي للتحميلات.';
  const b=$('#bDoUpd');
  b.disabled=!!u.applying;
  b.textContent=u.applying?'جارٍ التحديث وإعادة التشغيل...':'تحديث وإعادة التشغيل الآن';
 } else {
  bar.style.display='none';
 }
 if(u.msg && u.msg!==lastUpdMsg){
  lastUpdMsg=u.msg;
  if(!u.available || u.applying)toast(u.msg);
 }
}

function render(){
 for(const k in F)$('#c-'+k).textContent=S.items.filter(F[k]).length;
 const spdTxt=S.upload_speed>0&&S.speed<=0?('↑ '+B(S.upload_speed)+'/ث'):(B(S.speed)+'/ث');
 $('#spd').textContent=spdTxt;
 $('#spdCap').textContent=S.settings.max_speed>0?'الحد: '+B(S.settings.max_speed*1024)+'/ث':'';
 $('#ttl').textContent=TT[flt];
 renderEngine();
 renderUploads();
 renderTorrents();
 renderUpdate();
 $('#extBar').style.display=(S.settings&&S.settings.ext_updated_notice)?'flex':'none';
 if(flt==='video'||flt==='upload'||flt==='torrent'||flt==='soon')return;
 const vis=S.items.filter(F[flt]),ids=new Set(vis.map(i=>i.id)),list=$('#list');
 for(const[id,el]of els)if(!ids.has(id)){el.remove();els.delete(id)}
 vis.forEach((it,k)=>{let el=els.get(it.id);if(!el){el=make(it);els.set(it.id,el)}upd(el,it);if(list.children[k]!==el)list.insertBefore(el,list.children[k]||null)});
 $('#empty').style.display=vis.length?'none':'block';
}

async function doProbe(url, headers){
 url=(url||$('#vUrl').value||'').trim();
 if(!url){toast('الصق رابط الفيديو أولًا');return}
 $('#vUrl').value=url;
 lastVidHeaders=headers||null;
 const btn=$('#vProbe'),res=$('#vResult');
 btn.disabled=true;btn.textContent='جارٍ فحص الرابط...';
 res.classList.remove('hid');
 res.innerHTML='<p style="text-align:center;color:var(--mu);margin:14px 0">جارٍ جلب معلومات الفيديو والجودات المتاحة...</p>';
 try{
  const info=await api('/api/media/probe',{url,headers:lastVidHeaders});
  lastProbe=info;
  const dur=info.duration?D(info.duration):'';
  res.innerHTML=`<div class="vinfo">
   ${info.thumbnail?`<img class="vthumb" src="${esc(info.thumbnail)}" alt="">`:'<div class="vthumb"></div>'}
   <div>
    <div class="vtitle">${esc(info.title)}</div>
    <div class="vsub">
     ${info.site?`<span>الموقع: ${esc(info.site)}</span>`:''}
     ${info.uploader?`<span>القناة: ${esc(info.uploader)}</span>`:''}
     ${dur?`<span>المدة: ${dur}</span>`:''}
    </div>
    <div style="font-size:13px;color:var(--mu)">اختر الجودة المطلوبة لبدء التحميل فورًا:</div>
   </div>
  </div>
  <div class="fmts">${info.formats.map((f,idx)=>`
   <button class="fbtn${f.audio_only?' aud':''}" data-fi="${idx}">
    <div><b>${esc(f.label)}</b><small>${f.size>0?B(f.size):'حجم تقديري عند البدء'}</small></div>
    <span class="fext">${esc(f.ext)}</span>
   </button>`).join('')}</div>`;
  res.querySelectorAll('[data-fi]').forEach(b=>b.onclick=async()=>{
   const f=info.formats[+b.dataset.fi];
   b.disabled=true;
   try{
    await api('/api/media/add',{url:info.url,title:info.title,format_id:f.format_id,audio_only:f.audio_only,ext:f.ext,size:f.size,headers:lastVidHeaders,yt_clients:f.yt_clients||null,dir:$('#vDir').value.trim()});
    toast('بدأ تحميل: '+info.title);
    setTab('active');
    tick(true);
   }catch(e){toast(e.message);b.disabled=false}
  });
 }catch(e){
  res.innerHTML=`<p style="color:var(--er);margin:6px 0;font-weight:600">${esc(e.message)}</p>`;
 }finally{
  btn.disabled=false;btn.innerHTML=sv(I.search)+'فحص الرابط';
 }
}

async function tick(once){
 try{
  S=await api('/api/state');
  if(S.pending_video&&S.pending_video.url){
   const pv=S.pending_video;
   setTab('video');
   doProbe(pv.url, pv.headers);
  }
  if(S.pending_download&&S.pending_download.url){
   const pd=S.pending_download;
   openDownloadInfo(pd.url, pd.headers);
  }
  if(S.pending_magnet){
   const pm=S.pending_magnet;
   setTab('torrent');
   addMagnetUri(pm,false);
  }
  render();
 }catch(e){}
 if(!once)setTimeout(tick,700);
}

document.querySelectorAll('.nav[data-f]').forEach(b=>b.onclick=()=>setTab(b.dataset.f));
$('#bGoVideo').onclick=()=>{setTab('video');$('#vUrl').focus()};
$('#bGoUpload').onclick=()=>setTab('upload');
$('#bGoTorrent').onclick=()=>{setTab('torrent');$('#tMagnet').focus()};
$('#tAddBtn').onclick=()=>addMagnetUri(null,false);
$('#tFastBtn').onclick=()=>addMagnetUri(null,true);
$('#iCat').onchange=()=>{
 const cat=$('#iCat').value,cdirs=(S.settings&&S.settings.category_dirs)||{};
 if(cdirs[cat])$('#iDir').value=cdirs[cat];
 $('#iRemTxt').textContent=`تذكر هذا المسار لفئة «${cat}»`;
};
$('#iName').oninput=()=>updateInfoIcon($('#iName').value);
$('#iBrowse').onclick=async()=>{try{const r=await api('/api/browse_dir',{initial:$('#iDir').value});if(r.dir)$('#iDir').value=r.dir}catch(e){toast(e.message)}};
const submitInfo=async(startNow)=>{
 try{
  await api('/api/add_single',{
   url:$('#iUrl').value.trim(),dir:$('#iDir').value.trim(),filename:$('#iName').value.trim(),
   headers:curInfoHdrs,start_now:startNow,category:$('#iCat').value,
   remember_cat:$('#iRemCat').checked,desc:$('#iDesc').value.trim()
  });
  $('#dInfo').close();
  toast(startNow?'بدأ التحميل!':'تمت الإضافة للتحميل لاحقًا');
  setTab(startNow?'active':'all');tick(true);
 }catch(e){toast(e.message)}
};
$('#iStart').onclick=()=>submitInfo(true);
$('#iLater').onclick=()=>submitInfo(false);
$('#taBrowse').onclick=async()=>{
 try{
  const r=await api('/api/browse_dir',{initial:$('#taDir').value});
  if(r.dir){
   $('#taDir').value=r.dir;
   const d=await api('/api/disk_free',{dir:r.dir});
   if(d.free>0)$('#taDisk').textContent='المساحة المتاحة: '+B(d.free);
  }
 }catch(e){toast(e.message)}
};
$('#taFiles').onchange=updateTorStats;
$('#taSearch').oninput=()=>{
 const q=$('#taSearch').value.trim().toLowerCase();
 $('#taFiles').querySelectorAll('.tfile').forEach(r=>r.classList.toggle('hid',q&&!r.dataset.p.includes(q)));
};
$('#taAll').onclick=()=>{$('#taFiles').querySelectorAll('input[type=checkbox]').forEach(c=>{if(!c.closest('.tfile').classList.contains('hid'))c.checked=true});updateTorStats()};
$('#taNone').onclick=()=>{$('#taFiles').querySelectorAll('input[type=checkbox]').forEach(c=>{if(!c.closest('.tfile').classList.contains('hid'))c.checked=false});updateTorStats()};
$('#taNoOpt').onclick=()=>{
 const rx=/(optional|selective|russian|french|german|italian|polish|portuguese|brazilian|spanish|mexican|japanese|chinese|korean|turkish|dutch|czech|soundtrack|credits|4k-videos|bonus)/i;
 let removed=0;
 $('#taFiles').querySelectorAll('.tfile').forEach(row=>{
  const p=row.dataset.p,cb=row.querySelector('input');
  if(rx.test(p)&&!/arabic|english/i.test(p)){if(cb.checked){cb.checked=false;removed++}}
 });
 updateTorStats();
 toast(removed?`تم إلغاء تحديد ${removed} ملف اختياري/لغة إضافية`:'لم يتم العثور على ملفات لغات اختيارية');
};
const submitTor=async(paused)=>{
 if(!curTorInfo)return;
 const sel=[...$('#taFiles').querySelectorAll('input[type=checkbox]:checked')].map(c=>+c.dataset.idx);
 if(!sel.length){toast('اختر ملفًا واحدًا على الأقل للتحميل');return}
 try{
  await api('/api/torrent/file',{
   data:curTorInfo.torrent_b64,dir:$('#taDir').value.trim(),
   subfolder:$('#taMkSub').checked?$('#taSub').value.trim():'',
   select_files:sel,paused:paused
  });
  $('#dTorAdd').close();
  toast(paused?'تمت إضافة التورنت متوقفًا':'بدأ تحميل التورنت بالملفات المحددة!');
  setTab('torrent');tick(true);
 }catch(e){toast(e.message)}
};
$('#taStart').onclick=()=>submitTor(false);
$('#taLater').onclick=()=>submitTor(true);
$('#tMagnet').addEventListener('keydown',e=>{if(e.key==='Enter')addMagnetUri()});
$('#tPaste').onclick=async()=>{try{const t=(await navigator.clipboard.readText()).trim();$('#tMagnet').value=t;if(t.toLowerCase().startsWith('magnet:?'))addMagnetUri(t)}catch(e){toast('تعذّر قراءة الحافظة، الصق الرابط يدويًا')}};
const td=$('#tDrop'),tf=$('#tFile');
td.onclick=()=>tf.click();
tf.onchange=()=>{if(tf.files&&tf.files.length){addTorrentFiles(tf.files);tf.value=''}};
td.ondragover=e=>{e.preventDefault();td.classList.add('drag')};
td.ondragleave=()=>td.classList.remove('drag');
td.ondrop=e=>{e.preventDefault();td.classList.remove('drag');if(e.dataTransfer.files&&e.dataTransfer.files.length)addTorrentFiles(e.dataTransfer.files)};
$('#bClearTor').onclick=()=>act('/api/torrent/clear_done');
$('#tList').onclick=e=>{
 const b=e.target.closest('[data-ta]');if(!b)return;
 const id=b.closest('.item').dataset.id,t=(S.torrents||[]).find(x=>x.id===id);if(!t)return;
 const a=b.dataset.ta;
 if(a==='tog')act(['queued','downloading'].includes(t.status)?'/api/torrent/pause':'/api/torrent/resume',{id});
 else if(a==='dir')act('/api/torrent/open',{id});
 else if(a==='rm')act('/api/torrent/remove',{id});
};
$('#uModes').onclick=e=>{
 const b=e.target.closest('.umode');if(!b)return;
 uSvc=b.dataset.svc;uExp=b.dataset.exp||'';
 document.querySelectorAll('.umode').forEach(x=>x.classList.toggle('on',x===b));
 $('#dzHint').textContent=uSvc==='catbox'
  ?'Catbox دائم (حتى 200 م.ب) — عند اختيار فيديو سيفتح لك استوديو القص والضغط للبث الفوري.'
  :`Litterbox مؤقت (${uExp} — حتى 1 ج.ب) — عند اختيار فيديو سيفتح لك استوديو القص والضغط للبث الفوري.`;
};
const dz=$('#dropZone'),uf=$('#uFile');
dz.onclick=()=>uf.click();
uf.onchange=()=>{if(uf.files&&uf.files.length){uploadFiles(uf.files);uf.value=''}};
dz.ondragover=e=>{e.preventDefault();dz.classList.add('drag')};
dz.ondragleave=()=>dz.classList.remove('drag');
dz.ondrop=e=>{e.preventDefault();dz.classList.remove('drag');if(e.dataTransfer.files&&e.dataTransfer.files.length)uploadFiles(e.dataTransfer.files)};
$('#bClearUp').onclick=()=>act('/api/upload/clear_done');
$('#stCancel').onclick=closeStudio;
$('#stSetFrom').onclick=()=>{$('#stFrom').value=D($('#stPrev').currentTime||0)};
$('#stSetTo').onclick=()=>{$('#stTo').value=D($('#stPrev').currentTime||0)};
$('#stStart').onclick=async()=>{
 if(!stagedFile)return;
 const f=stagedFile,opts={video_mode:$('#stMode').value,trim_start:$('#stFrom').value.trim(),trim_end:$('#stTo').value.trim(),mute:$('#stMute').checked};
 closeStudio();
 await sendSingleFile(f,opts);
};
$('#uList').onclick=e=>{
 const b=e.target.closest('[data-ua]');if(!b)return;
 const card=b.closest('.uitem'),id=card.dataset.id,u=(S.uploads||[]).find(x=>x.id===id);if(!u)return;
 const a=b.dataset.ua;
 if(a==='copy')copyTxt(u.url,'تم نسخ الرابط المباشر!');
 else if(a==='play'){
  const box=card._r.player;
  if(box.classList.contains('hid')){box.innerHTML=`<video src="${esc(u.url)}" controls autoplay></video>`;box.classList.remove('hid')}
  else{box.innerHTML='';box.classList.add('hid')}
 }
 else if(a==='html')copyTxt(buildHtmlCode(u),'تم نسخ كود HTML!');
 else if(a==='bb')copyTxt(buildBbCode(u),'تم نسخ كود المنتديات (BBCode)!');
 else if(a==='cancel')act('/api/upload/cancel',{id});
 else if(a==='retry')act('/api/upload/retry',{id});
 else if(a==='rm')act('/api/upload/remove',{id,delete_remote:false});
 else if(a==='rm_srv'){if(confirm('هل تريد حذف هذا الملف نهائيًا من سيرفر Catbox؟'))act('/api/upload/remove',{id,delete_remote:true})}
};
$('#vProbe').onclick=()=>doProbe();
$('#vUrl').addEventListener('keydown',e=>{if(e.key==='Enter')doProbe()});
$('#vBrowse').onclick=async()=>{try{const r=await api('/api/browse_dir',{initial:$('#vDir').value||S.settings.dir||''});if(r.dir)$('#vDir').value=r.dir}catch(e){toast(e.message)}};
$('#vPaste').onclick=async()=>{try{const t=(await navigator.clipboard.readText()).trim();$('#vUrl').value=t;if(t)doProbe(t)}catch(e){toast('تعذّر قراءة الحافظة، الصق الرابط يدويًا')}};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
let delId=null,urlId=null;
$('#list').onclick=e=>{const b=e.target.closest('[data-a]');if(!b)return;const id=b.closest('.item').dataset.id,it=S.items.find(i=>i.id===id);if(!it)return;
 const a=b.dataset.a;
 if(a==='tog')act(['queued','connecting','downloading'].includes(it.status)?'/api/pause':'/api/resume',{id});
 else if(a==='url'){urlId=id;$('#uNew').value=it.url;$('#dUrl').showModal();$('#uNew').focus();$('#uNew').select()}
 else if(a==='up'){api('/api/upload/from_item',{id,service:'catbox'}).then(()=>{toast('بدأ رفع الملف على Catbox!');setTab('upload');tick(true)}).catch(err=>toast(err.message))}
 else if(a==='file'||a==='dir')act('/api/open',{id,what:a==='file'?'file':'folder'});
 else if(a==='rm'){if(it.status==='completed'){delId=id;$('#dDel').showModal()}else act('/api/remove',{id})}};
document.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{if(b.dataset.del!=='x'){act('/api/remove',{id:delId,delete_file:b.dataset.del==='1'})}$('#dDel').close()});
$('#okUrl').onclick=async()=>{try{await api('/api/refresh_url',{id:urlId,url:$('#uNew').value.trim()});$('#dUrl').close();toast('تم تحديث الرابط وجارٍ الاستئناف');tick(true)}catch(e){toast(e.message)}};
function openAdd(t){
 if(t&&/^magnet:\?/i.test(t)){addMagnetUri(t,false);return}
 if(t&&isVidUrl(t)){setTab('video');doProbe(t);return}
 if(t&&/^https?:\/\//i.test(t)&&S.settings&&S.settings.confirm_dialog!==false){openDownloadInfo(t);return}
 $('#urls').value=t||'';$('#dAdd').showModal();$('#urls').focus();
}
$('#bAdd').onclick=()=>openAdd();
$('#bPaste').onclick=async()=>{try{$('#urls').value=(await navigator.clipboard.readText()).trim()}catch(e){toast('تعذّر قراءة الحافظة، الصق الرابط يدويًا')}};
$('#okAdd').onclick=async()=>{
 const raw=$('#urls').value.trim().split(/\s+/).filter(Boolean);
 if(raw.length===1&&/^magnet:\?/i.test(raw[0])){$('#dAdd').close();addMagnetUri(raw[0],false);return}
 if(raw.length===1&&isVidUrl(raw[0])){$('#dAdd').close();setTab('video');doProbe(raw[0]);return}
 if(raw.length===1&&/^https?:\/\//i.test(raw[0])&&S.settings&&S.settings.confirm_dialog!==false){$('#dAdd').close();openDownloadInfo(raw[0]);return}
 try{const r=await api('/api/add',{urls:raw});$('#dAdd').close();
 toast(r.errors.length?`تم تجاهل ${r.errors.length} رابط غير صالح (يلزم http أو https)`:`أُضيف ${r.added} إلى القائمة`);tick(true)}catch(e){toast(e.message)}
};
document.addEventListener('paste',e=>{if($('dialog[open]')||/INPUT|TEXTAREA/.test(document.activeElement.tagName))return;
 const t=(e.clipboardData.getData('text')||'').trim();if(/^(https?:\/\/|magnet:\?)/i.test(t))openAdd(t)});
$('#bPauAll').onclick=()=>act('/api/pause_all');$('#bResAll').onclick=()=>act('/api/resume_all');$('#bClear').onclick=()=>act('/api/clear_done');
const opt=(s,a,v)=>{s.innerHTML=a.map(x=>`<option${x==v?' selected':''}>${x}</option>`).join('')};
$('#bSet').onclick=()=>{const s=S.settings;$('#sDir').value=s.dir||'';opt($('#sSeg'),[1,2,4,8,12,16],s.segments);opt($('#sAct'),[1,2,3,4,5,6,8],s.max_active);$('#sSpd').value=s.max_speed||0;$('#sHash').value=s.catbox_userhash||'';$('#sConf').checked=s.confirm_dialog!==false;$('#sAuto').checked=!!s.autostart;$('#sVidBtn').checked=s.show_video_btn!==false;$('#dSet').showModal()};
$('#okSet').onclick=async()=>{try{await api('/api/settings',{dir:$('#sDir').value,segments:+$('#sSeg').value,max_active:+$('#sAct').value,max_speed:Math.max(0,parseInt($('#sSpd').value,10)||0),catbox_userhash:$('#sHash').value.trim(),confirm_dialog:$('#sConf').checked,autostart:$('#sAuto').checked,show_video_btn:$('#sVidBtn').checked});$('#dSet').close();toast('تم حفظ الإعدادات');tick(true)}catch(e){toast(e.message)}};
$('#bChkUpd').onclick=async()=>{try{lastUpdMsg='';await api('/api/update/check',{});toast('جارٍ التحقق من التحديثات...');tick(true)}catch(e){toast(e.message)}};
$('#bDoUpd').onclick=async()=>{
 try{
  await api('/api/update/apply',{});
  toast('جارٍ تنزيل التحديث وإعادة تشغيل التطبيق...');
  setTimeout(()=>location.reload(), 4000);
 }catch(e){toast(e.message)}
};
$('#bRegMag').onclick=async()=>{try{const r=await api('/api/register_magnet',{});toast(r.locked_by_other?'تم التسجيل! اختر «الدولي للتحميلات» لبروتوكول MAGNET من نافذة إعدادات ويندوز التي فُتحت الآن.':'تم تعيين الدولي للتحميلات كبرنامج افتراضي لروابط Magnet بنجاح!')}catch(e){toast(e.message)}};
$('#bDeskSc').onclick=async()=>{try{await api('/api/create_shortcut',{});toast('تم إنشاء اختصار «الدولي للتحميلات» على سطح المكتب!')}catch(e){toast(e.message)}};
$('#bDisExt').onclick=()=>act('/api/dismiss_ext_notice');
$('#bQuit').onclick=async()=>{try{await api('/api/quit',{})}catch(e){}$('#bye').style.display='grid'};
tick();
</script></body></html>'''


POPUP_PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>معلومات ملف التحميل — الدولي</title>
<link rel="icon" type="image/png" sizes="256x256" href="/icon.png?v=3">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef0f3;--sf:#fff;--tx:#121b26;--mu:#667386;--ln:#dde2e8;--ac:#2447d6;--ac2:#e6ebfc;--er:#cf3a3a;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0d1218;--sf:#151c24;--tx:#e7ecf2;--mu:#8995a6;--ln:#252f3b;--ac:#7c9bff;--ac2:#1b2748;--er:#ff7878}}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--sf);color:var(--tx);font:14.5px/1.55 "SF Arabic","Segoe UI",Tahoma,system-ui,sans-serif}
button,input,select{font:inherit;color:inherit}
h2{margin:0 0 12px;font-size:18px;display:flex;align-items:center;gap:10px}
h2 img{width:28px;height:28px;border-radius:7px}
.fgrid{display:grid;grid-template-columns:1fr 96px;gap:14px;align-items:start}
.fbox{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;padding:14px 8px;border-radius:12px;background:var(--bg);border:1px solid var(--ln);text-align:center}
.fi{width:54px;height:54px;border-radius:12px;display:grid;place-items:center;font-size:13px;font-weight:700;direction:ltr;color:var(--c);background:color-mix(in srgb,var(--c) 15%,transparent)}
label{display:block;font-size:12.5px;color:var(--mu);margin:10px 0 4px}
input,select{width:100%;border:1px solid var(--ln);background:var(--bg);border-radius:10px;padding:8px 11px}
input.l{direction:ltr;text-align:left}
.inrow{display:flex;gap:6px;align-items:center}.inrow input{flex:1}
.ucheck{display:flex;align-items:center;gap:8px;padding:6px 10px;border:1px solid var(--ln);background:var(--bg);border-radius:10px;cursor:pointer;font-size:12.5px;margin-top:8px}
.ucheck input{width:auto;margin:0}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--ln);background:var(--bg);border-radius:10px;padding:8px 16px;cursor:pointer}
.btn:hover{border-color:var(--ac)}
.btn.pri{background:var(--ac);border-color:var(--ac);color:#fff;font-weight:600}
@media(prefers-color-scheme:dark){.btn.pri{color:#0b1020}}
.row{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
#err{color:var(--er);font-size:13px;margin-top:8px;min-height:18px}
</style></head><body>
<h2><img src="/icon.png?v=3" alt="">معلومات ملف التحميل</h2>
<div class="fgrid">
 <div>
  <label for="iUrl" style="margin-top:0">الرابط (URL)</label>
  <input class="l" id="iUrl" readonly>
  <label for="iCat">الفئة</label>
  <select id="iCat">
   <option value="عام">عام</option>
   <option value="مستندات">مستندات (PDF / Office)</option>
   <option value="مضغوط">ملفات مضغوطة (ZIP / RAR)</option>
   <option value="فيديو">فيديو</option>
   <option value="صوت">صوت</option>
   <option value="برامج">برامج (EXE / MSI)</option>
   <option value="صور">صور</option>
  </select>
  <label for="iDir">مجلد الحفظ</label>
  <div class="inrow">
   <input class="l" id="iDir">
   <button class="btn" id="iBrowse" type="button" title="اختيار مجلد">...</button>
  </div>
  <label class="ucheck"><input type="checkbox" id="iRemCat"><span id="iRemTxt">تذكر هذا المسار لهذه الفئة</span></label>
  <label for="iName">اسم الملف</label>
  <input id="iName" dir="auto">
  <label for="iDesc">الوصف (اختياري)</label>
  <input id="iDesc" placeholder="ملاحظة عن الملف...">
 </div>
 <div class="fbox">
  <div class="fi" id="iIcon" style="--c:#2447d6">FILE</div>
  <b id="iSize" style="font-size:13px">جارٍ الفحص...</b>
  <small id="iExt" style="font-size:12px;color:var(--mu)"></small>
 </div>
</div>
<div id="err"></div>
<div class="row">
 <button class="btn pri" id="iStart">بدء التحميل</button>
 <button class="btn" id="iLater">التحميل لاحقًا</button>
 <button class="btn" id="iCancel">إلغاء الأمر</button>
</div>
<script>
const T="__TOKEN__",PID="__PID__",$=s=>document.querySelector(s);
const api=async(p,b)=>{const r=await fetch(p,{method:b===undefined?'GET':'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'حدث خطأ');return j};
const B=n=>{if(n<0||n===undefined||n===null)return'—';const u=['بايت','ك.ب','م.ب','ج.ب','ت.ب'];let i=0;while(n>=1024&&i<4){n/=1024;i++}return(i?n.toFixed(n<10?2:1):Math.round(n))+' '+u[i]};
const CAT=[['#d98a00','zip rar 7z tar gz bz2 xz iso'],['#d6336c','mp4 mkv avi mov webm flv'],['#8f4fe0','mp3 flac wav aac ogg m4a'],['#1c9a5a','jpg jpeg png gif webp svg bmp'],['#2447d6','pdf doc docx xls xlsx ppt pptx txt epub'],['#0d9488','exe msi dmg pkg apk deb']];
const col=e=>(CAT.find(c=>c[1].split(' ').includes(e))||['#667386'])[0];
const CMAP=[['مضغوط',['zip','rar','7z','tar','gz','bz2','xz','iso']],['فيديو',['mp4','mkv','avi','mov','webm','flv','m4v']],['صوت',['mp3','flac','wav','aac','ogg','m4a']],['صور',['jpg','jpeg','png','gif','webp','svg','bmp']],['مستندات',['pdf','doc','docx','xls','xlsx','ppt','pptx','txt','epub']],['برامج',['exe','msi','dmg','pkg','apk','deb']]];
const guessCat=fn=>{const x=(fn&&fn.includes('.')?fn.split('.').pop().toLowerCase():'');const f=CMAP.find(c=>c[1].includes(x));return f?f[0]:'عام'};
let hdrs={},cfg={};
function setIc(fn){const x=(fn&&fn.includes('.')?fn.split('.').pop().toLowerCase():'');$('#iIcon').style.setProperty('--c',col(x));$('#iIcon').textContent=(x||'FILE').slice(0,4).toUpperCase();$('#iExt').textContent=x?x.toUpperCase():''}
function applyCat(c){const d=(cfg.category_dirs||{})[c]||cfg.last_dir||cfg.dir||'';$('#iDir').value=d;$('#iRemTxt').textContent=`تذكر هذا المسار لفئة «${c}»`}
$('#iCat').onchange=()=>applyCat($('#iCat').value);
$('#iName').oninput=()=>setIc($('#iName').value);
$('#iBrowse').onclick=async()=>{try{const r=await api('/api/browse_dir',{initial:$('#iDir').value});if(r.dir)$('#iDir').value=r.dir}catch(e){$('#err').textContent=e.message}};
$('#iCancel').onclick=()=>window.close();
const go=async(startNow)=>{
 try{
  await api('/api/add_single',{
   url:$('#iUrl').value.trim(),dir:$('#iDir').value.trim(),filename:$('#iName').value.trim(),
   headers:hdrs,start_now:startNow,category:$('#iCat').value,
   remember_cat:$('#iRemCat').checked,desc:$('#iDesc').value.trim()
  });
  window.close();
 }catch(e){$('#err').textContent=e.message}
};
$('#iStart').onclick=()=>go(true);
$('#iLater').onclick=()=>go(false);
(async()=>{
 try{
  const d=await api('/api/popup_data?pid='+encodeURIComponent(PID));
  hdrs=d.headers||{};cfg=d.settings||{};
  $('#iUrl').value=d.url;
  const n0=decodeURIComponent((d.url.split('?')[0].split('/').pop()||'download')).slice(0,180);
  $('#iName').value=n0;setIc(n0);
  const c0=guessCat(n0);$('#iCat').value=c0;applyCat(c0);
  const info=await api('/api/probe_direct',{url:d.url,headers:hdrs});
  if(info.filename){$('#iName').value=info.filename;setIc(info.filename);const c1=guessCat(info.filename);$('#iCat').value=c1;applyCat(c1)}
  if(info.warning){$('#err').textContent=info.warning;$('#iSize').textContent='تنبيه'}
  else{$('#iSize').textContent=info.size>0?B(info.size):'حجم غير معروف'}
 }catch(e){$('#err').textContent=e.message}
})();
</script></body></html>"""


VPOPUP_PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>تحميل فيديو — الدولي</title>
<link rel="icon" type="image/png" sizes="256x256" href="/icon.png?v=3">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#eef0f3;--sf:#fff;--tx:#121b26;--mu:#667386;--ln:#dde2e8;--ac:#2447d6;--ac2:#e6ebfc;--er:#cf3a3a;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#0d1218;--sf:#151c24;--tx:#e7ecf2;--mu:#8995a6;--ln:#252f3b;--ac:#7c9bff;--ac2:#1b2748;--er:#ff7878}}
*{box-sizing:border-box}
body{margin:0;padding:18px;background:var(--sf);color:var(--tx);font:14.5px/1.55 "SF Arabic","Segoe UI",Tahoma,system-ui,sans-serif}
button,input{font:inherit;color:inherit}
h2{margin:0 0 12px;font-size:18px;display:flex;align-items:center;gap:10px}
h2 img{width:28px;height:28px;border-radius:7px}
label{display:block;font-size:12.5px;color:var(--mu);margin:8px 0 4px}
input{width:100%;border:1px solid var(--ln);background:var(--bg);border-radius:10px;padding:8px 11px;direction:ltr;text-align:left}
.inrow{display:flex;gap:6px;align-items:center}.inrow input{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--ln);background:var(--bg);border-radius:10px;padding:8px 14px;cursor:pointer}
.btn:hover{border-color:var(--ac)}
.vinfo{display:grid;grid-template-columns:180px 1fr;gap:14px;align-items:start;margin-top:12px}
.vthumb{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:var(--bg);border:1px solid var(--ln)}
.vtitle{font-size:15.5px;font-weight:700;margin:0 0 4px;line-height:1.4}
.vsub{color:var(--mu);font-size:12.5px;display:flex;gap:10px;flex-wrap:wrap}
.fmts{display:grid;grid-template-columns:repeat(auto-fill,minmax(195px,1fr));gap:8px;margin-top:14px}
.fbtn{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-radius:11px;border:1px solid var(--ln);background:var(--bg);cursor:pointer;text-align:start}
.fbtn:hover{border-color:var(--ac)}.fbtn:disabled{opacity:.55;cursor:not-allowed}
.fbtn b{display:block;font-size:13.5px}.fbtn small{color:var(--mu);font-size:11.5px}
.fext{font-size:11px;font-weight:700;padding:2px 7px;border-radius:7px;background:var(--ac2);color:var(--ac);direction:ltr}
.fbtn.aud .fext{background:color-mix(in srgb,#8f4fe0 18%,transparent);color:#8f4fe0}
#msg{margin-top:14px;font-size:13.5px;color:var(--mu);text-align:center}
#msg.er{color:var(--er);font-weight:600}
</style></head><body>
<h2><img src="/icon.png?v=3" alt="">تحميل فيديو — الدولي للتحميلات</h2>
<label for="vDir">مجلد الحفظ (يتذكر آخر مجلد تلقائيًا)</label>
<div class="inrow">
 <input id="vDir">
 <button class="btn" id="vBrowse" type="button" title="اختيار مجلد">...</button>
</div>
<div id="msg">جارٍ فحص الفيديو وجلب الجودات المتاحة...</div>
<div id="res"></div>
<script>
const T="__TOKEN__",VID="__VID__",$=s=>document.querySelector(s);
const api=async(p,b)=>{const r=await fetch(p,{method:b===undefined?'GET':'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'حدث خطأ');return j};
const B=n=>{if(n<0||n===undefined||n===null)return'—';const u=['بايت','ك.ب','م.ب','ج.ب','ت.ب'];let i=0;while(n>=1024&&i<4){n/=1024;i++}return(i?n.toFixed(n<10?2:1):Math.round(n))+' '+u[i]};
const D=s=>{s=Math.round(s);const h=s/3600|0,m=s%3600/60|0,x=s%60,p=v=>String(v).padStart(2,'0');return h?`${h}:${p(m)}:${p(x)}`:`${p(m)}:${p(x)}`};
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
$('#vBrowse').onclick=async()=>{try{const r=await api('/api/browse_dir',{initial:$('#vDir').value});if(r.dir)$('#vDir').value=r.dir}catch(e){}};
(async()=>{
 try{
  const d=await api('/api/vpopup_data?vid='+encodeURIComponent(VID));
  const cfg=d.settings||{};
  $('#vDir').value=cfg.last_dir||cfg.dir||'';
  const info=await api('/api/media/probe',{url:d.url,headers:d.headers||{}});
  $('#msg').textContent='';
  const dur=info.duration?D(info.duration):'';
  $('#res').innerHTML=`<div class="vinfo">
   ${info.thumbnail?`<img class="vthumb" src="${esc(info.thumbnail)}" alt="">`:'<div class="vthumb"></div>'}
   <div>
    <div class="vtitle">${esc(info.title)}</div>
    <div class="vsub">${info.site?`<span>${esc(info.site)}</span>`:''}${info.uploader?`<span>${esc(info.uploader)}</span>`:''}${dur?`<span>${dur}</span>`:''}</div>
   </div>
  </div>
  <div class="fmts">${info.formats.map((f,idx)=>`
   <button class="fbtn${f.audio_only?' aud':''}" data-fi="${idx}">
    <div><b>${esc(f.label)}</b><small>${f.size>0?B(f.size):'حجم تقديري'}</small></div>
    <span class="fext">${esc(f.ext)}</span>
   </button>`).join('')}</div>`;
  $('#res').querySelectorAll('[data-fi]').forEach(b=>b.onclick=async()=>{
   const f=info.formats[+b.dataset.fi];
   b.disabled=true;
   try{
    await api('/api/media/add',{url:info.url,title:info.title,format_id:f.format_id,audio_only:f.audio_only,ext:f.ext,size:f.size,headers:d.headers||{},yt_clients:f.yt_clients||null,dir:$('#vDir').value.trim()});
    window.close();
   }catch(e){$('#msg').className='er';$('#msg').textContent=e.message;b.disabled=false}
  });
 }catch(e){
  $('#msg').className='er';
  $('#msg').textContent=e.message;
 }
})();
</script></body></html>"""

if __name__ == "__main__":
    main()
