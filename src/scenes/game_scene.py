import pygame as pg
import threading
import time

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager
from src.sprites import Sprite
from typing import override

import pytmx

class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite
    
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