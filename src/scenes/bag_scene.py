# src/scenes/bag_scene.py

import pygame as pg

from src.scenes.scene import Scene

# ✅ Evo overlay (Evolution Potion)
_evo_import_error: str | None = None
try:
    from src.scenes.evo_scene import EvoScene  # type: ignore
except Exception as e:
    EvoScene = None  # type: ignore
    _evo_import_error = repr(e)

class BagScene(Scene):
    """
    專門負責畫「背包面板」的靜態工具 Scene。
    GameScene 只要呼叫 BagScene.draw_panel(...) 就好。
    同時也提供 handle_click(...) 讓 GameScene 處理滑鼠點擊。
    """

    _icon_cache: dict[tuple[str, tuple[int, int]], pg.Surface] = {}
    _potion_hitbox: pg.Rect | None = None
    _evo_use_hitbox: pg.Rect | None = None
    _show_no_item_popup: bool = False 
    _prev_mouse_down: bool = False
    _prev_esc: bool = False
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
    # Helpers: normalize name & get count by aliases
    # -------------------------------------------------
    @staticmethod
    def _norm_name(s: str) -> str:
        return str(s).strip().lower().replace("_", " ")

    @staticmethod
    def _get_item_count_any(bag, aliases: list[str]) -> int:
        items = getattr(bag, "_items_data", [])
        want = {BagScene._norm_name(a) for a in aliases}
        for it in items:
            if BagScene._norm_name(it.get("name", "")) in want:
                try:
                    return int(it.get("count", 0))
                except Exception:
                    return 0
        return 0

    
    # -------------------------------------------------
    # 事件：輪詢式更新（不需要 GameScene 的 event loop）
    # -------------------------------------------------
    @staticmethod
    def update(dt: float, bag) -> None:
        """
        ✅ 你現在的 GameScene 沒有把滑鼠事件轉進來（所以按鈕會「看起來不能按」）。
        所以 BagScene 改成「輪詢式」：在 GameScene 的 update()、bag overlay 開啟時呼叫即可。

        在 GameScene.update 的 bag overlay 區塊加這行就好：
            BagScene.update(dt, self.game_manager.bag)

        功能：
        - 滑鼠左鍵「按下的那一刻」(edge) 觸發點擊
        - 如果 EvoScene 已開啟，優先把點擊交給 EvoScene
        - ESC：若 EvoScene 開著先關 EvoScene，否則由 GameScene 自己關 bag overlay（你原本就有）
        """
        # ESC edge（只處理 EvoScene 的關閉；bag overlay 的關閉你原本在 GameScene 做了）
        keys = pg.key.get_pressed()
        esc_now = bool(keys[pg.K_ESCAPE])
        if esc_now and (not BagScene._prev_esc):
            if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
                EvoScene.close()
        BagScene._prev_esc = esc_now

        # Let EvoScene do its own polling (ESC, timers)
        if EvoScene is not None and hasattr(EvoScene, "update") and EvoScene.is_open():
            try:
                EvoScene.update(dt)
            except Exception:
                pass

        # mouse click edge
        mouse_now = bool(pg.mouse.get_pressed(num_buttons=3)[0])
        if mouse_now and (not BagScene._prev_mouse_down):
            pos = pg.mouse.get_pos()

            # if evo overlay open -> forward click
            if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
                try:
                    EvoScene.handle_click(pos)
                except Exception as e:
                    print(f"[BagScene] EvoScene.handle_click error: {e}")
            else:
                BagScene.handle_click(pos, bag)

        BagScene._prev_mouse_down = mouse_now

