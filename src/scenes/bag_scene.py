# src/scenes/bag_scene.py

import pygame as pg

from src.scenes.scene import Scene


class BagScene(Scene):
    """
    專門負責畫「背包面板」的靜態工具 Scene。
    GameScene 只要呼叫 BagScene.draw_panel(...) 就好。
    同時也提供 handle_click(...) 讓 GameScene 處理滑鼠點擊。
    """

    _icon_cache: dict[tuple[str, tuple[int, int]], pg.Surface] = {}
    _potion_hitbox: pg.Rect | None = None
    _show_no_item_popup: bool = False

    # 路徑常數（如果你的專案路徑不一樣，改這裡）
    UI_BASE_PATH = "assets/images/UI/raw/"
    MONSTER_BANNER = UI_BASE_PATH + "UI_Flat_Banner03a.png"
    POTION_ICON = UI_BASE_PATH + "potion.png"
    COIN_ICON = UI_BASE_PATH + "coin.png"
    BALL_ICON = UI_BASE_PATH + "ball.png"
    EXCLAMATION_ICON = UI_BASE_PATH + "exclamation.png"

    # 預設寶可夢頭像
    DEFAULT_MONSTER_SPRITE = "assets/images/menu_sprites/menusprite1.png"

    @staticmethod
    def _load_image(path: str, size: tuple[int, int]) -> pg.Surface | None:
        if not path:
            return None

        key = (path, size)
        if key in BagScene._icon_cache:
            return BagScene._icon_cache[key]

        try:
            img = pg.image.load(path).convert_alpha()
            img = pg.transform.smoothscale(img, size)
            BagScene._icon_cache[key] = img
            return img
        except Exception as e:
            print(f"[BagScene] Failed to load image '{path}': {e}")
            return None

    # -------------------------------------------------
    # 事件：處理滑鼠點擊（GameScene 可以在滑鼠按下時呼叫）
    # -------------------------------------------------
    @staticmethod
    def handle_click(mouse_pos: tuple[int, int], bag) -> None:
        """
        在 GameScene 的事件迴圈中：
            if self.is_bag_open and event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                BagScene.handle_click(event.pos, self.game_manager.bag)
        """
        # 如果目前有跳出「沒有道具」的視窗，就先把視窗關掉
        if BagScene._show_no_item_popup:
            BagScene._show_no_item_popup = False
            return

        # 沒有設定過 hitbox，就不用處理
        if not BagScene._potion_hitbox:
            return

        # 點到 Potion 行
        if BagScene._potion_hitbox.collidepoint(mouse_pos):
            items = getattr(bag, "_items_data", [])
            potion_count = 0
            for it in items:
                if it.get("name", "").lower() == "potion":
                    potion_count = it.get("count", 0)
                    break

            if potion_count <= 0:
                # 沒藥水 -> 顯示提醒視窗
                BagScene._show_no_item_popup = True
            else:
                # 這裡可以依照你自己的邏輯去扣道具 / 回血
                # 先留一行提示，避免直接動到你的資料結構
                print("[BagScene] Potion clicked. TODO: implement heal & decrease count.")

    # -------------------------------------------------
    # 繪圖：背包面板
    # -------------------------------------------------
    @staticmethod
    def draw_panel(screen: pg.Surface, panel_rect: pg.Rect, bag) -> None:
        # 每次重畫時先清掉 Potion hitbox
        BagScene._potion_hitbox = None

        # === 背景：橘色面板 ===
        base_orange = (247, 182, 60)
        border_orange = (205, 132, 40)
        bottom_shadow = (222, 137, 38)

        pg.draw.rect(screen, base_orange, panel_rect)
        pg.draw.rect(screen, border_orange, panel_rect, 4)

        shadow_rect = pg.Rect(
            panel_rect.left + 4,
            panel_rect.bottom - 10,
            panel_rect.width - 8,
            6
        )
        pg.draw.rect(screen, bottom_shadow, shadow_rect)

        # === 字型設定 ===
        title_font = pg.font.SysFont(None, 40, bold=True)
        small_font = pg.font.SysFont(None, 24)
        mini_font = pg.font.SysFont(None, 18)

        # === 標題：左上角 "BAG" ===
        title_text = title_font.render("BAG", True, (40, 40, 40))
        title_x = panel_rect.left + 24
        title_y = panel_rect.top + 20
        screen.blit(title_text, (title_x, title_y))

        content_top = title_y + 40
        margin_side = 24

        # === 從 Bag 取資料（用你現成的結構） ===
        monsters = getattr(bag, "_monsters_data", [])
        items = getattr(bag, "_items_data", [])

        # -------------------------------------------------
        # 左邊：最多六隻寶可夢卡片（使用 Banner 圖片）
        # -------------------------------------------------
        card_width = 260
        card_height = 50
        card_x = panel_rect.left + margin_side

        banner_surf_raw = BagScene._load_image(
            BagScene.MONSTER_BANNER, (card_width, card_height)
        )

        icon_size = 40           # 寶可夢頭像大小
        vertical_gap = 5         # 卡片之間的間隔

        max_show = min(len(monsters), 6)

        for idx in range(max_show):
            monster = monsters[idx]

            card_y = content_top + 8 + idx * (card_height + vertical_gap)
            card_rect = pg.Rect(card_x, card_y, card_width, card_height)

            # 繪製卡片 Banner
            if banner_surf_raw:
                screen.blit(banner_surf_raw, card_rect.topleft)
            else:
                pg.draw.rect(screen, (250, 250, 250), card_rect, border_radius=4)
                pg.draw.rect(screen, (120, 120, 120), card_rect, 2, border_radius=4)

            # 寶可夢頭像（往下調 2px，比較居中）
            icon_y = card_rect.top + (card_height - icon_size) // 2 - 6
            icon_rect = pg.Rect(
                card_rect.left + 16,
                icon_y,
                icon_size,
                icon_size
            )

            sprite_rel = monster.get("sprite_path", "")
            sprite_path = (
                f"assets/images/{sprite_rel}"
                if sprite_rel
                else BagScene.DEFAULT_MONSTER_SPRITE
            )
            icon_surf = BagScene._load_image(sprite_path, (icon_size, icon_size))
            if icon_surf:
                screen.blit(icon_surf, icon_rect)
            else:
                pg.draw.rect(screen, (200, 200, 200), icon_rect)

            # 名稱
            name = monster.get("name", "???")
            name_text = small_font.render(str(name), True, (30, 30, 30))
            screen.blit(name_text, (icon_rect.right + 10, card_rect.top + 8))

            # 等級
            level = monster.get("level", 1)
            lv_text = mini_font.render(f"Lv.{level}", True, (30, 30, 30))
            screen.blit(
                lv_text,
                (card_rect.right - lv_text.get_width() - 10, card_rect.top + 6),
            )

            # HP Bar
            hp = monster.get("hp", 0)
            max_hp = monster.get("max_hp", max(hp, 1))
            ratio = max(0.0, min(1.0, hp / max_hp))

            bar_width = card_rect.width - (icon_rect.width + 10 + 20)
            bar_height = 12
            bar_x = icon_rect.right + 10
            bar_y = card_rect.bottom - 12 - bar_height

            bar_rect = pg.Rect(bar_x, bar_y, bar_width, bar_height)
            pg.draw.rect(screen, (0, 0, 0), bar_rect, 1)

            inner_rect = bar_rect.inflate(-2, -2)
            filled_rect = inner_rect.copy()
            filled_rect.width = int(inner_rect.width * ratio)
            pg.draw.rect(screen, (86, 176, 66), filled_rect)

            hp_text = mini_font.render(f"{hp}/{max_hp}", True, (20, 20, 20))
            screen.blit(
                hp_text,
                (
                    bar_rect.centerx - hp_text.get_width() // 2,
                    bar_rect.centery - hp_text.get_height() // 2,
                ),
            )

        # -------------------------------------------------
        # 右邊：道具列表（圖示 + 名稱 + 數量）
        # -------------------------------------------------
        item_area_x = panel_rect.left + int(panel_rect.width * 0.60)
        item_area_y = content_top + 8
        line_height = 34

        # 名稱 -> 預設 icon 路徑
        default_item_icons = {
            "potion": BagScene.POTION_ICON,
            "coins": BagScene.COIN_ICON,
            "coin": BagScene.COIN_ICON,
            "pokeball": BagScene.BALL_ICON,
            "ball": BagScene.BALL_ICON,
        }

        for i, item in enumerate(items[:6]):
            row_y = item_area_y + i * line_height

            name_item = item.get("name", "")
            qty = item.get("count", 1)

            icon_size_item = 24
            icon_rect_item = pg.Rect(
                item_area_x, row_y, icon_size_item, icon_size_item
            )

            # 先看 item 自己有沒有 sprite_path，沒有就用預設 mapping
            sprite_rel_item = item.get("sprite_path", "")
            sprite_path_item: str | None

            if sprite_rel_item:
                sprite_path_item = f"assets/images/{sprite_rel_item}"
            else:
                key = name_item.lower()
                sprite_path_item = default_item_icons.get(key)

            icon_surf_item = None
            if sprite_path_item:
                icon_surf_item = BagScene._load_image(
                    sprite_path_item, (icon_size_item, icon_size_item)
                )

            if icon_surf_item:
                screen.blit(icon_surf_item, icon_rect_item.topleft)
            else:
                center = icon_rect_item.center
                pg.draw.circle(screen, (240, 240, 240), center)
                pg.draw.circle(screen, (120, 120, 120), center, 2)

            # 文字垂直置中，對齊小圖
            text_name = small_font.render(str(name_item), True, (40, 40, 40))
            tn_y = row_y + (icon_size_item - text_name.get_height()) // 2
            screen.blit(text_name, (icon_rect_item.right + 8, tn_y))

            qty_text = small_font.render(f"x{qty}", True, (40, 40, 40))
            qty_x = panel_rect.right - 40 - qty_text.get_width()
            qty_y = row_y + (icon_size_item - qty_text.get_height()) // 2
            screen.blit(qty_text, (qty_x, qty_y))

            # 如果是 Potion，記錄一個比較大的 hitbox，當作按鈕區域
            if name_item.lower() == "potion":
                # 讓整列都可以點（icon ~ 數量文字）
                hit_x = icon_rect_item.left
                hit_y = row_y
                hit_w = qty_x + qty_text.get_width() - hit_x
                hit_h = line_height
                BagScene._potion_hitbox = pg.Rect(hit_x, hit_y, hit_w, hit_h)

        if not items:
            no_item_text = small_font.render("No items", True, (100, 100, 100))
            nix = item_area_x
            niy = item_area_y
            screen.blit(no_item_text, (nix, niy))

        # === 下方 ESC 提示 ===
        hint_text = mini_font.render("Press ESC to close", True, (40, 40, 40))
        hint_x = panel_rect.left + 20
        hint_y = panel_rect.bottom - hint_text.get_height() - 8
        screen.blit(hint_text, (hint_x, hint_y))

        # === 如果需要顯示「沒有道具」的彈出視窗 ===
        if BagScene._show_no_item_popup:
            popup_w = 260
            popup_h = 80
            popup_rect = pg.Rect(
                panel_rect.centerx - popup_w // 2,
                panel_rect.centery - popup_h // 2,
                popup_w,
                popup_h,
            )

            # 背景 + 邊框
            pg.draw.rect(screen, (250, 240, 200), popup_rect, border_radius=8)
            pg.draw.rect(screen, (120, 90, 40), popup_rect, 2, border_radius=8)

            # 圖示
            icon_size = 40
            icon_rect = pg.Rect(
                popup_rect.left + 12,
                popup_rect.centery - icon_size // 2,
                icon_size,
                icon_size,
            )

            ex_icon = BagScene._load_image(
                BagScene.EXCLAMATION_ICON, (icon_size, icon_size)
            )
            if ex_icon:
                screen.blit(ex_icon, icon_rect.topleft)
            else:
                pg.draw.circle(
                    screen, (240, 200, 0), icon_rect.center, icon_size // 2
                )

            # 文字
            msg = "no more item can be used"
            msg_text = mini_font.render(msg, True, (40, 40, 40))
            msg_x = icon_rect.right + 10
            msg_y = popup_rect.centery - msg_text.get_height() // 2
            screen.blit(msg_text, (msg_x, msg_y))
