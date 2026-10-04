"""Bambu Lab X1 Carbon (X1C) LAN helper. Original code; protocol knowledge only.

Read-only:   status | validate-gcode FILE|- | pin-show
Writes:      upload FILE          validate, then FTPS-upload (does NOT start a print)
             start-print NAME     human gate: a terminal + typed phrase, OR a fresh owner 'arm'
             arm NAME --minutes N owner-only (terminal + phrase): pre-authorise ONE start of THIS file
             disarm               cancel any pending arm
             pause | resume | cancel   stop-direction actions, no terminal needed

Environment (set it yourself; never paste the access code into chat):
  BAMBU_HOST, BAMBU_SERIAL, BAMBU_ACCESS_CODE
  BAMBU_TLS_FINGERPRINT   optional explicit SHA-256 pin
  BAMBU_STORAGE_DIR       optional, default /sdcard

UNVERIFIED against real hardware: FTPS upload path, the start-print MQTT payloads.
First live test: tiny file, you standing at the printer, hand on the stop button.
"""
import argparse, hashlib, ftplib, json, os, re, socket, ssl, sys, threading, time, zipfile
from datetime import datetime, timezone
from pathlib import Path

MQTT_PORT, FTPS_PORT, USER = 8883, 990, "bblp"
HOME = Path.home() / ".bambu_x1"
PIN_FILE, PENDING_FILE, AUDIT_FILE = HOME / "pins.json", HOME / "pending.json", HOME / "audit.log"

MAX_NOZZLE, MAX_BED = 300, 120          # conservative X1C limits
BUILD = {"X": (0, 256), "Y": (0, 256), "Z": (0, 256)}
BLOCKED = {
    "M502": "factory reset of settings", "M500": "writes settings to firmware",
    "M501": "reloads settings from firmware", "M997": "firmware update / reboot",
    "M999": "restart after error", "M141": "X1C has no chamber heater",
    "M191": "X1C has no chamber heater",
    "M112": "emergency stop is for the printer UI, not scripted use here",
}
MAX_UPLOAD = 500 * 1024 * 1024
MAX_GCODE_READ = 256 * 1024 * 1024
APPROVAL_MAX_AGE = 2 * 3600
SAFE_NAME = re.compile(r"^[A-Za-z0-9._ \-]{1,100}\.(3mf|gcode)$")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr); sys.exit(code)


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        die(f"environment variable {name} is not set")
    return v


def audit(action, **kw):
    HOME.mkdir(parents=True, exist_ok=True)
    rec = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "action": action, **kw}
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- G-code check
def validate_gcode(text):
    """Strict check of the print body; the slicer's machine start/end blocks get relaxed BOUNDS only.

    Bambu start/end G-code legitimately parks the head outside 0..256 (purge/wipe at Y265, Z below 0) and
    runs M500 to save calibration. Those blocks are found by the slicer's own markers. In them we skip the
    bounds check and allow M500/M501; temperature limits and every other blocked command still apply.
    Residual risk: the markers are text in the file, so a hostile file could fake them. The remaining checks
    still catch over-temperature and firmware commands, but not out-of-range moves inside a faked block.
    """
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if "MACHINE_START_GCODE_END" in l]
    ends = [i for i, l in enumerate(lines) if "MACHINE_END_GCODE_START" in l]
    body_lo = starts[0] if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0] else None
    body_hi = ends[0] if body_lo is not None else None
    problems, absolute = [], True
    for n, raw in enumerate(lines, 1):
        vendor = body_lo is not None and not (body_lo < n - 1 < body_hi)
        line = raw.split(";", 1)[0].strip().upper()
        if not line:
            continue
        cmd = line.split()[0]
        if cmd in BLOCKED and not (vendor and cmd in ("M500", "M501")):
            problems.append((n, raw.strip(), f"{cmd} blocked: {BLOCKED[cmd]}"))
        if cmd == "G91":
            absolute = False
        elif cmd == "G90":
            absolute = True
        if cmd in ("M104", "M109", "M140", "M190"):
            m = re.search(r"S(-?\d+(?:\.\d+)?)", line)
            if m:
                t = float(m.group(1)); lim = MAX_NOZZLE if cmd in ("M104", "M109") else MAX_BED
                if t > lim:
                    problems.append((n, raw.strip(), f"{cmd} S{t:g} exceeds limit {lim}"))
        if cmd in ("G0", "G1") and absolute and not vendor:
            for axis, (lo, hi) in BUILD.items():
                m = re.search(rf"{axis}(-?\d+(?:\.\d+)?)", line)
                if m and not lo <= float(m.group(1)) <= hi:
                    problems.append((n, raw.strip(), f"{axis}{m.group(1)} outside {lo}..{hi} mm"))
    return problems


