#!/usr/bin/env python3
"""
Multi-protocol stress test — interactive menu + CLI.
Python 3.8+ stdlib only. Single file. Compiles to .exe with PyInstaller.
"""

import json
import os
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import List


# ─── ANSI helpers ─────────────────────────────────────────────────────────────

if sys.platform == "win32":
    os.system("")  # enable ANSI on Windows CMD

CLEAR = "\033[2J\033[H"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
WHITE = "\033[97m"
MAGENTA = "\033[35m"


def cls():
    sys.stdout.write(CLEAR)
    sys.stdout.flush()


# ─── Stats Collector (thread-safe) ───────────────────────────────────────────

class StatsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self.packets_sent = 0
        self.bytes_sent = 0
        self.errors = 0
        self.connections_active = 0
        self.latencies: List[float] = []
        self.start_time = 0.0
        self._history: List[dict] = []
        self._last_packets = 0
        self._last_bytes = 0
        self._last_time = 0.0

    def start(self):
        self.start_time = time.monotonic()
        self._last_time = self.start_time

    def record_send(self, nbytes: int, latency: float = 0.0):
        with self._lock:
            self.packets_sent += 1
            self.bytes_sent += nbytes
            if latency > 0:
                self.latencies.append(latency)

    def record_error(self):
        with self._lock:
            self.errors += 1

    def conn_up(self):
        with self._lock:
            self.connections_active += 1

    def conn_down(self):
        with self._lock:
            self.connections_active -= 1

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            elapsed = max(now - self.start_time, 0.001)
            interval = max(now - self._last_time, 0.001)
            dp = self.packets_sent - self._last_packets
            db = self.bytes_sent - self._last_bytes
            avg_lat = (sum(self.latencies[-500:]) / len(self.latencies[-500:])) if self.latencies else 0.0

            snap = {
                "elapsed": round(elapsed, 1),
                "packets": self.packets_sent,
                "bytes": self.bytes_sent,
                "mbps": round((db * 8) / (interval * 1e6), 2),
                "MBs": round(db / (interval * 1_048_576), 2),
                "pps": round(dp / interval, 1),
                "lat_ms": round(avg_lat * 1000, 2),
                "errors": self.errors,
                "conns": self.connections_active,
                "err_pct": round((self.errors / max(self.packets_sent, 1)) * 100, 2),
            }
            self._last_packets = self.packets_sent
            self._last_bytes = self.bytes_sent
            self._last_time = now
            self._history.append(snap)
        return snap

    def report(self) -> dict:
        elapsed = max(time.monotonic() - self.start_time, 0.001)
        with self._lock:
            return {
                "total_packets": self.packets_sent,
                "total_bytes": self.bytes_sent,
                "total_errors": self.errors,
                "duration_s": round(elapsed, 2),
                "avg_MBs": round(self.bytes_sent / (elapsed * 1_048_576), 2),
                "avg_pps": round(self.packets_sent / elapsed, 1),
                "avg_lat_ms": round((sum(self.latencies) / len(self.latencies) * 1000) if self.latencies else 0, 2),
                "peak_pps": max((h["pps"] for h in self._history), default=0),
                "peak_MBs": max((h["MBs"] for h in self._history), default=0),
                "err_pct": round((self.errors / max(self.packets_sent, 1)) * 100, 2),
                "history": self._history,
            }


# ─── Shutdown ─────────────────────────────────────────────────────────────────

shutdown = threading.Event()


def _sig(s, f):
    shutdown.set()


# ─── Flooders ─────────────────────────────────────────────────────────────────

class UDPFlooder:
    def __init__(self, target, port, size, stats):
        self.target, self.port, self.stats = target, port, stats
        self.payload = os.urandom(size)

    def run(self, duration, ramp, wid, total):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        self.stats.conn_up()
        t0 = time.monotonic()
        try:
            while not shutdown.is_set():
                e = time.monotonic() - t0
                if e >= duration:
                    break
                if ramp > 0 and e < ramp and (wid / total) > (e / ramp):
                    time.sleep(0.05)
                    continue
                try:
                    s = sock.sendto(self.payload, (self.target, self.port))
                    self.stats.record_send(s, time.monotonic() - t0)
                except (BlockingIOError, OSError):
                    self.stats.record_error()
        finally:
            sock.close()
            self.stats.conn_down()


