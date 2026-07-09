#!/usr/bin/env python3
"""
NetApp Active IQ Advisor - Setup Installer
==========================================
A self-contained GUI installer written in Python.

Why Python instead of a .bat or .exe?
  - Runs through python.exe, which is a digitally-signed, trusted
    binary from the Python Software Foundation. Windows SmartScreen
    never blocks python.exe launching a .py script.
  - No PowerShell ExecutionPolicy bypass needed.
  - No Mark-of-the-Web issues with unsigned executables.

Double-click to run, or:  python Install_NetApp_AIQ_Advisor.py
"""

import sys
import os
import subprocess
import threading
import shutil
import socket
import time
import traceback
from pathlib import Path

# ── tkinter (built into every Python 3 install) ──────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, font as tkfont
    HAS_TK = True
except ImportError:
    HAS_TK = False

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0d1117"
BG2      = "#161b22"
BG3      = "#21262d"
BORDER   = "#30363d"
CYAN     = "#00e5ff"
GREEN    = "#3fb950"
YELLOW   = "#d29922"
RED      = "#f85149"
TEXT     = "#e6edf3"
TEXT2    = "#8b949e"
FONT     = ("Segoe UI", 10)
FONT_SM  = ("Segoe UI", 9)
FONT_LG  = ("Segoe UI", 13, "bold")
FONT_HED = ("Segoe UI", 11, "bold")


# ─────────────────────────────────────────────────────────────────────────────
# Installer logic (runs in a background thread)
# ─────────────────────────────────────────────────────────────────────────────

INSTALL_DIR = Path.home() / "NetApp AIQ Advisor"

SOURCE_CANDIDATES = [
    Path(r"G:\My Drive\AntiGravity\AIQscraper"),
    Path.home() / "Documents" / "AIQscraper",
    Path(os.environ.get("LOCALAPPDATA", "")) / "AIQscraper",
    # Also check the directory this script lives in
    Path(__file__).parent,
]

APP_FILES = [
    "index.html", "app.js", "styles.css", "chart.js",
    "launcher.py", "server.py", "AIQscraper.spec",
    "build_windows.bat", "build_mac.sh", "requirements_desktop.txt",
    "README.md", "CHANGELOG.md",
]

GITHUB_REPO = "https://github.com/ebeauzec/AIQscraper.git"


def find_pythonw() -> str:
    """Return path to pythonw.exe (silent Python runtime, no console window)."""
    pydir = Path(sys.executable).parent
    pw = pydir / "pythonw.exe"
    return str(pw) if pw.exists() else sys.executable


def find_source() -> Path | None:
    for c in SOURCE_CANDIDATES:
        if (c / "index.html").exists() and (c / "launcher.py").exists():
            return c
    return None


