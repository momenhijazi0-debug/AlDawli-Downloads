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
APP_VERSION = "10.17"
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


def _set_window_identity(hwnd, app_id, relaunch_cmd, icon_res, display_name):
    """
    تعيين هوية النافذة في شريط المهام (AppUserModelID + أمر إعادة التشغيل + الأيقونة + الاسم)
    على نافذة Chrome/Edge نفسها. بدون هذا يستخدم ويندوز أيقونة chrome.exe عند عمل Pin للتطبيق.
    """
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", ctypes.c_ulong)]
    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("pwszVal", ctypes.c_void_p), ("pad", ctypes.c_ulonglong)]

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(GUID)]

    def make_guid(txt):
        g = GUID()
        ole32.CLSIDFromString(txt, ctypes.byref(g))
        return g

    shell32.SHGetPropertyStoreForWindow.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long

    co_hr = ole32.CoInitialize(None)
    store = ctypes.c_void_p()
    try:
        iid = make_guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")  # IID_IPropertyStore
        hr = shell32.SHGetPropertyStoreForWindow(ctypes.c_void_p(hwnd), ctypes.byref(iid), ctypes.byref(store))
        if hr < 0 or not store.value:
            return False

        def vcall(idx, restype, argtypes, *args):
            vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[idx])
            return fn(store, *args)

        fmtid = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"  # System.AppUserModel.*
        items = [
            (5, app_id),            # ID
            (2, relaunch_cmd),      # RelaunchCommand
            (3, icon_res),          # RelaunchIconResource
            (4, display_name),      # RelaunchDisplayNameResource
        ]
        keep = []
        for pid, text in items:
            if not text:
                continue
            key = PROPERTYKEY()
            key.fmtid = make_guid(fmtid)
            key.pid = pid
            buf = ctypes.create_unicode_buffer(str(text))
            keep.append(buf)
            pv = PROPVARIANT()
            pv.vt = 31  # VT_LPWSTR
            pv.pwszVal = ctypes.cast(buf, ctypes.c_void_p).value
            vcall(6, ctypes.c_long, [ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)],
                  ctypes.byref(key), ctypes.byref(pv))
        vcall(7, ctypes.c_long, [])  # Commit
        return True
    except Exception:
        return False
    finally:
        if store.value:
            try:
                vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(store)
            except Exception:
                pass
        if co_hr in (0, 1):
            ole32.CoUninitialize()


def _relaunch_command():
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    py_exe = Path(sys.executable).resolve()
    pyw_exe = py_exe.with_name("pythonw.exe")
    runner = pyw_exe if pyw_exe.exists() else py_exe
    return f'"{runner}" "{Path(__file__).resolve()}"'


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
                            _set_window_identity(hwnd, "AlDawli.Downloads.App", _relaunch_command(),
                                                 f"{ico_path},0", APP_TITLE)
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
        # Set PKEY_AppUserModel_ID ({9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid=5) so pinned shortcuts keep their own identity
        try:
            IID_IPropertyStore = make_guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
            prop_store = ctypes.c_void_p()
            phr = vcall(
                shell_link, 0, ctypes.c_long,
                [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                ctypes.byref(IID_IPropertyStore), ctypes.byref(prop_store)
            )
            if phr >= 0 and prop_store.value:
                class PROPERTYKEY(ctypes.Structure):
                    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_ulong)]
                class PROPVARIANT(ctypes.Structure):
                    _fields_ = [
                        ("vt", ctypes.c_ushort),
                        ("wReserved1", ctypes.c_ushort),
                        ("wReserved2", ctypes.c_ushort),
                        ("wReserved3", ctypes.c_ushort),
                        ("pwszVal", ctypes.c_wchar_p),
                        ("pad", ctypes.c_ulonglong),
                    ]
                pkey = PROPERTYKEY()
                pkey.fmtid = make_guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}")
                pkey.pid = 5
                pv = PROPVARIANT()
                pv.vt = 31  # VT_LPWSTR
                pv.pwszVal = "AlDawli.Downloads.App"
                # IPropertyStore vtable: 3=GetCount, 4=GetAt, 5=GetValue, 6=SetValue, 7=Commit
                vcall(prop_store, 6, ctypes.c_long, [ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT)], ctypes.byref(pkey), ctypes.byref(pv))
                vcall(prop_store, 7, ctypes.c_long, [])
                vcall(prop_store, 2, ctypes.c_ulong, [])
                # Re-save lnk with property store committed
                vcall(persist_file, 6, ctypes.c_long, [ctypes.c_wchar_p, ctypes.c_int], str(lnk_path), 1)
        except Exception:
            pass
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


def set_windows_app_id(app_id="AlDawli.Downloads.App"):
    if platform.system() != "Windows":
        return
    try:
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


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