class TCPFlooder:
    def __init__(self, target, port, size, stats):
        self.target, self.port, self.stats = target, port, stats
        self.payload = os.urandom(size)

    def run(self, duration, ramp, wid, total):
        t0 = time.monotonic()
        while not shutdown.is_set():
            e = time.monotonic() - t0
            if e >= duration:
                break
            if ramp > 0 and e < ramp and (wid / total) > (e / ramp):
                time.sleep(0.05)
                continue
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                self.stats.conn_up()
                ts = time.monotonic()
                sock.connect((self.target, self.port))
                sock.sendall(self.payload)
                self.stats.record_send(len(self.payload), time.monotonic() - ts)
            except (OSError, socket.timeout):
                self.stats.record_error()
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
                    self.stats.conn_down()


class HTTPFlooder:
    def __init__(self, target, port, method, body_size, stats, https=False):
        self.target, self.port, self.method, self.stats = target, port, method.upper(), stats
        self.body = os.urandom(body_size) if self.method == "POST" else None
        scheme = "https" if https else "http"
        if (not https and port == 80) or (https and port == 443):
            self.url = f"{scheme}://{target}/"
        else:
            self.url = f"{scheme}://{target}:{port}/"
        self._ctx = None
        if https:
            self._ctx = ssl.create_default_context()
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE

    def run(self, duration, ramp, wid, total):
        t0 = time.monotonic()
        while not shutdown.is_set():
            e = time.monotonic() - t0
            if e >= duration:
                break
            if ramp > 0 and e < ramp and (wid / total) > (e / ramp):
                time.sleep(0.05)
                continue
            self.stats.conn_up()
            try:
                req = urllib.request.Request(self.url, method=self.method)
                req.add_header("User-Agent", "StressTest/1.0")
                req.add_header("Connection", "close")
                if self.body:
                    req.add_header("Content-Type", "application/octet-stream")
                    req.data = self.body
                ts = time.monotonic()
                r = urllib.request.urlopen(req, timeout=5, context=self._ctx)
                r.read()
                r.close()
                self.stats.record_send(len(self.body) if self.body else len(self.url), time.monotonic() - ts)
            except Exception:
                self.stats.record_error()
            finally:
                self.stats.conn_down()


# ─── Dashboard ────────────────────────────────────────────────────────────────

def dashboard(stats, proto, target, port, duration):
    while not shutdown.is_set():
        s = stats.snapshot()
        p = min(s["elapsed"] / duration, 1.0)
        bar = "█" * int(30 * p) + "░" * (30 - int(30 * p))

        cls()
        print(f"""
  {BOLD}{CYAN}╔══════════════════════════════════════════════════════╗{RESET}
  {BOLD}{CYAN}║{RESET}  {BOLD}{WHITE}STRESS TEST RUNNING{RESET}  {DIM}—{RESET}  {proto.upper()} → {target}:{port}     {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}╠══════════════════════════════════════════════════════╣{RESET}
  {BOLD}{CYAN}║{RESET}                                                      {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {DIM}Progress:{RESET} [{GREEN}{bar}{RESET}] {p*100:3.0f}%   {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {DIM}Time:{RESET}     {s['elapsed']:.0f}s / {duration:.0f}s                          {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}                                                      {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {YELLOW}Packets:{RESET}     {s['packets']:>14,}                   {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {YELLOW}Throughput:{RESET}  {s['MBs']:>10.2f} MB/s  ({s['mbps']:.1f} Mbps)     {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {YELLOW}Packets/s:{RESET}   {s['pps']:>14,.1f}                   {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {YELLOW}Latency:{RESET}     {s['lat_ms']:>10.2f} ms                    {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {YELLOW}Active:{RESET}      {s['conns']:>14,}                   {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {RED}Errors:{RESET}      {s['errors']:>14,}  ({s['err_pct']:.1f}%)        {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {MAGENTA}Data sent:{RESET}   {s['bytes']/1_048_576:>10.2f} MB                    {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}                                                      {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}  {DIM}Ctrl+C to stop{RESET}                                     {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}╚══════════════════════════════════════════════════════╝{RESET}
""")
        time.sleep(1.0)


# ─── Test Runner ──────────────────────────────────────────────────────────────