def clone_from_github(log_fn) -> Path:
    """Clone the repo to a temp dir and return its path."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="aiq_install_"))
    log_fn(f"  Cloning from GitHub to {tmp}...")
    result = subprocess.run(
        ["git", "clone", GITHUB_REPO, str(tmp), "--depth", "1", "--quiet"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git clone failed:\n{result.stderr or result.stdout}")
    return tmp


def create_vbs_launcher(install_dir: Path, pythonw: str) -> Path:
    vbs = install_dir / "Launch.vbs"
    launcher_py = install_dir / "launcher.py"
    content = (
        'Set oShell = CreateObject("WScript.Shell")\r\n'
        f'oShell.CurrentDirectory = "{install_dir}"\r\n'
        f'oShell.Run Chr(34) & "{pythonw}" & Chr(34)'
        f' & " " & Chr(34) & "{launcher_py}" & Chr(34), 0, False\r\n'
    )
    vbs.write_text(content, encoding="utf-8")
    return vbs


def create_desktop_shortcut(vbs_path: Path, install_dir: Path):
    """Create a .lnk on the Desktop pointing to Launch.vbs."""
    desktop = Path.home() / "Desktop"
    lnk = desktop / "NetApp AIQ Advisor.lnk"
    ps = (
        f'$ws = New-Object -ComObject WScript.Shell;'
        f'$sc = $ws.CreateShortcut("{lnk}");'
        f'$sc.TargetPath = "{vbs_path}";'
        f'$sc.WorkingDirectory = "{install_dir}";'
        f'$sc.Description = "NetApp Active IQ Advisor - Open Dashboard";'
        f'$sc.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

class InstallerApp:
    def __init__(self, root: "tk.Tk"):
        self.root = root
        self._cancelled = False
        self._done = False
        self._vbs_path: Path | None = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        r = self.root
        r.title("NetApp Active IQ Advisor — Setup")
        r.configure(bg=BG)
        r.resizable(False, False)
        r.geometry("620x520")
        r.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to center on screen
        r.update_idletasks()
        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        x = (sw - 620) // 2
        y = (sh - 520) // 2
        r.geometry(f"620x520+{x}+{y}")

        # ── Header ───────────────────────────────────────────────────────────
        header = tk.Frame(r, bg=BG2, pady=18)
        header.pack(fill="x")

        tk.Label(
            header, text="NetApp Active IQ Advisor",
            bg=BG2, fg=CYAN, font=("Segoe UI", 16, "bold")
        ).pack()
        tk.Label(
            header, text="Setup Installer  ·  Version 1.11.0",
            bg=BG2, fg=TEXT2, font=FONT_SM
        ).pack(pady=(2, 0))

        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        # ── Steps panel ──────────────────────────────────────────────────────
        steps_frame = tk.Frame(r, bg=BG, padx=28, pady=16)
        steps_frame.pack(fill="x")

        self._step_labels = {}
        steps = [
            ("step1", "1", "Verify Python installation"),
            ("step2", "2", "Install pywebview  (native window library)"),
            ("step3", "3", "Locate application source files"),
            ("step4", "4", "Copy files and create Desktop shortcut"),
        ]
        for key, num, text in steps:
            row = tk.Frame(steps_frame, bg=BG)
            row.pack(fill="x", pady=3)
            badge = tk.Label(
                row, text=num, width=2,
                bg=BG3, fg=TEXT2,
                font=("Segoe UI", 9, "bold"),
                relief="flat", padx=4, pady=2
            )
            badge.pack(side="left", padx=(0, 10))
            lbl = tk.Label(row, text=text, bg=BG, fg=TEXT2, font=FONT, anchor="w")
            lbl.pack(side="left", fill="x")
            self._step_labels[key] = (badge, lbl)

        # ── Progress bar ──────────────────────────────────────────────────────
        pb_frame = tk.Frame(r, bg=BG, padx=28, pady=4)
        pb_frame.pack(fill="x")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "AIQ.Horizontal.TProgressbar",
            troughcolor=BG3, background=CYAN,
            bordercolor=BG3, lightcolor=CYAN, darkcolor=CYAN,
            thickness=8
        )
        self.progress = ttk.Progressbar(
            pb_frame, style="AIQ.Horizontal.TProgressbar",
            mode="determinate", maximum=100, value=0
        )
        self.progress.pack(fill="x")

        # ── Status log ───────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x", padx=0, pady=(8, 0))

        log_outer = tk.Frame(r, bg=BG2, padx=16, pady=12)
        log_outer.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_outer,
            bg=BG2, fg=TEXT, font=("Consolas", 9),
            relief="flat", wrap="word",
            state="disabled", height=10,
            insertbackground=CYAN,
            selectbackground=BG3,
        )
        sb = tk.Scrollbar(log_outer, command=self.log_text.yview, bg=BG2)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Tag colours for log
        self.log_text.tag_configure("ok",   foreground=GREEN)
        self.log_text.tag_configure("info", foreground=CYAN)
        self.log_text.tag_configure("warn", foreground=YELLOW)
        self.log_text.tag_configure("err",  foreground=RED)
        self.log_text.tag_configure("dim",  foreground=TEXT2)

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Frame(r, bg=BORDER, height=1).pack(fill="x")

        footer = tk.Frame(r, bg=BG, pady=12, padx=20)
        footer.pack(fill="x")

        self.status_lbl = tk.Label(
            footer, text="Initialising...",
            bg=BG, fg=TEXT2, font=FONT_SM, anchor="w"
        )
        self.status_lbl.pack(side="left", fill="x", expand=True)

        self.action_btn = tk.Button(
            footer, text="Cancel",
            bg=BG3, fg=TEXT, font=FONT,
            relief="flat", padx=16, pady=6,
            activebackground=BORDER, activeforeground=TEXT,
            cursor="hand2",
            command=self._on_close,
        )
        self.action_btn.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _log(self, msg: str, tag: str = ""):
        def _do():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _do)

    def _set_progress(self, pct: int):
        self.root.after(0, lambda: self.progress.configure(value=pct))

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.status_lbl.configure(text=msg))

    def _mark_step(self, key: str, state: str):
        """state: 'active' | 'done' | 'error'"""
        badge, lbl = self._step_labels[key]
        colours = {
            "active": (CYAN,  TEXT,  "bold"),
            "done":   (GREEN, TEXT,  "normal"),
            "error":  (RED,   RED,   "normal"),
        }
        bg_col, fg_col, weight = colours.get(state, (BG3, TEXT2, "normal"))
        self.root.after(0, lambda: badge.configure(bg=bg_col, fg=BG))
        self.root.after(0, lambda: lbl.configure(
            fg=fg_col, font=("Segoe UI", 10, weight)
        ))

    def _set_done_ui(self, success: bool):
        def _do():
            if success:
                self.action_btn.configure(
                    text="Launch Now",
                    bg=CYAN, fg=BG,
                    font=("Segoe UI", 10, "bold"),
                    command=self._launch_and_exit,
                )
                self.status_lbl.configure(
                    text="Installation complete!  Desktop shortcut created.",
                    fg=GREEN
                )
            else:
                self.action_btn.configure(
                    text="Close",
                    bg=RED, fg=TEXT,
                    command=self.root.destroy,
                )
                self.status_lbl.configure(
                    text="Installation failed.  See log above.",
                    fg=RED
                )
        self.root.after(0, _do)

    def _launch_and_exit(self):
        if self._vbs_path and self._vbs_path.exists():
            os.startfile(str(self._vbs_path))
            time.sleep(1)
        self.root.destroy()

    def _on_close(self):
        if self._done:
            self.root.destroy()
        else:
            self._cancelled = True
            self.root.destroy()

    # ── Main install thread ───────────────────────────────────────────────────
    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self):
        try:
            self._install()
        except Exception as exc:
            self._log(f"\nUnexpected error:\n{traceback.format_exc()}", "err")
            self._set_done_ui(False)

    def _install(self):
        # ── Step 1: Python ────────────────────────────────────────────────────
        self._mark_step("step1", "active")
        self._set_status("Checking Python...")
        self._set_progress(5)
        pver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self._log(f"[1/4] Python {pver} confirmed.", "ok")
        pythonw = find_pythonw()
        self._log(f"      pythonw: {pythonw}", "dim")
        self._mark_step("step1", "done")
        self._set_progress(15)

        if self._cancelled: return

        # ── Step 2: pywebview ─────────────────────────────────────────────────
        self._mark_step("step2", "active")
        self._set_status("Installing pywebview...")
        self._log("\n[2/4] Installing pywebview...", "info")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade",
                 "pywebview", "--quiet", "--no-warn-script-location"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr or "pip failed")
            self._log("      pywebview ready.", "ok")
            self._mark_step("step2", "done")
        except Exception as e:
            self._log(f"      ERROR: {e}", "err")
            self._mark_step("step2", "error")
            self._set_done_ui(False)
            return
        self._set_progress(35)

        if self._cancelled: return

        # ── Step 3: Source files ──────────────────────────────────────────────
        self._mark_step("step3", "active")
        self._set_status("Locating source files...")
        self._log("\n[3/4] Locating source files...", "info")
        src = find_source()
        if not src:
            self._log("      Not found locally. Cloning from GitHub...", "warn")
            try:
                src = clone_from_github(self._log)
                self._log("      Downloaded from GitHub.", "ok")
            except Exception as e:
                self._log(f"      ERROR: {e}", "err")
                self._log(
                    "      TIP: Place this installer inside the AIQscraper\n"
                    "           project folder and re-run.", "warn"
                )
                self._mark_step("step3", "error")
                self._set_done_ui(False)
                return
        else:
            self._log(f"      Found: {src}", "ok")
        self._mark_step("step3", "done")
        self._set_progress(55)

        if self._cancelled: return

        # ── Step 4: Copy + shortcut ───────────────────────────────────────────
        self._mark_step("step4", "active")
        self._set_status("Installing application files...")
        self._log(f"\n[4/4] Installing to: {INSTALL_DIR}", "info")
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)

        copied = 0
        for f in APP_FILES:
            fp = src / f
            if fp.exists():
                shutil.copy2(fp, INSTALL_DIR / f)
                copied += 1
        self._log(f"      Copied {copied} files.", "ok")
        self._set_progress(72)

        # VBS silent launcher
        vbs = create_vbs_launcher(INSTALL_DIR, pythonw)
        self._vbs_path = vbs
        self._log(f"      Launcher: {vbs}", "ok")
        self._set_progress(85)

        # Desktop shortcut
        try:
            create_desktop_shortcut(vbs, INSTALL_DIR)
            self._log("      Desktop shortcut created: 'NetApp AIQ Advisor'", "ok")
        except Exception as e:
            self._log(f"      Shortcut skipped ({e}). Manually link to: {vbs}", "warn")

        self._mark_step("step4", "done")
        self._set_progress(100)

        self._log("\n━━━ Installation complete! ━━━", "ok")
        self._log(f"  App folder:  {INSTALL_DIR}\\", "dim")
        self._log("  Shortcut:    'NetApp AIQ Advisor' on your Desktop", "dim")
        self._log("\nClick 'Launch Now' to open the dashboard.", "info")
        self._done = True
        self._set_done_ui(True)


# ─────────────────────────────────────────────────────────────────────────────
# Console fallback (if tkinter is unavailable)
# ─────────────────────────────────────────────────────────────────────────────

def console_install():
    """Minimal console installer for environments without tkinter."""
    print("\n NetApp Active IQ Advisor — Setup v1.11.0\n")
    input(" Press Enter to begin...\n")

    pver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f" [1/4] Python {pver} confirmed.")

    print(" [2/4] Installing pywebview...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade",
         "pywebview", "--quiet"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"       ERROR: {r.stderr}"); sys.exit(1)
    print("       Done.")

    print(" [3/4] Locating source files...")
    src = find_source()
    if not src:
        print("       Cloning from GitHub...")
        src = clone_from_github(print)
    print(f"       Source: {src}")

    print(f" [4/4] Installing to {INSTALL_DIR}...")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    for f in APP_FILES:
        fp = src / f
        if fp.exists():
            shutil.copy2(fp, INSTALL_DIR / f)
    pythonw = find_pythonw()
    vbs = create_vbs_launcher(INSTALL_DIR, pythonw)
    create_desktop_shortcut(vbs, INSTALL_DIR)
    print("       Complete.")

    print(f"\n Installation complete!")
    print(f" App folder: {INSTALL_DIR}")
    print(" Desktop shortcut: NetApp AIQ Advisor\n")
    go = input(" Launch now? [y/N]: ")
    if go.strip().lower() == "y":
        os.startfile(str(vbs))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if HAS_TK:
        root = tk.Tk()
        app = InstallerApp(root)
        # Start the install after a short delay so the window paints first
        root.after(300, app.start)
        root.mainloop()
    else:
        console_install()


if __name__ == "__main__":
    main()
