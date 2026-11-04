"""Private folders on every platform (03 §5.57 item 23). Restore copies, reviewers' scratch folders and the browser
driver's key are readable only by the user who made them: 0700 where POSIX modes exist; on native Windows, which
ignores those modes, icacls (from the System32 folder Windows reports, never one a project could supply: Qodo on #28,
#29) locks the folder in an order where no step leaves it looser than it was (Qodo on #29):
  1. inheritance off and only this user and SYSTEM granted on the folder;
  2. its contents reset to inherit that;
  3. any other account's explicit grant on the folder removed, read by security id from icacls /save (SDDL), so no
     translated name or code page can hide or misname one (Qodo on #29).
A link or junction is refused, and icacls is told not to follow links (/L), so a planted link can't send the change to
files elsewhere. make_private() returns False when the lock could not be applied; a caller about to write something
sensitive refuses instead of writing it into an unlocked folder."""
import os, re, tempfile

WHY = ""  # why the last make_private() failed, for the caller's message

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

SDDL_ALIASES = {"SY": "S-1-5-18", "WD": "S-1-1-0", "AU": "S-1-5-11", "BU": "S-1-5-32-545", "BA": "S-1-5-32-544", "BG": "S-1-5-32-546",
                "PU": "S-1-5-32-547", "IU": "S-1-5-4", "NU": "S-1-5-2", "AN": "S-1-5-7", "LS": "S-1-5-19", "NS": "S-1-5-20", "CO": "S-1-3-0",
                "OW": "S-1-3-4", "AC": "S-1-15-2-1", "RD": "S-1-5-32-555", "RU": "S-1-5-32-554", "SU": "S-1-5-6", "PS": "S-1-5-10", "ED": "S-1-5-9"}

ACE_TYPES = {"A", "D", "OA", "OD", "AU", "AL", "OU", "OL", "ML", "XA", "XD", "ZA", "XU", "SP", "RA", "SA", "TL", "FL", "SC"}  # every ACE type SDDL can write

def _alias_sid(alias):
    """An SDDL alias whose id depends on this machine or domain (LA is the local administrator, the Windows CI's own
    user; DA, DU ... the domain's), as Windows expands it. None when it can't be expanded: the lock then refuses."""
    try:
        import ctypes
        from ctypes import wintypes
        a = ctypes.windll.advapi32; psid = ctypes.c_void_p(); out = wintypes.LPWSTR()
        if not a.ConvertStringSidToSidW(alias, ctypes.byref(psid)): return None
        try:
            if not a.ConvertSidToStringSidW(psid, ctypes.byref(out)): return None
            try: return out.value
            finally: ctypes.windll.kernel32.LocalFree(out)
        finally: ctypes.windll.kernel32.LocalFree(psid)
    except (AttributeError, OSError, ImportError, ValueError): return None

def _trustees(sddl):
    """The security ids every entry of an SDDL access list names, aliases expanded (SY is SYSTEM): allow, deny,
    object and conditional entries alike. A conditional entry (XA, ZA) carries an expression in nested parentheses
    that may hold quoted text, ")" or "S:" included, so the list is scanned with quotes and depth tracked, never split
    on text (Qodo on #29). None when an entry can't be read, its type isn't known or its alias isn't in the table, so
    the lock refuses rather than reporting a folder private while an entry it skipped still grants access."""
    i = sddl.find("D:")
    if i < 0: return []
    i += 2; out = []
    while i < len(sddl) and sddl[i] not in "(": 
        if sddl.startswith("S:", i): return out  # flags only (D:PAI), then the system list
        i += 1
    while i < len(sddl):
        if sddl[i] != "(":
            if sddl.startswith("S:", i): break  # the system access list starts at the top level only
            i += 1; continue
        depth, q, j = 0, False, i
        while j < len(sddl):
            c = sddl[j]
            if c == '"': q = not q
            elif not q: depth += c == "("; depth -= c == ")"
            if depth == 0 and not q: break
            j += 1
        if depth != 0 or q: return None  # an entry that never closes
        f = sddl[i + 1:j].split(";", 6)
        if len(f) < 6 or f[0] not in ACE_TYPES or not f[5]: return None
        sid = f[5] if f[5].startswith("S-") else (SDDL_ALIASES.get(f[5]) or _alias_sid(f[5]))  # LA, DA ...: relative to this machine or domain, so Windows expands them
        if sid is None: return None
        out.append(sid); i = j + 1
    return out

def _is_link(path):
    """A symbolic link or a Windows junction (a reparse point): never locked, since the change would land elsewhere."""
    try:
        if os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path)): return True
        st = os.stat(path, follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError: return True

def make_private(path, windows=None):
    """Lock a folder to the current user. True when the platform's own lock was applied."""
    global WHY
    WHY = ""
    def no(why):
        global WHY
        WHY = why; return False
    windows = (os.name == "nt") if windows is None else windows
    if _is_link(path): return no("it is a link or junction, or can't be read")
    try: os.chmod(path, 0o700)
    except OSError:
        if not windows: return no("its mode could not be set to 0700")  # POSIX: the mode is the lock
    if not windows: return True
    user, sysdir = os.environ.get("USERNAME", ""), _system_dir()
    if not user or not sysdir: return no("the user name or the System32 folder is unknown")
    import subprocess  # only here: Windows is the only platform that needs it
    who = f"{os.environ['USERDOMAIN']}\\{user}" if os.environ.get("USERDOMAIN") else user
    exe, p = os.path.join(sysdir, "icacls.exe"), str(path)
    def ok(args, **k):
        try: return subprocess.run([exe, *args], capture_output=True, timeout=120, **k)
        except (OSError, subprocess.SubprocessError): return None
    r = ok([p, "/inheritance:r", "/grant:r", f"{who}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/L", "/Q"])  # 1. tighter first
    if not r or r.returncode != 0: return no(f"icacls could not grant the user ({getattr(r, 'returncode', 'not run')})")
    if any(os.scandir(p)):
        r = ok([os.path.join(p, "*"), "/reset", "/T", "/C", "/L", "/Q"])  # 2. the contents inherit the locked folder
        if not r or r.returncode != 0: return no(f"icacls could not reset the folder's contents ({getattr(r, 'returncode', 'not run')})")
    me = _sid(who)
    if not me: return no(f"the security id of {who} could not be looked up")
    try: fd, save = tempfile.mkstemp(suffix=".acl"); os.close(fd)  # 3. the folder's own grants, as security ids (SDDL): no names, so no translation or code page (Qodo on #29)
    except OSError: return no("no temp file could be made for the saved access list")  # no temp file (a full disk): the lock failed, never an exception (Qodo on #29)
    try:
        r = ok([p, "/save", save, "/Q"])
        if not r or r.returncode != 0: return no(f"icacls /save failed ({getattr(r, 'returncode', 'not run')})")
        raw = open(save, "rb").read()
    except OSError: return no("the saved access list could not be read")
    finally:
        try: os.unlink(save)
        except OSError: pass
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:8] else raw.decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if l.strip()]
    sids = _trustees(lines[-1]) if lines else None
    if sids is None: return no(f"the saved access list has an entry the lock can't read: {(lines[-1] if lines else '')[:200]}")
    for sid in dict.fromkeys(sids):
        if sid in ("S-1-5-18", me): continue  # SYSTEM and this user, by id
        rr = ok([p, "/remove:g", "*" + sid, "/L", "/Q"])
        if not rr or rr.returncode != 0: return no(f"icacls could not remove {sid} ({getattr(rr, 'returncode', 'not run')})")
    return True
