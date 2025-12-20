# src/scenes/dr_scene.py
from __future__ import annotations

import pygame as pg


# =========================
#      DR MANAGER (offline)
# =========================
try:
    # Expected:
    #   class DrManager:
    #       def ask(self, question_key: str) -> str: ...
    from src.core.dr_manager import DrManager  # type: ignore
except Exception:
    DrManager = None  # type: ignore


class _FallbackDrManager:
    """doctor's replies (so UI works even if src/core/dr_manager.py is missing)."""

    def ask(self, question_key: str) -> str:
        key = (question_key or "").strip().upper()

        if key == "ATTR":
            return (
                "[Element Advantage]\n"
                "There are three main elements:\n\n"
                "Water beats Fire\n"
                "Fire beats Grass\n"
                "Grass beats Water\n\n"
                "Using an advantaged element deals higher damage."
            )

        if key == "MONEY":
            return (
                "You can earn coins by:\n\n"
                "Selling your Pokemon to the shop NPC\n\n"
                "Coins can be used in the shop to buy items."
            )

        if key == "CATCH":
            return (
                "[How to Catch a Pokemon]\n"
                "1) Enter grass or sand areas to trigger a wild encounter\n"
                "2) Use items to strengthen your Pokemon\n"
                "3) Use a Pokeball to capture the Pokemon\n\n"
                "Be careful of element advantages and disadvantages."
            )

        return "Please choose one of the options below."


