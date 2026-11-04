"""Private folders on every platform (03 §5.57 item 23). Restore copies, reviewers' scratch folders and the browser
driver's key are readable only by the user who made them: 0700 where POSIX modes exist, and on native Windows, which
ignores those modes, the folder's existing permissions are reset, inheritance is removed and only the current user
and SYSTEM are granted access (icacls, run from System32 so a project's own icacls.exe never runs: Qodo on #28).
make_private() returns False when the lock could not be applied; a caller that is about to write something sensitive
refuses instead of writing it into an unlocked folder."""
import os

def _icacls():
    """icacls.exe in Windows' own System32 folder, never a name looked up from the current folder or PATH."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or "C:\\Windows"
    return os.path.join(root, "System32", "icacls.exe")

def make_private(path, windows=None):
    """Lock a folder to the current user. True when the platform's own lock was applied."""
    windows = (os.name == "nt") if windows is None else windows
    try: os.chmod(path, 0o700)
    except OSError:
        if not windows: return False  # POSIX: the mode is the lock
    if not windows: return True
    user = os.environ.get("USERNAME", "")
    if not user: return False
    import subprocess  # only here: Windows is the only platform that needs it
    who = f"{os.environ['USERDOMAIN']}\\{user}" if os.environ.get("USERDOMAIN") else user
    exe, p = _icacls(), str(path)
    steps = ([exe, p, "/reset", "/T", "/C", "/Q"],  # existing explicit grants go first, the folder's contents included (Qodo on #28)
             [exe, p, "/inheritance:r", "/grant:r", f"{who}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/Q"])  # then only this user and SYSTEM
    try: return all(subprocess.run(s, capture_output=True, timeout=120).returncode == 0 for s in steps)
    except (OSError, subprocess.SubprocessError): return False
