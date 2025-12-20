# src/scenes/game_scene.py

import pygame as pg
import pytmx
import os
import random
from collections import deque

from dataclasses import dataclass
from typing import Any


from typing import override



# =========================
#      SIMPLE TEXT BUTTON
# =========================
class TextButton:
    """A lightweight text-only button (no image assets needed)."""

    def __init__(self, text: str, x: int, y: int, w: int, h: int, on_click):
        self.text = text
        self.rect = pg.Rect(x, y, w, h)
        self.on_click = on_click
        self._prev_mouse_down = False

    def update(self, dt: float) -> None:
        mouse_down = bool(pg.mouse.get_pressed(num_buttons=3)[0])
        if mouse_down and (not self._prev_mouse_down):
            if self.rect.collidepoint(pg.mouse.get_pos()):
                try:
                    self.on_click()
                except Exception:
                    pass
        self._prev_mouse_down = mouse_down

    def draw(self, screen: pg.Surface) -> None:
        hovered = self.rect.collidepoint(pg.mouse.get_pos())
        bg = (250, 240, 220) if hovered else (245, 245, 245)
        pg.draw.rect(screen, bg, self.rect, border_radius=10)
        pg.draw.rect(screen, (82, 44, 32), self.rect, 3, border_radius=10)

        font = pg.font.SysFont(None, 30, bold=True)
        label = font.render(self.text, True, (20, 20, 20))
        screen.blit(
            label,
            (
                self.rect.centerx - label.get_width() // 2,
                self.rect.centery - label.get_height() // 2,
            ),
        )

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager, scene_manager
from src.sprites import Sprite
from src.interface.components import Button
from src.scenes.setting_scene import SettingScene
from src.scenes.bag_scene import BagScene

# ✅ Evo overlay (Evolution Potion)
try:
    from src.scenes.evo_scene import EvoScene  # type: ignore
except Exception:
    EvoScene = None  # type: ignore

# ✅ Dr overlay (Call Dr popup)
try:
    from src.scenes.dr_scene import DrScene  # type: ignore
except Exception:
    DrScene = None  # type: ignore

from src.scenes.wild_scene import WildScene
from src.scenes.shop_scene import ShopScene


# =========================
#          MINIMAP
# =========================
class MiniMap:
    def __init__(self, game_manager):
        self.game_manager = game_manager

        # UI config
        self.pos = (12, 12)
        self.size = (180, 180)
        self.padding = 6

        # cache
        self._cached_map_name: str | None = None
        self._cached_full_map_surf: pg.Surface | None = None
        self._cached_map_px_size: tuple[int, int] = (1, 1)

        # NEW: cache the scaled minimap (this is the heavy part)
        self._cached_scaled_surf: pg.Surface | None = None
        self._cached_scaled_dest: pg.Rect | None = None
        self._cached_scale: float = 1.0

    def invalidate(self):
        self._cached_map_name = None
        self._cached_full_map_surf = None
        self._cached_scaled_surf = None
        self._cached_scaled_dest = None
        self._cached_scale = 1.0

    def _build_full_map_surface(self):
        """Build the full map surface only when map changes."""
        cur_map = self.game_manager.current_map
        map_name = getattr(cur_map, "path_name", None) or getattr(cur_map, "path", None) or "unknown"

        if self._cached_map_name == map_name and self._cached_full_map_surf is not None:
            return

        tmx = getattr(cur_map, "tmxdata", None)
        tile_size = GameSettings.TILE_SIZE

        if tmx is not None and hasattr(tmx, "width") and hasattr(tmx, "height"):
            map_px_w = int(tmx.width * tile_size)
            map_px_h = int(tmx.height * tile_size)
        else:
            map_px_w, map_px_h = 1024, 768

        full = pg.Surface((map_px_w, map_px_h), pg.SRCALPHA)
        cam = PositionCamera(0, 0)
        cur_map.draw(full, cam)

        self._cached_map_name = map_name
        self._cached_full_map_surf = full
        self._cached_map_px_size = (map_px_w, map_px_h)

        # map changed => scaled cache becomes invalid
        self._cached_scaled_surf = None
        self._cached_scaled_dest = None
        self._cached_scale = 1.0

    def _ensure_scaled_cache(self, screen: pg.Surface):
        """Scale the full map into minimap size only once (per map change / size change)."""
        if self._cached_scaled_surf is not None and self._cached_scaled_dest is not None:
            return

        self._build_full_map_surface()
        if self._cached_full_map_surf is None:
            return

        x, y = self.pos
        w, h = self.size

        frame = pg.Rect(x, y, w, h)
        inner = frame.inflate(-self.padding * 2, -self.padding * 2)

        map_w, map_h = self._cached_map_px_size
        if map_w <= 0 or map_h <= 0:
            return

        scale = min(inner.width / map_w, inner.height / map_h)
        scaled_w = max(1, int(map_w * scale))
        scaled_h = max(1, int(map_h * scale))

        # HEAVY OPERATION: do it once
        scaled = pg.transform.smoothscale(self._cached_full_map_surf, (scaled_w, scaled_h))

        dest = pg.Rect(0, 0, scaled_w, scaled_h)
        dest.center = inner.center

        self._cached_scaled_surf = scaled
        self._cached_scaled_dest = dest
        self._cached_scale = scale

    def draw(self, screen: pg.Surface):
        self._ensure_scaled_cache(screen)
        if self._cached_scaled_surf is None or self._cached_scaled_dest is None:
            return

        player = self.game_manager.player
        x, y = self.pos
        w, h = self.size

        # frame
        frame = pg.Rect(x, y, w, h)
        bg = pg.Surface((w, h), pg.SRCALPHA)
        bg.fill((0, 0, 0, 110))
        screen.blit(bg, (x, y))
        pg.draw.rect(screen, (255, 255, 255), frame, 2, border_radius=8)

        # draw cached scaled map (FAST)
        dest = self._cached_scaled_dest
        screen.blit(self._cached_scaled_surf, dest.topleft)

        # player dot (FAST)
        if player:
            px = float(player.position.x) + GameSettings.TILE_SIZE / 2
            py = float(player.position.y) + GameSettings.TILE_SIZE / 2

            dot_x = dest.left + int(px * self._cached_scale)
            dot_y = dest.top + int(py * self._cached_scale)

            pg.draw.circle(screen, (255, 255, 255), (dot_x, dot_y), 5)
            pg.draw.circle(screen, (220, 40, 40), (dot_x, dot_y), 3)

        # optional tiny map name
        map_name = getattr(self.game_manager.current_map, "path_name", "")
        if map_name:
            font = pg.font.SysFont(None, 18, bold=True)
            txt = font.render(map_name.replace(".tmx", ""), True, (255, 255, 255))
            screen.blit(txt, (x + 10, y + h - txt.get_height() - 6))


# =========================
#        SHOP OVERLAY
# =========================
class ShopOverlay:
    def __init__(self, bag, shop_id: str = "default"):
        self.bag = bag
        self.shop_id = shop_id

        self.open = True
        self.tab = "buy"   # "buy" / "sell"
        self.msg = ""

        # edge triggers（不靠 event loop）
        self._prev_mouse_down = False
        self._prev_esc = False

    def update(self, dt: float) -> None:
        if not self.open:
            return

        # ESC edge：關閉
        keys = pg.key.get_pressed()
        esc_now = bool(keys[pg.K_ESCAPE])
        if esc_now and (not self._prev_esc):
            self.open = False
            self._prev_esc = esc_now
            return
        self._prev_esc = esc_now

        # Mouse left click edge：交給 ShopScene
        mouse_down = bool(pg.mouse.get_pressed(num_buttons=3)[0])
        if mouse_down and (not self._prev_mouse_down):
            mouse_pos = pg.mouse.get_pos()
            new_tab, msg = ShopScene.handle_click(
                mouse_pos,
                self.bag,
                self.shop_id,
                self.tab,
            )
            self.tab = new_tab

            if msg == "__CLOSE__":
                self.open = False
            elif msg:
                self.msg = msg

        self._prev_mouse_down = mouse_down

    def draw(self, screen: pg.Surface) -> None:
        if not self.open:
            return

        veil = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        veil.fill((0, 0, 0, 120))
        screen.blit(veil, (0, 0))

        panel_rect = pg.Rect(
            80, 60,
            GameSettings.SCREEN_WIDTH - 160,
            GameSettings.SCREEN_HEIGHT - 120,
        )

        ShopScene.draw_panel(screen, panel_rect, self.bag, self.shop_id, self.tab)

        # 顯示操作訊息（Purchased / Sold / Not enough coins）
        if self.msg:
            font = pg.font.SysFont(None, 26, bold=True)
            text = font.render(self.msg, True, (255, 255, 255))
            screen.blit(text, (panel_rect.left + 20, panel_rect.bottom + 8 - text.get_height()))