def run_test(cfg: dict):
    shutdown.clear()
    signal.signal(signal.SIGINT, _sig)
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, _sig)
        except (AttributeError, OSError):
            pass

    target = cfg["target"]
    port = cfg["port"]
    proto = cfg["protocol"]
    workers = cfg["workers"]
    duration = cfg["duration"]
    pkt = cfg["packet_size"]
    ramp = cfg["ramp_up"]
    method = cfg.get("http_method", "GET")
    https = cfg.get("https", False)

    try:
        ip = socket.gethostbyname(target)
    except socket.gaierror:
        print(f"\n  {RED}[!] Cannot resolve: {target}{RESET}")
        input("\n  Press Enter...")
        return

    stats = StatsCollector()
    stats.start()

    dt = threading.Thread(target=dashboard, args=(stats, proto, target, port, duration), daemon=True)
    dt.start()

    real_target = target if proto == "http" else ip
    threads = []
    for i in range(workers):
        if proto == "udp":
            f = UDPFlooder(real_target, port, pkt, stats)
        elif proto == "tcp":
            f = TCPFlooder(real_target, port, pkt, stats)
        else:
            f = HTTPFlooder(real_target, port, method, pkt, stats, https)
        t = threading.Thread(target=f.run, args=(duration, ramp, i, workers), daemon=True)
        t.start()
        threads.append(t)

    deadline = time.monotonic() + duration
    while time.monotonic() < deadline and not shutdown.is_set():
        time.sleep(0.25)
    shutdown.set()

    for t in threads:
        t.join(timeout=5)

    time.sleep(0.5)
    r = stats.report()

    report = {
        "timestamp": datetime.now().isoformat(),
        "target": target, "ip": ip, "port": port,
        "protocol": proto, "workers": workers,
        "packet_size": pkt, "duration_requested": duration,
        "results": r,
    }

    report_file = f"report_{proto}_{target}_{port}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    cls()
    print(f"""
  {BOLD}{GREEN}╔══════════════════════════════════════════════════════╗{RESET}
  {BOLD}{GREEN}║{RESET}  {BOLD}{WHITE}TEST COMPLETE{RESET}                                       {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}╠══════════════════════════════════════════════════════╣{RESET}
  {BOLD}{GREEN}║{RESET}                                                      {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Duration:        {r['duration_s']:>10.1f} s                     {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Total packets:   {r['total_packets']:>14,}                 {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Total data:      {r['total_bytes']/1_048_576:>10.2f} MB                   {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Avg throughput:  {r['avg_MBs']:>10.2f} MB/s                 {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Avg packets/s:   {r['avg_pps']:>14,.1f}                 {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Peak packets/s:  {r['peak_pps']:>14,.1f}                 {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Peak throughput: {r['peak_MBs']:>10.2f} MB/s                 {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Avg latency:     {r['avg_lat_ms']:>10.2f} ms                   {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  Errors:          {r['total_errors']:>14,} ({r['err_pct']:.1f}%)          {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}                                                      {BOLD}{GREEN}║{RESET}
  {BOLD}{GREEN}║{RESET}  {DIM}Report: {report_file}{RESET}
  {BOLD}{GREEN}╚══════════════════════════════════════════════════════╝{RESET}
""")
    input(f"  {DIM}Press Enter to return to menu...{RESET}")


# ─── Preset Profiles ─────────────────────────────────────────────────────────

PRESETS = {
    "1": {
        "name": "Light — HTTP GET",
        "protocol": "http", "http_method": "GET",
        "workers": 25, "duration": 15, "packet_size": 512, "ramp_up": 3, "https": False,
    },
    "2": {
        "name": "Medium — HTTP POST",
        "protocol": "http", "http_method": "POST",
        "workers": 100, "duration": 30, "packet_size": 4096, "ramp_up": 5, "https": False,
    },
    "3": {
        "name": "Heavy — TCP Flood",
        "protocol": "tcp", "http_method": "GET",
        "workers": 200, "duration": 60, "packet_size": 8192, "ramp_up": 5, "https": False,
    },
    "4": {
        "name": "UDP Blast",
        "protocol": "udp", "http_method": "GET",
        "workers": 300, "duration": 30, "packet_size": 1400, "ramp_up": 0, "https": False,
    },
    "5": {
        "name": "HTTPS Hammer",
        "protocol": "http", "http_method": "GET",
        "workers": 150, "duration": 30, "packet_size": 1024, "ramp_up": 3, "https": True,
    },
}


# ─── Input helpers ────────────────────────────────────────────────────────────

def ask(prompt, default="", validator=None):
    while True:
        val = input(f"  {prompt}" + (f" [{DIM}{default}{RESET}]: " if default else ": ")).strip()
        if not val and default:
            val = default
        if validator:
            try:
                return validator(val)
            except (ValueError, TypeError):
                print(f"  {RED}Invalid input.{RESET}")
        else:
            return val


def ask_int(prompt, default):
    return ask(prompt, str(default), lambda v: int(v))


