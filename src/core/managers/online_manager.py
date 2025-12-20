# src/core/managers/online_manager.py
from __future__ import annotations

import threading
import time
from typing import Optional, Any

import requests

from src.utils import Logger, GameSettings

# 10Hz 足夠，不要太高頻
SEND_INTERVAL = 0.10
FETCH_INTERVAL = 0.10
CHAT_FETCH_INTERVAL = 0.10

# timeout 短，避免卡住
REQ_TIMEOUT = 0.20


class OnlineManager:
    """
    主迴圈只呼叫 set_local_state()（不打網路）
    背景 thread 會固定頻率 POST 自己 / GET 其他玩家
    + GET /chat 拉聊天
    """

    def __init__(self):
        self.base: str = GameSettings.ONLINE_SERVER_URL  # e.g. http://localhost:8989
        self.player_id: int = -1

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._players: list[dict[str, Any]] = []  # other players
        self._my_state = {"x": 0.0, "y": 0.0, "map": ""}

        # chat inbox (received from server)
        self._chat_inbox: list[dict[str, Any]] = []
        self._chat_last_id: int = 0

        self._next_send_t = 0.0
        self._next_fetch_t = 0.0
        self._next_chat_fetch_t = 0.0

        self._sess = requests.Session()

        Logger.info("OnlineManager initialized")

    # ---------------------------
    # lifecycle
    # ---------------------------
    def enter(self) -> None:
        if self.player_id == -1:
            self.register()
        self.start()

    def exit(self) -> None:
        self.stop()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="OnlineManagerThread", daemon=True
        )
        self._thread.start()
        Logger.info("OnlineManager thread started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        Logger.info("OnlineManager thread stopped")

    # ---------------------------
    # API used by GameScene (FAST)
    # ---------------------------
    def set_local_state(self, x: float, y: float, map_name: str) -> None:
        with self._lock:
            self._my_state["x"] = float(x)
            self._my_state["y"] = float(y)
            self._my_state["map"] = str(map_name)

    def get_list_players(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._players)

    # -------- Chat API for GameScene --------
    def send_chat(self, text: str) -> None:
        """
        Send chat to server. GameScene 可以直接呼叫這個。
        """
        pid = self.player_id
        if pid == -1:
            return

        msg = str(text).strip()
        if not msg:
            return

        try:
            url = f"{self.base}/chat"
            self._sess.post(url, json={"id": pid, "text": msg}, timeout=REQ_TIMEOUT)
        except Exception:
            pass

    def get_chat_messages(self) -> list[dict[str, Any]]:
        """
        Drain received chat messages. GameScene 每幀可以拉一次。
        return format: [{"msg_id":int,"from":int,"text":str,"ts":float}, ...]
        """
        with self._lock:
            msgs = list(self._chat_inbox)
            self._chat_inbox.clear()
            return msgs

    # ---------------------------
    # network
    # ---------------------------
    def register(self) -> None:
        try:
            url = f"{self.base}/register"
            resp = self._sess.get(url, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            self.player_id = int(data.get("id", -1))
            Logger.info(f"OnlineManager registered id={self.player_id}")
        except Exception as e:
            Logger.warning(f"OnlineManager register error: {e}")

    def _send_me(self) -> None:
        pid = self.player_id
        if pid == -1:
            return

        with self._lock:
            body = {
                "id": pid,
                "x": self._my_state["x"],
                "y": self._my_state["y"],
                "map": self._my_state["map"],
            }

        try:
            url = f"{self.base}/players"
            self._sess.post(url, json=body, timeout=REQ_TIMEOUT)
        except Exception:
            pass

    def _fetch_players(self) -> None:
        try:
            url = f"{self.base}/players"
            resp = self._sess.get(url, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            all_players = resp.json().get("players", {})

            pid = self.player_id
            filtered: list[dict[str, Any]] = []
            for key, p in all_players.items():
                try:
                    if int(key) == pid:
                        continue
                except Exception:
                    if int(p.get("id", -999)) == pid:
                        continue
                filtered.append(p)

            with self._lock:
                self._players = filtered
        except Exception:
            pass

    def _fetch_chat(self) -> None:
        """
        GET /chat?after=<last_id> to receive new chat messages.
        """
        if self.player_id == -1:
            return
        try:
            with self._lock:
                after = int(self._chat_last_id)

            url = f"{self.base}/chat?after={after}"
            resp = self._sess.get(url, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            msgs = resp.json().get("messages", [])
            if not msgs:
                return

            # update last_id and push inbox
            new_last = after
            cleaned: list[dict[str, Any]] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                mid = int(m.get("msg_id", 0))
                if mid > new_last:
                    new_last = mid
                cleaned.append(m)

            if not cleaned:
                return

            with self._lock:
                self._chat_last_id = new_last
                self._chat_inbox.extend(cleaned)

        except Exception:
            pass

    # ---------------------------
    # thread loop
    # ---------------------------
    def _loop(self) -> None:
        now = time.monotonic()
        self._next_send_t = now
        self._next_fetch_t = now
        self._next_chat_fetch_t = now

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now >= self._next_send_t:
                self._send_me()
                self._next_send_t = now + SEND_INTERVAL

            if now >= self._next_fetch_t:
                self._fetch_players()
                self._next_fetch_t = now + FETCH_INTERVAL

            if now >= self._next_chat_fetch_t:
                self._fetch_chat()
                self._next_chat_fetch_t = now + CHAT_FETCH_INTERVAL

            time.sleep(0.005)
