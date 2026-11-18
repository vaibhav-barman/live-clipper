"""Background tasks. Long work (download, Demucs, WhisperX, render) runs in a worker process so an
MCP tool call returns at once with a task id; agents poll task_status(task_id, wait_s)."""
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import db, paths

WINDOWS = os.name == "nt"


def start(kind, args, job_id=None, clip_id=None):
    tid = f"t_{uuid.uuid4().hex[:10]}"
    log = paths.LOGS / f"{tid}_{kind}.log"
    db.exec_("INSERT INTO tasks(id, kind, job_id, clip_id, args, status, log, started) "
             "VALUES (?,?,?,?,?,?,?,?)", tid, kind, job_id, clip_id, json.dumps(args), "running",
             str(log), time.time())
    here = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        p for p in (here, os.environ.get("PYTHONPATH", "")) if p))
    # own process group / session so stop() can end the worker together with ffmpeg & co.
    detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
              if WINDOWS else {"start_new_session": True})
    with open(log, "w", encoding="utf-8") as lf:
        p = subprocess.Popen([sys.executable, "-m", "clipper.worker", tid], stdout=lf,
                             stderr=subprocess.STDOUT, env=env,
                             cwd=str(Path(__file__).resolve().parents[1]), **detach)
    db.exec_("UPDATE tasks SET pid=? WHERE id=?", p.pid, tid)
    return tid


def _alive_windows(pid):
    # os.kill(pid, 0) is NOT a probe on Windows (0 == CTRL_C_EVENT), so ask the kernel instead.
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def alive(pid):
    if not pid:
        return False
    if WINDOWS:
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                   # reap if it is our zombie child
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True


def status(tid, wait_s=0):
    deadline = time.time() + max(0, min(wait_s, 55))
    while True:
        t = db.one("SELECT * FROM tasks WHERE id=?", tid)
        if t is None:
            return {"error": f"no task {tid}"}
        if t["status"] == "running" and not alive(t["pid"]):
            time.sleep(0.5)
            t = db.one("SELECT * FROM tasks WHERE id=?", tid)
            if t["status"] == "running":
                db.exec_("UPDATE tasks SET status='failed', finished=? WHERE id=?", time.time(), tid)
                t["status"] = "failed"
        if t["status"] != "running" or time.time() >= deadline:
            break
        time.sleep(1.0)
    tail = ""
    try:
        tail = "".join(Path(t["log"]).read_text(encoding="utf-8", errors="replace").splitlines(True)[-25:])
    except OSError:
        pass
    return {"task_id": tid, "kind": t["kind"], "status": t["status"], "result": t["result"],
            "log_tail": tail, "elapsed_s": round((t["finished"] or time.time()) - t["started"], 1)}


def stop(tid):
    t = db.one("SELECT * FROM tasks WHERE id=?", tid)
    if not t:
        return {"error": f"no task {tid}"}
    if t["pid"] and alive(t["pid"]):
        try:
            if WINDOWS:                  # /T takes the whole tree (streamlink, ffmpeg, ...)
                subprocess.run(["taskkill", "/PID", str(t["pid"]), "/T", "/F"], capture_output=True)
            else:
                os.killpg(t["pid"], signal.SIGTERM)
        except OSError:
            pass
    db.exec_("UPDATE tasks SET status='stopped', finished=? WHERE id=?", time.time(), tid)
    return {"task_id": tid, "status": "stopped"}
