import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, input_manager
from typing import override

# 直接沿用 SettingScene 的音量 / Mute / 滑桿邏輯
from src.scenes.setting_scene import SettingScene


class SettingGameScene(Scene):
    """
    遊戲中的「設定」獨立場景。
    外觀：跟圖片一樣，上面是 SETTINGS + Volume + Mute，
    下面一排三顆大按鈕，右邊那顆用來回到 GameScene。
    """

    background: BackgroundSprite

    def __init__(self):
        super().__init__()
        self.background = BackgroundSprite("backgrounds/background1.png")

        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        wid_mid, hig_mid = sw // 2, sh // 2

        # 設定面板（比整個畫面小一點，置中）
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 260 // 2,
            480, 260
        )

        # ===== 下方三顆大按鈕（圖檔你可以之後自己改） =====
        btn_size = 80
        gap = 20
        total_w = btn_size * 3 + gap * 2
        start_x = wid_mid - total_w // 2
        y = self.panel_rect.bottom + 40

        # 左邊：例如「狀態」或其他功能（目前只是佔位）
        self.left_button = Button(
            "UI/button_play.png",          # TODO: 換成你自己的 icon
            "UI/button_play_hover.png",
            start_x,
            y,
            btn_size,
            btn_size,
            lambda: None                   # 之後你可以改成真正功能
        )

        # 中間：之後可以改成「存檔」
        self.middle_button = Button(
            "UI/button_setting.png",       # TODO: 換成存檔 icon
            "UI/button_setting_hover.png",
            start_x + (btn_size + gap),
            y,
            btn_size,
            btn_size,
            lambda: None                   # TODO: 改成你的存檔邏輯
        )

        # 右邊：回到遊戲（跟圖片中的返回按鈕）
        self.right_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            start_x + (btn_size + gap) * 2,
            y,
            btn_size,
            btn_size,
            lambda: scene_manager.change_scene("game")
        )

    @override
    def enter(self) -> None:
        # 不重新播放 BGM，沿用 GameScene 的音樂
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        # ESC 直接回到遊戲
        if input_manager.key_pressed(pg.K_ESCAPE):
            scene_manager.change_scene("game")
            return

        # 更新三顆按鈕
        self.left_button.update(dt)
        self.middle_button.update(dt)
        self.right_button.update(dt)

        # 使用 SettingScene 的滑桿 / Mute 互動邏輯
        SettingScene.handle_panel_input(self.panel_rect)

    @override
    def draw(self, screen: pg.Surface) -> None:
        # 橘色背景
        self.background.draw(screen)

        # 上方設定面板：用 SettingScene.draw_panel，但不給 back_button
        SettingScene.draw_panel(screen, self.panel_rect, back_button=None)

        # 畫下面三顆大按鈕
        self.left_button.draw(screen)
        self.middle_button.draw(screen)
        self.right_button.draw(screen)

        # 左下角提示文字：「Press ESC to close」
        small_font = pg.font.SysFont(None, 28)
        hint_text = small_font.render("Press ESC to close", True, (20, 20, 20))
        screen.blit(hint_text, (40, GameSettings.SCREEN_HEIGHT - 60))