def ask_float(prompt, default):
    return ask(prompt, str(default), lambda v: float(v))


def ask_choice(prompt, choices, default):
    return ask(prompt, default, lambda v: v if v.lower() in choices else (_ for _ in ()).throw(ValueError))


# ─── Interactive Menu ─────────────────────────────────────────────────────────

def menu_header():
    cls()
    print(f"""
  {BOLD}{CYAN}╔══════════════════════════════════════════════════════╗{RESET}
  {BOLD}{CYAN}║{RESET}                                                      {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}     {BOLD}{WHITE}S T R E S S   T E S T   T O O L{RESET}                {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}     {DIM}multi-protocol infrastructure tester{RESET}             {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}║{RESET}                                                      {BOLD}{CYAN}║{RESET}
  {BOLD}{CYAN}╚══════════════════════════════════════════════════════╝{RESET}
""")


def main_menu():
    while True:
        menu_header()
        print(f"  {BOLD}{WHITE}MAIN MENU{RESET}\n")
        print(f"  {CYAN}[1]{RESET} Quick Start  {DIM}— pick a preset, enter target, go{RESET}")
        print(f"  {CYAN}[2]{RESET} Custom Test   {DIM}— configure everything manually{RESET}")
        print(f"  {CYAN}[3]{RESET} View Presets  {DIM}— see available load profiles{RESET}")
        print(f"  {CYAN}[0]{RESET} Exit\n")

        choice = input(f"  {BOLD}>{RESET} ").strip()

        if choice == "1":
            quick_start()
        elif choice == "2":
            custom_test()
        elif choice == "3":
            view_presets()
        elif choice == "0":
            cls()
            print(f"\n  {DIM}done.{RESET}\n")
            sys.exit(0)


def view_presets():
    menu_header()
    print(f"  {BOLD}{WHITE}LOAD PROFILES{RESET}\n")
    for k, v in PRESETS.items():
        proto_str = v["protocol"].upper()
        if v["protocol"] == "http":
            proto_str += f" {v['http_method']}"
            if v["https"]:
                proto_str = "HTTPS " + v["http_method"]
        print(f"  {CYAN}[{k}]{RESET} {BOLD}{v['name']}{RESET}")
        print(f"      {DIM}Protocol: {proto_str}  |  Workers: {v['workers']}  |  Duration: {v['duration']}s{RESET}")
        print(f"      {DIM}Payload: {v['packet_size']}B  |  Ramp-up: {v['ramp_up']}s{RESET}\n")
    input(f"  {DIM}Press Enter to go back...{RESET}")


def quick_start():
    menu_header()
    print(f"  {BOLD}{WHITE}QUICK START{RESET}\n")
    for k, v in PRESETS.items():
        print(f"  {CYAN}[{k}]{RESET} {v['name']}")
    print()

    choice = input(f"  {BOLD}Pick a profile>{RESET} ").strip()
    if choice not in PRESETS:
        print(f"  {RED}Invalid choice.{RESET}")
        time.sleep(1)
        return

    preset = dict(PRESETS[choice])
    name = preset.pop("name")

    print(f"\n  {GREEN}Profile: {name}{RESET}\n")
    target = ask("Target (IP/hostname)")
    port = ask_int("Port", 80 if preset["protocol"] == "http" else 9000)

    if not target:
        return

    preset["target"] = target
    preset["port"] = port

    print(f"\n  {BOLD}Starting {name} → {target}:{port} in 3s...{RESET}")
    print(f"  {DIM}Ctrl+C to cancel{RESET}")
    time.sleep(3)

    if not shutdown.is_set():
        run_test(preset)


