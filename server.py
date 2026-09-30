"""HTTP konularını öğretmek için yalnızca yerelde çalışan eğitim sunucusu."""

from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import hashlib
import json
import math
import os
import secrets
import ssl
import subprocess
import uuid


ROOT = Path(__file__).resolve().parent
BOOKS = [
    {"id": 1, "title": "Küçük Prens", "author": "Antoine de Saint-Exupéry"},
    {"id": 2, "title": "Saatleri Ayarlama Enstitüsü", "author": "Ahmet Hamdi Tanpınar"},
]
USERS = {"student": "http101", "teacher": "teach101"}
SESSIONS = {}  # session id -> username; only in memory
TOKENS = {}    # bearer token -> session id; only in memory
STATUS_DEMOS = {
    401: "Kimlik doğrulaması gerekiyor.",
    403: "Kimliğin doğrulandı ancak bu işleme iznin yok.",
    405: "Bu adreste kullanılan yöntem desteklenmiyor.",
    409: "İstek mevcut kaynakla çakışıyor.",
    429: "İstek sınırına ulaşıldı; biraz bekle.",
    500: "Sunucu hatasını anlatan kontrollü örnek yanıt.",
}


def cors_client_origin(is_https):
    return "https://localhost:8444" if is_https else "http://localhost:8001"


