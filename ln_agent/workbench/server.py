"""Zero-dependency localhost-only dashboard with genuine SSE event streaming.

Not a public service: no authentication, no upload, no third-party calls. Only
packaged fabricated scenarios can be executed. Binds to 127.0.0.1 exclusively.
"""
from __future__ import annotations
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .runner import WorkbenchRunner

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 4096

class WorkbenchHTTP(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, addr, runner):
        super().__init__(addr, Handler)
        self.runner = runner

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LNWorkbench/0.9"

    def log_message(self, fmt, *args):
        # avoid logging URLs with query parameters or raw request data
        return

    def send(self, code, payload, *, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Content-Security-Policy","default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/","/index.html"):
            return self._static("index.html")
        if path in ("/app.js","/style.css"):
            return self._static(path[1:])
        if path == "/api/capabilities":
            return self.send(200,self.server.runner.capabilities())
        if path == "/api/runs":
            with self.server.runner.lock:
                jobs = list(self.server.runner.runs.values())
            return self.send(200,{"runs":[r.snapshot() for r in jobs]})
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[:2] == ["api","runs"]:
            try: run = self.server.runner.get(parts[2])
            except KeyError: return self.send(404,{"error":"unknown run"})
            if len(parts) == 3:
                return self.send(200,run.snapshot())
            if len(parts)==4 and parts[3]=="report":
                with run.cond:
                    report=run.report
                if report is None:return self.send(409,{"error":"run report is not yet ready"})
                return self.send(200,report)
            if len(parts)==4 and parts[3]=="events":
                query=parse_qs(urlsplit(self.path).query)
                try: after=max(0,int((query.get("after") or ["0"])[0]))
                except (TypeError,ValueError): after=0
                return self._stream(run,after)
        self.send(404,{"error":"not found"})

    def _static(self,name):
        if name not in ("index.html","app.js","style.css"):
            return self.send(404,{"error":"not found"})
        data=(STATIC / name).read_bytes()
        self.send(200,data,ctype=mimetypes.guess_type(name)[0] or "application/octet-stream")

    def do_POST(self):
        if urlsplit(self.path).path != "/api/runs":
            return self.send(404,{"error":"not found"})
        # Cross-origin sites must not be allowed to drive localhost requests.
        origin=self.headers.get("Origin","")
        if origin not in ("", "http://127.0.0.1:%s" % self.server.server_port,
                          "http://localhost:%s" % self.server.server_port):
            return self.send(403,{"error":"origin forbidden"})
        if self.headers.get("Content-Type","").split(";")[0].strip().lower() != "application/json":
            return self.send(415,{"error":"application/json required"})
        try:
            size=int(self.headers.get("Content-Length","-1"))
            if size < 1 or size>MAX_BODY: raise ValueError("request too large or empty")
            raw=json.loads(self.rfile.read(size))
            if not isinstance(raw,dict): raise ValueError("JSON object required")
            run=self.server.runner.start(raw.get("case_key","multi"),raw.get("workers",4))
        except (ValueError,TypeError) as e:
            return self.send(400,{"error":str(e)[:150]})
        except RuntimeError as e:
            return self.send(429,{"error":str(e)[:150]})
        return self.send(201,{"run_id":run.run_id,"status":run.status})

    def _stream(self,run,after):
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream; charset=utf-8")
        self.send_header("Cache-Control","no-cache, no-transform")
        self.send_header("Connection","close")
        self.send_header("X-Accel-Buffering","no")
        self.end_headers()
        index=after
        self.close_connection=True
        try:
            while True:
                with run.cond:
                    if len(run.events) <= index and run.status=="running":
                        run.cond.wait(timeout=5.0)
                    new_events=run.events[index:]
                    done=run.status != "running"
                if new_events:
                    for event in new_events:
                        line=(f"id: {event['seq']}\nevent: trace\ndata: "+
                              json.dumps(event,ensure_ascii=False)+"\n\n")
                        self.wfile.write(line.encode("utf-8"))
                    index=new_events[-1]["seq"]
                    self.wfile.flush()
                else:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                if done:
                    self.wfile.write(("event: finished\ndata: "+
                                      json.dumps({"status":run.status})+"\n\n").encode("utf-8"))
                    self.wfile.flush()
                    break
        except (BrokenPipeError,ConnectionResetError,OSError):
            pass

def serve(*,port:int=8765):
    if port < 1024 or port > 65535:
        raise ValueError("port must be between 1024 and 65535")
    # Explicitly no 0.0.0.0 mode for a non-authenticated local prototype.
    server=WorkbenchHTTP(("127.0.0.1",port),WorkbenchRunner())
    print(f"LN Local Workbench — http://127.0.0.1:{server.server_port}")
    print("Synthetic, offline and read-only. Ctrl+C to stop.")
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()