def custom_test():
    menu_header()
    print(f"  {BOLD}{WHITE}CUSTOM TEST CONFIGURATION{RESET}\n")

    target = ask("Target (IP/hostname)")
    if not target:
        return

    port = ask_int("Port", 80)

    print(f"\n  {DIM}Protocols: http, tcp, udp{RESET}")
    proto = ask_choice("Protocol", ["http", "tcp", "udp"], "http")

    method = "GET"
    https = False
    if proto == "http":
        method = ask_choice("HTTP Method (GET/POST)", ["get", "post"], "GET").upper()
        https_yn = ask_choice("Use HTTPS? (y/n)", ["y", "n"], "n")
        https = https_yn == "y"

    workers = ask_int("Workers (threads)", 50)
    duration = ask_float("Duration (seconds)", 30)
    pkt = ask_int("Payload size (bytes)", 1024)
    ramp = ask_float("Ramp-up (seconds, 0=instant)", 0)

    cfg = {
        "target": target, "port": port, "protocol": proto,
        "http_method": method, "https": https,
        "workers": workers, "duration": duration,
        "packet_size": pkt, "ramp_up": ramp,
    }

    proto_str = proto.upper()
    if proto == "http":
        proto_str = ("HTTPS" if https else "HTTP") + f" {method}"

    print(f"\n  {BOLD}{'─'*50}{RESET}")
    print(f"  Target:    {CYAN}{target}:{port}{RESET}")
    print(f"  Protocol:  {proto_str}")
    print(f"  Workers:   {workers}")
    print(f"  Duration:  {duration}s")
    print(f"  Payload:   {pkt} bytes")
    print(f"  Ramp-up:   {ramp}s")
    print(f"  {BOLD}{'─'*50}{RESET}")

    print(f"\n  {BOLD}Starting in 3s... Ctrl+C to cancel{RESET}")
    time.sleep(3)

    if not shutdown.is_set():
        run_test(cfg)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def run_test_stream(cfg: dict):
    """Run test with JSON stats streamed to stdout every second."""
    shutdown.clear()
    signal.signal(signal.SIGINT, _sig)
    if sys.platform != "win32":
        signal.signal(signal.SIGUSR1, lambda s, f: None)  # pause signal
        signal.signal(signal.SIGUSR2, lambda s, f: None)  # resume signal

    paused = threading.Event()

    if sys.platform != "win32":
        def _pause(s, f):
            paused.set()
        def _resume(s, f):
            paused.clear()
        signal.signal(signal.SIGUSR1, _pause)
        signal.signal(signal.SIGUSR2, _resume)

    target = cfg["target"]
    port = cfg["port"]
    proto = cfg["protocol"]
    workers = cfg["workers"]
    duration = cfg["duration"]
    pkt = cfg["packet_size"]
    ramp = cfg["ramp_up"]
    method = cfg.get("http_method", "GET")
    https = cfg.get("https", False)

    try:
        ip = socket.gethostbyname(target)
    except socket.gaierror:
        print(json.dumps({"error": f"Cannot resolve: {target}"}), flush=True)
        return

    stats = StatsCollector()
    stats.start()

    real_target = target if proto == "http" else ip
    threads = []
    for i in range(workers):
        if proto == "udp":
            f = UDPFlooder(real_target, port, pkt, stats)
        elif proto == "tcp":
            f = TCPFlooder(real_target, port, pkt, stats)
        else:
            f = HTTPFlooder(real_target, port, method, pkt, stats, https)
        t = threading.Thread(target=f.run, args=(duration, ramp, i, workers), daemon=True)
        t.start()
        threads.append(t)

    t0 = time.monotonic()
    while not shutdown.is_set():
        if paused.is_set():
            print(json.dumps({"status": "paused"}), flush=True)
            time.sleep(1)
            continue
        elapsed = time.monotonic() - t0
        if elapsed >= duration:
            break
        s = stats.snapshot()
        s["status"] = "running"
        s["pid"] = os.getpid()
        print(json.dumps(s), flush=True)
        time.sleep(1)

    shutdown.set()
    for t in threads:
        t.join(timeout=5)

    r = stats.report()
    r["status"] = "done"
    print(json.dumps(r), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import argparse
        parser = argparse.ArgumentParser(description="Stress test tool")
        parser.add_argument("--target", required=True)
        parser.add_argument("--port", type=int, required=True)
        parser.add_argument("--protocol", choices=["http", "tcp", "udp"], required=True)
        parser.add_argument("--workers", type=int, default=50)
        parser.add_argument("--duration", type=float, default=30)
        parser.add_argument("--packet-size", type=int, default=1024)
        parser.add_argument("--ramp-up", type=float, default=0)
        parser.add_argument("--http-method", choices=["GET", "POST"], default="GET")
        parser.add_argument("--https", action="store_true")
        parser.add_argument("--stream", action="store_true", help="Output JSON stats per second")
        args = parser.parse_args()
        cfg = {
            "target": args.target, "port": args.port, "protocol": args.protocol,
            "workers": args.workers, "duration": args.duration,
            "packet_size": args.packet_size, "ramp_up": args.ramp_up,
            "http_method": args.http_method, "https": args.https,
        }
        if args.stream:
            run_test_stream(cfg)
        else:
            run_test(cfg)
    else:
        try:
            main_menu()
        except KeyboardInterrupt:
            shutdown.set()
            cls()
            print(f"\n  {DIM}interrupted.{RESET}\n")