# =========================
#           SCENE
# =========================
class DrScene:
    """
    Offline Dr overlay (POPUP, not scene switch)

    Use:
        DrScene.open()
        DrScene.update(dt)
        DrScene.draw(screen, center)
    """

    _open: bool = False
    _dr = None

    _messages: list[tuple[str, str]] = []
    _scroll_px: int = 0
    _max_scroll_px: int = 0

    _panel: pg.Rect | None = None
    _chat_rect: pg.Rect | None = None
    _close_rect: pg.Rect | None = None

    _btn_attr: pg.Rect | None = None
    _btn_money: pg.Rect | None = None
    _btn_catch: pg.Rect | None = None

    @staticmethod
    def is_open() -> bool:
        return DrScene._open

    @staticmethod
    def open() -> None:
        DrScene._open = True
        DrScene._dr = DrManager() if DrManager is not None else _FallbackDrManager()

        if not DrScene._messages:
            DrScene._messages = [
                ("dr", "Hello. I am Dr.\nChoose one question below to learn about the game.")
            ]
        DrScene._scroll_px = 0
        DrScene._max_scroll_px = 0

    @staticmethod
    def close() -> None:
        DrScene._open = False

    # -------------------------
    # wrapping & scrolling
    # -------------------------
    @staticmethod
    def _wrap_lines(font: pg.font.Font, text: str, max_w: int) -> list[str]:
        """Word wrap (English) + keeps manual line breaks."""
        if not text:
            return [""]

        if "\n" in text:
            out: list[str] = []
            for part in text.split("\n"):
                out.extend(DrScene._wrap_lines(font, part, max_w))
            return out

        if " " not in text:
            # char wrap fallback
            lines: list[str] = []
            cur = ""
            for ch in text:
                cand = cur + ch
                if font.size(cand)[0] <= max_w:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    cur = ch
            if cur:
                lines.append(cur)
            return lines

        words = text.split(" ")
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip()
            if font.size(cand)[0] <= max_w:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                # If a single word too long, break it
                if font.size(w)[0] <= max_w:
                    cur = w
                else:
                    piece = ""
                    for ch in w:
                        cand2 = piece + ch
                        if font.size(cand2)[0] <= max_w:
                            piece = cand2
                        else:
                            if piece:
                                lines.append(piece)
                            piece = ch
                    cur = piece
        if cur:
            lines.append(cur)
        return lines

    @staticmethod
    def _recalc_scroll_limits(font: pg.font.Font, chat_rect: pg.Rect) -> None:
        # We compute message height based on bubble layout
        y = 0
        BUBBLE_MAX_W = int(chat_rect.w * 0.72)
        PAD_X = 10
        PAD_Y = 8
        LINE_GAP = 5
        GAP_Y = 10

        for role, msg in DrScene._messages:
            prefix = "Dr: " if role == "dr" else "You: "
            max_text_w = max(50, BUBBLE_MAX_W - PAD_X * 2)
            lines = DrScene._wrap_lines(font, prefix + msg, max_text_w)

            text_h = len(lines) * font.get_height() + max(0, (len(lines) - 1) * LINE_GAP)
            bubble_h = text_h + PAD_Y * 2

            y += bubble_h + GAP_Y

        DrScene._max_scroll_px = max(0, y - chat_rect.h + 12)
        DrScene._scroll_px = max(0, min(DrScene._scroll_px, DrScene._max_scroll_px))

    @staticmethod
    def _scroll_to_bottom(font: pg.font.Font, chat_rect: pg.Rect) -> None:
        DrScene._recalc_scroll_limits(font, chat_rect)
        DrScene._scroll_px = DrScene._max_scroll_px

    @staticmethod
    def _ask(question_key: str, question_label: str, font: pg.font.Font, chat_rect: pg.Rect) -> None:
        DrScene._messages.append(("you", question_label))
        try:
            reply = DrScene._dr.ask(question_key)  # type: ignore[attr-defined]
        except Exception:
            reply = "Sorry. I cannot answer right now."
        DrScene._messages.append(("dr", str(reply)))
        DrScene._scroll_to_bottom(font, chat_rect)

    # -------------------------
    # input
    # -------------------------
    @staticmethod
    def scroll(dy: int) -> None:
        if not DrScene._open:
            return
        DrScene._scroll_px = max(0, min(DrScene._scroll_px + dy, DrScene._max_scroll_px))

    @staticmethod
    def update(dt: float) -> None:
        if not DrScene._open:
            return
        _ = dt  # no-op

    @staticmethod
    def draw(screen: pg.Surface, center: tuple[int, int]) -> None:
        if not DrScene._open:
            return

        # =========================
        # Theme (Shop-like Orange UI)
        # =========================
        ORANGE_BG = (245, 170, 65)
        ORANGE_DARK = (150, 90, 30)
        PANEL_LIGHT = (255, 245, 225)
        CARD_LIGHT = (255, 252, 242)
        TEXT_DARK = (35, 30, 20)

        DR_BUBBLE = (255, 252, 242)   # left
        YOU_BUBBLE = (255, 245, 225)  # right

        sw, sh = screen.get_size()

        pop = pg.Rect(0, 0, 900, 560)
        pop.center = center

        DrScene._panel = pop

        header_h = 64
        footer_h = 112
        DrScene._chat_rect = pg.Rect(
            pop.x + 18,
            pop.y + header_h + 12,
            pop.w - 36,
            pop.h - header_h - footer_h - 22,
        )

        # bottom buttons layout
        btn_y = pop.bottom - footer_h + 18
        btn_h = 64
        gap = 14
        total_w = pop.w - 36
        btn_w = (total_w - gap * 2) // 3
        x0 = pop.x + 18

        DrScene._btn_attr = pg.Rect(x0, btn_y, btn_w, btn_h)
        DrScene._btn_money = pg.Rect(x0 + btn_w + gap, btn_y, btn_w, btn_h)
        DrScene._btn_catch = pg.Rect(x0 + (btn_w + gap) * 2, btn_y, btn_w, btn_h)

        DrScene._close_rect = pg.Rect(pop.right - 56, pop.y + 14, 40, 36)

        # Fonts
        title_font = pg.font.SysFont(None, 40, bold=True)
        body_font = pg.font.SysFont(None, 24)
        mini_font = pg.font.SysFont(None, 18)

        # =========================
        # Draw panel
        # =========================
        pg.draw.rect(screen, ORANGE_BG, pop, border_radius=10)
        pg.draw.rect(screen, ORANGE_DARK, pop, 3, border_radius=10)

        header = pg.Rect(pop.x + 8, pop.y + 8, pop.w - 16, header_h - 10)
        pg.draw.rect(screen, (250, 190, 90), header, border_radius=8)
        pg.draw.rect(screen, ORANGE_DARK, header, 2, border_radius=8)

        screen.blit(title_font.render("Dr Help (Offline Q&A)", True, TEXT_DARK), (pop.x + 18, pop.y + 18))

        # Close button "X"
        pg.draw.rect(screen, PANEL_LIGHT, DrScene._close_rect, border_radius=8)
        pg.draw.rect(screen, ORANGE_DARK, DrScene._close_rect, 2, border_radius=8)
        x_s = title_font.render("X", True, TEXT_DARK)
        screen.blit(x_s, x_s.get_rect(center=DrScene._close_rect.center))

        # Chat area
        pg.draw.rect(screen, CARD_LIGHT, DrScene._chat_rect, border_radius=10)
        pg.draw.rect(screen, ORANGE_DARK, DrScene._chat_rect, 2, border_radius=10)

        # Scroll limits
        DrScene._recalc_scroll_limits(body_font, DrScene._chat_rect)

        # =========================
        # Draw messages as bubbles (Dr left, You right)
        # =========================
        old_clip = screen.get_clip()
        screen.set_clip(DrScene._chat_rect)

        x_left = DrScene._chat_rect.x + 12
        x_right = DrScene._chat_rect.right - 12
        y = DrScene._chat_rect.y + 12 - DrScene._scroll_px

        PAD_X = 10
        PAD_Y = 8
        LINE_GAP = 5
        GAP_Y = 10

        BUBBLE_MAX_W = int(DrScene._chat_rect.w * 0.72)
        max_text_w = max(50, BUBBLE_MAX_W - PAD_X * 2)

        for role, msg in DrScene._messages:
            is_you = (role != "dr")
            prefix = "Dr: " if role == "dr" else "You: "

            lines = DrScene._wrap_lines(body_font, prefix + msg, max_text_w)

            # measure bubble width
            text_w = 0
            for ln in lines:
                text_w = max(text_w, body_font.size(ln)[0])
            text_h = len(lines) * body_font.get_height() + max(0, (len(lines) - 1) * LINE_GAP)

            bubble_w = min(BUBBLE_MAX_W, text_w + PAD_X * 2)
            bubble_h = text_h + PAD_Y * 2

            if is_you:
                bx = x_right - bubble_w
                fill = YOU_BUBBLE
            else:
                bx = x_left
                fill = DR_BUBBLE

            bubble_rect = pg.Rect(bx, y, bubble_w, bubble_h)

            pg.draw.rect(screen, fill, bubble_rect, border_radius=10)
            pg.draw.rect(screen, ORANGE_DARK, bubble_rect, 2, border_radius=10)

            tx = bubble_rect.x + PAD_X
            ty = bubble_rect.y + PAD_Y
            for ln in lines:
                surf = body_font.render(ln, True, TEXT_DARK)
                screen.blit(surf, (tx, ty))
                ty += body_font.get_height() + LINE_GAP

            y += bubble_h + GAP_Y

        screen.set_clip(old_clip)

        # =========================
        # Buttons
        # =========================
        def draw_btn(rect: pg.Rect, top: str, bottom: str) -> None:
            pg.draw.rect(screen, PANEL_LIGHT, rect, border_radius=10)
            pg.draw.rect(screen, ORANGE_DARK, rect, 2, border_radius=10)

            inner = pg.Rect(rect.x + 6, rect.y + 6, rect.w - 12, rect.h - 12)
            pg.draw.rect(screen, CARD_LIGHT, inner, border_radius=8)

            t1 = body_font.render(top, True, TEXT_DARK)
            t2 = mini_font.render(bottom, True, TEXT_DARK)
            screen.blit(t1, t1.get_rect(center=(rect.centerx, rect.centery - 8)))
            screen.blit(t2, t2.get_rect(center=(rect.centerx, rect.centery + 18)))

        draw_btn(DrScene._btn_attr, "1) Element Advantage", "Water > Fire > Grass > Water")
        draw_btn(DrScene._btn_money, "2) Earn Money", "Win trainer / wild battles")
        draw_btn(DrScene._btn_catch, "3) Catch Pokemon", "Lower HP, then use Pokeball")

        hint = mini_font.render(
            "Click a button or press 1/2/3  |  Mouse Wheel: Scroll  |  ESC: Close",
            True,
            TEXT_DARK,
        )
        screen.blit(hint, (pop.x + 18, pop.bottom - 20))

        # =========================
        # Events (need rects ready)
        # =========================
        for ev in pg.event.get([pg.KEYDOWN, pg.MOUSEBUTTONDOWN, pg.MOUSEWHEEL]):
            if ev.type == pg.KEYDOWN:
                if ev.key == pg.K_ESCAPE:
                    DrScene.close()
                    continue

                if ev.key in (pg.K_1, pg.K_KP1):
                    DrScene._ask("ATTR", "Element advantage?", body_font, DrScene._chat_rect)
                elif ev.key in (pg.K_2, pg.K_KP2):
                    DrScene._ask("MONEY", "How do I earn money?", body_font, DrScene._chat_rect)
                elif ev.key in (pg.K_3, pg.K_KP3):
                    DrScene._ask("CATCH", "How do I catch Pokemon?", body_font, DrScene._chat_rect)

            elif ev.type == pg.MOUSEWHEEL:
                DrScene.scroll(int(-ev.y * 40))

            elif ev.type == pg.MOUSEBUTTONDOWN and ev.button == 1:
                pos = ev.pos

                if DrScene._close_rect and DrScene._close_rect.collidepoint(pos):
                    DrScene.close()
                    continue

                if DrScene._btn_attr and DrScene._btn_attr.collidepoint(pos):
                    DrScene._ask("ATTR", "Element advantage?", body_font, DrScene._chat_rect)
                elif DrScene._btn_money and DrScene._btn_money.collidepoint(pos):
                    DrScene._ask("MONEY", "How do I earn money?", body_font, DrScene._chat_rect)
                elif DrScene._btn_catch and DrScene._btn_catch.collidepoint(pos):
                    DrScene._ask("CATCH", "How do I catch Pokemon?", body_font, DrScene._chat_rect)
