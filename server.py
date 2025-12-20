# server.py
from server.playerHandler import PlayerHandler

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
import time
import threading

PORT = 8989

PLAYER_HANDLER = PlayerHandler()
PLAYER_HANDLER.start()

# =========================
#   CHAT (in-memory)
# =========================
# chat message format:
# {"msg_id": int, "from": int, "text": str, "ts": float}
_CHAT_LOCK = threading.Lock()
_CHAT_MESSAGES: list[dict] = []
_CHAT_NEXT_ID = 1

# Keep at most this many messages (oldest trimmed)
CHAT_MAX_MESSAGES = 200


def _chat_add(sender_id: int, text: str) -> dict:
    global _CHAT_NEXT_ID
    msg = {
        "msg_id": _CHAT_NEXT_ID,
        "from": int(sender_id),
        "text": str(text),
        "ts": time.time(),
    }
    _CHAT_NEXT_ID += 1

    _CHAT_MESSAGES.append(msg)
    # trim old
    if len(_CHAT_MESSAGES) > CHAT_MAX_MESSAGES:
        del _CHAT_MESSAGES[: len(_CHAT_MESSAGES) - CHAT_MAX_MESSAGES]
    return msg


def _chat_list(after_id: int) -> list[dict]:
    # return messages with msg_id > after_id
    if after_id <= 0:
        return list(_CHAT_MESSAGES)
    return [m for m in _CHAT_MESSAGES if int(m.get("msg_id", 0)) > after_id]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        # parse URL + query
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._json(200, {"status": "ok"})
            return

        if path == "/register":
            pid = PLAYER_HANDLER.register()
            self._json(200, {"message": "registration successful", "id": pid})
            return

        if path == "/players":
            self._json(200, {"players": PLAYER_HANDLER.list_players()})
            return

        # -------- Chat fetch --------
        # GET /chat?after=<last_msg_id>
        if path == "/chat":
            try:
                after = int(qs.get("after", ["0"])[0])
            except Exception:
                after = 0

            with _CHAT_LOCK:
                msgs = _chat_list(after)
            self._json(200, {"messages": msgs})
            return

        self._json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            self._json(400, {"error": "invalid_json"})
            return

        # -------- Position update --------
        if path == "/players":
            missing = [k for k in ("id", "x", "y", "map") if k not in data]
            if missing:
                self._json(400, {"error": "bad_fields", "missing": missing})
                return

            try:
                pid = int(data["id"])
                x = float(data["x"])
                y = float(data["y"])
                map_name = str(data["map"])
            except (ValueError, TypeError):
                self._json(400, {"error": "bad_fields"})
                return

            ok = PLAYER_HANDLER.update(pid, x, y, map_name)
            if not ok:
                self._json(404, {"error": "player_not_found"})
                return

            self._json(200, {"success": True})
            return

        # -------- Chat send --------
        # POST /chat  body: {"id": <pid>, "text": "..."}
        if path == "/chat":
            missing = [k for k in ("id", "text") if k not in data]
            if missing:
                self._json(400, {"error": "bad_fields", "missing": missing})
                return

            try:
                pid = int(data["id"])
                text = str(data["text"])
            except (ValueError, TypeError):
                self._json(400, {"error": "bad_fields"})
                return

            # optional: ignore empty messages
            text = text.strip()
            if not text:
                self._json(200, {"success": True, "ignored": True})
                return

            # ensure player exists
            # (playerHandler stores registered players; if not found, reject)
            # NOTE: We can check by trying to update with same x/y/map? Not good.
            # We'll accept if pid is registered; list_players has keys
            try:
                players = PLAYER_HANDLER.list_players()
                if str(pid) not in players and pid not in players:
                    # Some implementations key by str(pid)
                    # We'll still accept if it exists in values
                    found = False
                    for _, p in players.items():
                        try:
                            if int(p.get("id", -1)) == pid:
                                found = True
                                break
                        except Exception:
                            pass
                    if not found:
                        self._json(404, {"error": "player_not_found"})
                        return
            except Exception:
                # if list_players fails, still allow
                pass

            with _CHAT_LOCK:
                msg = _chat_add(pid, text)

            self._json(200, {"success": True, "message": msg})
            return

        self._json(404, {"error": "not_found"})

    # Utility for JSON responses
    def _json(self, code: int, obj: object) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"[Server] Running on localhost with port {PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
