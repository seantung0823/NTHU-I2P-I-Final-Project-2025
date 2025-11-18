import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override

# 共用 SettingScene 的面板畫圖 & 處理邏輯
from src.scenes.setting_scene import SettingScene


class MenuScene(Scene):
    background: BackgroundSprite
    play_button: Button
    setting_button: Button
    quit_button: Button

    def __init__(self):
        super().__init__()
        self.background = BackgroundSprite("backgrounds/background1.png")

        px, py = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT * 3 // 4
        
        # ▶ Play：進入遊戲
        self.play_button = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            px - 50 + 120, py, 100, 100,
            lambda: scene_manager.change_scene("game")
        )

        # ▶ Setting：打開 / 關閉 overlay，不切場景
        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            px - 50, py, 100, 100,
            lambda: self.toggle_setting_overlay()
        )

        # ▶ Quit：離開遊戲
        self.quit_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            px - 50 - 120, py, 100, 100,
            lambda: pg.event.post(pg.event.Event(pg.QUIT))
        )

        # ==== 設定 overlay 狀態 ====
        self.show_setting_overlay = False

        # 跟 SettingScene 一樣尺寸的 panel
        cx, cy = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2
        self.setting_panel_rect = pg.Rect(
            cx - 480 // 2,
            cy - 420 // 2,
            480, 420
        )

        # 左下角 back 按鈕：只關閉 overlay（不換場景）
        self.setting_back_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            self.setting_panel_rect.left + 20,
            self.setting_panel_rect.bottom - 100,
            80, 80,
            lambda: self.toggle_setting_overlay()
        )

    # 切換 overlay 顯示
    def toggle_setting_overlay(self):
        self.show_setting_overlay = not self.show_setting_overlay
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 101 Opening (Part 1).ogg")

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        # 如果設定視窗打開，只處理設定視窗
        if self.show_setting_overlay:
            self.setting_back_button.update(dt)
            SettingScene.handle_panel_input(self.setting_panel_rect)

            # ESC 也可以關閉 overlay
            if input_manager.key_pressed(pg.K_ESCAPE):
                self.show_setting_overlay = False
            return

        # 平常 Menu 的操作
        if input_manager.key_pressed(pg.K_SPACE):
            scene_manager.change_scene("game")
            return

        self.play_button.update(dt)
        self.setting_button.update(dt)
        self.quit_button.update(dt)

    @override
    def draw(self, screen: pg.Surface) -> None:
        # 背景 + 3 顆主選單按鈕
        self.background.draw(screen)
        self.play_button.draw(screen)
        self.setting_button.draw(screen)
        self.quit_button.draw(screen)

        # 疊上設定視窗（跟 SettingScene 長一樣）
        if self.show_setting_overlay:
            # （可選）加一層淡淡的暗幕
            dim = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dim.fill((0, 0, 0, 80))
            screen.blit(dim, (0, 0))

            SettingScene.draw_panel(
                screen,
                self.setting_panel_rect,
                self.setting_back_button
            )
