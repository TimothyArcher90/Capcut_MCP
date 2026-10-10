"""Control básico de la aplicación CapCut escritorio (abrir / comprobar / cerrar)."""

from __future__ import annotations

import subprocess

from .config import IS_MAC, IS_WINDOWS, capcut_exe


def is_running() -> bool:
    try:
        if IS_WINDOWS:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe"], capture_output=True, text=True).stdout
            return "CapCut.exe" in out
        out = subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True, text=True).stdout
        return bool(out.strip())
    except OSError:
        return False


def launch() -> str:
    exe = capcut_exe()
    if not exe:
        return "No encontré CapCut. Define CAPCUT_EXE con la ruta al ejecutable."
    if IS_MAC:
        subprocess.Popen(["open", "-a", str(exe)])
    else:
        subprocess.Popen([str(exe)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return f"CapCut lanzado: {exe}"


def close() -> str:
    """Cierra CapCut (útil para que relea la lista de borradores). Guarda tu trabajo antes."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/IM", "CapCut.exe"], capture_output=True)
    elif IS_MAC:
        subprocess.run(["osascript", "-e", 'quit app "CapCut"'], capture_output=True)
    return "Solicitud de cierre enviada a CapCut."