def gcode_text_for(path, plate):
    """Return the G-code text to validate: the file itself, or plate_N.gcode inside a .3mf."""
    p = Path(path)
    if p.suffix.lower() == ".gcode":
        if p.stat().st_size > MAX_GCODE_READ:
            die("gcode file too large to validate")
        return p.read_text(errors="replace")
    member = f"Metadata/plate_{plate}.gcode"
    with zipfile.ZipFile(p) as z:
        try:
            info = z.getinfo(member)
        except KeyError:
            die(f"{member} not found in 3mf (is it sliced? try --plate N)")
        if info.file_size > MAX_GCODE_READ:
            die("embedded gcode too large to validate")
        return z.read(member).decode("utf-8", "replace")


def report_problems(problems):
    for n, line, why in problems[:50]:
        print(f"  line {n}: {why}\n      {line}")
    if len(problems) > 50:
        print(f"  ... and {len(problems) - 50} more")


def cmd_validate(a):
    text = sys.stdin.read() if a.file == "-" else gcode_text_for(a.file, a.plate)
    problems = validate_gcode(text)
    report_problems(problems)
    print(f"{'BLOCKED' if problems else 'OK'}: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


# ------------------------------------------------------------------ TLS pinning
def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_json(path, obj):
    HOME.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def peer_fingerprint(host, port):
    ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=10) as s, ctx.wrap_socket(s) as t:
        return hashlib.sha256(t.getpeercert(binary_form=True)).hexdigest()


def verify_pin(host, port, trust_new):
    """Check the printer's certificate BEFORE any credential is sent."""
    try:
        fp = peer_fingerprint(host, port)
    except Exception as e:
        die(f"cannot reach {host}:{port} ({e}). Is LAN mode on and the IP right?")
    explicit = env("BAMBU_TLS_FINGERPRINT", False).lower().replace(":", "")
    pins = load_json(PIN_FILE); pinned = explicit or pins.get(host.lower())
    if pinned and pinned != fp:
        die(f"CERT MISMATCH for {host}: got {fp}, expected {pinned}. Nothing was sent.")
    if not pinned:
        if not trust_new:
            die(f"No pin stored. Verify this fingerprint on a trusted network, then rerun with --trust-new:\n  {fp}")
        pins[host.lower()] = fp; save_json(PIN_FILE, pins); print(f"pinned {fp}")
    return fp


def cmd_pin_show(_):
    print(load_json(PIN_FILE).get(env("BAMBU_HOST").lower(), "no pin stored"))


# ------------------------------------------------------------------------ MQTT
class Session:
    def __init__(self, trust_new=False):
        self.host, self.serial, self.code = env("BAMBU_HOST"), env("BAMBU_SERIAL"), env("BAMBU_ACCESS_CODE")
        self.trust_new = trust_new
        self.report, self._got, self._up, self._err = {}, threading.Event(), threading.Event(), []

    def connect(self, timeout=15):
        import paho.mqtt.client as mqtt
        verify_pin(self.host, MQTT_PORT, self.trust_new)
        ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE   # identity checked by pin above
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"claude-x1-{os.getpid()}")
        c.username_pw_set(USER, self.code); c.tls_set_context(ctx)

        def on_connect(cl, _u, _f, rc, _p=None):
            if getattr(rc, "is_failure", rc != 0):
                self._err.append(f"connect refused: {rc}")
            else:
                cl.subscribe(f"device/{self.serial}/report")
            self._up.set()

        def on_message(_c, _u, msg):
            try:
                p = json.loads(msg.payload).get("print", {})
            except Exception:
                return
            if p:
                self.report.update(p)
                if "gcode_state" in p:
                    self._got.set()

        c.on_connect, c.on_message = on_connect, on_message
        c.connect(self.host, MQTT_PORT, keepalive=30); c.loop_start(); self.c = c
        if not self._up.wait(timeout) or self._err:
            self.close(); die(self._err[0] if self._err else "MQTT connect timed out (wrong access code?)")

    def snapshot(self, timeout=15):
        self._got.clear()
        self.c.publish(f"device/{self.serial}/request", json.dumps({"pushing": {"sequence_id": "1", "command": "pushall"}}))
        if not self._got.wait(timeout):
            self.close(); die("no status received (wrong serial or access code, or LAN mode off)")
        return self.report

    def send(self, payload):
        info = self.c.publish(f"device/{self.serial}/request", json.dumps(payload), qos=1)
        info.wait_for_publish(10)
        return info.is_published()

    def close(self):
        try:
            self.c.loop_stop(); self.c.disconnect()
        except Exception:
            pass