def is_tiktok_url(url):
    try:
        host = (up.urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"))
    except Exception:
        return False


def _probe_tiktok_fallback(url):
    """جلب روابط تحميل تيك توك مباشرة (بدون علامة مائية) بسرعة."""
    api_url = "https://www.tikwm.com/api/?" + up.urlencode({"url": url, "hd": "1"})
    req = rq.Request(api_url, headers={"User-Agent": UA, "Accept": "application/json"})
    with rq.urlopen(req, timeout=7) as r:
        res = json.loads(r.read().decode("utf-8", errors="replace"))
    if res.get("code") != 0 or not isinstance(res.get("data"), dict):
        raise RuntimeError(res.get("msg") or "تعذّر جلب فيديو تيك توك من الرابط")
    d = res["data"]
    choices = []
    if d.get("hdplay"):
        choices.append({
            "label": "HD بدون علامة مائية",
            "ext": "MP4",
            "size": int(d.get("hd_size") or -1),
            "format_id": "direct:" + str(d["hdplay"]),
            "audio_only": False,
            "quality_hint": 1080,
            "yt_clients": None,
        })
    if d.get("play"):
        choices.append({
            "label": "جودة عادية بدون علامة مائية",
            "ext": "MP4",
            "size": int(d.get("size") or -1),
            "format_id": "direct:" + str(d["play"]),
            "audio_only": False,
            "quality_hint": 720,
            "yt_clients": None,
        })
    if d.get("wmplay"):
        choices.append({
            "label": "مع علامة مائية",
            "ext": "MP4",
            "size": int(d.get("wm_size") or -1),
            "format_id": "direct:" + str(d["wmplay"]),
            "audio_only": False,
            "quality_hint": 480,
            "yt_clients": None,
        })
    if d.get("music"):
        choices.append({
            "label": "صوت فقط (MP3)",
            "ext": "MP3",
            "size": -1,
            "format_id": "direct:" + str(d["music"]),
            "audio_only": True,
            "quality_hint": 0,
            "yt_clients": None,
        })
    if not choices:
        raise RuntimeError("لم يتم العثور على ملفات فيديو قابلة للتحميل في هذا الرابط")
    author = d.get("author") or {}
    return {
        "url": url,
        "title": (d.get("title") or "TikTok Video").strip()[:140] or "TikTok Video",
        "uploader": author.get("nickname") or author.get("unique_id") or "",
        "duration": int(d.get("duration") or 0),
        "thumbnail": d.get("cover") or d.get("origin_cover") or "",
        "site": "TikTok",
        "has_ffmpeg": bool(find_ffmpeg()),
        "formats": choices,
    }


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
        "socket_timeout": 12,
        "retries": 1,
        "nocheckcertificate": True,
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

    if is_tiktok_url(url):
        try:
            return _probe_tiktok_fallback(url)
        except Exception:
            pass

    has_ff = bool(find_ffmpeg(force=False))
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
                if is_tiktok_url(url):
                    return _probe_tiktok_fallback(url)
                raise

    if not info:
        if is_tiktok_url(url):
            return _probe_tiktok_fallback(url)
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
        is_direct_media = isinstance(format_id, str) and format_id.startswith("direct:")
        real_url = format_id[7:].strip() if is_direct_media else url
        with self.lock:
            self.items[i] = Item(self, dict(
                id=i, url=real_url, dir=target_dir, filename=fname,
                custom_name=is_direct_media,
                size=int(size) if size else -1,
                kind="direct" if is_direct_media else "media",
                format_id="" if is_direct_media else (format_id or ""),
                audio_only=bool(audio_only),
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
                def bye():
                    try:
                        MGR.shutdown()
                    except Exception:
                        pass
                    time.sleep(0.25)
                    os._exit(0)
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
    profile_dir = APP / "app_profile_v16"
    profile_dir.mkdir(parents=True, exist_ok=True)
    for x in c:
        if x and os.path.exists(x):
            subprocess.Popen([
                x,
                f"--app={url}",
                f"--user-data-dir={profile_dir}",
                "--app-id=AlDawliDownloads",
                "--class=AlDawliDownloads",
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
    set_windows_app_id()
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
    if platform.system() == "Windows":
        def _clean_old_mei():
            try:
                tmp_root = Path(tempfile.gettempdir())
                my_mei = Path(getattr(sys, "_MEIPASS", "")).name if getattr(sys, "_MEIPASS", None) else ""
                for p in tmp_root.glob("_MEI*"):
                    if p.is_dir() and p.name != my_mei:
                        shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass
        threading.Thread(target=_clean_old_mei, daemon=True).start()
    start_windows_tray()
    if not a.no_window: open_window(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: MGR.shutdown()


ICON_PNG_B64 = "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"
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
 <div class="brand"><img class="logo-img" src="/icon.png?v=3" alt="الدولي للتحميلات"><div><b>الدولي للتحميلات</b><small>الإصدار <span id="appVer">10.17</span></small></div></div>
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
