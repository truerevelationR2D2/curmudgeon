"""Private folders on every platform (03 §5.57 item 23). Restore copies, reviewers' scratch folders and the browser
driver's key are readable only by the user who made them, and make_private() says so only after reading it back.
- POSIX: 0700, then os.stat must show no group or other bits and the user as owner (some file systems accept chmod
  and ignore it); on macOS every extended access entry is removed with chmod -N and ls -le must show none.
- Native Windows, which ignores modes: icacls from the System32 folder Windows reports (never one a project could
  supply: Qodo on #28, #29), for the account in the process's own token (never USERNAME, which code can set):
  1. the folder: inheritance off, only this user and SYSTEM granted, this user made its owner (an owner can always
     change the access list back);
  2. every other account's grant and every deny on the folder removed by security id read from icacls /save (SDDL),
     then read back, before any content inherits from it (Qodo on #29, #30; blind round on the redesign);
  3. the contents reset to inherit the clean folder and made this user's own, with no /C, so icacls fails on the
     first entry it can't change; then every entry is read back.
  A folder holding a link, junction or hard link is refused before anything runs, so neither a reset nor Windows' own
  inheritance can reach a file elsewhere; so is a folder that is itself a link, or that can't be listed.
make_private() returns False, with the reason in WHY, when the lock could not be applied or read back; a caller about
to write something sensitive refuses instead of writing it into an unlocked folder. A link swapped in while the lock
runs, by another program with write access to the folder, is outside what this guards against."""
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

def _me():
    """The security id of the account this process runs as, from its own token (GetTokenInformation, TokenUser), never
    from USERNAME or USERDOMAIN, which a project's code can set to "Users" or anyone else (blind round on the
    redesign). None when Windows can't be asked: the lock then refuses."""
    try:
        import ctypes
        from ctypes import wintypes
        k, a = ctypes.windll.kernel32, ctypes.windll.advapi32
        k.GetCurrentProcess.restype = wintypes.HANDLE
        tok = wintypes.HANDLE()
        if not a.OpenProcessToken(k.GetCurrentProcess(), 0x0008, ctypes.byref(tok)): return None  # TOKEN_QUERY
        try:
            n = wintypes.DWORD()
            a.GetTokenInformation(tok, 1, None, 0, ctypes.byref(n))  # TokenUser: first ask the size
            buf = ctypes.create_string_buffer(n.value or 256)
            if not a.GetTokenInformation(tok, 1, buf, len(buf), ctypes.byref(n)): return None
            psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER starts with the SID pointer
            out = wintypes.LPWSTR()
            if not a.ConvertSidToStringSidW(ctypes.c_void_p(psid), ctypes.byref(out)): return None
            try: return out.value
            finally: k.LocalFree(out)
        finally: k.CloseHandle(tok)
    except (AttributeError, OSError, ImportError, ValueError): return None

