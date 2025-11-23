# src/scenes/game_scene.py

import pygame as pg
import threading
import time

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager, scene_manager
from src.sprites import Sprite
from src.interface.components import Button
from src.scenes.setting_scene import SettingScene
from typing import override

from src.scenes.bag_scene import BagScene
from src.scenes.wild_scene import WildScene  # ★ 新增匯入

import pytmx


class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite

    # 設定相關
    setting_button: Button
    overlay_close_button: Button
    bottom_buttons: list[Button]
    is_setting_open: bool
    panel_rect: pg.Rect

    # 背包相關
    bag_button: Button
    is_bag_open: bool

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

        # ====== 彈窗狀態 ======
        self.popup_msg: str | None = None
        self.popup_timer: float = 0.0  # 倒數 1 秒

        # ====== 設定 / 背包 overlay 狀態 ======
        self.is_setting_open = False
        self.is_bag_open = False

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        # 右上角兩顆按鈕：背包在左、設定在右
        btn_size_top = 60
        margin_top = 16
        margin_right = 16
        gap_top = 10

        # 設定按鈕（最右邊）
        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            sw - margin_right - btn_size_top,
            margin_top,
            btn_size_top, btn_size_top,
            lambda: self.open_setting_overlay()
        )

        # 背包按鈕（在設定左邊）
        self.bag_button = Button(
            "UI/button_backpack.png", "UI/button_backpack_hover.png",
            sw - margin_right - btn_size_top * 2 - gap_top,
            margin_top,
            btn_size_top, btn_size_top,
            lambda: self.open_bag_overlay()
        )

        # 設定／背包共用的面板
        wid_mid, hig_mid = sw // 2, sh // 2
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 420 // 2,
            480, 420
        )

        # 下方一排三顆按鈕：Save / Load / Menu
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

        # ====== Bush / 野生寶可夢狀態 ======
        # 上一幀玩家是否站在 PokemonBush 草叢上
        self._was_on_bush: bool = False

    # ====== 彈窗功能 ======
    def show_popup(self, msg: str):
        self.popup_msg = msg
        self.popup_timer = 1.0

    # ====== 存檔 / 讀檔 ======
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

    # ====== Overlay 開關 ======
    def close_all_overlays(self):
        self.is_setting_open = False
        self.is_bag_open = False

    def open_setting_overlay(self):
        self.is_setting_open = True
        self.is_bag_open = False

    def open_bag_overlay(self):
        self.is_bag_open = True
        self.is_setting_open = False

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

        # ====== 彈窗倒數 ======
        if self.popup_timer > 0:
            self.popup_timer -= dt
            if self.popup_timer <= 0:
                self.popup_msg = None

        # ----- 右上按鈕 -----
        self.setting_button.update(dt)
        self.bag_button.update(dt)

        # ====== 設定 overlay ======
        if self.is_setting_open:

            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.is_setting_open = False

            for btn in self.bottom_buttons:
                btn.update(dt)

            self.overlay_close_button.update(dt)
            SettingScene.handle_panel_input(self.panel_rect)
            return

        # ====== 背包 overlay ======
        if self.is_bag_open:

            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.is_bag_open = False

            self.overlay_close_button.update(dt)
            return

        # ====== 原本遊戲邏輯 ======
        if self.game_manager.player:
            self.game_manager.player.update(dt)
            # 玩家移動完後檢查是否踩在 PokemonBush 上
            self._update_bush_state()

        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)

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

        # ===== 地圖 =====
        self.game_manager.current_map.draw(screen, camera)

        # ===== 玩家 =====
        if self.game_manager.player:
            self.game_manager.player.draw(screen, camera)

        # ===== 敵人 =====
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)

        # ===== 背包（玩家 UI）=====
        self.game_manager.bag.draw(screen)

        # ===== 線上玩家 =====
        if self.online_manager and self.game_manager.player:
            list_online = self.online_manager.get_list_players()
            for player in list_online:
                if player["map"] == self.game_manager.current_map.path_name:
                    pos = camera.transform_position_as_position(
                        Position(player["x"], player["y"])
                    )
                    self.sprite_online.update_pos(pos)
                    self.sprite_online.draw(screen)

        # ===== 右上角按鈕 =====
        self.setting_button.draw(screen)
        self.bag_button.draw(screen)

        # ====== overlay 覆蓋層 ======
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

        # ====== 把敵人確認視窗畫在最上面 !!! ======
        for enemy in self.game_manager.current_enemy_trainers:
            if hasattr(enemy, "show_confirm_dialog") and enemy.show_confirm_dialog:
                enemy._draw_confirm_dialog(screen)

        # ====== 彈窗（popup）=====
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

    # ====== Bush / Pokemon 草叢偵測 ======
    def _is_player_on_bush_tile(self) -> bool:
        """回傳玩家現在這一格是不是 PokemonBush 圖層的草叢"""
        player = self.game_manager.player
        if player is None:
            return False

        tmx = self.game_manager.current_map.tmxdata

        # 找到 Tiled 裡的 PokemonBush 圖層
        try:
            bush_layer = tmx.get_layer_by_name("PokemonBush")
        except ValueError:
            # 地圖沒有這個圖層就直接略過
            return False

        # 只處理 TileLayer
        if not isinstance(bush_layer, pytmx.TiledTileLayer):
            return False

        # 以玩家中心點算 tile 座標
        px = player.position.x + GameSettings.TILE_SIZE / 2
        py = player.position.y + GameSettings.TILE_SIZE / 2
        tile_x = int(px // GameSettings.TILE_SIZE)
        tile_y = int(py // GameSettings.TILE_SIZE)

        # 邊界檢查
        if tile_x < 0 or tile_y < 0 or tile_x >= tmx.width or tile_y >= tmx.height:
            return False

        # 在該圖層取出這一格的 gid，0 代表沒有放 tile
        gid = bush_layer.data[tile_y][tile_x]
        return gid != 0

    def _update_bush_state(self) -> None:
        """偵測玩家是否剛踏進 / 離開草叢，踏進去就進 wild 戰鬥"""
        on_bush = self._is_player_on_bush_tile()

        # 剛踏進草叢的一瞬間（上一幀不在，這一幀在）
        if on_bush and not self._was_on_bush:
            Logger.info("Player stepped into PokemonBush")
            # ★ 每次進 Wild，都用「目前這一份 bag」建立 WildScene
            scene_manager.register_scene("wild", WildScene(self.game_manager.bag))
            scene_manager.change_scene("wild")

        self._was_on_bush = on_bush
