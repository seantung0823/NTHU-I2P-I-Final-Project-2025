import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override


class SettingScene(Scene):

    # 全遊戲共用的設定狀態
    volume: float = 0.5   # 0.0 ~ 1.0
    muted: bool = False

    # 滑桿互動狀態（class 變數，Scene 和 overlay 共用）
    _slider_dragging: bool = False
    _mouse_was_down: bool = False

    background: BackgroundSprite
    back_button: Button
    
    def __init__(self):
        super().__init__()
        self.background = BackgroundSprite("backgrounds/background1.png")

        wid_mid, hig_mid = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2
        self.panel_rect = pg.Rect(
            wid_mid - 480 // 2,
            hig_mid - 420 // 2,
            480, 420
        )

        # 左下角返回按鈕（在 SettingScene 裡是直接回 menu）
        self.back_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            self.panel_rect.left + 20,
            self.panel_rect.bottom - 100,
            80, 80,
            lambda: scene_manager.change_scene("menu")
        )
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 101 Opening (Part 1).ogg")

    @override
    def exit(self) -> None:
        pass

    # === 音量實際套用到聲音系統 ===
    @staticmethod
    def _apply_volume_to_audio() -> None:
        actual = 0.0 if SettingScene.muted else SettingScene.volume

        # 之後新的 BGM 播放時，play_bgm 會用到這個值
        GameSettings.AUDIO_VOLUME = actual

        # 如果現在有正在播的 BGM，就直接改它的音量
        bgm = getattr(sound_manager, "current_bgm", None)
        if bgm is not None:
            try:
                bgm.set_volume(actual)
            except Exception:
                pass

    @staticmethod
    def _set_volume_from_mouse(mouse_x: int, bar_x: int, bar_width: int, handle_width: int) -> None:
        rel = (mouse_x - (bar_x + handle_width / 2)) / (bar_width - handle_width)
        SettingScene.volume = max(0.0, min(1.0, rel))
        SettingScene._apply_volume_to_audio()

    # === 共用的「處理滑桿與 Mute 點擊」邏輯 ===
    @staticmethod
    def handle_panel_input(panel_rect: pg.Rect) -> None:
        mouse_pos = pg.mouse.get_pos()
        mouse_down = pg.mouse.get_pressed()[0]

        # Volume bar 幾何
        bar_x = panel_rect.left + 40
        bar_y = panel_rect.top + 80
        bar_width = panel_rect.width - 80
        bar_height = 16
        bar_rect = pg.Rect(bar_x, bar_y, bar_width, bar_height)

        handle_width = 20
        handle_x = bar_x + int(SettingScene.volume * (bar_width - handle_width))
        handle_y = bar_y - 4
        handle_rect = pg.Rect(handle_x, handle_y, handle_width, bar_height + 8)

        # Mute 開關幾何
        mute_label_y = panel_rect.top + 140
        mute_box_width, mute_box_height = 60, 28
        mute_box_x = panel_rect.left + 140
        mute_box_y = mute_label_y - 4
        mute_rect = pg.Rect(mute_box_x, mute_box_y, mute_box_width, mute_box_height)

        # 剛按下滑鼠左鍵那一瞬間
        if mouse_down and not SettingScene._mouse_was_down:
            if handle_rect.collidepoint(mouse_pos) or bar_rect.collidepoint(mouse_pos):
                SettingScene._slider_dragging = True
                SettingScene._set_volume_from_mouse(mouse_pos[0], bar_x, bar_width, handle_width)
            elif mute_rect.collidepoint(mouse_pos):
                SettingScene.muted = not SettingScene.muted
                SettingScene._apply_volume_to_audio()

        # 按住滑桿拖曳
        if SettingScene._slider_dragging and mouse_down:
            SettingScene._set_volume_from_mouse(mouse_pos[0], bar_x, bar_width, handle_width)

        # 放開滑鼠就結束拖曳
        if not mouse_down:
            SettingScene._slider_dragging = False

        SettingScene._mouse_was_down = mouse_down

    @override
    def update(self, dt: float) -> None:
        # ESC 回主選單
        if input_manager.key_pressed(pg.K_ESCAPE):
            scene_manager.change_scene("menu")
            return
        
        self.back_button.update(dt)

        # 處理滑桿 & Mute
        SettingScene.handle_panel_input(self.panel_rect)

    # === 畫出設定面板（Scene 本身 + overlay 都共用） ===
    @staticmethod
    def draw_panel(
        screen: pg.Surface,
        panel_rect: pg.Rect,
        back_button: Button | None,
        bottom_buttons: list[Button] | None = None
    ) -> None:
        # panel 底色與外框
        pg.draw.rect(screen, (231, 161, 74), panel_rect)
        pg.draw.rect(screen, (82, 44, 32), panel_rect, 5)

        # 標題
        font = pg.font.SysFont(None, 40)
        title = font.render("SETTINGS", True, (20, 20, 20))
        screen.blit(title, (panel_rect.left + 20, panel_rect.top + 10))


        # 目前音量/靜音狀態
        volume = SettingScene.volume
        muted = SettingScene.muted

        # Volume 標籤 + 百分比
        text_font = pg.font.SysFont(None, 32)
        vol_percent = int(volume * 100)
        vol_label = text_font.render(f"Volume: {vol_percent}%", True, (20, 20, 20))
        vol_label_x = panel_rect.left + 40
        vol_label_y = panel_rect.top + 70 - 20
        screen.blit(vol_label, (vol_label_x, vol_label_y))

        # Volume bar
        bar_x = panel_rect.left + 40
        bar_y = panel_rect.top + 80
        bar_width = panel_rect.width - 80
        bar_height = 16
        bar_rect = pg.Rect(bar_x, bar_y, bar_width, bar_height)
        pg.draw.rect(screen, (230, 230, 230), bar_rect)
        pg.draw.rect(screen, (150, 150, 150), bar_rect, 2)

        # Slider handle
        handle_width = 20
        handle_x = bar_x + int(volume * (bar_width - handle_width))
        handle_y = bar_y - 4
        handle_rect = pg.Rect(handle_x, handle_y, handle_width, bar_height + 8)
        pg.draw.rect(screen, (245, 245, 245), handle_rect)
        pg.draw.rect(screen, (82, 44, 32), handle_rect, 2)

        # Mute 標籤 + 開關
        mute_label_y = panel_rect.top + 140
        mute_label = text_font.render(f"Mute: {'On' if muted else 'Off'}", True, (20, 20, 20))
        screen.blit(mute_label, (panel_rect.left + 40, mute_label_y))

        mute_box_width, mute_box_height = 60, 28
        mute_box_x = panel_rect.left + 140
        mute_box_y = mute_label_y - 4
        mute_rect = pg.Rect(mute_box_x, mute_box_y, mute_box_width, mute_box_height)
        pg.draw.rect(screen, (245, 245, 245), mute_rect)
        pg.draw.rect(screen, (82, 44, 32), mute_rect, 2)

        # 裡面的滑塊
        knob_margin = 4
        knob_width = (mute_box_width // 2) - knob_margin
        if muted:
            knob_x = mute_box_x + mute_box_width // 2
        else:
            knob_x = mute_box_x + knob_margin
        knob_rect = pg.Rect(
            knob_x,
            mute_box_y + knob_margin,
            knob_width,
            mute_box_height - 2 * knob_margin,
        )
        pg.draw.rect(screen, (200, 200, 200), knob_rect)
        pg.draw.rect(screen, (82, 44, 32), knob_rect, 1)

        # Back 按鈕 + 提示文字
        small_font = pg.font.SysFont(None, 28)
        hint_text = small_font.render("Press ESC to close", True, (20, 20, 20))

        if back_button is not None:
            back_button.draw(screen)
            hint_x = back_button.hitbox.right + 10
            hint_y = back_button.hitbox.centery - hint_text.get_height() // 2
            screen.blit(hint_text, (hint_x, hint_y))

        # ★ 遊戲 overlay 用：底下一排按鈕（例如你那 3 顆方塊）
        if bottom_buttons:
            for btn in bottom_buttons:
                btn.draw(screen)

    @override
    def draw(self, screen: pg.Surface) -> None:
        self.background.draw(screen)
        SettingScene.draw_panel(screen, self.panel_rect, self.back_button)
