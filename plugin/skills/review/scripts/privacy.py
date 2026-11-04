"""Private folders on every platform (03 §5.57 item 23). Restore copies, reviewers' scratch folders and the browser
driver's key are readable only by the user who made them: 0700 where POSIX modes exist; on native Windows, which
ignores those modes, icacls (from the System32 folder Windows reports, never one a project could supply: Qodo on #28,
#29) locks the folder in an order where no step leaves it looser than it was (Qodo on #29):
  1. inheritance off and only this user and SYSTEM granted on the folder;
  2. its contents reset to inherit that;
  3. any other principal's explicit grant on the folder removed.
A link or junction is refused, and icacls is told not to follow links (/L), so a planted link can't send the change to
files elsewhere. make_private() returns False when the lock could not be applied; a caller about to write something
sensitive refuses instead of writing it into an unlocked folder."""
import os

def _system_dir():
    """The Windows System32 folder, as Windows reports it (GetSystemDirectoryW), never from SystemRoot or PATH, which a
    project's code could set. None when it can't be asked."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetSystemDirectoryW(buf, len(buf))
        return buf.value if 0 < n < len(buf) else None
    except (AttributeError, OSError, ImportError): return None

def _sid(name):
    """An account's security id (S-1-5-18 for SYSTEM), as Windows resolves the name icacls printed. None when it can't
    be resolved; such an account is never kept. SYSTEM is known by its id, never by a name ending in SYSTEM, which a
    foreign domain's account can carry and which a translated Windows spells otherwise (Qodo on #29)."""
    try:
        import ctypes
        from ctypes import wintypes
        a = ctypes.windll.advapi32
        sid, size = ctypes.create_string_buffer(256), wintypes.DWORD(256)
        dom, dsize, use = ctypes.create_unicode_buffer(256), wintypes.DWORD(256), wintypes.DWORD()
        if not a.LookupAccountNameW(None, name, sid, ctypes.byref(size), dom, ctypes.byref(dsize), ctypes.byref(use)): return None
        out = wintypes.LPWSTR()
        if not a.ConvertSidToStringSidW(sid, ctypes.byref(out)): return None
        try: return out.value
        finally: ctypes.windll.kernel32.LocalFree(out)
    except (AttributeError, OSError, ImportError, ValueError): return None

def _is_link(path):
    """A symbolic link or a Windows junction (a reparse point): never locked, since the change would land elsewhere."""
    try:
        if os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path)): return True
        st = os.stat(path, follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError: return True

def make_private(path, windows=None):
    """Lock a folder to the current user. True when the platform's own lock was applied."""
    windows = (os.name == "nt") if windows is None else windows
    if _is_link(path): return False
    try: os.chmod(path, 0o700)
    except OSError:
        if not windows: return False  # POSIX: the mode is the lock
    if not windows: return True
    user, sysdir = os.environ.get("USERNAME", ""), _system_dir()
    if not user or not sysdir: return False
    import subprocess  # only here: Windows is the only platform that needs it
    who = f"{os.environ['USERDOMAIN']}\\{user}" if os.environ.get("USERDOMAIN") else user
    exe, p = os.path.join(sysdir, "icacls.exe"), str(path)
    def ok(args, **k):
        try: return subprocess.run([exe, *args], capture_output=True, timeout=120, **k)
        except (OSError, subprocess.SubprocessError): return None
    r = ok([p, "/inheritance:r", "/grant:r", f"{who}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/L", "/Q"])  # 1. tighter first
    if not r or r.returncode != 0: return False
    if any(os.scandir(p)):
        r = ok([os.path.join(p, "*"), "/reset", "/T", "/C", "/L", "/Q"])  # 2. the contents inherit the locked folder
        if not r or r.returncode != 0: return False
    r = ok([p], text=True, encoding="utf-8", errors="replace")  # 3. the folder's own grants, listed
    if not r or r.returncode != 0: return False
    me = _sid(who)
    for line in (r.stdout or "").splitlines():
        line = line[len(p):] if line.startswith(p) else line
        if ":(" not in line: continue
        name = line.strip().split(":(", 1)[0].strip()
        sid = _sid(name)
        if sid == "S-1-5-18" or (me and sid == me) or name.casefold() == who.casefold(): continue  # SYSTEM by its id, and this user
        rr = ok([p, "/remove:g", name, "/L", "/Q"])
        if not rr or rr.returncode != 0: return False
    return True
