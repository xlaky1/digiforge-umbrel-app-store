#!/usr/bin/env python3
import base64
import json
import os
import re
import socket
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/app")
DATA = Path("/data")
CONFIG = DATA / "config.json"
DEFAULT = DATA / "config.default.json"

RPC_USER = "digiforge"
RPC_PASSWORD = os.environ.get("APP_SEED", "")
RPC_URL = "http://digibyted:14022/"
MC_API = "http://miningcore:4000/api"
POOL_ID = "dgb-sha256"

def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def ensure_config():
    if not CONFIG.exists():
        raw = DEFAULT.read_text(encoding="utf-8").replace("__APP_SEED__", RPC_PASSWORD)
        atomic_write(CONFIG, raw)

def load_config():
    ensure_config()
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def current_address():
    pools = load_config().get("pools") or []
    return str(pools[0].get("address", "")) if pools else ""

def valid_address_syntax(value):
    # Conservative syntax guard only. DigiByte/Miningcore perform
    # authoritative chain validation when the pool starts.
    return bool(re.fullmatch(r"[A-Za-z0-9]{20,100}", value or ""))

def write_pool(address):
    cfg = load_config()
    cfg["pools"] = [{
        "id": POOL_ID,
        "enabled": True,
        "coin": "digibyte-sha256",
        "address": address,
        "blockRefreshInterval": 500,
        "jobRebroadcastTimeout": 10,
        "clientConnectionTimeout": 600,
        "banning": {
            "enabled": True,
            "time": 600,
            "invalidPercent": 50,
            "checkThreshold": 50
        },
        "ports": {
            "3256": {
                "name": "DigiForge SHA256",
                "listenAddress": "0.0.0.0",
                "difficulty": 512,
                "varDiff": {
                    "minDiff": 256,
                    "maxDiff": 8192,
                    "targetTime": 15,
                    "retargetTime": 90,
                    "variancePercent": 30
                }
            }
        },
        "daemons": [{
            "host": "digibyted",
            "port": 14022,
            "user": RPC_USER,
            "password": RPC_PASSWORD
        }],
        "paymentProcessing": {
            "enabled": False,
            "minimumPayment": 10,
            "payoutScheme": "PPLNS",
            "payoutSchemeConfig": {"factor": 2.0}
        }
    }]
    atomic_write(CONFIG, json.dumps(cfg, indent=2) + "\n")

def rpc(method, params=None):
    auth = base64.b64encode(f"{RPC_USER}:{RPC_PASSWORD}".encode()).decode()
    payload = json.dumps({
        "jsonrpc": "1.0",
        "id": "digiforge",
        "method": method,
        "params": params or []
    }).encode()
    request = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + auth
        }
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        body = json.loads(response.read().decode())
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    return body.get("result")

def get_json(url):
    with urllib.request.urlopen(url, timeout=4) as response:
        return json.loads(response.read().decode())

def miningcore_pool():
    body = get_json(MC_API + "/pools")
    pools = body.get("pools", body) if isinstance(body, dict) else body
    if not isinstance(pools, list):
        return {}
    for pool in pools:
        if pool.get("id") == POOL_ID:
            return pool
    return pools[0] if pools else {}

def miningcore_miners():
    urls = [
        f"{MC_API}/pools/{POOL_ID}/miners?page=0&pageSize=50",
        f"{MC_API}/pools/{POOL_ID}/miners"
    ]
    last_error = None
    for url in urls:
        try:
            body = get_json(url)
            if isinstance(body, dict):
                value = body.get("miners", body.get("results", []))
                return value if isinstance(value, list) else []
            return body if isinstance(body, list) else []
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("miners endpoint unavailable")

def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False

class Handler(BaseHTTPRequestHandler):
    server_version = "DigiForge/1.0.4"

    def send_json(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, filename, content_type):
        raw = (ROOT / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            return self.send_file("index.html", "text/html; charset=utf-8")
        if path == "/icon.svg":
            return self.send_file("icon.svg", "image/svg+xml")
        if path == "/api/health":
            return self.send_json({"ok": True, "version": "1.0.4"})

        if path == "/api/status":
            result = {
                "version": "1.0.4",
                "configured": bool(current_address()),
                "address": current_address(),
                "node": {"online": False},
                "pool": {"online": False, "stratum": port_open("miningcore", 3256)},
                "miners": []
            }

            try:
                chain = rpc("getblockchaininfo")
                net = rpc("getnetworkinfo")
                mem = rpc("getmempoolinfo")
                result["node"] = {
                    "online": True,
                    "blocks": chain.get("blocks", 0),
                    "headers": chain.get("headers", 0),
                    "progress": chain.get("verificationprogress", 0),
                    "pruned": chain.get("pruned", False),
                    "disk": chain.get("size_on_disk", 0),
                    "connections": net.get("connections", 0),
                    "mempool": mem.get("size", 0)
                }
            except Exception as exc:
                result["node"]["error"] = str(exc)

            try:
                pool = miningcore_pool()
                stats = pool.get("poolStats") or {}
                network = pool.get("networkStats") or {}
                result["pool"].update({
                    "online": bool(pool),
                    "id": pool.get("id"),
                    "connectedMiners": stats.get("connectedMiners", 0),
                    "poolHashrate": stats.get("poolHashrate", 0),
                    "sharesPerSecond": stats.get("sharesPerSecond", 0),
                    "networkHashrate": network.get("networkHashrate", 0),
                    "networkDifficulty": network.get("networkDifficulty", 0),
                    "blockHeight": network.get("blockHeight", 0)
                })
                try:
                    result["miners"] = miningcore_miners()
                except Exception:
                    result["miners"] = []
            except Exception as exc:
                result["pool"]["error"] = str(exc)

            return self.send_json(result)

        return self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/setup":
            return self.send_json({"error": "Not found"}, 404)

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8192:
                return self.send_json({"error": "Invalid request"}, 400)

            body = json.loads(self.rfile.read(length).decode())
            address = str(body.get("address", "")).strip()

            if not valid_address_syntax(address):
                return self.send_json(
                    {"error": "Enter a valid-looking DigiByte address."},
                    400
                )

            write_pool(address)
            return self.send_json({
                "ok": True,
                "address": address,
                "message": "Saved. DigiForge is starting the SHA256 pool automatically."
            })
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

if __name__ == "__main__":
    ensure_config()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
