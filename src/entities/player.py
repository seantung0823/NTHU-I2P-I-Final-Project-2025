from __future__ import annotations
import pygame as pg
from .entity import Entity
from src.core.services import input_manager
from src.utils import Position, PositionCamera, GameSettings, Logger
from src.core import GameManager
import math
from typing import override

class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    game_manager: GameManager

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager) 


    def get_rect(self) -> pg.Rect:
        # 先用一格大小，之後覺得碰撞太大再縮
        return pg.Rect(int(self.position.x),int(self.position.y),GameSettings.TILE_SIZE,GameSettings.TILE_SIZE)  


    @override
    def update(self, dt: float) -> None:
        dis = Position(0, 0)

        '''
        [TODO HACKATHON 2]
        Calculate the distance change, and then normalize the distance
        '''
        
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= 1
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += 1
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= 1
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += 1

        length = math.sqrt(dis.x**2 + dis.y**2) # 避免斜著走比較快

        if length != 0:
            dis.x = dis.x / length * self.speed * dt
            dis.y = dis.y / length * self.speed * dt   

        self.position.x += dis.x
        if self.game_manager.check_collision(self.get_rect()):
            self.position.x = self._snap_to_grid(self.position.x)
        
        self.position.y += dis.y
        if self.game_manager.check_collision(self.get_rect()):
            self.position.y = self._snap_to_grid(self.position.y)


        '''
        
        [TODO HACKATHON 4]
        Check if there is collision, if so try to make the movement smooth
        Hint #1 : use entity.py _snap_to_grid function or create a similar function
        Hint #2 : Beware of glitchy teleportation, you must do
                    1. Update X
                    2. If collide, snap to grid
                    3. Update Y
                    4. If collide, snap to grid
                  instead of update both x, y, then snap to grid
        
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= ...
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += ...
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= ...
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += ...
        
        self.position = ...
        '''

         # 這一幀如果「不在傳送區」，就更新安全位置
        if not self.game_manager.current_map.check_teleport(self.position):
            self.game_manager.last_positions[self.game_manager.current_map_key] = self.position.copy()
        
        # Check teleportation
        tp = self.game_manager.current_map.check_teleport(self.position)
        if tp:
            dest = tp.destination
            self.game_manager.switch_map(dest)
            return 
                
        super().update(dt)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        
    @override
    def to_dict(self) -> dict[str, object]:
        return super().to_dict()
    
    @property
    @override
    def camera(self) -> PositionCamera:
        return PositionCamera(int(self.position.x) - GameSettings.SCREEN_WIDTH // 2, int(self.position.y) - GameSettings.SCREEN_HEIGHT // 2)
            
    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> Player:
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)

