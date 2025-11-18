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

        # ====== 設定 overlay 狀態 ======
        self.is_setting_open = False

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        # 右上角：打開設定 overlay
        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            sw - 16 - 60,   # 離右邊 16 px
            16,             # 離上方 16 px
            60, 60,
            lambda: self.open_setting_overlay()
        )

        # 設定面板（跟 SettingScene 一樣大小，置中）
        wid_mid, hig_mid = sw // 2, sh // 2
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 420 // 2,
            480, 420
        )

        # ====== 下方一排三顆按鈕：Save / Menu / Back ======
        btn_size = 80
        gap = 20

        # 靠 panel 左邊、在中間偏下的位置
        start_x = self.panel_rect.left + 40
        row_y = self.panel_rect.top + 190

        # 左：存檔（之後可接真正存檔功能）
        save_button = Button(
            "UI/button_save.png", "UI/button_save_hover.png",
            start_x, row_y,
            btn_size, btn_size,
            lambda: None
        )

        # 中：回主選單
        menu_button = Button(
            "UI/button_load.png", "UI/button_load_hover.png",
            start_x + (btn_size + gap), row_y,
            btn_size, btn_size,
            lambda: None
        )

        # 右：回到遊戲（關閉設定 overlay）
        back_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            start_x + (btn_size + gap) * 2, row_y,
            btn_size, btn_size,
            lambda: scene_manager.change_scene("menu")
        )

        # 交給 SettingScene.draw_panel 畫下面那一排
        self.bottom_buttons = [save_button, menu_button, back_button]

        # ====== 面板右上角的叉叉（button_x）：只關閉設定 ======
        close_size = 40
        close_x = self.panel_rect.right - close_size - 10
        close_y = self.panel_rect.top + 10
        self.overlay_close_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            close_x, close_y,
            close_size, close_size,
            lambda: self.close_setting_overlay()
        )

    # 打開 / 關閉 overlay
    def open_setting_overlay(self):
        self.is_setting_open = True

    def close_setting_overlay(self):
        self.is_setting_open = False

    @override
    def enter(self) -> None:
        # 回GameScene，一律關掉設定視窗（解決 game -> menu -> game setting還開著的問題）
        self.is_setting_open = False

        sound_manager.play_bgm("RBY 103 Pallet Town.ogg")
        if self.online_manager:
            self.online_manager.enter()
        
    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()
        
    @override
    def update(self, dt: float):
        # 先更新右上角設定按鈕
        self.setting_button.update(dt)

        # 如果設定畫面打開，只處理設定，不跑遊戲邏輯
        if self.is_setting_open:
            # ESC 關閉
            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.close_setting_overlay()

            # 更新下方三顆按鈕
            for btn in self.bottom_buttons:
                btn.update(dt)

            # 更新右上叉叉
            self.overlay_close_button.update(dt)

            # 使用 SettingScene 一樣的滑桿 / Mute 互動邏輯
            SettingScene.handle_panel_input(self.panel_rect)
            return
        
        # ====== 以下是原本的遊戲更新邏輯 ======
        if self.game_manager.player:
            self.game_manager.player.update(dt)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)
            
        self.game_manager.bag.update(dt)
        
        if self.game_manager.player is not None and self.online_manager is not None:
            _ = self.online_manager.update(
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

        # 地圖
        self.game_manager.current_map.draw(screen, camera)

        # 玩家
        if self.game_manager.player:
            self.game_manager.player.draw(screen, camera)

        # 敵人
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)

        # 背包 / UI
        self.game_manager.bag.draw(screen)
        
        # 線上其他玩家
        if self.online_manager and self.game_manager.player:
            list_online = self.online_manager.get_list_players()
            for player in list_online:
                if player["map"] == self.game_manager.current_map.path_name:
                    pos = camera.transform_position_as_position(
                        Position(player["x"], player["y"])
                    )
                    self.sprite_online.update_pos(pos)
                    self.sprite_online.draw(screen)

        # 固定在最上層的設定按鈕
        self.setting_button.draw(screen)

        # 如果 overlay 有開，就疊上去
        if self.is_setting_open:
            sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

            # 半透明黑幕
            dark_surface = pg.Surface((sw, sh), pg.SRCALPHA)
            dark_surface.fill((0, 0, 0, 160))
            screen.blit(dark_surface, (0, 0))

            # 用 SettingScene 畫上半部設定面板（Volume/Mute）＋下面三顆大按鈕
            SettingScene.draw_panel(
                screen,
                self.panel_rect,
                back_button=None,                  # 不用 SettingScene 自帶的 back
                bottom_buttons=self.bottom_buttons  # 使用我們自訂的一列按鈕
            )

            # 畫右上角叉叉
            self.overlay_close_button.draw(screen)

            # 左下角提示文字：「Press ESC to close」
            small_font = pg.font.SysFont(None, 28)
            hint_text = small_font.render("Press ESC to close", True, (20, 20, 20))
            hint_x = self.panel_rect.left + 20
            hint_y = self.panel_rect.bottom - hint_text.get_height() - 10
            screen.blit(hint_text, (hint_x, hint_y))
