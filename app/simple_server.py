# app/simple_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import os
import math

class SimpleAppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Simular algum trabalho
        #processing_time = float(os.getenv("PROCESSING_TIME", "0.1")) # Inicaimos com Padrão 0.01s
        #time.sleep(processing_time)
        #print(f"Processing time: {processing_time}s")
        for _ in range(int(1e6)):  # Adjust to increase/decrease workload  -- 1e6 foi um bom resultado que escalonou para 2 instancias. 
            _ = math.sqrt(123.456) * math.sin(123.456)

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        # Adicionar o nome do host (container ID) na resposta para fácil identificação
        hostname = os.getenv("HOSTNAME", "unknown_container") # HOSTNAME é injetado pelo Docker
        message = f"Hello from {hostname}! Processed in {processing_time:.4f}s"
        self.wfile.write(message.encode())

if __name__ == '__main__':
    server_port = int(os.getenv("APP_PORT", "80")) # O container sempre escuta na porta 80 internamente
    server_address = ('', server_port)
    httpd = HTTPServer(server_address, SimpleAppHandler)
    print(f"Simple app server running on port {server_port} inside the container...")
    httpd.serve_forever()