def _owner(path):
    """The security id of a file's or folder's owner (GetNamedSecurityInfoW), or None when it can't be read. On Windows
    an owner can always change the access list again, so a private folder and everything in it must be the user's own."""
    try:
        import ctypes
        from ctypes import wintypes
        a, k = ctypes.windll.advapi32, ctypes.windll.kernel32
        psid, psd, out = ctypes.c_void_p(), ctypes.c_void_p(), wintypes.LPWSTR()
        if a.GetNamedSecurityInfoW(str(path), 1, 1, ctypes.byref(psid), None, None, None, ctypes.byref(psd)) != 0: return None  # SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION
        try:
            if not a.ConvertSidToStringSidW(psid, ctypes.byref(out)): return None
            try: return out.value
            finally: k.LocalFree(out)
        finally: k.LocalFree(psd)
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
    """(type, flags, security id) for every entry of an SDDL access list, aliases expanded (SY is SYSTEM): allow, deny,
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
        out.append((f[0], f[1], sid)); i = j + 1
    return out

def _is_link(path):
    """A symbolic link or a Windows junction (a reparse point): never locked, since the change would land elsewhere."""
    try:
        if os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path)): return True
        st = os.stat(path, follow_symlinks=False)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError: return True

def make_private(path, windows=None):
    """Lock a folder to the current user. True only when the lock was applied and read back."""
    global WHY
    WHY = ""
    def no(why):
        global WHY
        WHY = why; return False
    windows = (os.name == "nt") if windows is None else windows
    if _is_link(path): return no("it is a link or junction, or can't be read")
    if not windows: return _posix(path, no)
    try: os.chmod(path, 0o700)
    except OSError: pass  # Windows ignores the mode; the access list below is the lock
    me, sysdir = _me(), _system_dir()
    if not me or not sysdir: return no("Windows could not say which account this is, or where System32 is")
    kids = _walk(path)  # every entry inside; a link, junction or hard link refuses the lock, so nothing below reaches files elsewhere
    if isinstance(kids, str): return no(kids)
    import subprocess  # only here: Windows is the only platform that needs it
    exe, p = os.path.join(sysdir, "icacls.exe"), str(path)
    def ok(args, **k):
        try: return subprocess.run([exe, *args], capture_output=True, timeout=120, **k)
        except (OSError, subprocess.SubprocessError): return None
    def step(args, what):
        r = ok(args)
        return None if r and r.returncode == 0 else f"icacls could not {what} ({getattr(r, 'returncode', 'not run')})"
    def bad(entries, where):
        extra = sorted({f"{k} {s}" for k, fl, s in entries if not (k in ALLOW and (s in ("S-1-5-18", me) or "ID" in fl and where != "the folder"))})
        return f"{where} still has entries for other accounts or a deny after the lock: {', '.join(extra)[:200]}" if extra else None
    # 1. the folder: inheritance off, only this user and SYSTEM granted, owned by this user (an owner can always change the access list back)
    why = step([p, "/inheritance:r", "/grant:r", f"*{me}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/L", "/Q"], "grant you the folder") \
          or step([p, "/setowner", "*" + me, "/L", "/Q"], "make you the folder's owner")
    if why: return no(why)
    # 2. every other account's grant and every deny on the folder removed, by security id, before any content inherits from it
    entries = _saved(ok, [p])
    if isinstance(entries, str): return no(entries)
    for kind, _fl, sid in dict.fromkeys(entries[0][1]):
        if kind in DENY: why = step([p, "/remove:d", "*" + sid, "/L", "/Q"], f"remove a deny for {sid}")
        elif sid not in ("S-1-5-18", me): why = step([p, "/remove:g", "*" + sid, "/L", "/Q"], f"remove {sid}")
        if why: return no(why)
    after = _saved(ok, [p])
    if isinstance(after, str): return no(after)
    why = bad(after[0][1], "the folder")
    if why: return no(why)
    if not any(k in ALLOW and s == me for k, _fl, s in after[0][1]): return no("the folder has no grant for you after the lock")
    if _owner(p) != me: return no("the folder is not owned by you after the lock")
    # 3. the contents: reset to inherit the clean folder, owned by this user, then every one read back. No /C: icacls stops
    #    at the first entry it can't change and fails, so a file it skipped can't be reported private.
    if kids:
        why = step([os.path.join(p, "*"), "/reset", "/T", "/L", "/Q"], "reset the folder's contents") \
              or step([os.path.join(p, "*"), "/setowner", "*" + me, "/T", "/L", "/Q"], "make you the owner of the folder's contents")
        if why: return no(why)
        saved = _saved(ok, [os.path.join(p, "*"), "/T"])
        if isinstance(saved, str): return no(saved)
        for where, ents in saved:
            why = bad(ents, where)
            if why: return no(why)
        if len(saved) < len(kids): return no(f"icacls read back {len(saved)} of the {len(kids)} entries inside the folder")
        other = next((k for k in kids if _owner(k) != me), None)
        if other: return no(f"{other} is not owned by you after the lock")
    return True

ALLOW, DENY = {"A", "OA", "XA", "ZA"}, {"D", "OD", "XD"}

def _posix(path, no):
    """0700, read back: some file systems accept chmod and ignore it (WSL's /mnt/c without metadata, FAT, many network
    shares), and macOS keeps extended access entries that a mode change doesn't touch, so success is what os.stat and
    ls -le show afterwards, never just that chmod didn't fail (blind round on the redesign)."""
    import stat, sys
    try: os.chmod(path, 0o700)
    except OSError: return no("its mode could not be set to 0700")
    if sys.platform == "darwin":
        import subprocess
        try:
            subprocess.run(["/bin/chmod", "-RN", str(path)], capture_output=True, timeout=120)  # every extended entry, inherited ones on the contents too
            ls = subprocess.run(["/bin/ls", "-lde", str(path)], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError): return no("its macOS access entries could not be checked")
        if re.search(r"(?m)^\s*\d+: ", ls): return no("macOS access entries still grant access after chmod -N")
    try: st = os.stat(path, follow_symlinks=False)
    except OSError: return no("it could not be read back")
    if stat.S_IMODE(st.st_mode) & 0o077: return no(f"its mode is {oct(stat.S_IMODE(st.st_mode))} after chmod 0700 (this file system ignores modes)")
    if hasattr(os, "geteuid") and st.st_uid != os.geteuid(): return no("it belongs to another account")
    return True

def _walk(top):
    """Every path inside top, never entering a link. A link, junction or hard link inside refuses the lock: Windows'
    own inheritance or a reset could reach the file elsewhere (blind round on the redesign). So does a folder that
    can't be listed: the lock is refused with its reason, never left to an exception."""
    out, todo = [], [str(top)]
    while todo:
        d = todo.pop()
        try:
            with os.scandir(d) as it: kids = list(it)
        except OSError as e: return f"{d} could not be listed ({type(e).__name__}: {e.strerror or e})"
        for k in kids:
            if _is_link(k.path): return f"it holds a link or junction ({k.path}); remove it, or use a fresh folder"
            try: st = os.stat(k.path, follow_symlinks=False)
            except OSError as e: return f"{k.path} could not be read ({type(e).__name__})"
            if k.is_dir(follow_symlinks=False): todo.append(k.path)
            elif st.st_nlink > 1: return f"it holds a hard link ({k.path}), which is also a file elsewhere"
            out.append(k.path)
    return out

def _saved(ok, target):
    """[(path, [(type, flags, security id)])] from icacls /save for target (a folder, or folder\\* /T for everything
    under it), or a reason it couldn't be read."""
    try: fd, save = tempfile.mkstemp(suffix=".acl"); os.close(fd)
    except OSError: return "no temp file could be made for the saved access list"  # a full disk: the lock failed, never an exception
    try:
        r = ok([target[0], "/save", save, *target[1:], "/Q"])
        if not r or r.returncode != 0: return f"icacls /save failed ({getattr(r, 'returncode', 'not run')})"
        raw = open(save, "rb").read()
    except OSError: return "the saved access list could not be read"
    finally:
        try: os.unlink(save)
        except OSError: pass
    try: text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:8] else raw.decode("utf-8", "replace")
    except UnicodeDecodeError: return "the saved access list could not be decoded"
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or len(lines) % 2: return "the saved access list is not in pairs of a name and its entries"
    out = []
    for name, sddl in zip(lines[0::2], lines[1::2]):
        got = _trustees(sddl)
        if got is None: return f"the saved access list has an entry the lock can't read: {sddl[:200]}"
        out.append((name, got))
    return out
