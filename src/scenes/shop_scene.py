# src/scenes/shop_scene.py

from __future__ import annotations

import os
import pygame as pg
from src.scenes.scene import Scene
from src.scenes.bag_scene import BagScene


class ShopScene(Scene):
    """
    Shop overlay renderer / click handler (used as overlay on top of GameScene)
    - Buy: shows items you can buy
    - Sell: shows monsters you own (bag._monsters_data)
    - Coins sync with bag._items_data ("Coins")
    - Toast messages shown bottom-center
    - Selling monster requires confirmation dialog
    """

    _icon_cache: dict[tuple[str, tuple[int, int]], pg.Surface] = {}

    # Click hitboxes (rebuilt every draw_panel)
    _tab_buy_rect: pg.Rect | None = None
    _tab_sell_rect: pg.Rect | None = None
    _close_rect: pg.Rect | None = None
    _row_btn_rects: list[tuple[str, str, pg.Rect]] = []  # (action, key, rect)

    # ---- toast ----
    _toast_msg: str = ""
    _toast_until_ms: int = 0

    # ---- confirm dialog (sell monster) ----
    _confirm_open: bool = False
    _confirm_monster_name: str = ""
    _confirm_price: int = 0
    _confirm_yes_rect: pg.Rect | None = None
    _confirm_no_rect: pg.Rect | None = None

    # coin icon candidates
    COIN_ICON_CANDIDATES = [
        "assets/images/UI/raw/coin.png",
        "assets/images/ingame_ui/coin.png",
        "assets/images/UI/coin.png",
        "assets/images/coin.png",
    ]

    # --------------------------
    # Helpers: image
    # --------------------------
    @staticmethod
    def _resolve_path(path: str) -> str:
        if not path:
            return ""
        if os.path.exists(path):
            return path
        p2 = os.path.join("assets", "images", path)  # for "ingame_ui/coin.png" style
        if os.path.exists(p2):
            return p2
        return path

    @staticmethod
    def _load_image(path: str, size: tuple[int, int]) -> pg.Surface | None:
        if not path:
            return None
        path = ShopScene._resolve_path(path)
        key = (path, size)
        if key in ShopScene._icon_cache:
            return ShopScene._icon_cache[key]
        try:
            img = pg.image.load(path)
            try:
                img = img.convert_alpha()
            except Exception:
                pass
            img = pg.transform.smoothscale(img, size)
            ShopScene._icon_cache[key] = img
            return img
        except Exception:
            return None

    @staticmethod
    def _load_coin_icon(size: tuple[int, int]) -> pg.Surface | None:
        for p in ShopScene.COIN_ICON_CANDIDATES:
            img = ShopScene._load_image(p, size)
            if img is not None:
                return img
        return None

    # --------------------------
    # Helpers: toast
    # --------------------------
    @staticmethod
    def _toast(msg: str, duration_ms: int = 1200) -> None:
        ShopScene._toast_msg = msg
        ShopScene._toast_until_ms = pg.time.get_ticks() + duration_ms

    @staticmethod
    def _draw_toast(screen: pg.Surface) -> None:
        if not ShopScene._toast_msg:
            return
        now = pg.time.get_ticks()
        if now > ShopScene._toast_until_ms:
            ShopScene._toast_msg = ""
            return

        sw, sh = screen.get_width(), screen.get_height()
        font = pg.font.SysFont(None, 28, bold=True)

        txt = font.render(ShopScene._toast_msg, True, (255, 255, 255))
        pad_x, pad_y = 18, 10
        box = pg.Rect(0, 0, txt.get_width() + pad_x * 2, txt.get_height() + pad_y * 2)
        box.center = (sw // 2, sh - 40)

        bg = pg.Surface((box.width, box.height), pg.SRCALPHA)
        bg.fill((0, 0, 0, 170))
        screen.blit(bg, box.topleft)
        pg.draw.rect(screen, (255, 255, 255), box, 2, border_radius=10)
        screen.blit(txt, (box.left + pad_x, box.top + pad_y))

    # --------------------------
    # Bag helpers: items/coins
    # --------------------------
    @staticmethod
    def _get_items(bag) -> list[dict]:
        return getattr(bag, "_items_data", [])

    @staticmethod
    def _find_item(items: list[dict], name: str) -> dict | None:
        lname = name.lower()
        for it in items:
            if str(it.get("name", "")).lower() == lname:
                return it
        return None

    @staticmethod
    def get_coins(bag) -> int:
        items = ShopScene._get_items(bag)
        coin = ShopScene._find_item(items, "Coins")
        return int(coin.get("count", 0)) if coin else 0

    @staticmethod
    def add_item(bag, name: str, delta: int, sprite_path: str | None = None) -> None:
        items = ShopScene._get_items(bag)
        it = ShopScene._find_item(items, name)

        if it is None:
            if delta <= 0:
                return
            items.append({"name": name, "count": int(delta), "sprite_path": sprite_path or ""})
            return

        it["count"] = int(it.get("count", 0)) + int(delta)
        if it["count"] <= 0:
            items.remove(it)

    @staticmethod
    def add_coins(bag, delta: int) -> None:
        ShopScene.add_item(bag, "Coins", delta, sprite_path="ingame_ui/coin.png")

    # --------------------------
    # Bag helpers: monsters
    # --------------------------
    @staticmethod
    def _get_monsters(bag) -> list[dict]:
        return getattr(bag, "_monsters_data", [])

    @staticmethod
    def _find_monster(monsters: list[dict], name: str) -> dict | None:
        lname = name.lower()
        for m in monsters:
            if str(m.get("name", "")).lower() == lname:
                return m
        return None

    # --------------------------
    # Shop data: BUY inventory (items only)
    # --------------------------
    @staticmethod
    def get_shop_inventory(shop_id: str) -> list[dict]:
        """
        BUY inventory: items only.
        - Keep original goods
        - Add Heal / Strength / Defense Potion
        - Add Evolution Potion (you said it got deleted)
        """

        goods = [
            {"name": "Potion", "price": 5, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Pokeball", "price": 3, "sprite_path": "ingame_ui/ball.png"},
        ]

        # add required potions (do NOT remove existing goods)
        goods.extend([
            {"name": "Heal Potion", "price": 5, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Strength Potion", "price": 8, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Defense Potion", "price": 8, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Evolution Potion", "price": 15, "sprite_path": "ingame_ui/potion.png"},  # ✅ added back
        ])

        return goods

    # --------------------------
    # Selling price for MONSTERS (fixed 20)
    # --------------------------
    @staticmethod
    def get_monster_sell_price(monster: dict, shop_id: str) -> int:
        return 20

    # --------------------------
    # Confirm dialog helpers
    # --------------------------
    @staticmethod
    def _open_sell_confirm(bag, shop_id: str, monster_name: str) -> None:
        monsters = ShopScene._get_monsters(bag)
        m = ShopScene._find_monster(monsters, monster_name)
        if not m:
            ShopScene._toast("You don't have this.")
            return

        if len(monsters) <= 1:
            ShopScene._toast("Cannot sell your last monster.", 1500)
            return

        price = ShopScene.get_monster_sell_price(m, shop_id)
        ShopScene._confirm_open = True
        ShopScene._confirm_monster_name = monster_name
        ShopScene._confirm_price = int(price)

    @staticmethod
    def _do_sell_monster_confirmed(bag, shop_id: str) -> None:
        name = ShopScene._confirm_monster_name
        monsters = ShopScene._get_monsters(bag)
        m = ShopScene._find_monster(monsters, name)
        if not m:
            ShopScene._toast("You don't have this.")
            return

        price = int(ShopScene._confirm_price)
        monsters.remove(m)
        ShopScene.add_coins(bag, +price)
        ShopScene._toast(f"Sold {name}!", 1200)

    # --------------------------
    # Click handling
    # --------------------------
    @staticmethod
    def handle_click(mouse_pos: tuple[int, int], bag, shop_id: str, tab: str) -> tuple[str, str]:
        """
        return (new_tab, result_msg)
        - result_msg only used for "__CLOSE__"
        - other messages shown via toast
        """

        # If confirm dialog open: only handle YES/NO
        if ShopScene._confirm_open:
            if ShopScene._confirm_yes_rect and ShopScene._confirm_yes_rect.collidepoint(mouse_pos):
                ShopScene._do_sell_monster_confirmed(bag, shop_id)
                ShopScene._confirm_open = False
                return (tab, "")
            if ShopScene._confirm_no_rect and ShopScene._confirm_no_rect.collidepoint(mouse_pos):
                ShopScene._confirm_open = False
                return (tab, "")
            return (tab, "")

        # switch tabs
        if ShopScene._tab_buy_rect and ShopScene._tab_buy_rect.collidepoint(mouse_pos):
            return ("buy", "")
        if ShopScene._tab_sell_rect and ShopScene._tab_sell_rect.collidepoint(mouse_pos):
            return ("sell", "")

        # close
        if ShopScene._close_rect and ShopScene._close_rect.collidepoint(mouse_pos):
            return (tab, "__CLOSE__")

        # row buttons
        for action, key, rect in ShopScene._row_btn_rects:
            if rect.collidepoint(mouse_pos):
                if action == "buy":
                    ShopScene._do_buy(bag, shop_id, key)
                    return (tab, "")
                if action == "sell_monster":
                    ShopScene._open_sell_confirm(bag, shop_id, key)
                    return (tab, "")

        return (tab, "")

    @staticmethod
    def _do_buy(bag, shop_id: str, item_name: str) -> None:
        inv = ShopScene.get_shop_inventory(shop_id)
        target = None
        for it in inv:
            if str(it["name"]).lower() == item_name.lower():
                target = it
                break
        if not target:
            ShopScene._toast("Cannot buy this.")
            return

        price = int(target["price"])
        coins = ShopScene.get_coins(bag)
        if coins < price:
            ShopScene._toast("Not enough coins!", 1400)
            return

        ShopScene.add_coins(bag, -price)
        ShopScene.add_item(bag, target["name"], +1, sprite_path=target.get("sprite_path", ""))
        ShopScene._toast("Purchased!", 1200)

    # --------------------------
    # Draw
    # --------------------------
    @staticmethod
    def draw_panel(screen: pg.Surface, panel_rect: pg.Rect, bag, shop_id: str, tab: str) -> None:
        # rebuild hitboxes
        ShopScene._row_btn_rects = []
        ShopScene._tab_buy_rect = None
        ShopScene._tab_sell_rect = None
        ShopScene._close_rect = None

        # panel background
        base_orange = (247, 182, 60)
        border_orange = (205, 132, 40)
        bottom_shadow = (222, 137, 38)

        pg.draw.rect(screen, base_orange, panel_rect)
        pg.draw.rect(screen, border_orange, panel_rect, 4)

        shadow_rect = pg.Rect(panel_rect.left + 4, panel_rect.bottom - 10, panel_rect.width - 8, 6)
        pg.draw.rect(screen, bottom_shadow, shadow_rect)

        title_font = pg.font.SysFont(None, 40, bold=True)
        small_font = pg.font.SysFont(None, 24)
        mini_font = pg.font.SysFont(None, 18)

        # title
        title_text = title_font.render("SHOP", True, (40, 40, 40))
        screen.blit(title_text, (panel_rect.left + 24, panel_rect.top + 20))

        # tabs
        tab_y = panel_rect.top + 70
        tab_w, tab_h = 80, 28
        tab_buy = pg.Rect(panel_rect.left + 24, tab_y, tab_w, tab_h)
        tab_sell = pg.Rect(tab_buy.right + 10, tab_y, tab_w, tab_h)
        ShopScene._tab_buy_rect = tab_buy
        ShopScene._tab_sell_rect = tab_sell

        def draw_tab(r: pg.Rect, label: str, active: bool):
            bg = (255, 230, 160) if active else (240, 200, 110)
            pg.draw.rect(screen, bg, r, border_radius=4)
            pg.draw.rect(screen, (80, 60, 20), r, 2, border_radius=4)
            txt = mini_font.render(label, True, (40, 40, 40))
            screen.blit(txt, txt.get_rect(center=r.center))

        draw_tab(tab_buy, "Buy", tab == "buy")
        draw_tab(tab_sell, "Sell", tab == "sell")

        # close X
        close_size = 28
        close_rect = pg.Rect(panel_rect.right - close_size - 14, panel_rect.top + 14, close_size, close_size)
        ShopScene._close_rect = close_rect
        pg.draw.rect(screen, (255, 245, 220), close_rect, border_radius=6)
        pg.draw.rect(screen, (80, 60, 20), close_rect, 2, border_radius=6)
        x_txt = mini_font.render("X", True, (40, 40, 40))
        screen.blit(x_txt, x_txt.get_rect(center=close_rect.center))

        # coins (top-right)
        coins = ShopScene.get_coins(bag)
        coin_icon = ShopScene._load_coin_icon((24, 24))

        coin_x = panel_rect.right - 140
        coin_y = tab_y
        if coin_icon:
            screen.blit(coin_icon, (coin_x, coin_y))
        else:
            pg.draw.circle(screen, (255, 220, 80), (coin_x + 12, coin_y + 12), 12)
            pg.draw.circle(screen, (80, 60, 20), (coin_x + 12, coin_y + 12), 12, 2)

        coin_txt = small_font.render(f"x{coins}", True, (40, 40, 40))
        screen.blit(coin_txt, (coin_x + 30, coin_y + 2))

        # content area (photo/banner REMOVED)
        content_top = tab_y + 45
        list_top = content_top

        row_h = 44
        row_w = panel_rect.width - 48
        row_x = panel_rect.left + 24

        if tab == "buy":
            rows = ShopScene.get_shop_inventory(shop_id)

            if not rows:
                msg = small_font.render("No goods", True, (80, 60, 20))
                screen.blit(msg, (row_x, list_top + 10))
            else:
                for idx, it in enumerate(rows[:6]):
                    y = list_top + idx * (row_h + 8)
                    r = pg.Rect(row_x, y, row_w, row_h)

                    pg.draw.rect(screen, (255, 245, 220), r, border_radius=6)
                    pg.draw.rect(screen, (80, 60, 20), r, 2, border_radius=6)

                    # icon
                    icon_rect = pg.Rect(r.left + 12, r.centery - 12, 24, 24)
                    sprite_rel = it.get("sprite_path", "")
                    sprite_path = f"assets/images/{sprite_rel}" if sprite_rel else ""
                    icon = BagScene._load_image(sprite_path, (24, 24)) if sprite_path else None
                    if icon:
                        screen.blit(icon, icon_rect.topleft)

                    # name
                    name = str(it["name"])
                    name_txt = small_font.render(name, True, (40, 40, 40))
                    screen.blit(name_txt, (icon_rect.right + 10, r.centery - name_txt.get_height() // 2))

                    # qty fixed x1
                    qty_txt = small_font.render("x1", True, (40, 40, 40))
                    screen.blit(qty_txt, (r.right - 170, r.centery - qty_txt.get_height() // 2))

                    # button (+)
                    btn = pg.Rect(r.right - 130, r.top + 8, 34, r.height - 16)
                    pg.draw.rect(screen, (240, 220, 180), btn, border_radius=6)
                    pg.draw.rect(screen, (80, 60, 20), btn, 2, border_radius=6)
                    btxt = mini_font.render("+", True, (40, 40, 40))
                    screen.blit(btxt, btxt.get_rect(center=btn.center))

                    # price with coin icon
                    price = int(it["price"])
                    ptxt = small_font.render(f"x{price}", True, (40, 40, 40))
                    cicon = ShopScene._load_coin_icon((20, 20))
                    if cicon:
                        screen.blit(cicon, (btn.right + 10, r.centery - 10))
                    else:
                        pg.draw.circle(screen, (255, 220, 80), (btn.right + 20, r.centery), 10)
                        pg.draw.circle(screen, (80, 60, 20), (btn.right + 20, r.centery), 10, 2)

                    screen.blit(ptxt, (btn.right + 34, r.centery - ptxt.get_height() // 2))

                    ShopScene._row_btn_rects.append(("buy", name, btn))

        else:
            monsters = ShopScene._get_monsters(bag)

            if not monsters:
                msg = small_font.render("No monsters", True, (80, 60, 20))
                screen.blit(msg, (row_x, list_top + 10))
            else:
                for idx, m in enumerate(monsters[:6]):
                    y = list_top + idx * (row_h + 8)
                    r = pg.Rect(row_x, y, row_w, row_h)

                    pg.draw.rect(screen, (255, 245, 220), r, border_radius=6)
                    pg.draw.rect(screen, (80, 60, 20), r, 2, border_radius=6)

                    mname = str(m.get("name", "???"))
                    lv = int(m.get("level", 1))
                    price = ShopScene.get_monster_sell_price(m, shop_id)

                    # icon
                    icon_rect = pg.Rect(r.left + 12, r.centery - 12, 24, 24)
                    sprite_rel = m.get("sprite_path", "")
                    sprite_path = f"assets/images/{sprite_rel}" if sprite_rel else ""
                    icon = BagScene._load_image(sprite_path, (24, 24)) if sprite_path else None
                    if icon:
                        screen.blit(icon, icon_rect.topleft)

                    # name + lv
                    name_txt = small_font.render(f"{mname}  Lv.{lv}", True, (40, 40, 40))
                    screen.blit(name_txt, (icon_rect.right + 10, r.centery - name_txt.get_height() // 2))

                    # qty fixed x1
                    qty_txt = small_font.render("x1", True, (40, 40, 40))
                    screen.blit(qty_txt, (r.right - 170, r.centery - qty_txt.get_height() // 2))

                    # button (-)
                    btn = pg.Rect(r.right - 130, r.top + 8, 34, r.height - 16)
                    pg.draw.rect(screen, (240, 220, 180), btn, border_radius=6)
                    pg.draw.rect(screen, (80, 60, 20), btn, 2, border_radius=6)
                    btxt = mini_font.render("-", True, (40, 40, 40))
                    screen.blit(btxt, btxt.get_rect(center=btn.center))

                    # price with coin icon
                    ptxt = small_font.render(f"x{price}", True, (40, 40, 40))
                    cicon = ShopScene._load_coin_icon((20, 20))
                    if cicon:
                        screen.blit(cicon, (btn.right + 10, r.centery - 10))
                    else:
                        pg.draw.circle(screen, (255, 220, 80), (btn.right + 20, r.centery), 10)
                        pg.draw.circle(screen, (80, 60, 20), (btn.right + 20, r.centery), 10, 2)

                    screen.blit(ptxt, (btn.right + 34, r.centery - ptxt.get_height() // 2))

                    ShopScene._row_btn_rects.append(("sell_monster", mname, btn))

        hint = mini_font.render("Press ESC to close", True, (40, 40, 40))
        screen.blit(hint, (panel_rect.left + 20, panel_rect.bottom - hint.get_height() - 8))

        # ---- confirm dialog draw (topmost) ----
        ShopScene._confirm_yes_rect = None
        ShopScene._confirm_no_rect = None

        if ShopScene._confirm_open:
            sw, sh = screen.get_width(), screen.get_height()

            dim = pg.Surface((sw, sh), pg.SRCALPHA)
            dim.fill((0, 0, 0, 120))
            screen.blit(dim, (0, 0))

            box_w, box_h = 420, 180
            box = pg.Rect(0, 0, box_w, box_h)
            box.center = (sw // 2, sh // 2)

            pg.draw.rect(screen, (255, 245, 220), box, border_radius=12)
            pg.draw.rect(screen, (80, 60, 20), box, 3, border_radius=12)

            font = pg.font.SysFont(None, 28, bold=True)
            small = pg.font.SysFont(None, 22)

            msg = f"Sell {ShopScene._confirm_monster_name} for x{ShopScene._confirm_price}?"
            t = font.render(msg, True, (40, 40, 40))
            screen.blit(t, t.get_rect(center=(box.centerx, box.top + 55)))

            yes = pg.Rect(0, 0, 120, 44)
            no = pg.Rect(0, 0, 120, 44)
            yes.center = (box.centerx - 80, box.bottom - 55)
            no.center = (box.centerx + 80, box.bottom - 55)

            ShopScene._confirm_yes_rect = yes
            ShopScene._confirm_no_rect = no

            pg.draw.rect(screen, (200, 255, 200), yes, border_radius=10)
            pg.draw.rect(screen, (80, 60, 20), yes, 2, border_radius=10)
            pg.draw.rect(screen, (255, 200, 200), no, border_radius=10)
            pg.draw.rect(screen, (80, 60, 20), no, 2, border_radius=10)

            ytxt = small.render("Yes", True, (40, 40, 40))
            ntxt = small.render("No", True, (40, 40, 40))
            screen.blit(ytxt, ytxt.get_rect(center=yes.center))
            screen.blit(ntxt, ntxt.get_rect(center=no.center))

        ShopScene._draw_toast(screen)