# =========================
#     NAVIGATION OVERLAY
# =========================
class NavigationOverlay:
    def __init__(self, get_places_fn, on_go_fn):
        """
        get_places_fn() -> list[dict]
          dict: {"name": str, "map": str, "tx": int, "ty": int}
        on_go_fn(place_dict) -> None
        """
        self.open = True
        self._get_places_fn = get_places_fn
        self._on_go_fn = on_go_fn

        self._prev_mouse_down = False
        self._prev_esc = False

        # hitboxes（每次 draw 時重建）
        self._close_rect: pg.Rect | None = None
        self._go_rects: list[tuple[dict, pg.Rect]] = []

    def update(self, dt: float) -> None:
        if not self.open:
            return

        # ESC edge：關閉
        keys = pg.key.get_pressed()
        esc_now = bool(keys[pg.K_ESCAPE])
        if esc_now and (not self._prev_esc):
            self.open = False
            self._prev_esc = esc_now
            return
        self._prev_esc = esc_now

        # Mouse left click edge：點選 Go / X
        mouse_down = bool(pg.mouse.get_pressed(num_buttons=3)[0])
        if mouse_down and (not self._prev_mouse_down):
            pos = pg.mouse.get_pos()

            if self._close_rect and self._close_rect.collidepoint(pos):
                self.open = False
            else:
                for place, r in self._go_rects:
                    if r.collidepoint(pos):
                        self._on_go_fn(place)
                        self.open = False
                        break

        self._prev_mouse_down = mouse_down

    def draw(self, screen: pg.Surface) -> None:
        if not self.open:
            return

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        veil = pg.Surface((sw, sh), pg.SRCALPHA)
        veil.fill((0, 0, 0, 120))
        screen.blit(veil, (0, 0))

        panel = pg.Rect(0, 0, 560, 380)
        panel.center = (sw // 2, sh // 2)

        base_orange = (247, 182, 60)
        border_orange = (205, 132, 40)

        pg.draw.rect(screen, base_orange, panel, border_radius=10)
        pg.draw.rect(screen, border_orange, panel, 4, border_radius=10)

        title_font = pg.font.SysFont(None, 40, bold=True)
        small = pg.font.SysFont(None, 24)
        mini = pg.font.SysFont(None, 18)

        title = title_font.render("NAVIGATION", True, (40, 40, 40))
        screen.blit(title, (panel.left + 20, panel.top + 18))

        # close X
        close_size = 28
        self._close_rect = pg.Rect(panel.right - close_size - 14, panel.top + 14, close_size, close_size)
        pg.draw.rect(screen, (255, 245, 220), self._close_rect, border_radius=6)
        pg.draw.rect(screen, (80, 60, 20), self._close_rect, 2, border_radius=6)
        x_txt = mini.render("X", True, (40, 40, 40))
        screen.blit(x_txt, x_txt.get_rect(center=self._close_rect.center))

        # places list
        places = self._get_places_fn()
        self._go_rects = []

        list_top = panel.top + 80
        row_h = 44
        row_gap = 10
        row_x = panel.left + 20
        row_w = panel.width - 40

        if not places:
            msg = small.render("No places available.", True, (60, 40, 20))
            screen.blit(msg, (row_x, list_top + 20))
        else:
            for i, p in enumerate(places[:6]):
                r = pg.Rect(row_x, list_top + i * (row_h + row_gap), row_w, row_h)
                pg.draw.rect(screen, (255, 245, 220), r, border_radius=8)
                pg.draw.rect(screen, (80, 60, 20), r, 2, border_radius=8)

                name_txt = small.render(p["name"], True, (40, 40, 40))
                screen.blit(name_txt, (r.left + 16, r.centery - name_txt.get_height() // 2))

                # Go button
                btn = pg.Rect(r.right - 96, r.top + 7, 76, r.height - 14)
                pg.draw.rect(screen, (240, 220, 180), btn, border_radius=8)
                pg.draw.rect(screen, (80, 60, 20), btn, 2, border_radius=8)
                btxt = mini.render("Go", True, (40, 40, 40))
                screen.blit(btxt, btxt.get_rect(center=btn.center))

                self._go_rects.append((p, btn))

        hint = mini.render("Choose a place and click Go  |  ESC to close", True, (40, 40, 40))
        screen.blit(hint, (panel.left + 18, panel.bottom - 28))


# =========================
#        CHAT OVERLAY
# =========================
class ChatLog:
    """Keeps recent chat lines and draws them at bottom-left."""

    def __init__(self, max_lines: int = 30):
        self.lines: deque[tuple[str, str]] = deque(maxlen=max_lines)  # (prefix, text)

    def add(self, prefix: str, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return
        self.lines.append((str(prefix), t))

    def draw(self, screen: pg.Surface) -> None:
        if not self.lines:
            return

        font = pg.font.SysFont(None, 22)
        outline = pg.font.SysFont(None, 22, bold=True)

        margin = 10
        x = margin
        y = GameSettings.SCREEN_HEIGHT - margin

        show = list(self.lines)[-6:]
        for prefix, msg in reversed(show):
            line = f"{prefix}: {msg}"
            surf = font.render(line, True, (240, 240, 240))
            osurf = outline.render(line, True, (0, 0, 0))

            y -= surf.get_height()

            screen.blit(osurf, (x + 1, y + 1))
            screen.blit(osurf, (x - 1, y + 1))
            screen.blit(osurf, (x + 1, y - 1))
            screen.blit(osurf, (x - 1, y - 1))
            screen.blit(surf, (x, y))

            y -= 2


class ChatOverlay:
    """Press T to toggle chat input. Enter to send. Esc to close.

    Integrates with OnlineManager via duck-typed methods:
      send_chat/send_chat_message/... and get_chat_messages/get_chat_history/...

    If your OnlineManager uses different names, just add them below.
    """

    def __init__(self):
        self.open: bool = False
        self.input_text: str = ""
        self._prev_t: bool = False

        self._seen_keys: set[str] = set()

        self._blink_t: float = 0.0
        self._cursor_on: bool = True

    def _try_send_online(self, online_manager: Any, text: str) -> None:
        if not online_manager:
            return

        for fn in ("send_chat", "send_chat_message", "chat_send", "send_message", "post_chat"):
            if hasattr(online_manager, fn):
                try:
                    getattr(online_manager, fn)(text)
                    return
                except Exception:
                    pass

        for fn in ("send_packet", "emit", "send"):
            if hasattr(online_manager, fn):
                try:
                    getattr(online_manager, fn)({"type": "chat", "text": text})
                    return
                except Exception:
                    pass

    def _try_pull_online(self, online_manager: Any) -> list[dict]:
        if not online_manager:
            return []

        for fn in ("get_chat_messages", "get_chat_history", "poll_chat", "fetch_chat", "recv_chat"):
            if hasattr(online_manager, fn):
                try:
                    msgs = getattr(online_manager, fn)()
                    if isinstance(msgs, list):
                        return msgs
                except Exception:
                    return []
        return []

    def _normalize_msg(self, raw: dict) -> tuple[str, str, str] | None:
        if not isinstance(raw, dict):
            return None

        text = raw.get("text") or raw.get("msg") or raw.get("message") or ""
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                return None
        text = text.strip()
        if not text:
            return None

        pid = raw.get("id") or raw.get("pid") or raw.get("player_id") or raw.get("sender") or "?"
        prefix = "Other player"

        pid_str = str(pid)

        mid = raw.get("mid") or raw.get("msg_id") or raw.get("uuid") or raw.get("time") or raw.get("ts")
        if mid is None:
            key = f"{pid_str}:{text}"
        else:
            key = f"{pid_str}:{mid}:{text}"
        return key, prefix, text

    def toggle(self) -> None:
        self.open = not self.open
        if self.open:
            self.input_text = ""
            try:
                pg.key.start_text_input()
            except Exception:
                pass
        else:
            try:
                pg.key.stop_text_input()
            except Exception:
                pass

    def update(self, dt: float, online_manager: Any, chat_log: ChatLog) -> None:
        got_any_event = False
        
        keys = pg.key.get_pressed()
        t_now = bool(keys[pg.K_t])
        if t_now and (not self._prev_t):
            self.toggle()
        self._prev_t = t_now

                # Pull new online messages (so log updates even if chat is closed)
        my_id = getattr(online_manager, "player_id", None) if online_manager else None
        try:
            my_id_int = int(my_id) if my_id is not None else None
        except Exception:
            my_id_int = None

        for raw in self._try_pull_online(online_manager):
            # ✅ Server may echo back your own message; ignore self-echo to avoid
            # showing both "You:" and "Other player:" for the same line.
            if my_id_int is not None and isinstance(raw, dict):
                sender = raw.get("from")
                if sender is None:
                    sender = raw.get("sender") or raw.get("player_id") or raw.get("pid")
                try:
                    if sender is not None and int(sender) == my_id_int:
                        continue
                except Exception:
                    pass

            norm = self._normalize_msg(raw)
            if not norm:
                continue
            key, prefix, text = norm
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            chat_log.add(prefix, text)

        if not self.open:
            return

        self._blink_t += dt
        if self._blink_t >= 0.5:
            self._blink_t = 0.0
            self._cursor_on = not self._cursor_on

        for ev in pg.event.get([pg.KEYDOWN, pg.TEXTINPUT]):
            got_any_event = True
            if ev.type == pg.TEXTINPUT:
                if len(self.input_text) < 140:
                    self.input_text += ev.text
            elif ev.type == pg.KEYDOWN:
                if ev.key == pg.K_ESCAPE:
                    self.toggle()
                elif ev.key == pg.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                elif ev.key in (pg.K_RETURN, pg.K_KP_ENTER):
                    msg = self.input_text.strip()
                    if msg:
                        chat_log.add("You", msg)
                        self._try_send_online(online_manager, msg)
                    self.input_text = ""

        # Fallback: if another system already consumed pygame events, we can still
        # type using key polling (letters/numbers/basic punctuation).
        if not got_any_event:
            prev = getattr(self, "_prev_keys", None)
            if prev is None:
                self._prev_keys = keys
                return

            mods = pg.key.get_mods()
            shift = bool(mods & pg.KMOD_SHIFT)
            caps = bool(mods & pg.KMOD_CAPS)

            def just_pressed(k: int) -> bool:
                try:
                    return bool(keys[k]) and (not bool(prev[k]))
                except Exception:
                    return False

            def append(ch: str) -> None:
                if len(self.input_text) < 140:
                    self.input_text += ch

            # Special keys
            if just_pressed(pg.K_ESCAPE):
                self.toggle()
            if just_pressed(pg.K_BACKSPACE):
                self.input_text = self.input_text[:-1]
            if just_pressed(pg.K_RETURN) or just_pressed(pg.K_KP_ENTER):
                msg = self.input_text.strip()
                if msg:
                    chat_log.add("You", msg)
                    self._try_send_online(online_manager, msg)
                self.input_text = ""
                self._prev_keys = keys
                return

            # Space
            if just_pressed(pg.K_SPACE):
                append(" ")

            # Letters
            for k, ch in [
                (pg.K_a,"a"),(pg.K_b,"b"),(pg.K_c,"c"),(pg.K_d,"d"),(pg.K_e,"e"),(pg.K_f,"f"),
                (pg.K_g,"g"),(pg.K_h,"h"),(pg.K_i,"i"),(pg.K_j,"j"),(pg.K_k,"k"),(pg.K_l,"l"),
                (pg.K_m,"m"),(pg.K_n,"n"),(pg.K_o,"o"),(pg.K_p,"p"),(pg.K_q,"q"),(pg.K_r,"r"),
                (pg.K_s,"s"),(pg.K_t,"t"),(pg.K_u,"u"),(pg.K_v,"v"),(pg.K_w,"w"),(pg.K_x,"x"),
                (pg.K_y,"y"),(pg.K_z,"z"),
            ]:
                if just_pressed(k):
                    upper = shift ^ caps
                    append(ch.upper() if upper else ch)

            # Digits and common punctuation (US layout)
            num_map = {
                pg.K_0: ("0", ")"),
                pg.K_1: ("1", "!"),
                pg.K_2: ("2", "@"),
                pg.K_3: ("3", "#"),
                pg.K_4: ("4", "$"),
                pg.K_5: ("5", "%"),
                pg.K_6: ("6", "^"),
                pg.K_7: ("7", "&"),
                pg.K_8: ("8", "*"),
                pg.K_9: ("9", "("),
            }
            for k, (a, b) in num_map.items():
                if just_pressed(k):
                    append(b if shift else a)

            punct_map = {
                pg.K_MINUS: ("-", "_"),
                pg.K_EQUALS: ("=", "+"),
                pg.K_LEFTBRACKET: ("[", "{"),
                pg.K_RIGHTBRACKET: ("]", "}"),
                pg.K_BACKSLASH: ("\\", "|"),
                pg.K_SEMICOLON: (";", ":"),
                pg.K_QUOTE: ("'", '"'),
                pg.K_COMMA: (",", "<"),
                pg.K_PERIOD: (".", ">"),
                pg.K_SLASH: ("/", "?"),
                pg.K_BACKQUOTE: ("`", "~"),
            }
            for k, (a, b) in punct_map.items():
                if just_pressed(k):
                    append(b if shift else a)

            self._prev_keys = keys

    def draw(self, screen: pg.Surface) -> None:
        if not self.open:
            return

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        bar_h = 40
        rect = pg.Rect(10, sh - bar_h - 10, sw - 20, bar_h)

        bg = pg.Surface((rect.width, rect.height), pg.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, rect.topleft)
        pg.draw.rect(screen, (255, 255, 255), rect, 2, border_radius=8)

        font = pg.font.SysFont(None, 24)
        prompt = "> "
        txt = self.input_text + ("|" if self._cursor_on else "")
        surf = font.render(prompt + txt, True, (255, 255, 255))
        screen.blit(surf, (rect.left + 10, rect.centery - surf.get_height() // 2))



# =========================
#   ONLINE AVATAR RENDER
# =========================

@dataclass
class _RemoteAvatarState:
    x: float = 0.0
    y: float = 0.0
    dir: str = "DOWN"     # "DOWN" / "LEFT" / "RIGHT" / "UP"
    frame: int = 0        # 0~3
    anim_t: float = 0.0   # animation timer


class OnlineAvatarRenderer:
    """Render other online players using a 4x4 character sheet (ow1.png).

    This is a client-side approximation:
    - Direction is inferred from position delta.
    - If moving -> animate (frames 1~3), else -> stand (frame 0).
    """

    def __init__(self, sprite_path: str, size: tuple[int, int]):
        self.size = size

        # Match project convention: Sprite("character/ow1.png") loads from assets/images
        full_path = os.path.join("assets", "images", sprite_path)
        sheet = pg.image.load(full_path).convert_alpha()

        self.cols = 4
        self.rows = 4
        self.fw = sheet.get_width() // self.cols
        self.fh = sheet.get_height() // self.rows

        # row mapping for directions
        # If your direction looks wrong, swap these row numbers.
        self.row_for_dir = {
            "DOWN": 0,
            "LEFT": 1,
            "RIGHT": 2,
            "UP": 3,
        }

        self.frames: dict[str, list[pg.Surface]] = {k: [] for k in self.row_for_dir.keys()}
        for d, r in self.row_for_dir.items():
            for c in range(self.cols):
                rect = pg.Rect(c * self.fw, r * self.fh, self.fw, self.fh)
                img = sheet.subsurface(rect).copy()
                img = pg.transform.smoothscale(img, self.size)
                self.frames[d].append(img)

        self.states: dict[int, _RemoteAvatarState] = {}

        # animation speed (seconds per frame)
        self.frame_dt = 0.12

    def update_remote(self, pid: int, x: float, y: float, dt: float) -> None:
        st = self.states.get(pid)
        if st is None:
            self.states[pid] = _RemoteAvatarState(x=float(x), y=float(y))
            return

        dx = float(x) - st.x
        dy = float(y) - st.y
        moved = (abs(dx) + abs(dy)) > 0.01

        if moved:
            # choose the dominant axis to determine direction
            if abs(dx) >= abs(dy):
                st.dir = "RIGHT" if dx > 0 else "LEFT"
            else:
                st.dir = "DOWN" if dy > 0 else "UP"

            st.anim_t += dt
            if st.anim_t >= self.frame_dt:
                st.anim_t = 0.0
                st.frame = (st.frame + 1) % 4
                if st.frame == 0:
                    st.frame = 1  # avoid standing frame while moving
        else:
            st.anim_t = 0.0
            st.frame = 0  # standing

        st.x = float(x)
        st.y = float(y)

    def prune_not_in(self, alive_ids: set[int]) -> None:
        for pid in list(self.states.keys()):
            if pid not in alive_ids:
                self.states.pop(pid, None)

    def draw(self, screen: pg.Surface, pid: int, screen_x: float, screen_y: float) -> None:
        st = self.states.get(pid)
        if st is None:
            return
        img = self.frames.get(st.dir, self.frames["DOWN"])[st.frame]
        screen.blit(img, (int(screen_x), int(screen_y)))


# =========================
#           SCENE
# =========================
class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    _online_avatar: OnlineAvatarRenderer

    setting_button: Button
    overlay_close_button: Button
    bottom_buttons: list[Button]
    is_setting_open: bool
    call_dr_button: TextButton
    panel_rect: pg.Rect

    bag_button: Button
    is_bag_open: bool

    # shop overlay
    is_shop_open: bool
    shop_overlay: ShopOverlay | None

    def __init__(self):
        super().__init__()

        # ====== Wild encounter shuffle-bag (avoid repeats) ======
        self._encounter_bag: dict[tuple[str, int], list[int]] = {}  # key -> remaining indices
        self._last_encounter_name: dict[tuple[str, int], str | None] = {}  # key -> last name
        self._encounter_cycle_idx: dict[tuple, int] = {}
        self._rng = random.SystemRandom()  # ✅ 不受 random.seed 影響


        # Game Manager
        manager = GameManager.load("saves/game0.json")
        if manager is None:
            Logger.error("Failed to load game manager")
            exit(1)
        self.game_manager = manager

        # Online Manager
        if GameSettings.IS_ONLINE:
            self.online_manager = OnlineManager()
        else:
            self.online_manager = None

        self._online_avatar = OnlineAvatarRenderer(
            "character/ow1.png",
            (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
        )

        # ====== popup ======
        self.popup_msg: str | None = None
        self.popup_timer: float = 0.0

        # ====== overlays ======
        self.is_setting_open = False
        self.is_bag_open = False


        # bag overlay click edge trigger
        self._bag_prev_mouse_down: bool = False
        self.is_shop_open = False
        self.shop_overlay = None

        # chat
        self.chat_overlay = ChatOverlay()
        self.chat_log = ChatLog(max_lines=40)

        # navigation overlay
        self.is_nav_open: bool = False
        self.nav_overlay: NavigationOverlay | None = None

        # navigation state
        self.nav_active: bool = False
        self.nav_target_pos: Position | None = None
        self.nav_target_name: str | None = None

        self._last_map_name_for_nav: str | None = None

        # path tiles (A* result)
        self.nav_path_tiles: list[tuple[int, int]] = []   # (tx, ty)
        self.nav_blocked: set[tuple[int, int]] = set()    # blocked tiles
        self._nav_cached_map_name: str | None = None

        # multi-segment route (cross-map)
        self._nav_route_queue: list[dict] = []            # [{"map":..., "tx":..., "ty":..., "label":...}, ...]
        self._nav_dest_id: str | None = None

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        # minimap
        self.minimap = MiniMap(self.game_manager)
        self._minimap_map_name = None

        # 右上角：背包 / 設定 / 導航
        btn_size_top = 60
        margin_top = 16
        margin_right = 16
        gap_top = 10

        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            sw - margin_right - btn_size_top,
            margin_top,
            btn_size_top, btn_size_top,
            lambda: self.open_setting_overlay()
        )

        self.bag_button = Button(
            "UI/button_backpack.png", "UI/button_backpack_hover.png",
            sw - margin_right - btn_size_top * 2 - gap_top,
            margin_top,
            btn_size_top, btn_size_top,
            lambda: self.open_bag_overlay()
        )

        # 導航按鈕（先沿用你現成的 button_play）
        self.nav_button = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            sw - margin_right - btn_size_top * 3 - gap_top * 2,
            margin_top,
            btn_size_top, btn_size_top,
            lambda: self.open_nav_overlay()
        )

        # 共用面板
        wid_mid, hig_mid = sw // 2, sh // 2
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 420 // 2,
            480, 420
        )


        # Text-only button inside Setting overlay (Call Dr. -> DrScene)
        # NOTE: you must register scene name "dr" in your scene manager.
        self.call_dr_button = TextButton(
            "CALL DR.",
            self.panel_rect.left + 40,
            self.panel_rect.top + 120,
            self.panel_rect.width - 80,
            50,
            lambda: DrScene.open() if DrScene is not None else None,
        )

        # Save / Load / Menu
        btn_size = 80
        gap = 20
        start_x = self.panel_rect.left + 40
        row_y = self.panel_rect.top + 190

        save_button = Button(
            "UI/button_save.png", "UI/button_save_hover.png",
            start_x, row_y,
            btn_size, btn_size,
            lambda: self.save_game()
        )

        load_button = Button(
            "UI/button_load.png", "UI/button_load_hover.png",
            start_x + (btn_size + gap), row_y,
            btn_size, btn_size,
            lambda: self.load_game()
        )

        back_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            start_x + (btn_size + gap) * 2, row_y,
            btn_size, btn_size,
            lambda: scene_manager.change_scene("menu")
        )

        self.bottom_buttons = [save_button, load_button, back_button]

        # 面板右上角叉叉
        close_size = 40
        close_x = self.panel_rect.right - close_size - 10
        close_y = self.panel_rect.top + 10
        self.overlay_close_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            close_x, close_y,
            close_size, close_size,
            lambda: self.close_all_overlays()
        )

        # ====== Bush / wild state ======
        self._was_on_bush: bool = False

        # E edge trigger（給 ShopNPC 互動用）
        self._prev_e: bool = False

        # ✅ online sync throttle (avoid POST every frame)
        self._online_send_acc: float = 0.0
        self._online_send_interval: float = 0.1  # 10Hz



    # =========================
    # Overlay panel rect helpers
    # =========================
    def _get_setting_panel_rect(self) -> pg.Rect:
        """Setting overlay uses the existing self.panel_rect."""
        return self.panel_rect

    def _get_bag_panel_rect(self) -> pg.Rect:
        """Bag overlay uses a larger panel rect, centered on screen."""
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        r = pg.Rect(0, 0, 900, 520)
        r.center = (sw // 2, sh // 2)
        return r

    def _sync_overlay_close_button(self, panel_rect: pg.Rect) -> None:
        """Keep the X button anchored to the top-right corner of the given overlay panel."""
        close_size = 40
        padding = 10
        x = panel_rect.right - close_size - padding
        y = panel_rect.top + padding
        # Button class in this project uses x/y/w/h fields via rect; keep both updated if present.
        if hasattr(self.overlay_close_button, "rect"):
            self.overlay_close_button.rect = pg.Rect(x, y, close_size, close_size)
        # some Button implementations store x/y
        if hasattr(self.overlay_close_button, "x"):
            self.overlay_close_button.x = x
        if hasattr(self.overlay_close_button, "y"):
            self.overlay_close_button.y = y
    # =========================
    # Navigation Overlay Open
    # =========================
    def open_nav_overlay(self):
        self.is_nav_open = True
        self.is_setting_open = False
        self.is_bag_open = False
        self.is_shop_open = False
        self.shop_overlay = None

        self.nav_overlay = NavigationOverlay(
            get_places_fn=self._get_places_on_current_map,
            on_go_fn=self._start_navigation_to_place
        )

    def _get_places_on_current_map(self) -> list[dict]:
        """
        ✅ 永遠固定三個：Home / Gym / Shop NPC
        """
        return [
            {"id": "HOME", "name": "Home"},
            {"id": "GYM", "name": "Gym"},
            {"id": "SHOP_NPC", "name": "Shop NPC"},
        ]

    def _nav_route_for(self, dest_id: str, cur_map: str) -> list[dict]:
        """
        回傳跨地圖分段路線（每段就是同一張地圖上的一個 tile 目標點）
        你只要把門/出口座標填對，就可以自動跨圖接續。
        """
        ROUTE = {
            "HOME": {
                "map.tmx":  [{"map": "map.tmx",  "tx": 16, "ty": 28, "label": "Home Door"}],
                "home.tmx": [{"map": "home.tmx", "tx": 10, "ty": 18, "label": "Exit"}],
                "gym.tmx":  [
                    {"map": "gym.tmx", "tx": 12, "ty": 18, "label": "Exit"},
                    {"map": "map.tmx", "tx": 16, "ty": 28, "label": "Home Door"},
                ],
            },
            "GYM": {
                "map.tmx":  [{"map": "map.tmx", "tx": 24, "ty": 23, "label": "Gym Door"}],
                "gym.tmx":  [{"map": "gym.tmx", "tx": 12, "ty": 18, "label": "Exit"}],
                "home.tmx": [
                    {"map": "home.tmx", "tx": 10, "ty": 18, "label": "Exit"},
                    {"map": "map.tmx",  "tx": 24, "ty": 23, "label": "Gym Door"},
                ],
            },
            "SHOP_NPC": {
                "home.tmx": [{"map": "home.tmx", "tx": 14, "ty": 12, "label": "Shop NPC"}],
                "map.tmx":  [{"map": "map.tmx",  "tx": 16, "ty": 28, "label": "Home Door"}],
                "gym.tmx":  [
                    {"map": "gym.tmx", "tx": 12, "ty": 18, "label": "Exit"},
                    {"map": "map.tmx",  "tx": 16, "ty": 28, "label": "Home Door"},
                ],
            },
        }
        return ROUTE.get(dest_id, {}).get(cur_map, [])

    def _start_navigation_to_place(self, place: dict):
        dest_id = place.get("id")
        if not dest_id:
            return

        self._nav_dest_id = dest_id
        cur_map = self.game_manager.current_map.path_name
        self._nav_route_queue = self._nav_route_for(dest_id, cur_map)

        if not self._nav_route_queue:
            self.show_popup("No route from here.")
            return

        self._nav_apply_next_segment()

    def _nav_apply_next_segment(self):
        """
        套用下一段（同圖段）：算 A* 路徑並啟動 nav_path_tiles
        如果下一段是別張地圖，等換圖後再自動接續（update() 會呼叫）
        """
        if not self._nav_route_queue:
            self.nav_active = False
            self.nav_target_pos = None
            self.nav_target_name = None
            self.nav_path_tiles = []
            return

        seg = self._nav_route_queue[0]
        if seg["map"] != self.game_manager.current_map.path_name:
            # 還沒換到該張圖，先不算
            return

        player = self.game_manager.player
        if not player:
            return

        self.nav_target_name = seg.get("label", "Destination")
        self.nav_target_pos = Position(
            int(seg["tx"]) * GameSettings.TILE_SIZE,
            int(seg["ty"]) * GameSettings.TILE_SIZE
        )
        self.nav_active = True

        # build blocked + A*
        self._build_nav_blocked()
        tmx = getattr(self.game_manager.current_map, "tmxdata", None)
        if not tmx:
            self.show_popup("No tmx data.")
            self.nav_active = False
            self.nav_path_tiles = []
            return

        w, h = int(tmx.width), int(tmx.height)

        sx = int((player.position.x + GameSettings.TILE_SIZE / 2) // GameSettings.TILE_SIZE)
        sy = int((player.position.y + GameSettings.TILE_SIZE / 2) // GameSettings.TILE_SIZE)
        gx, gy = int(seg["tx"]), int(seg["ty"])

        self.nav_path_tiles = self._astar((sx, sy), (gx, gy), w, h)
        if not self.nav_path_tiles:
            self.show_popup("No path found.")
            self.nav_active = False
            self.nav_target_pos = None
            self.nav_target_name = None
            self._nav_route_queue = []
            return

        self.show_popup(f"Navigating to {self.nav_target_name}")

    # =========================
    # Blocked tiles builder
    # =========================
    def _build_nav_blocked(self) -> None:
        """
        ✅ 避開你指定的所有 layer：
        House / Decorative / PokemonBush / Collision* (CollisionTree/Water/Fall/...)
        只要該 layer 的 tile gid != 0 就算 blocked
        """
        cur_map = self.game_manager.current_map
        map_name = getattr(cur_map, "path_name", None)

        if map_name == self._nav_cached_map_name and self.nav_blocked:
            return

        self._nav_cached_map_name = map_name
        self.nav_blocked = set()

        tmx = getattr(cur_map, "tmxdata", None)
        if not tmx:
            return

        BLOCK_NAMES = {"House", "Decorative", "PokemonBush"}
        COLLISION_PREFIX = "Collision"

        blocked_layers = []
        for layer in getattr(tmx, "layers", []):
            name = getattr(layer, "name", "")
            if not isinstance(name, str):
                continue
            if (name in BLOCK_NAMES) or name.startswith(COLLISION_PREFIX):
                if hasattr(layer, "data"):
                    blocked_layers.append(layer)

        if not blocked_layers:
            return

        for y in range(int(tmx.height)):
            for x in range(int(tmx.width)):
                for layer in blocked_layers:
                    try:
                        if layer.data[y][x] != 0:
                            self.nav_blocked.add((x, y))
                            break
                    except Exception:
                        continue

    # =========================
    # A* Pathfinding (4-dir)
    # =========================
    def _astar(self, start: tuple[int, int], goal: tuple[int, int], w: int, h: int) -> list[tuple[int, int]]:
        import heapq

        def in_bounds(a: tuple[int, int]) -> bool:
            return 0 <= a[0] < w and 0 <= a[1] < h

        def passable(a: tuple[int, int]) -> bool:
            return a not in self.nav_blocked

        def neighbors(a: tuple[int, int]):
            x, y = a
            cand = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            for n in cand:
                if in_bounds(n) and passable(n):
                    yield n

        def h_score(a: tuple[int, int], b: tuple[int, int]) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        if start == goal:
            return [start]

        if start in self.nav_blocked:
            return []
        if goal in self.nav_blocked:
            # 目標點如果剛好是 blocked（例如門上有圖層），就找它附近可站的位置
            gx, gy = goal
            around = [(gx+1,gy),(gx-1,gy),(gx,gy+1),(gx,gy-1)]
            around = [p for p in around if 0 <= p[0] < w and 0 <= p[1] < h and p not in self.nav_blocked]
            if not around:
                return []
            goal = around[0]

        frontier = []
        heapq.heappush(frontier, (0, start))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost_so_far: dict[tuple[int, int], int] = {start: 0}

        while frontier:
            _, current = heapq.heappop(frontier)

            if current == goal:
                break

            for nxt in neighbors(current):
                new_cost = cost_so_far[current] + 1
                if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                    cost_so_far[nxt] = new_cost
                    priority = new_cost + h_score(nxt, goal)
                    heapq.heappush(frontier, (priority, nxt))
                    came_from[nxt] = current

        if goal not in came_from:
            return []

        # reconstruct
        path = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came_from.get(cur)
        path.reverse()
        return path

    # =========================
    # Draw navigation (turning path)
    # =========================
    def _draw_navigation(self, screen: pg.Surface, camera: PositionCamera):
        """
        ✅ 沿路排列的紅色箭頭（會隨玩家前進而推進）
        - 箭頭沿 nav_path_tiles 排列
        - 只畫「玩家前方」的 N 格
        - 玩家走一步，箭頭自然往前流動
        """
        if not self.nav_active or not self.nav_path_tiles or not self.game_manager.player:
            return

        player = self.game_manager.player
        tile = GameSettings.TILE_SIZE

        # 玩家目前 tile
        px = int((player.position.x + tile / 2) // tile)
        py = int((player.position.y + tile / 2) // tile)

        path = self.nav_path_tiles

        # -----------------------------
        # 1) 找出玩家在 path 中「最接近的位置」
        # -----------------------------
        cur_idx = 0
        best_dist = 10**9
        for i, (tx, ty) in enumerate(path):
            d = abs(tx - px) + abs(ty - py)
            if d < best_dist:
                best_dist = d
                cur_idx = i

        # 若已經到終點
        if cur_idx >= len(path) - 1:
            self.nav_path_tiles = []
            self.nav_active = False

            if self._nav_route_queue:
                self._nav_route_queue.pop(0)
                self._nav_apply_next_segment()
            else:
                self.nav_target_pos = None
                self.nav_target_name = None
                self.show_popup("Arrived!")
            return

        # -----------------------------
        # 2) 設定要顯示多少個箭頭（前方 N 格）
        # -----------------------------
        MAX_ARROWS = 6  # 可自行調整（5~8 都很自然）
        start = cur_idx
        end = min(cur_idx + MAX_ARROWS, len(path) - 1)

        # -----------------------------
        # 3) 工具：tile → world → screen
        # -----------------------------
        def tile_center_screen(tx: int, ty: int) -> tuple[int, int]:
            wx = tx * tile + tile / 2
            wy = ty * tile + tile / 2
            wp = Position(wx, wy)
            sp = camera.transform_position_as_position(wp)
            return int(sp.x), int(sp.y)

        def tri_points(center: tuple[int, int], direction: tuple[int, int], size: int = 10):
            cx, cy = center
            dx, dy = direction

            if dx > 0:   dx, dy = 1, 0
            elif dx < 0: dx, dy = -1, 0
            elif dy > 0: dx, dy = 0, 1
            else:        dx, dy = 0, -1

            if dx == 1:   # →
                return [(cx + size, cy), (cx - size, cy - size), (cx - size, cy + size)]
            if dx == -1:  # ←
                return [(cx - size, cy), (cx + size, cy - size), (cx + size, cy + size)]
            if dy == 1:   # ↓
                return [(cx, cy + size), (cx - size, cy - size), (cx + size, cy - size)]
            # ↑
            return [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]

        # -----------------------------
        # 4) 沿路畫出箭頭
        # -----------------------------
        for i in range(start, end):
            (x1, y1) = path[i]
            (x2, y2) = path[i + 1]

            dx = x2 - x1
            dy = y2 - y1

            center = tile_center_screen(x1, y1)

            tri = tri_points(center, (dx, dy), size=10)
            pg.draw.polygon(screen, (220, 40, 40), tri)
            pg.draw.polygon(screen, (0, 0, 0), tri, 2)

    # =========================
    # Popup
    # =========================
    def show_popup(self, msg: str):
        self.popup_msg = msg
        self.popup_timer = 1.0

    # =========================
    # Save/Load
    # =========================
    def save_game(self):
        self.game_manager.save("saves/backup.json")
        Logger.info("Game saved to saves/backup.json")
        self.show_popup("Saved Successful!")

    def load_game(self):
        manager = GameManager.load("saves/backup.json")
        if manager is None:
            Logger.error("Failed to load backup")
            self.show_popup("Load Failed")
            return

        self.game_manager = manager
        Logger.info("Game loaded from saves/backup.json")
        self.show_popup("Loaded!")

    # =========================
    # Overlay control
    # =========================
    def close_all_overlays(self):
        self.is_setting_open = False
        self.is_bag_open = False

        self.is_shop_open = False
        self.shop_overlay = None

        self.is_nav_open = False
        self.nav_overlay = None

    def open_setting_overlay(self):
        self.is_setting_open = True
        self.is_bag_open = False
        self.is_shop_open = False
        self.shop_overlay = None

        self.is_nav_open = False
        self.nav_overlay = None

    def open_bag_overlay(self):
        self.is_bag_open = True
        self.is_setting_open = False
        self.is_shop_open = False
        self.shop_overlay = None

        self.is_nav_open = False
        self.nav_overlay = None

    def open_shop_overlay(self, shop_id: str = "default"):
        self.is_shop_open = True
        self.is_setting_open = False
        self.is_bag_open = False
        self.shop_overlay = ShopOverlay(self.game_manager.bag, shop_id)

        self.is_nav_open = False
        self.nav_overlay = None

    # =========================
    # Scene lifecycle
    # =========================
    @override
    def enter(self) -> None:
        self.close_all_overlays()
        sound_manager.play_bgm("RBY 103 Pallet Town.ogg")
        if self.online_manager:
            self.online_manager.enter()

    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()

    # =========================
    # Update
    # =========================
    @override
    def update(self, dt: float):

        # popup timer
        if self.popup_timer > 0:
            self.popup_timer -= dt
            if self.popup_timer <= 0:
                self.popup_msg = None

        # top-right buttons
        self.setting_button.update(dt)
        self.bag_button.update(dt)
        self.nav_button.update(dt)

        # Dr overlay (highest priority)
        if DrScene is not None and hasattr(DrScene, "is_open") and DrScene.is_open():
            try:
                DrScene.update(dt)
            except Exception:
                pass
            return

        # chat (press T to toggle). While chat is open, pause gameplay input.
        if not (self.is_nav_open or self.is_shop_open or self.is_setting_open or self.is_bag_open):
            self.chat_overlay.update(dt, self.online_manager, self.chat_log)
            if self.chat_overlay.open:
                return

        # NAV overlay (high priority)
        if self.is_nav_open and self.nav_overlay and self.nav_overlay.open:
            self.nav_overlay.update(dt)
            if not self.nav_overlay.open:
                self.is_nav_open = False
                self.nav_overlay = None
            return

        # SHOP overlay (highest priority)
        if self.is_shop_open and self.shop_overlay and self.shop_overlay.open:
            self.shop_overlay.update(dt)
            if not self.shop_overlay.open:
                self.is_shop_open = False
                self.shop_overlay = None
            return

        # setting overlay
        if self.is_setting_open:
            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.is_setting_open = False

            for btn in self.bottom_buttons:
                btn.update(dt)

            self._sync_overlay_close_button(self._get_setting_panel_rect())
            self.overlay_close_button.update(dt)
            self.call_dr_button.update(dt)
            SettingScene.handle_panel_input(self.panel_rect)
            return

        # bag overlay
        if self.is_bag_open:
            keys = pg.key.get_pressed()

            # If EvoScene popup is open, ESC closes it first (so bag stays open).
            if keys[pg.K_ESCAPE]:
                if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
                    try:
                        EvoScene.close()
                    except Exception:
                        pass
                else:
                    self.is_bag_open = False

            bag_rect = self._get_bag_panel_rect()
            self._sync_overlay_close_button(bag_rect)

            # Update X button
            self.overlay_close_button.update(dt)

            # Mouse left click edge: route click to EvoScene (if open) else BagScene
            mouse_down = bool(pg.mouse.get_pressed(num_buttons=3)[0])
            if mouse_down and (not self._bag_prev_mouse_down):
                pos = pg.mouse.get_pos()
                if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
                    try:
                        EvoScene.handle_click(pos)
                    except Exception:
                        pass
                else:
                    BagScene.handle_click(pos, self.game_manager.bag)

            self._bag_prev_mouse_down = mouse_down
            return
        # original game logic
        if self.game_manager.player:
            self.game_manager.player.update(dt)
            self._update_bush_state()

        # enemies
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)

        # shop npcs interact
        player = self.game_manager.player
        if player:
            player_rect = player.get_rect()
            keys = pg.key.get_pressed()
            e_now = bool(keys[pg.K_e])
            e_pressed_once = e_now and (not self._prev_e)

            for npc in self.game_manager.current_shop_npcs:
                npc.detected = npc.can_interact(player_rect)
                npc.update(dt)

                if npc.detected and e_pressed_once:
                    self.open_shop_overlay(getattr(npc, "shop_id", "default"))
                    break

            self._prev_e = e_now

        self.game_manager.bag.update(dt)

        # ✅ Online: send my position at 10Hz (not every frame)
        if self.game_manager.player and self.online_manager:
            map_name = os.path.basename(self.game_manager.current_map.path_name).lower()
            self.online_manager.set_local_state(
                self.game_manager.player.position.x,
                self.game_manager.player.position.y,
                map_name
            )

        # ✅ Online: update remote avatars (direction + animation)
        if self.online_manager:
            alive: set[int] = set()
            for p in self.online_manager.get_list_players():
                try:
                    pid = int(p.get("id", -1))
                except Exception:
                    continue
                if pid < 0:
                    continue
                alive.add(pid)
                try:
                    self._online_avatar.update_remote(pid, float(p["x"]), float(p["y"]), dt)
                except Exception:
                    pass
            self._online_avatar.prune_not_in(alive)


        # -------- map switching (keep your original logic) --------
        before_map = getattr(self.game_manager.current_map, "path_name", None)

        self.game_manager.try_switch_map()

        after_map = getattr(self.game_manager.current_map, "path_name", None)

        # -------- minimap refresh --------
        if after_map != self._minimap_map_name:
            self._minimap_map_name = after_map
            self.minimap.invalidate()

        # -------- NAV: handle cross-map continuation --------
        # 如果換圖了：把 queue 裡「不是當前地圖」的段全部 pop 掉，直到第一段就是當前地圖
        if self._nav_route_queue and (before_map != after_map):
            # 你可能沒有剛好踩到 segment 的最後 tile 就換圖，所以直接視為完成上一段
            while self._nav_route_queue and self._nav_route_queue[0].get("map") != after_map:
                self._nav_route_queue.pop(0)

            # 清掉上一段的 path，並算新的同圖段
            self.nav_path_tiles = []
            self.nav_active = False
            self.nav_target_pos = None
            self.nav_target_name = None

            self._nav_apply_next_segment()


    # =========================
    # Draw
    # =========================
    @override
    def draw(self, screen: pg.Surface):

        # camera
        if self.game_manager.player:
            camera = self.game_manager.player.camera
        else:
            camera = PositionCamera(0, 0)

        # map
        self.game_manager.current_map.draw(screen, camera)

        # shop npcs
        for npc in self.game_manager.current_shop_npcs:
            npc.draw(screen, camera)

        # player
        if self.game_manager.player:
            self.game_manager.player.draw(screen, camera)

        # enemies
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)

        # bag ui
        self.game_manager.bag.draw(screen)

        # online players
        if self.online_manager and self.game_manager.player:
            cur_map = os.path.basename(self.game_manager.current_map.path_name).lower()
            list_online = self.online_manager.get_list_players()
            for player in list_online:
                p_map = os.path.basename(str(player.get("map", ""))).lower()
                if p_map == cur_map:
                    pos = camera.transform_position_as_position(
                        Position(player["x"], player["y"])
                    )
                    try:
                        pid = int(player.get("id", -1))
                    except Exception:
                        pid = -1
                    if pid >= 0:
                        self._online_avatar.draw(screen, pid, pos.x, pos.y)

        # chat messages (bottom-left)
        if not (self.is_setting_open or self.is_bag_open or self.is_shop_open or self.is_nav_open):
            self.chat_log.draw(screen)
            self.chat_overlay.draw(screen)

        # top-right buttons
        self.setting_button.draw(screen)
        self.bag_button.draw(screen)
        self.nav_button.draw(screen)

        # minimap
        self.minimap.draw(screen)

        # navigation path
        if self.nav_active and self.nav_path_tiles:
            self._draw_navigation(screen, camera)

        # setting/bag overlays
        if self.is_setting_open or self.is_bag_open:
            sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
            dark = pg.Surface((sw, sh), pg.SRCALPHA)
            dark.fill((0, 0, 0, 160))
            screen.blit(dark, (0, 0))

            if self.is_setting_open:
                SettingScene.draw_panel(
                    screen,
                    self.panel_rect,
                    back_button=None,
                    bottom_buttons=self.bottom_buttons
                )
                # Draw Call Dr. button on top of the setting panel
                self.call_dr_button.draw(screen)
                self._sync_overlay_close_button(self._get_setting_panel_rect())
            elif self.is_bag_open:
                # ✅ Dim background
                overlay = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
                overlay.fill((0, 0, 0, 120))
                screen.blit(overlay, (0, 0))

                # ✅ Bag panel rect
                bag_rect = pg.Rect(0, 0, 900, 520)
                bag_rect.center = (GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2)

                # ✅ Bag panel background (BagScene 不畫背景)
                base_orange = (247, 182, 60)
                border_orange = (205, 132, 40)
                bottom_shadow = (222, 137, 38)

                pg.draw.rect(screen, base_orange, bag_rect, border_radius=12)
                pg.draw.rect(screen, border_orange, bag_rect, 4, border_radius=12)

                shadow_rect = pg.Rect(bag_rect.left + 4, bag_rect.bottom - 10, bag_rect.width - 8, 6)
                pg.draw.rect(screen, bottom_shadow, shadow_rect, border_radius=6)

                # ✅ Bag contents
                BagScene.draw_panel(screen, bag_rect, self.game_manager.bag)

                # ✅ EvoScene popup (opened by Evolution Potion USE)
                if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
                    try:
                        EvoScene.draw(screen, bag_rect.center)
                    except Exception:
                        pass

                # ✅ 固定叉叉座標（相對 bag_rect）
                self.overlay_close_button.x = bag_rect.right - 60
                self.overlay_close_button.y = bag_rect.top + 24
                if hasattr(self.overlay_close_button, "rect"):
                    try:
                        self.overlay_close_button.rect.topleft = (self.overlay_close_button.x, self.overlay_close_button.y)
                    except Exception:
                        pass
                if hasattr(self.overlay_close_button, "button_rect"):
                    try:
                        self.overlay_close_button.button_rect.topleft = (self.overlay_close_button.x, self.overlay_close_button.y)
                    except Exception:
                        pass
                if hasattr(self.overlay_close_button, "hitbox"):
                    try:
                        self.overlay_close_button.hitbox.topleft = (self.overlay_close_button.x, self.overlay_close_button.y)
                    except Exception:
                        pass

                # ✅ Draw X on top
                self.overlay_close_button.draw(screen)

        # enemy confirm dialog must be topmost
        for enemy in self.game_manager.current_enemy_trainers:
            if hasattr(enemy, "show_confirm_dialog") and enemy.show_confirm_dialog:
                enemy._draw_confirm_dialog(screen)

        # shop overlay topmost
        if self.is_shop_open and self.shop_overlay and self.shop_overlay.open:
            self.shop_overlay.draw(screen)

        # nav overlay topmost
        if self.is_nav_open and self.nav_overlay and self.nav_overlay.open:
            self.nav_overlay.draw(screen)

        # popup
        if self.popup_msg:
            font = pg.font.SysFont(None, 36)
            surf = font.render(self.popup_msg, True, (0, 0, 0))

            pad_x, pad_y = 20, 10
            w = surf.get_width() + pad_x * 2
            h = surf.get_height() + pad_y * 2

            x = GameSettings.SCREEN_WIDTH // 2 - w // 2
            y = GameSettings.SCREEN_HEIGHT // 2 - h // 2

            rect = pg.Rect(x, y, w, h)
            pg.draw.rect(screen, (255, 255, 255), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)
            screen.blit(surf, (x + pad_x, y + pad_y))
        # Dr overlay (draw on top of everything)
        if DrScene is not None and hasattr(DrScene, "is_open") and DrScene.is_open():
            try:
                DrScene.draw(
                    screen,
                    (GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2),
                )
            except Exception:
                pass


    # =========================
    # Bush / Pokemon grass
    # =========================
    def _get_bush_gid_under_player(self) -> int:
        """
        回傳玩家腳下 PokemonBush layer 的 gid（0 = 不是草叢）
        """
        player = self.game_manager.player
        if player is None:
            return 0

        tmx = self.game_manager.current_map.tmxdata

        try:
            bush_layer = tmx.get_layer_by_name("PokemonBush")
        except ValueError:
            return 0

        if not isinstance(bush_layer, pytmx.TiledTileLayer):
            return 0

        px = player.position.x + GameSettings.TILE_SIZE / 2
        py = player.position.y + GameSettings.TILE_SIZE / 2
        tile_x = int(px // GameSettings.TILE_SIZE)
        tile_y = int(py // GameSettings.TILE_SIZE)

        if tile_x < 0 or tile_y < 0 or tile_x >= tmx.width or tile_y >= tmx.height:
            return 0

        gid = bush_layer.data[tile_y][tile_x]
        return int(gid or 0)

    def _update_bush_state(self) -> None:
        """
        ✅ 終極版（一次解決）：
        - 抽怪用 SystemRandom：不怕 random.seed 讓你永遠同一隻
        - 若 pool >= 2：保證不會連續同一隻（而且真的會換）
        - key 用 (map, local_id)；如果 MISS 就退回到整張圖的 default pool（也會換）
        """
        def norm_map_name(s: str) -> str:
            return os.path.basename(s).lower()

        def gid_to_local_id(tmx, gid: int) -> int:
            if gid <= 0 or tmx is None:
                return 0
            try:
                ts = tmx.get_tileset_from_gid(gid)
                first = int(getattr(ts, "firstgid", 1))
                return (gid - first) + 1  # 1-based
            except Exception:
                return 0

        bush_gid = self._get_bush_gid_under_player()
        on_bush = (bush_gid != 0)

        if on_bush and not self._was_on_bush:
            cur_map_full = getattr(self.game_manager.current_map, "path_name", "unknown")
            cur_map = norm_map_name(cur_map_full)

            tmx = getattr(self.game_manager.current_map, "tmxdata", None)
            global_gid = int(bush_gid)
            local_id = int(gid_to_local_id(tmx, global_gid))

            Logger.info(f"[BUSH DEBUG] map={cur_map!r} global_gid={global_gid} local_id={local_id}")

            # ✅ table key 也全部用小寫 map.tmx，避免大小寫造成 MISS
            ENCOUNTER_TABLE: dict[tuple[str, int], list[dict]] = {
                ("map.tmx", 1): [
                    {"name": "Pidgey",  "max_hp": 60, "sprite": "sprites/sprite1_idle.png"},
                    {"name": "Rattata", "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                ],
                ("map.tmx", 2): [
                    {"name": "Rattata", "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                    {"name": "Oddish",  "max_hp": 65, "sprite": "sprites/sprite4_idle.png"},
                ],
                ("map.tmx", 4): [
                    {"name": "Pikachu", "max_hp": 70, "sprite": "sprites/sprite3_idle.png"},
                    {"name": "Pidgey",  "max_hp": 60, "sprite": "sprites/sprite1_idle.png"},
                ],
                ("map.tmx", 7): [
                    {"name": "Oddish",  "max_hp": 65, "sprite": "sprites/sprite4_idle.png"},
                    {"name": "Rattata", "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                ],
                ("map.tmx", 53): [
                    {"name": "Caterpie", "max_hp": 50, "sprite": "sprites/sprite5_idle.png"},
                    {"name": "Weedle",   "max_hp": 50, "sprite": "sprites/sprite5_idle.png"},
                ],
                ("map.tmx", 54): [
                    {"name": "Caterpie", "max_hp": 50, "sprite": "sprites/sprite5_idle.png"},
                    {"name": "Weedle",   "max_hp": 50, "sprite": "sprites/sprite5_idle.png"},
                ],
                ("map.tmx", 55): [
                    {"name": "Caterpie", "max_hp": 50, "sprite": "sprites/sprite6_idle.png"},
                    {"name": "Weedle",   "max_hp": 50, "sprite": "sprites/sprite6_idle.png"},
                ],
                ("map.tmx", 105): [
                    {"name": "Bellsprout", "max_hp": 62, "sprite": "sprites/sprite7_idle.png"},
                    {"name": "Oddish",     "max_hp": 65, "sprite": "sprites/sprite4_idle.png"},
                ],
                ("map.tmx", 106): [
                    {"name": "Bellsprout", "max_hp": 62, "sprite": "sprites/sprite7_idle.png"},
                    {"name": "Pidgey",     "max_hp": 60, "sprite": "sprites/sprite1_idle.png"},
                ],
                ("map.tmx", 107): [
                    {"name": "Bellsprout", "max_hp": 62, "sprite": "sprites/sprite7_idle.png"},
                    {"name": "Rattata",    "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                ],
                ("map.tmx", 157): [
                    {"name": "Sandshrew", "max_hp": 68, "sprite": "sprites/sprite8_idle.png"},
                    {"name": "Diglett",   "max_hp": 52, "sprite": "sprites/sprite8_idle.png"},
                ],
                ("map.tmx", 158): [
                    {"name": "Sandshrew", "max_hp": 68, "sprite": "sprites/sprite9_idle.png"},
                    {"name": "Diglett",   "max_hp": 52, "sprite": "sprites/sprite9_idle.png"},
                ],
                ("map.tmx", 159): [
                    {"name": "Sandshrew", "max_hp": 68, "sprite": "sprites/sprite10_idle.png"},
                    {"name": "Diglett",   "max_hp": 52, "sprite": "sprites/sprite10_idle.png"},
                ],
            }

            # ✅ 先用 local_id 查；查不到就用「該地圖預設池」(一定>=2)，避免你又掉回單隻 fallback
            key = (cur_map, local_id)
            pool = ENCOUNTER_TABLE.get(key)

            default_pool_by_map: dict[str, list[dict]] = {
                "map.tmx": [
                    {"name": "Pidgey",  "max_hp": 60, "sprite": "sprites/sprite1_idle.png"},
                    {"name": "Rattata", "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                    {"name": "Oddish",  "max_hp": 65, "sprite": "sprites/sprite4_idle.png"},
                    {"name": "Pikachu", "max_hp": 70, "sprite": "sprites/sprite3_idle.png"},
                ],
                # 你之後要支援 home.tmx / gym.tmx 也可以加在這裡
            }

            if not isinstance(pool, list) or len(pool) == 0:
                Logger.warning(f"[ENCOUNTER MISS] key={key} -> use default_pool_by_map[{cur_map!r}]")
                pool = default_pool_by_map.get(cur_map, [
                    {"name": "Pidgey",  "max_hp": 60, "sprite": "sprites/sprite1_idle.png"},
                    {"name": "Rattata", "max_hp": 55, "sprite": "sprites/sprite2_idle.png"},
                ])

            names = [p.get("name") for p in pool]
            Logger.info(f"[ENCOUNTER POOL] key={key} size={len(pool)} names={names}")

            # ✅ 用 SystemRandom 抽（不吃 seed）
            picked = self._rng.choice(pool)

            # ✅ 保證不連續同一隻（pool>=2 才做）
            if len(pool) >= 2:
                last = self._last_encounter_name.get(key)
                if last is not None and picked.get("name") == last:
                    # 從「不是 last」的候選裡再抽一次（完全避免連續相同）
                    candidates = [p for p in pool if p.get("name") != last]
                    if candidates:
                        picked = self._rng.choice(candidates)

            self._last_encounter_name[key] = picked.get("name")
            Logger.info(f"[ENCOUNTER PICK] picked={picked.get('name')}")

            encounter = {"enemy": picked}
            scene_key = f"wild_{pg.time.get_ticks()}"
            scene_manager.register_scene(scene_key, WildScene(self.game_manager.bag, encounter))
            scene_manager.change_scene(scene_key)

        self._was_on_bush = on_bush
