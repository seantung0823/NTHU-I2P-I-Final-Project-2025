import pygame as pg

from src.utils import GameSettings, Logger
from .services import scene_manager, input_manager

from src.scenes.menu_scene import MenuScene
from src.scenes.game_scene import GameScene
from src.scenes.setting_scene import SettingScene
from src.scenes.battle_scene import BattleScene
from src.scenes.wild_scene import WildScene


class Engine:

    screen: pg.Surface              # Screen Display of the Game
    clock: pg.time.Clock            # Clock for FPS control
    running: bool                   # Running state of the game

    def __init__(self):
        Logger.info("Initializing Engine")

        pg.init()

        self.screen = pg.display.set_mode(
            (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT)
        )
        self.clock = pg.time.Clock()
        self.running = True

        pg.display.set_caption(GameSettings.TITLE)

        # 先建立場景實例，特別是 GameScene 要留住，讓 WildScene 可以拿到同一個 Bag
        menu_scene = MenuScene()
        game_scene = GameScene()
        setting_scene = SettingScene()
        
        battle_scene = BattleScene(game_scene.game_manager.bag)
        # 這裡把 game_scene.game_manager.bag 傳進 WildScene
        wild_scene = WildScene(game_scene.game_manager.bag)

        scene_manager.register_scene("menu", menu_scene)
        scene_manager.register_scene("game", game_scene)
        scene_manager.register_scene("setting", setting_scene)
        scene_manager.register_scene("battle", battle_scene)
        scene_manager.register_scene("wild", wild_scene)

        # 你這行原本是用 SettingScene 當 "bag" scene，其實完全沒用到可以刪掉：
        # scene_manager.register_scene("bag", SettingScene())

        '''
        [TODO HACKATHON 5]
        Register the setting scene here
        '''
        scene_manager.change_scene("menu")

    def run(self):
        Logger.info("Running the Game Loop ...")

        while self.running:
            dt = self.clock.tick(GameSettings.FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.render()

    def handle_events(self):
        input_manager.reset()
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            input_manager.handle_events(event)

    def update(self, dt: float):
        scene_manager.update(dt)

    def render(self):
        self.screen.fill((0, 0, 0))     # Make sure the display is cleared
        scene_manager.draw(self.screen) # Draw the current scene
        pg.display.flip()               # Render the display
