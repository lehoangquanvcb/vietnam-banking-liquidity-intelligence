
import os, sys, subprocess, urllib.request, importlib
from pathlib import Path

INSTALLER_URL="https://vnstocks.com/files/vnstock-cli-installer.run"
VENV=Path("/tmp/vnstock_sponsor_venv")
RUN=Path("/tmp/vnstock-cli-installer.run")

def add_site():
    for p in list(VENV.glob("lib/python*/site-packages"))+list(VENV.glob("Lib/site-packages")):
        s=str(p)
        if s not in sys.path: sys.path.insert(0,s)
    importlib.invalidate_caches()

def sponsor_available():
    add_site()
    try:
        import vnstock_data
        return True, getattr(vnstock_data,"__version__","available")
    except Exception as e:
        return False, str(e)

def configure_key(key):
    if key:
        os.environ["VNSTOCK_API_KEY"]=key.strip()
        os.environ["VNSTOCK_INTERACTIVE"]="0"
        os.environ["VNSTOCK_LANGUAGE"]="2"

def install_sponsor(key, timeout=90):
    # IMPORTANT: only called from an explicit user button, never automatically on app startup.
    if not key or len(key.strip())<8:
        return False,"API Key chưa hợp lệ."
    configure_key(key)
    ok,detail=sponsor_available()
    if ok:return True,f"vnstock_data sẵn sàng ({detail})"
    os.environ["VNSTOCK_VENV_PATH"]=str(VENV)
    try:
        urllib.request.urlretrieve(INSTALLER_URL,RUN)
        RUN.chmod(0o755)
    except Exception as e:
        return False,f"Không tải được installer: {e}"
    cmd=[str(RUN),"--","--non-interactive","--venv-path",str(VENV),"--language","vi"]
    try:
        p=subprocess.run(cmd,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return False,"Installer quá 90 giây nên đã dừng. App sẽ dùng Free/Fallback."
    except Exception as e:
        return False,f"Lỗi installer: {e}"
    add_site()
    ok,detail=sponsor_available()
    if ok:return True,f"Kết nối Sponsor thành công ({detail})"
    log=(p.stdout or "")[-1500:].replace(key.strip(),"***REDACTED***")
    return False,f"Không import được vnstock_data sau cài đặt. Exit={p.returncode}\n{log}"
