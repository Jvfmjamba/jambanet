# JambaNet — Distributed C2 Stress Testing Framework

Custom-built command-and-control infrastructure designed to simulate real-world botnet operations for offensive security research. The platform enables remote deployment and coordination of stress-testing agents across multiple Linux endpoints, featuring encrypted SSH communications, modular multi-protocol payload delivery, and a real-time operator dashboard.

Built end-to-end in Python (stdlib only, no external dependencies) with a tkinter-based GUI controller for centralized host management.

> **Disclaimer:** This tool was developed for authorized security testing and research purposes only. Only use against infrastructure you own or have explicit written permission to test.

---

## Architecture

```
┌─────────────────────┐
│   Controller (GUI)   │  ← Windows operator machine
│   controller_gui.py  │
└──────────┬──────────┘
           │ SSH (key-based)
     ┌─────┼─────┐
     ▼     ▼     ▼
  ┌─────┐┌─────┐┌─────┐
  │Node1││Node2││Node3│  ← Linux VPS endpoints
  └─────┘└─────┘└─────┘
     │     │     │
     └─────┼─────┘
           ▼
      Target Host
```

## Components

### `controller_gui.py` — C2 Operator Panel
- **Node Management:** register/remove endpoints with SSH credentials
- **Health Check:** verify connectivity, Python version, script deployment status
- **Deploy:** SCP upload of attack scripts to all registered nodes
- **Fire Attack:** configure and launch coordinated stress tests with real-time dashboard
- **Quick Fire:** one-line command interface for rapid launches
- **Multi Attack:** simultaneous multi-vector attacks with independent slot configuration
- **Shell:** execute arbitrary commands across all nodes in parallel

### `stresstest.py` — Layer 3/4 Stress Engine
Multi-protocol network stress testing with support for:
- **UDP Flood** — high-volume datagram flooding
- **TCP Flood** — connection-based flooding with payload delivery
- **HTTP/HTTPS** — application-layer request flooding
- **SYN Flood** — half-open connection exhaustion (requires root)
- **ICMP Flood** — ping-based flooding (requires root)
- **DNS/NTP Amplification** — reflection-based amplification (requires root)
- **Slowloris** — connection exhaustion via slow headers
- **GRE Flood** — encapsulated tunnel flooding (requires root)
- **VSE Query** — Valve Source Engine query flood

Features: ramp-up control, live stats dashboard, JSON streaming output, configurable packet sizes and worker counts.

### `webstress.py` — Layer 7 Web Stress Engine
Application-layer HTTP stress testing with evasion:
- **HTTP/HTTPS Flood** — keep-alive connection reuse with randomized headers
- **TLS Exhaustion** — rapid TLS handshake-only connections to drain server resources
- **Slowloris** — partial header attack maintaining 200+ concurrent connections
- **RUDY (R-U-Dead-Yet)** — slow POST body drip-feed attack
- **HTTP Pipeline** — batched pipelined requests (50-100 per connection)
- **Cache Bypass** — forced cache-miss requests with randomized parameters
- **POST Flood** — large body POST requests (64KB-1MB payloads)
- **HEAD Flood** — lightweight HEAD request flooding
- **Multi-Vector** — weighted distribution across all methods simultaneously

Evasion features: 50+ rotating user agents, randomized paths/cookies/headers, spoofed X-Forwarded-For, jitter control, per-worker rate limiting.

## Setup

### Requirements
- **Controller:** Windows 10/11 with Python 3.10+ and OpenSSH client
- **Nodes:** Linux VPS with Python 3.10+ and SSH access

### Quick Start

1. Copy `nodes.example.json` to `nodes.json` and configure your endpoints:
```bash
cp nodes.example.json nodes.json
```

2. Launch the controller:
```bash
python controller_gui.py
```

3. Add your nodes via the GUI (Nodes page)
4. Check connectivity (Check page)
5. Deploy scripts to all nodes (Deploy page)
6. Configure and launch a test (Fire Attack or Quick Fire)

### Node Configuration

```json
[
  {
    "name": "node1",
    "ip": "10.0.0.1",
    "user": "user",
    "port": 22,
    "key": "/path/to/ssh/key"
  }
]
```

### Standalone Usage

Layer 3/4:
```bash
python stresstest.py --target 10.0.0.5 --port 80 --protocol tcp --workers 200 --duration 30 --stream
```

Layer 7:
```bash
python webstress.py --target 10.0.0.5 --port 80 --method http --workers 500 --duration 30 --jitter 100 --stream
```

## Building (Optional)

Compile the controller to a standalone .exe:
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name C2Controller controller_gui.py
```

## Tech Stack

- **Language:** Python 3.10+ (stdlib only — zero external dependencies)
- **GUI:** tkinter
- **Transport:** SSH/SCP via system OpenSSH
- **Protocols:** Raw sockets, ssl module, urllib
- **Target OS:** Controller on Windows, nodes on Linux

## License

MIT