def summarize_ams(p):
    ams = p.get("ams") or {}
    now = str(ams.get("tray_now", ""))
    out = {"active_slot": {"254": "external spool", "255": "none"}.get(now, now or "?"), "units": []}
    for u in ams.get("ams", []) or []:
        slots = []
        for t in u.get("tray", []) or []:
            if "tray_type" not in t:
                slots.append({"slot": t.get("id"), "empty": True}); continue
            c = str(t.get("tray_color", ""))
            slots.append({"slot": t.get("id"), "type": t.get("tray_type"),
                          "color_hex": ("#" + c[:6]) if len(c) >= 6 else None,
                          "remain_pct": t.get("remain"),
                          "nozzle_c": f"{t.get('nozzle_temp_min','?')}-{t.get('nozzle_temp_max','?')}"})
        out["units"].append({"unit": u.get("id"), "humidity_index": u.get("humidity"),
                             "temp_c": u.get("temp"), "slots": slots})
    vt = p.get("vt_tray")
    if isinstance(vt, dict) and vt.get("tray_type"):
        out["external_spool"] = {"type": vt.get("tray_type"), "color_hex": "#" + str(vt.get("tray_color", ""))[:6]}
    if not out["units"]:
        out["note"] = "no AMS reported (not fitted, or report did not include it)"
    return out


def summarize(p):
    g = lambda k, d="?": p.get(k, d)
    return {"state": g("gcode_state"), "job": g("subtask_name", "") or g("gcode_file", ""),
            "progress_pct": g("mc_percent"), "minutes_left": g("mc_remaining_time"),
            "layer": f"{g('layer_num')}/{g('total_layer_num')}",
            "nozzle_c": f"{g('nozzle_temper')} -> {g('nozzle_target_temper')}",
            "bed_c": f"{g('bed_temper')} -> {g('bed_target_temper')}", "chamber_c": g("chamber_temper"),
            "wifi": g("wifi_signal"), "print_error": g("print_error", 0), "ams": summarize_ams(p)}


def cmd_status(a):
    s = Session(a.trust_new); s.connect(); r = s.snapshot(a.timeout); s.close()
    print(json.dumps(summarize(r), indent=2))


# ------------------------------------------------------------------------ FTPS
class ImplicitFTPTLS(ftplib.FTP_TLS):
    """Implicit TLS (port 990) with TLS session reuse on data connections, as Bambu requires."""
    def connect(self, host="", port=0, timeout=-999, source_address=None):
        self.host, self.port = host, port
        if timeout != -999:
            self.timeout = timeout
        self.sock = socket.create_connection((host, port), self.timeout, source_address)
        self.af = self.sock.family
        self.sock = self.context.wrap_socket(self.sock, server_hostname=host)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def ftp_connect(trust_new=False):
    host, code = env("BAMBU_HOST"), env("BAMBU_ACCESS_CODE")
    verify_pin(host, FTPS_PORT, trust_new)                       # before sending the code
    ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    ftp = ImplicitFTPTLS(context=ctx, timeout=30)
    ftp.connect(host, FTPS_PORT); ftp.login(USER, code); ftp.prot_p()
    return ftp


def storage_dir():
    d = env("BAMBU_STORAGE_DIR", False) or "/sdcard"
    if not re.fullmatch(r"/[A-Za-z0-9_\-]+", d):
        die("BAMBU_STORAGE_DIR must be a single top-level folder like /sdcard")
    return d


def check_name(path_or_name):
    name = Path(path_or_name).name
    if not SAFE_NAME.match(name):
        die(f"unsafe file name {name!r}: use letters, digits, space . _ - and a .3mf or .gcode extension")
    return name


