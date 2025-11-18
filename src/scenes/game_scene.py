import pygame as pg
import threading
import time

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager
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
    overlay_back_button: Button
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
        self.sprite_online = Sprite("ingame_ui/options1.png", (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))

        # ====== 設定 overlay 狀態 ======
        self.is_setting_open = False

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

        # 右上角打開設定的按鈕
        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            sw - 16 - 60,   # 離右邊 16px
            16,             # 離上面 16px
            60, 60,
            lambda: self.open_setting_overlay()
        )

        # 做一個跟 SettingScene 一樣大小的 panel（置中 480x420）
        wid_mid, hig_mid = sw // 2, sh // 2
        self.panel_rect = pg.Rect(wid_mid - 480 // 2, hig_mid - 420 // 2, 480, 420)

        # overlay 裡的返回按鈕：位置對應 SettingScene.draw_panel 的邏輯
        self.overlay_back_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            self.panel_rect.left + 20,
            self.panel_rect.bottom - 100,
            80, 80,
            lambda: self.close_setting_overlay()
        )

    def open_setting_overlay(self):
        self.is_setting_open = True

    def close_setting_overlay(self):
        self.is_setting_open = False

    @override
    def enter(self) -> None:
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
            if pg.key.get_pressed()[pg.K_ESCAPE]:
                self.close_setting_overlay()

            # 更新 Back 按鈕（overlay 版本）
            self.overlay_back_button.update(dt)
            # 使用跟 SettingScene 一樣的滑桿 / Mute 互動邏輯
            SettingScene.handle_panel_input(self.panel_rect)
            return
        
        # Update player and other data
        if self.game_manager.player:
            self.game_manager.player.update(dt)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)
            
        # Update others
        self.game_manager.bag.update(dt)
        
        if self.game_manager.player is not None and self.online_manager is not None:
            _ = self.online_manager.update(
                self.game_manager.player.position.x, 
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name
            )
        
        # Check if there is assigned next scene
        self.game_manager.try_switch_map()
        
    @override
    def draw(self, screen: pg.Surface):        
        # 先決定 camera 要用什麼
        if self.game_manager.player:
            # 把玩家自己的 camera 拿出來用
            camera = self.game_manager.player.camera
        else:
            # 沒玩家就固定用 (0, 0)
            camera = PositionCamera(0, 0)

        # 先畫地圖
        self.game_manager.current_map.draw(screen, camera)

        # 再畫玩家（如果有）
        if self.game_manager.player:
            self.game_manager.player.draw(screen, camera)

        # 再畫敵人
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)

        # 畫背包 / UI
        self.game_manager.bag.draw(screen)
        
        # 畫線上其他玩家（如果有）
        if self.online_manager and self.game_manager.player:
            list_online = self.online_manager.get_list_players()
            for player in list_online:
                if player["map"] == self.game_manager.current_map.path_name:
                    # 這裡也用同一個 camera
                    pos = camera.transform_position_as_position(
                        Position(player["x"], player["y"])
                    )
                    self.sprite_online.update_pos(pos)
                    self.sprite_online.draw(screen)

        # 固定在最上層的設定按鈕
        self.setting_button.draw(screen)

        # 如果 overlay 有開，就蓋上去
        if self.is_setting_open:
            sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT

            # 半透明黑幕
            dark_surface = pg.Surface((sw, sh), pg.SRCALPHA)
            dark_surface.fill((0, 0, 0, 160))
            screen.blit(dark_surface, (0, 0))

            # 直接使用 SettingScene 的共用畫面
            SettingScene.draw_panel(screen, self.panel_rect, self.overlay_back_button)
