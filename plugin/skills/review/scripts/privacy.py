"""Private folders on every platform (03 §5.57 item 23). Restore copies, reviewers' scratch copies and the browser
driver's key are readable only by the user who made them: 0700 where POSIX modes exist, and on native Windows, which
ignores those modes, the folder's inherited permissions are removed and only the current user is granted access
(icacls). Best effort: a folder that can't be locked is reported as False, never an error."""
import os

def make_private(path, windows=None):
    """Lock a folder to the current user. Returns True when the platform's own lock was applied."""
    windows = (os.name == "nt") if windows is None else windows
    try: os.chmod(path, 0o700)
    except OSError: pass
    if not windows: return True
    user = os.environ.get("USERNAME", "")
    if not user: return False
    import subprocess  # only here: Windows is the only platform that needs it
    who = f"{os.environ['USERDOMAIN']}\\{user}" if os.environ.get("USERDOMAIN") else user
    try:
        r = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:(OI)(CI)F"], capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError): return False
