# src/scenes/game_scene.py

import pygame as pg
import pytmx

from typing import override

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager, scene_manager
from src.sprites import Sprite
from src.interface.components import Button
from src.scenes.setting_scene import SettingScene
from src.scenes.bag_scene import BagScene
from src.scenes.wild_scene import WildScene
from src.scenes.shop_scene import ShopScene


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
#           SCENE
# =========================
class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite

    setting_button: Button
    overlay_close_button: Button
    bottom_buttons: list[Button]
    is_setting_open: bool
    panel_rect: pg.Rect

    bag_button: Button
    is_bag_open: bool

    # shop overlay
    is_shop_open: bool
    shop_overlay: ShopOverlay | None

    def __init__(self):
        super().__init__()

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

        self.sprite_online = Sprite(
            "ingame_ui/options1.png",
            (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
        )

        # ====== popup ======
        self.popup_msg: str | None = None
        self.popup_timer: float = 0.0

        # ====== overlays ======
        self.is_setting_open = False
        self.is_bag_open = False

        self.is_shop_open = False
        self.shop_overlay = None

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        # 右上角：背包 / 設定
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

        # 共用面板
        wid_mid, hig_mid = sw // 2, sh // 2
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 420 // 2,
            480, 420
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

    # ====== popup ======
    def show_popup(self, msg: str):
        self.popup_msg = msg
        self.popup_timer = 1.0

    # ====== save/load ======
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

    # ====== overlay control ======
    def close_all_overlays(self):
        self.is_setting_open = False
        self.is_bag_open = False

        self.is_shop_open = False
        self.shop_overlay = None

    def open_setting_overlay(self):
        self.is_setting_open = True
        self.is_bag_open = False
        self.is_shop_open = False
        self.shop_overlay = None

    def open_bag_overlay(self):
        self.is_bag_open = True
        self.is_setting_open = False
        self.is_shop_open = False
        self.shop_overlay = None

    def open_shop_overlay(self, shop_id: str = "default"):
        self.is_shop_open = True
        self.is_setting_open = False
        self.is_bag_open = False
        self.shop_overlay = ShopOverlay(self.game_manager.bag, shop_id)

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

    @override
    def update(self, dt: float):

        # ===== popup timer =====
        if self.popup_timer > 0:
            self.popup_timer -= dt
            if self.popup_timer <= 0:
                self.popup_msg = None

        # ----- right top buttons -----
        self.setting_button.update(dt)
        self.bag_button.update(dt)

        # ===== SHOP overlay（最高優先）=====
        if self.is_shop_open and self.shop_overlay and self.shop_overlay.open:
            self.shop_overlay.update(dt)
            if not self.shop_overlay.open:
                self.is_shop_open = False
                self.shop_overlay = None
            return

        # ===== setting overlay =====
        if self.is_setting_open:
            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.is_setting_open = False

            for btn in self.bottom_buttons:
                btn.update(dt)

            self.overlay_close_button.update(dt)
            SettingScene.handle_panel_input(self.panel_rect)
            return

        # ===== bag overlay =====
        if self.is_bag_open:
            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.is_bag_open = False
            self.overlay_close_button.update(dt)
            return

        # ===== original game logic =====
        if self.game_manager.player:
            self.game_manager.player.update(dt)
            self._update_bush_state()

        # Enemy trainers
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)

        # Shop NPCs：偵測玩家是否可互動 + 按 E 開商店
        player = self.game_manager.player
        if player:
            player_rect = player.get_rect()
            keys = pg.key.get_pressed()
            e_now = bool(keys[pg.K_e])
            e_pressed_once = e_now and (not self._prev_e)

            for npc in self.game_manager.current_shop_npcs:
                # 讓 NPC 自己決定 detected，用來畫驚嘆號
                npc.detected = npc.can_interact(player_rect)

                npc.update(dt)

                if npc.detected and e_pressed_once:
                    # 不切 scene，直接開 overlay
                    self.open_shop_overlay(getattr(npc, "shop_id", "default"))
                    break

            self._prev_e = e_now

        self.game_manager.bag.update(dt)

        if self.game_manager.player and self.online_manager:
            self.online_manager.update(
                self.game_manager.player.position.x,
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name
            )

        self.game_manager.try_switch_map()

    @override
    def draw(self, screen: pg.Surface):

        # camera
        if self.game_manager.player:
            camera = self.game_manager.player.camera
        else:
            camera = PositionCamera(0, 0)

        # ===== map =====
        self.game_manager.current_map.draw(screen, camera)

        # ===== shop npcs =====
        for npc in self.game_manager.current_shop_npcs:
            npc.draw(screen, camera)

        # ===== player =====
        if self.game_manager.player:
            self.game_manager.player.draw(screen, camera)

        # ===== enemies =====
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)

        # ===== bag ui =====
        self.game_manager.bag.draw(screen)

        # ===== online players =====
        if self.online_manager and self.game_manager.player:
            list_online = self.online_manager.get_list_players()
            for player in list_online:
                if player["map"] == self.game_manager.current_map.path_name:
                    pos = camera.transform_position_as_position(
                        Position(player["x"], player["y"])
                    )
                    self.sprite_online.update_pos(pos)
                    self.sprite_online.draw(screen)

        # ===== top-right buttons =====
        self.setting_button.draw(screen)
        self.bag_button.draw(screen)

        # ===== setting/bag overlays =====
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
            elif self.is_bag_open:
                BagScene.draw_panel(
                    screen,
                    self.panel_rect,
                    self.game_manager.bag
                )

            self.overlay_close_button.draw(screen)

        # ===== enemy confirm dialog must be topmost =====
        for enemy in self.game_manager.current_enemy_trainers:
            if hasattr(enemy, "show_confirm_dialog") and enemy.show_confirm_dialog:
                enemy._draw_confirm_dialog(screen)

        # ===== shop overlay draws on top of everything =====
        if self.is_shop_open and self.shop_overlay and self.shop_overlay.open:
            self.shop_overlay.draw(screen)

        # ===== popup =====
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

    # ====== Bush / Pokemon grass ======
    def _is_player_on_bush_tile(self) -> bool:
        player = self.game_manager.player
        if player is None:
            return False

        tmx = self.game_manager.current_map.tmxdata

        try:
            bush_layer = tmx.get_layer_by_name("PokemonBush")
        except ValueError:
            return False

        if not isinstance(bush_layer, pytmx.TiledTileLayer):
            return False

        px = player.position.x + GameSettings.TILE_SIZE / 2
        py = player.position.y + GameSettings.TILE_SIZE / 2
        tile_x = int(px // GameSettings.TILE_SIZE)
        tile_y = int(py // GameSettings.TILE_SIZE)

        if tile_x < 0 or tile_y < 0 or tile_x >= tmx.width or tile_y >= tmx.height:
            return False

        gid = bush_layer.data[tile_y][tile_x]
        return gid != 0

    def _update_bush_state(self) -> None:
        on_bush = self._is_player_on_bush_tile()

        if on_bush and not self._was_on_bush:
            Logger.info("Player stepped into PokemonBush")
            scene_manager.register_scene("wild", WildScene(self.game_manager.bag))
            scene_manager.change_scene("wild")

        self._was_on_bush = on_bush