class Handler(BaseHTTPRequestHandler):
    server_version = "HttpOgrenmeLaboratuvari/1.0"

    @property
    def is_https(self):
        return isinstance(self.connection, ssl.SSLSocket)

    def send_page(self, filename="index.html"):
        content = (ROOT / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status, data, headers=None, cors=False):
        body = b"" if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if data is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if not headers or "Cache-Control" not in headers:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", uuid.uuid4().hex[:12])
        if cors:
            origin = self.headers.get("Origin")
            if origin == cors_client_origin(self.is_https):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                self.close_connection = True
                raise ValueError("Gövde çok büyük.")
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON nesne biçiminde olmalı.")
            return payload
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            raise ValueError("Geçerli bir JSON nesnesi gönder.") from error

    def cookie_session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookie.get("http_lab_session")
        return morsel.value if morsel else None

    def current_session(self):
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            session_id = TOKENS.get(authorization[7:].strip())
            if session_id in SESSIONS:
                return session_id
            return None
        session_id = self.cookie_session()
        return session_id if session_id in SESSIONS else None

    def do_OPTIONS(self):
        if urlparse(self.path).path != "/api/cors-demo":
            return self.send_json(204, None, {"Allow": "GET, POST, OPTIONS"})
        origin = self.headers.get("Origin")
        if origin != cors_client_origin(self.is_https):
            return self.send_json(204, None)
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Demo-Header, Content-Type")
        self.send_header("Access-Control-Max-Age", "0")
        self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send_page()
        if parsed.path == "/cors-client":
            return self.send_page("cors-client.html")
        if parsed.path == "/api/health":
            return self.send_json(200, {"status": "ok", "message": "Sunucu çalışıyor."})
        if parsed.path == "/api/whoami":
            student = self.headers.get("X-Student")
            if not student:
                return self.send_json(400, {"error": "X-Student başlığı gönderilmedi."})
            return self.send_json(200, {"message": "Sunucu özel başlığı okudu.", "student": student})
        if parsed.path == "/api/profile":
            session_id = self.current_session()
            if not session_id:
                return self.send_json(401, {"error": "Giriş yapmalısın."}, {"WWW-Authenticate": 'Bearer realm="http-lab"'})
            return self.send_json(200, {"username": SESSIONS[session_id], "message": "Oturum doğrulandı."})
        if parsed.path == "/api/admin":
            session_id = self.current_session()
            if not session_id:
                return self.send_json(401, {"error": "Önce giriş yap."}, {"WWW-Authenticate": 'Bearer realm="http-lab"'})
            if SESSIONS[session_id] != "teacher":
                return self.send_json(403, {"error": "Giriş yaptın ancak öğretmen izni gerekiyor."})
            return self.send_json(200, {"message": "Öğretmen alanına eriştin."})
        if parsed.path == "/api/status-demo":
            try:
                status = int(parse_qs(parsed.query).get("code", ["401"])[0])
            except ValueError:
                return self.send_json(400, {"error": "code sayı olmalı."})
            if status not in STATUS_DEMOS:
                return self.send_json(400, {"error": "Desteklenen demo kodları: 401, 403, 405, 409, 429, 500."})
            extra = {
                401: {"WWW-Authenticate": 'Bearer realm="http-lab"'},
                405: {"Allow": "POST"},
                429: {"Retry-After": "5"},
            }
            return self.send_json(status, {"status": status, "meaning": STATUS_DEMOS[status]}, extra.get(status))
        if parsed.path == "/api/cache-demo":
            payload = {"message": "ETag ile koşullu GET örneği", "books": BOOKS}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
            headers = {"ETag": etag, "Cache-Control": "no-cache"}
            if self.headers.get("If-None-Match") == etag:
                return self.send_json(304, None, headers)
            return self.send_json(200, payload, headers)
        if parsed.path == "/api/cors-demo":
            return self.send_json(200, {
                "message": "CORS izinli origin isteği okuyabildi.",
                "origin": self.headers.get("Origin"),
                "demoHeader": self.headers.get("X-Demo-Header"),
            }, cors=True)
        if parsed.path == "/api/cors-denied":
            return self.send_json(200, {"message": "Sunucu yanıt verdi; CORS başlığı olmadığı için tarayıcı sayfaya sonucu göstermiyor."})
        if parsed.path == "/api/books":
            query = parse_qs(parsed.query)
            books = list(BOOKS)
            if query.get("q"):
                term = query["q"][0].casefold()
                books = [b for b in books if term in b["title"].casefold() or term in b["author"].casefold()]
            sort = query.get("sort", ["id"])[0]
            order = query.get("order", ["asc"])[0].lower()
            if sort not in ("id", "title", "author") or order not in ("asc", "desc"):
                return self.send_json(400, {"error": "sort id/title/author, order asc/desc olabilir."})
            books.sort(key=lambda book: str(book[sort]).casefold() if sort != "id" else book[sort], reverse=order == "desc")
            try:
                page = int(query.get("page", ["1"])[0])
                limit = int(query.get("limit", [str(max(1, len(books)))])[0])
                if page < 1 or limit < 1 or limit > 50:
                    raise ValueError
            except ValueError:
                return self.send_json(400, {"error": "page en az 1, limit 1-50 arasında tam sayı olmalı."})
            total = len(books)
            results = books[(page - 1) * limit:page * limit]
            return self.send_json(200, {"count": len(results), "total": total, "page": page,
                                        "limit": limit, "totalPages": math.ceil(total / limit),
                                        "sort": sort, "order": order, "books": results})
        if parsed.path.startswith("/api/books/"):
            try:
                book_id = int(parsed.path.rsplit("/", 1)[1])
            except ValueError:
                return self.send_json(400, {"error": "Kitap numarası sayı olmalı."})
            book = next((b for b in BOOKS if b["id"] == book_id), None)
            return self.send_json(200, book) if book else self.send_json(404, {"error": "Kitap bulunamadı."})
        return self.send_json(404, {"error": "Bu adres bulunamadı."})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
        except ValueError as error:
            return self.send_json(400, {"error": str(error)})
        if path == "/api/login":
            username, password = payload.get("username"), payload.get("password")
            valid_user = isinstance(username, str) and isinstance(password, str) and username in USERS
            if not valid_user or not secrets.compare_digest(USERS.get(username, "") if valid_user else "", password if isinstance(password, str) else ""):
                return self.send_json(401, {"error": "Kullanıcı adı veya parola yanlış."}, {"WWW-Authenticate": 'Bearer realm="http-lab"'})
            session_id = secrets.token_urlsafe(24)
            bearer = secrets.token_urlsafe(32)
            SESSIONS[session_id] = username
            TOKENS[bearer] = session_id
            cookie = f"http_lab_session={session_id}; Path=/; HttpOnly; SameSite=Lax" + ("; Secure" if self.is_https else "")
            return self.send_json(200, {"message": "Giriş başarılı.", "username": username, "accessToken": bearer}, {"Set-Cookie": cookie})
        if path == "/api/logout":
            session_id = self.cookie_session()
            authorization = self.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                session_id = TOKENS.get(authorization[7:].strip(), session_id)
            if session_id:
                SESSIONS.pop(session_id, None)
                for token, owner in list(TOKENS.items()):
                    if owner == session_id:
                        TOKENS.pop(token, None)
            cookie = "http_lab_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + ("; Secure" if self.is_https else "")
            return self.send_json(200, {"message": "Oturum kapatıldı."}, {"Set-Cookie": cookie})
        if path == "/api/books":
            if not payload.get("title") or not payload.get("author"):
                return self.send_json(400, {"error": "title ve author alanları gerekli."})
            book = {"id": max((b["id"] for b in BOOKS), default=0) + 1,
                    "title": payload["title"], "author": payload["author"]}
            BOOKS.append(book)
            return self.send_json(201, book)
        if path == "/api/status-demo":
            return self.send_json(200, {"message": "POST bu demo adresinde destekleniyor."})
        if path == "/api/cors-demo":
            return self.send_json(200, {"message": "CORS izinli origin POST isteği aldı."}, cors=True)
        return self.send_json(404, {"error": "Bu adres bulunamadı."})

    def do_PUT(self):
        try:
            book_id = int(urlparse(self.path).path.rsplit("/", 1)[1])
            payload = self.read_json()
        except (ValueError, IndexError) as error:
            return self.send_json(400, {"error": str(error) or "Adres geçersiz."})
        book = next((b for b in BOOKS if b["id"] == book_id), None)
        if not book:
            return self.send_json(404, {"error": "Kitap bulunamadı."})
        if not payload.get("title") or not payload.get("author"):
            return self.send_json(400, {"error": "PUT için title ve author alanlarını birlikte gönder."})
        book["title"], book["author"] = payload["title"], payload["author"]
        return self.send_json(200, book)

    def do_PATCH(self):
        try:
            book_id = int(urlparse(self.path).path.rsplit("/", 1)[1])
            payload = self.read_json()
        except (ValueError, IndexError) as error:
            return self.send_json(400, {"error": str(error) or "Adres geçersiz."})
        book = next((b for b in BOOKS if b["id"] == book_id), None)
        if not book:
            return self.send_json(404, {"error": "Kitap bulunamadı."})
        allowed = {key: payload[key] for key in ("title", "author") if payload.get(key)}
        if not allowed:
            return self.send_json(400, {"error": "Güncellemek için title veya author gönder."})
        book.update(allowed)
        return self.send_json(200, book)

    def do_DELETE(self):
        try:
            book_id = int(urlparse(self.path).path.rsplit("/", 1)[1])
        except (ValueError, IndexError):
            return self.send_json(400, {"error": "Kitap numarası geçersiz."})
        book = next((b for b in BOOKS if b["id"] == book_id), None)
        if not book:
            return self.send_json(404, {"error": "Kitap bulunamadı."})
        BOOKS.remove(book)
        return self.send_json(200, {"message": "Kitap silindi.", "deleted": book})


