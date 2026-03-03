# app/simple_server.py
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
import os
import math

from urllib.parse import urlparse, parse_qs


class SimpleAppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parametrização por env: WORK_UNITS (CPU) e PROCESSING_TIME (latência)
        #Valores defaults
        default_work = int(os.getenv("WORK_UNITS", "1000000"))      # 1e6 = pesado; use 0 para "sem loop"
        default_sleep = float(os.getenv("PROCESSING_TIME", "0"))  # em segundos; ex.: 0.05

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        work_units = int(qs.get("work",[default_work])[0])
        processing_time = float(qs.get("sleep",[default_sleep])[0])

        t0 = time.perf_counter()

        for _ in range(work_units):
            _ = math.sqrt(123.456) * math.sin(123.456)
        if processing_time > 0:
            time.sleep(processing_time)
        t1 = time.perf_counter()

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

        hostname = os.getenv("HOSTNAME", "unknown_container")
        self.wfile.write(
            f"host={hostname} work={work_units} sleep={processing_time:.4f}s elapsed={t1-t0:.4f}s\n".encode()
        )

if __name__ == '__main__':
    # Dentro do container, mantenha 80; no host você mapeia pra 8080
    server_port = int(os.getenv("APP_PORT", "80"))
    httpd = ThreadingHTTPServer(('', server_port), SimpleAppHandler)
    print(f"Simple app server running on port {server_port} (threading on)")
    httpd.serve_forever()
