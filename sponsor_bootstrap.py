
from __future__ import annotations
import os, sys, subprocess, tempfile, urllib.request, importlib
from pathlib import Path

INSTALLER_URL = "https://vnstocks.com/files/vnstock-cli-installer.run"
SPONSOR_VENV = Path("/tmp/vnstock_sponsor_venv")
INSTALLER_PATH = Path("/tmp/vnstock-cli-installer.run")

def _add_venv_site_packages():
    candidates = []
    if SPONSOR_VENV.exists():
        candidates += list(SPONSOR_VENV.glob("lib/python*/site-packages"))
        candidates += list(SPONSOR_VENV.glob("Lib/site-packages"))
    for p in candidates:
        s=str(p)
        if s not in sys.path:
            sys.path.insert(0,s)
    importlib.invalidate_caches()

def sponsor_available():
    _add_venv_site_packages()
    try:
        import vnstock_data
        return True, getattr(vnstock_data,"__version__","installed")
    except Exception as e:
        return False, str(e)

def install_sponsor(api_key: str, timeout: int = 360):
    if not api_key or len(api_key.strip()) < 8:
        return False, "API Key chưa được nhập hoặc không hợp lệ."

    os.environ["VNSTOCK_API_KEY"] = api_key.strip()
    os.environ["VNSTOCK_INTERACTIVE"] = "0"
    os.environ["VNSTOCK_LANGUAGE"] = "2"
    os.environ["VNSTOCK_VENV_PATH"] = str(SPONSOR_VENV)

    ok, detail = sponsor_available()
    if ok:
        return True, f"vnstock_data đã sẵn sàng ({detail})."

    try:
        urllib.request.urlretrieve(INSTALLER_URL, INSTALLER_PATH)
        INSTALLER_PATH.chmod(0o755)
    except Exception as e:
        return False, f"Không tải được Vnstock CLI installer: {e}"

    # API key is provided ONLY via environment, not command line, to avoid leaking into logs/process args.
    cmd = [
        str(INSTALLER_PATH), "--",
        "--non-interactive",
        "--venv-path", str(SPONSOR_VENV),
        "--language", "vi",
    ]
    env=os.environ.copy()
    try:
        proc=subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "Cài Sponsor quá thời gian chờ."
    except Exception as e:
        return False, f"Lỗi chạy installer: {e}"

    _add_venv_site_packages()
    ok, detail = sponsor_available()
    if ok:
        return True, f"Kết nối Sponsor thành công ({detail})."

    # Redact any accidental API-key occurrence before returning log tail.
    log=(proc.stdout or "")[-2500:]
    log=log.replace(api_key.strip(),"***REDACTED***")
    return False, f"Installer exit={proc.returncode}. vnstock_data chưa import được. Log cuối:\n{log}"

def set_runtime_key(api_key: str):
    if api_key:
        os.environ["VNSTOCK_API_KEY"]=api_key.strip()
        os.environ["VNSTOCK_INTERACTIVE"]="0"
