from __future__ import annotations
import pygame as pg
from .entity import Entity
from src.core.services import input_manager
from src.utils import Position, PositionCamera, GameSettings
from src.core import GameManager
import math
from typing import override

class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    game_manager: GameManager

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager)

        # ===== 新增：角色方向與動畫 =====
        # 你要把路徑改成你專案實際的 ow1.png 位置
        self._sheet = pg.image.load("assets/images/character/ow1.png").convert_alpha()

        self._frame_w = self._sheet.get_width() // 4
        self._frame_h = self._sheet.get_height() // 4

        # 行(row) 對應方向：常見是 down, left, right, up
        self.ROW = {"DOWN": 0, "LEFT": 1, "RIGHT": 2, "UP": 3}

        self.facing = "DOWN"
        self._moving = False

        # 走路動畫：用前三格 0,1,2 循環（站著用 1）
        self._walk_frames = [0, 1, 2, 1]  # 走起來比較順
        self._walk_i = 0
        self._anim_timer = 0.0
        self._anim_fps = 8  # 每秒切幾次格（可調）

    def get_rect(self) -> pg.Rect:
        return pg.Rect(int(self.position.x), int(self.position.y),
                       GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)

    @override
    def update(self, dt: float) -> None:
        dis = Position(0, 0)

        # 先用 raw input 決定 facing（不要用正規化後的 dis）
        raw_x = 0
        raw_y = 0

        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            raw_x -= 1
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            raw_x += 1
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            raw_y -= 1
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            raw_y += 1

        # ===== 新增：更新面向 =====
        if raw_x != 0 or raw_y != 0:
            # 你也可以改成「最後按下優先」；這裡用「移動量較大者優先」
            if abs(raw_x) >= abs(raw_y):
                self.facing = "LEFT" if raw_x < 0 else "RIGHT"
            else:
                self.facing = "UP" if raw_y < 0 else "DOWN"

        # ===== 原本移動（保留你斜走正規化）=====
        dis.x = raw_x
        dis.y = raw_y

        length = math.sqrt(dis.x**2 + dis.y**2)
        if length != 0:
            dis.x = dis.x / length * self.speed * dt
            dis.y = dis.y / length * self.speed * dt

        # ===== 新增：更新 moving 狀態 + 動畫 =====
        self._moving = (raw_x != 0 or raw_y != 0)

        if self._moving:
            self._anim_timer += dt
            if self._anim_timer >= 1.0 / self._anim_fps:
                self._anim_timer = 0.0
                self._walk_i = (self._walk_i + 1) % len(self._walk_frames)
        else:
            # 站著：固定站姿（通常用中間那格）
            self._walk_i = 1
            self._anim_timer = 0.0

        # ===== 你原本的碰撞處理（不要改）=====
        self.position.x += dis.x
        if self.game_manager.check_collision(self.get_rect()):
            self.position.x = self._snap_to_grid(self.position.x)

        self.position.y += dis.y
        if self.game_manager.check_collision(self.get_rect()):
            self.position.y = self._snap_to_grid(self.position.y)

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
        # ===== 改成自己畫：用 facing + frame 取出對應小格 =====
        row = self.ROW[self.facing]
        col = self._walk_frames[self._walk_i]  # 0/1/2/1

        src_rect = pg.Rect(col * self._frame_w, row * self._frame_h,
                           self._frame_w, self._frame_h)
        frame = self._sheet.subsurface(src_rect)

        # 縮放到 TILE_SIZE（如果你本來就是同尺寸也沒差）
        frame = pg.transform.scale(frame, (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))

        screen.blit(frame, (int(self.position.x - camera.x), int(self.position.y - camera.y)))

    @property
    @override
    def camera(self) -> PositionCamera:
        return PositionCamera(int(self.position.x) - GameSettings.SCREEN_WIDTH // 2,
                              int(self.position.y) - GameSettings.SCREEN_HEIGHT // 2)

    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> "Player":
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)
