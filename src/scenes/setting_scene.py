import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override


class SettingScene(Scene):
    # Background Image
    background: BackgroundSprite
    # Buttons
    back_button: Button
    
    def __init__(self):
        super().__init__()
        self.background = BackgroundSprite("backgrounds/background1.png")

        wid_mid, hig_mid = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2
        self.panel_rect = pg.Rect(wid_mid - 480 // 2, hig_mid - 420 // 2, 480, 420)

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
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        if input_manager.key_pressed(pg.K_ESCAPE):
            scene_manager.change_scene("menu")
            return
        
        self.back_button.update(dt)


    @override
    def draw(self, screen: pg.Surface) -> None:
        self.background.draw(screen)

        pg.draw.rect(screen, (231, 161, 74), self.panel_rect)
        pg.draw.rect(screen, (82, 44, 32), self.panel_rect, 5)   

        font = pg.font.SysFont(None, 40)
        title = font.render("SETTINGS", True, (20, 20, 20))
        screen.blit(title, (self.panel_rect.left + 20, self.panel_rect.top + 10))
        
        # 🔸 在按鈕右邊加上文字
        text_font = pg.font.SysFont(None, 28)
        hint_text = text_font.render("Press ESC to exit", True, (20, 20, 20))

        # 放在返回按鈕右邊
        hint_x = self.back_button.hitbox.right + 10
        hint_y = self.back_button.hitbox.centery - hint_text.get_height() // 2
        screen.blit(hint_text, (hint_x, hint_y))

        self.back_button.draw(screen)   
