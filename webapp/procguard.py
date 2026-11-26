"""
Чтобы туннель cloudflared не оставался висеть после закрытия программы.

1. bind_to_parent(proc) — Windows: cloudflared кладётся в «задание» (Job Object) с флагом «завершить при закрытии».
   Программа закрылась любым способом (крестик окна, сбой, «Снять задачу») — Windows сама завершит и туннель.
   Linux: то же самое делает popen_kwargs() (сигнал ребёнку, когда родитель умер).
2. kill_orphans(address) — при запуске завершает cloudflared, оставшиеся от прошлых запусков: туннель на наш адрес
   (http://127.0.0.1:<порт>), а программы, которая его запустила, уже нет. Чужие туннели и службы не трогаются.
"""
from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import time

log = logging.getLogger("FPC.webapp")

_job = None
_k32 = None


def _windows_job():
    """Одно «задание» на всю программу: когда программа завершится, Windows закроет всё, что в нём."""
    global _job, _k32
    if _job is not None:
        return _job or None
    _job = 0
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                          "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9 = ExtendedLimitInformation
            return None
        _job, _k32 = job, k32
    except Exception:
        log.debug("TRACEBACK", exc_info=True)
    return _job or None


def bind_to_parent(proc) -> bool:
    """Туннель завершится вместе с программой. True — получилось."""
    if os.name != "nt":
        return False
    job = _windows_job()
    if not job:
        return False
    try:
        return bool(_k32.AssignProcessToJobObject(job, int(proc._handle)))
    except Exception:
        log.debug("TRACEBACK", exc_info=True)
        return False


def _linux_pdeathsig():
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def popen_kwargs() -> dict:
    """Доп. параметры для subprocess.Popen: на Linux туннель получит сигнал, когда программа умрёт."""
    if os.name != "nt" and os.uname().sysname == "Linux":
        return {"preexec_fn": _linux_pdeathsig}
    return {}


# ───────────────────────────── брошенные туннели ──────────────────────────────
def _psutil_list(name: str):
    import psutil
    procs, created = [], {}
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline", "create_time"]):
        created[p.info["pid"]] = p.info.get("create_time") or 0
        if (p.info.get("name") or "").lower().startswith(name.lower()):
            procs.append((p.info["pid"], p.info.get("ppid") or 0, " ".join(p.info.get("cmdline") or []), p.info.get("create_time") or 0))
    return procs, created


def _windows_list(name: str):
    """Без psutil: список процессов через PowerShell (Win32_Process)."""
    ps = ("Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{i=$_.ProcessId; p=$_.ParentProcessId; n=$_.Name; "
          "c=$_.CommandLine; t=$(if ($_.CreationDate) { $_.CreationDate.ToFileTimeUtc() } else { 0 })} } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=40, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(r.stdout or "[]")
    data = [data] if isinstance(data, dict) else data
    procs, created = [], {}
    for x in data:
        pid, t = int(x.get("i") or 0), int(x.get("t") or 0) / 1e7  # FILETIME: сотни наносекунд
        created[pid] = t
        if str(x.get("n") or "").lower().startswith(name.lower()):
            procs.append((pid, int(x.get("p") or 0), str(x.get("c") or ""), t))
    return procs, created


def kill_orphans(address: str, name: str = "cloudflared", use_psutil: bool = True) -> int:
    """Завершает брошенные туннели на этот адрес (например, http://127.0.0.1:8095). Возвращает, сколько закрыто."""
    try:
        procs = None
        if use_psutil:
            try:
                procs, created = _psutil_list(name)
            except ImportError:
                procs = None
        if procs is None:
            if os.name != "nt":
                return 0
            procs, created = _windows_list(name)
    except Exception:
        log.debug("TRACEBACK", exc_info=True)
        return 0
    mark = re.compile(re.escape(address) + r"(?![\d.])")
    killed = 0
    for pid, ppid, cmd, born in procs:
        if pid == os.getpid() or ppid == os.getpid() or "tunnel" not in cmd or not mark.search(cmd):
            continue
        parent_born = created.get(ppid)
        # родитель жив, если процесс с его номером есть и он старше туннеля (номер мог достаться другой программе)
        if parent_born is not None and parent_born <= born + 1:
            continue
        try:
            os.kill(pid, signal.SIGTERM)  # на Windows это TerminateProcess
            killed += 1
        except OSError:
            pass
    if killed:
        time.sleep(0.3)
        log.info(f"Закрыл старые туннели cloudflared от прошлых запусков: {killed}.")
    return killed