def cmd_upload(a):
    path = Path(a.file)
    if not path.is_file():
        die("file not found")
    name = check_name(path)
    if path.stat().st_size > MAX_UPLOAD:
        die("file larger than 500 MB")
    problems = validate_gcode(gcode_text_for(path, a.plate))
    if problems:
        report_problems(problems); audit("upload_refused", name=name, problems=len(problems))
        die(f"{len(problems)} G-code problem(s); nothing uploaded")
    digest = sha256_file(path); remote = f"/{name}"  # FTP root is the SD card on the X1C; print commands still use storage_dir()
    ftp = ftp_connect(a.trust_new)
    try:
        with open(path, "rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        remote_size = ftp.size(remote)
    finally:
        try: ftp.quit()
        except Exception: pass
    if remote_size != path.stat().st_size:
        die(f"size mismatch after upload (local {path.stat().st_size}, printer {remote_size})")
    pend = load_json(PENDING_FILE)
    pend[name] = {"local": str(path.resolve()), "sha256": digest, "size": remote_size, "plate": a.plate,
                  "uploaded": time.time()}
    save_json(PENDING_FILE, pend); audit("upload", name=name, sha256=digest, size=remote_size)
    print(f"uploaded {name} ({remote_size} bytes, validated, sha256 {digest[:16]}...)")
    print(f"Not started. To print, run this yourself in a normal PowerShell window:\n  python scripts/x1.py start-print \"{name}\"")


# ----------------------------------------------------------------- print control
ARM_FILE = HOME / "armed.json"
ARM_MAX_MINUTES = 60


def consume_arm(name, rec):
    """True only if the owner armed THIS file (same sha256) and it has not expired. Always single use."""
    a = load_json(ARM_FILE)
    try:
        ARM_FILE.unlink()
    except FileNotFoundError:
        pass
    return bool(a) and a.get("name") == name and a.get("sha256") == rec["sha256"] and time.time() < a.get("expires", 0)


def cmd_arm(a):
    name = check_name(a.name)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        audit("arm_refused_no_tty", name=name)
        die("arm must be run by the owner in a real terminal. Claude cannot arm itself.", 3)
    if not 1 <= a.minutes <= ARM_MAX_MINUTES:
        die(f"--minutes must be 1..{ARM_MAX_MINUTES}")
    rec = load_json(PENDING_FILE).get(name)
    if not rec:
        die("no upload record for this name; upload it with this tool first")
    if not Path(rec["local"]).is_file() or sha256_file(rec["local"]) != rec["sha256"]:
        die("local file changed since upload; upload again")
    serial = env("BAMBU_SERIAL")
    print(f"ARM: allow Claude to start '{name}' (sha256 {rec['sha256'][:16]}...) once, within {a.minutes} min.")
    print("Only do this if you are, or will be, next to the printer with the bed clear and the right filament loaded.")
    phrase = f"ARM {serial[-4:]}"
    if input(f"Type  {phrase}  to authorise, anything else cancels: ").strip() != phrase:
        die("not armed", 0)
    save_json(ARM_FILE, {"name": name, "sha256": rec["sha256"], "expires": time.time() + a.minutes * 60})
    audit("armed", name=name, sha256=rec["sha256"], minutes=a.minutes)
    print(f"Armed for {a.minutes} min, single use. Cancel any time with:  python scripts/x1.py disarm")


def cmd_disarm(_):
    try:
        ARM_FILE.unlink(); audit("disarmed"); print("disarmed")
    except FileNotFoundError:
        print("nothing was armed")


def cmd_start(a):
    name = check_name(a.name)
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    rec = load_json(PENDING_FILE).get(name)
    if not rec:
        die("no upload record for this name; upload it with this tool first")
    armed = False
    if not tty:
        armed = consume_arm(name, rec)
        if not armed:
            audit("start_refused_no_tty_not_armed", name=name)
            die("start-print needs either a real terminal with you typing the confirmation, or a fresh 'arm' from you.\n"
                f"In your own PowerShell window run:  python scripts/x1.py arm \"{name}\" --minutes 15", 3)
    if time.time() - rec["uploaded"] > APPROVAL_MAX_AGE:
        die("upload record is older than 2 hours; upload again")
    if not Path(rec["local"]).is_file() or sha256_file(rec["local"]) != rec["sha256"]:
        die("local file changed or vanished since upload; upload again")
    s = Session(); s.connect(); r = s.snapshot()
    state = r.get("gcode_state")
    if state not in ("IDLE", "FINISH", "FAILED"):
        s.close(); die(f"printer state is {state!r}, not ready for a new job")
    info = summarize(r)
    print("\n=== START PRINT ===")
    print(f"file     : {name}   sha256 {rec['sha256'][:16]}...   {rec['size']} bytes")
    print(f"nozzle/bed now: {info['nozzle_c']} / {info['bed_c']}")
    print(f"AMS      : {json.dumps(info['ams'])[:600]}")
    print("filament : " + (f"AMS slot {a.ams_slot}" if a.ams_slot is not None else "external spool (no AMS)"))
    print("Check: build plate, correct filament loaded, nothing on the bed, you are next to the printer.")
    if armed:
        print("Pre-authorised by the owner via 'arm' (single use). Starting without a prompt.")
        audit("start_armed", name=name, sha256=rec["sha256"])
    else:
        phrase = f"PRINT {s.serial[-4:]}"
        try:
            typed = input(f"Type  {phrase}  to start, anything else cancels: ").strip()
        except EOFError:
            typed = ""
        if typed != phrase:
            s.close(); audit("start_cancelled", name=name); die("cancelled, nothing sent", 0)
    seq = str(int(time.time()) % 100000)
    if name.lower().endswith(".gcode"):
        payload = {"print": {"sequence_id": seq, "command": "gcode_file", "param": f"{storage_dir()}/{name}"}}
    else:
        use_ams = a.ams_slot is not None
        md5 = hashlib.md5(open(rec["local"], "rb").read()).hexdigest().upper()
        payload = {"print": {"sequence_id": seq, "command": "project_file",
                             "param": f"Metadata/plate_{rec['plate']}.gcode", "subtask_name": Path(name).stem,
                             "file": name, "url": f"ftp:///{name}", "md5": md5,
                             "project_id": "0", "profile_id": "0", "task_id": "0", "subtask_id": "0",
                             "timelapse": False, "bed_type": "auto", "bed_leveling": True, "flow_cali": False,
                             "vibration_cali": True, "layer_inspect": False, "use_ams": use_ams,
                             "ams_mapping": [a.ams_slot] if use_ams else []}}
    ok = s.send(payload); s.close()
    audit("start_sent", name=name, sha256=rec["sha256"], published=ok)
    print("Command sent." if ok else "WARNING: publish not confirmed.")
    print("Sent is not the same as started. Watch the printer and run 'status' to confirm.")
    print("If it does not behave as expected, press stop on the printer.")


def simple_command(cmd_name, mqtt_cmd):
    def run(a):
        if mqtt_cmd == "stop" and not a.yes:
            die("cancel is irreversible for the current job; add --yes to confirm")
        s = Session(); s.connect(); r = s.snapshot()
        state = r.get("gcode_state")
        ok = s.send({"print": {"sequence_id": "1", "command": mqtt_cmd, "param": ""}}); s.close()
        audit(cmd_name, state_before=state, published=ok)
        print(f"{cmd_name} sent (state was {state}). Confirm with 'status'.")
    return run


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--trust-new", action="store_true"); s.add_argument("--timeout", type=int, default=15); s.set_defaults(fn=cmd_status)
    v = sub.add_parser("validate-gcode"); v.add_argument("file"); v.add_argument("--plate", type=int, default=1); v.set_defaults(fn=cmd_validate)
    sub.add_parser("pin-show").set_defaults(fn=cmd_pin_show)
    u = sub.add_parser("upload"); u.add_argument("file"); u.add_argument("--plate", type=int, default=1); u.add_argument("--trust-new", action="store_true"); u.set_defaults(fn=cmd_upload)
    st = sub.add_parser("start-print"); st.add_argument("name"); st.add_argument("--ams-slot", type=int, choices=range(0, 4)); st.set_defaults(fn=cmd_start)
    ar = sub.add_parser("arm"); ar.add_argument("name"); ar.add_argument("--minutes", type=int, default=15); ar.set_defaults(fn=cmd_arm)
    sub.add_parser("disarm").set_defaults(fn=cmd_disarm)
    for n, m in (("pause", "pause"), ("resume", "resume"), ("cancel", "stop")):
        p = sub.add_parser(n); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=simple_command(n, m))
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