def create_local_certificate():
    cert_dir = ROOT / "certs"
    cert_file, key_file = cert_dir / "localhost-cert.pem", cert_dir / "localhost-key.pem"
    if cert_file.exists() and key_file.exists():
        return cert_file, key_file
    if not shutil_which("openssl"):
        raise SystemExit("OpenSSL bulunamadı. Kur veya README’deki sertifika komutunu çalıştır.")
    cert_dir.mkdir(exist_ok=True)
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "30", "-nodes",
        "-keyout", str(key_file), "-out", str(cert_file), "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ], check=True, stdout=subprocess.DEVNULL)
    os.chmod(key_file, 0o600)
    return cert_file, key_file


def shutil_which(command):
    from shutil import which
    return which(command)


def main():
    parser = argparse.ArgumentParser(description="HTTP eğitim sunucusu")
    parser.add_argument("--port", type=int, default=None, help="Port (varsayılan HTTP 8000, HTTPS 8443)")
    parser.add_argument("--https", action="store_true", help="HTTPS ve yerel sertifika ile başlat")
    args = parser.parse_args()
    port = args.port or (8443 if args.https else 8000)
    server = HTTPServer(("127.0.0.1", port), Handler)
    protocol = "HTTPS" if args.https else "HTTP"
    if args.https:
        cert_file, key_file = create_local_certificate()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"{protocol} eğitim sunucusu: {'https' if args.https else 'http'}://localhost:{port} (durdurmak için Ctrl+C)")
    server.serve_forever()


if __name__ == "__main__":
    main()