# -------------------------------------------------
    # 事件：處理滑鼠點擊（GameScene 可以在滑鼠按下時呼叫）
    # -------------------------------------------------
    @staticmethod
    def handle_click(mouse_pos: tuple[int, int], bag) -> None:
        """
        在 GameScene 的事件迴圈中：
            if self.is_bag_open and event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                BagScene.handle_click(event.pos, self.game_manager.bag)

        ✅ 本版支援：
        - Potion 點擊（原本功能保留）
        - Evolution Potion 的 USE 按鈕：按下會開啟 EvoScene（進化選擇視窗）
          （EvoScene 需要在 GameScene 另外呼叫 draw / handle_click）
        """

        # 1) 沒有道具 popup：點一下關閉
        if BagScene._show_no_item_popup:
            BagScene._show_no_item_popup = False
            return

        # 2) Evolution Potion USE：改成「跳到 / 開啟 EvoScene」
        if BagScene._evo_use_hitbox and BagScene._evo_use_hitbox.collidepoint(mouse_pos):
            evo_cnt = BagScene._get_item_count_any(
                bag, ["evolution potion", "evo potion", "evolution_potion"]
            )
            if evo_cnt <= 0:
                BagScene._show_no_item_popup = True
                return

            # ✅ 打開 EvoScene overlay
            if EvoScene is not None:
                EvoScene.open(bag)
            else:
                print(f"[BagScene] EvoScene import failed: {_evo_import_error}")
            return

        # 3) Potion（整列點擊）
        if BagScene._potion_hitbox and BagScene._potion_hitbox.collidepoint(mouse_pos):
            potion_count = BagScene._get_item_count_any(bag, ["potion"])
            if potion_count <= 0:
                BagScene._show_no_item_popup = True
            else:
                print("[BagScene] Potion clicked. TODO: implement heal & decrease count.")
            return


    # -------------------------------------------------
    # 繪圖：背包面板
    # -------------------------------------------------
    @staticmethod
    def draw_panel(screen: pg.Surface, panel_rect: pg.Rect, bag) -> None:
        # 每次重畫時先清掉 Potion hitbox
        BagScene._potion_hitbox = None
        BagScene._evo_use_hitbox = None

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

        if max_show == 0:
            no_mon_text = small_font.render("No Pokemon", True, (100, 100, 100))
            screen.blit(no_mon_text, (card_x, content_top + 12))
        else:
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

                # 寶可夢頭像（往下調 6px，比較居中）
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
        # 右邊：道具列表（圖示 + 名稱 + USE + 數量）
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
            "evolution potion": BagScene.POTION_ICON,
            "evo potion": BagScene.POTION_ICON,
        }

        # 欄位位置（避免黏在一起）
        icon_size_item = 24
        qty_col_right = panel_rect.right - 40               # 數量欄靠右
        use_col_right = qty_col_right - 90                  # USE 按鈕欄
        name_col_left = item_area_x + icon_size_item + 12   # 名稱欄開始

        for i, item in enumerate(items[:6]):
            row_y = item_area_y + i * line_height
            name_item = str(item.get("name", ""))
            qty = item.get("count", 1)

            # icon rect
            icon_rect_item = pg.Rect(item_area_x, row_y, icon_size_item, icon_size_item)

            # 先看 item 自己有沒有 sprite_path，沒有就用預設 mapping
            sprite_rel_item = item.get("sprite_path", "")
            if sprite_rel_item:
                sprite_path_item = f"assets/images/{sprite_rel_item}"
            else:
                key = BagScene._norm_name(name_item)
                sprite_path_item = default_item_icons.get(key)

            icon_surf_item = None
            if sprite_path_item:
                icon_surf_item = BagScene._load_image(sprite_path_item, (icon_size_item, icon_size_item))

            if icon_surf_item:
                screen.blit(icon_surf_item, icon_rect_item.topleft)
            else:
                center = icon_rect_item.center
                pg.draw.circle(screen, (240, 240, 240), center)
                pg.draw.circle(screen, (120, 120, 120), center, 2)

            # 名稱（太長就截斷，避免撞到 USE/數量）
            display_name = name_item
            max_name_px = (use_col_right - 14) - name_col_left
            if small_font.size(display_name)[0] > max_name_px:
                while display_name and small_font.size(display_name + "...")[0] > max_name_px:
                    display_name = display_name[:-1]
                display_name = display_name + "..."

            text_name = small_font.render(display_name, True, (40, 40, 40))
            tn_y = row_y + (icon_size_item - text_name.get_height()) // 2
            screen.blit(text_name, (name_col_left, tn_y))

            # 數量（固定靠右）
            qty_text = small_font.render(f"x{qty}", True, (40, 40, 40))
            qty_x = qty_col_right - qty_text.get_width()
            qty_y = row_y + (icon_size_item - qty_text.get_height()) // 2
            screen.blit(qty_text, (qty_x, qty_y))

            # Potion：整列可點（保留你原本設計）
            if BagScene._norm_name(name_item) == "potion":
                hit_x = icon_rect_item.left
                hit_y = row_y
                hit_w = (qty_x + qty_text.get_width()) - hit_x
                hit_h = line_height
                BagScene._potion_hitbox = pg.Rect(hit_x, hit_y, hit_w, hit_h)

            # Evolution Potion：顯示 USE 按鈕
            if BagScene._norm_name(name_item) in ("evolution potion", "evo potion"):
                use_w, use_h = 56, 22
                use_x = use_col_right - use_w
                use_y = row_y + (icon_size_item - use_h) // 2 + 1
                use_rect = pg.Rect(use_x, use_y, use_w, use_h)

                pg.draw.rect(screen, (250, 240, 200), use_rect, border_radius=6)
                pg.draw.rect(screen, (120, 90, 40), use_rect, 2, border_radius=6)
                use_txt = mini_font.render("USE", True, (40, 40, 40))
                screen.blit(use_txt, use_txt.get_rect(center=use_rect.center))

                BagScene._evo_use_hitbox = use_rect

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


        # -------------------------------------------------
        # Evo overlay（如果開啟，就畫在最上層）
        # -------------------------------------------------
        if EvoScene is not None and hasattr(EvoScene, "is_open") and EvoScene.is_open():
            try:
                EvoScene.draw(screen, center=screen.get_rect().center)
            except Exception as e:
                print(f"[BagScene] EvoScene.draw error: {e}")
