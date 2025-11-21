# src/scenes/battle_scene.py

from __future__ import annotations
import pygame as pg
from typing import override

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.core.services import scene_manager, input_manager
from src.sprites import BackgroundSprite


class BattleScene(Scene):
    """
    基礎版 BattleScene：
    - 上面：background1.png 當背景
    - 下面：一條黑色對話框
    - 先不做戰鬥系統，只確認場景有切成功。
    """

    background: BackgroundSprite

    @override
    def __init__(self) -> None:
        super().__init__()

        # 背景圖片（assets/images/backgrounds/background1.png）
        self.background = BackgroundSprite("backgrounds/background1.png")

        # 文字
        pg.font.init()
        self.font_small = pg.font.Font(None, 20)
        self.font_medium = pg.font.Font(None, 26)

        # 對話框區域（畫面下方一條黑色框）
        self.dialog_height = 100
        self.dialog_rect = pg.Rect(
            0,
            GameSettings.SCREEN_HEIGHT - self.dialog_height,
            GameSettings.SCREEN_WIDTH,
            self.dialog_height,
        )

        # 先隨便放一句話，之後可以改成戰鬥文字
        self.message = "Rival challenged you to a battle!"

    @override
    def enter(self) -> None:
        # 之後如果要播戰鬥 BGM，可以在這裡呼叫 sound_manager.play_bgm(...)
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        # 目前先簡單：按 ESC 回到 game scene
        if input_manager.key_pressed(pg.K_ESCAPE):
            scene_manager.change_scene("game")

    @override
    def draw(self, screen: pg.Surface) -> None:
        # 先畫背景
        self.background.draw(screen)

        # 畫底下黑色對話框
        pg.draw.rect(screen, (0, 0, 0), self.dialog_rect)

        # 對話框文字（左上角）
        text = self.font_medium.render(self.message, True, (255, 255, 255))
        screen.blit(
            text,
            (self.dialog_rect.left + 16, self.dialog_rect.top + 16),
        )

        # 右下角提示字（可有可無）
        hint = self.font_small.render("Press ESC to return", True, (200, 200, 100))
        screen.blit(
            hint,
            (
                self.dialog_rect.right - hint.get_width() - 16,
                self.dialog_rect.bottom - hint.get_height() - 8,
            ),
        )
