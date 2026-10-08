"""Ticket attachment service. Training challenge; intentionally vulnerable."""
import http.server
import json
import os
import pathlib
import urllib.parse

ROOT = pathlib.Path(os.environ.get('ATTACHMENT_ROOT', '/work/runtime/attachments'))


def read_attachment(name):
    return (ROOT / name).read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body, content_type='application/octet-stream'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == '/health':
            return self.reply(200, b'ok\n', 'text/plain')
        if url.path == '/':
            return self.reply(200, b'<h1>Ticket attachments</h1><a href="/api/attachments">List attachments</a>', 'text/html')
        if url.path == '/api/attachments':
            files = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
                           if p.is_file() and not p.is_symlink())
            return self.reply(200, json.dumps({'files': files}).encode(), 'application/json')
        if url.path != '/download':
            return self.reply(404, b'not found')
        values = urllib.parse.parse_qs(url.query, keep_blank_values=True).get('name', [])
        if len(values) != 1 or not values[0]:
            return self.reply(400, b'invalid name')
        try:
            self.reply(200, read_attachment(values[0]))
        except (OSError, ValueError):
            self.reply(404, b'attachment not found')


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(
        (os.environ.get('TICKET_BIND', '127.0.0.1'),
         int(os.environ.get('TICKET_PORT', '8080'))), Handler).serve_forever()
