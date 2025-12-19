# src/entities/shop_npc.py

from __future__ import annotations

import pygame as pg
from typing import override

from src.entities.entity import Entity
from src.sprites import Sprite
from src.utils import GameSettings, Position, PositionCamera, Direction

if False:  # typing only
    from src.game_manager import GameManager


class ShopNPC(Entity):
    def __init__(self, x: int, y: int, game_manager: "GameManager", sprite_name: str, shop_id: str = "default"):
        super().__init__(x, y, game_manager, sprite_name)
        self.shop_id = shop_id

        # 互動範圍（玩家不用貼太近）
        self.interact_rect = pg.Rect(0, 0, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE).inflate(16, 16)

        # ✅ 商店按鈕 icon（永遠顯示 + 漂浮）
        self.shop_hint_icon = Sprite(
            "UI/button_shop.png",
            (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2),
        )

        # 玩家是否在互動範圍內（你在 GameScene 會設定 detected）
        self.detected = False

        self.facing: Direction | None = None

        # 漂浮動畫用
        self._float_t: float = 0.0

    def _get_rect(self) -> pg.Rect:
        return pg.Rect(
            int(self.position.x),
            int(self.position.y),
            GameSettings.TILE_SIZE,
            GameSettings.TILE_SIZE,
        )

    def _update_hint_icon_pos(self) -> None:
        """
        icon 永遠在 NPC 頭上，並做上下漂浮動畫
        """
        # 漂浮：每秒來回，幅度 4px（你可調）
        float_amp = 4
        float_speed = 5.0  # 越大越快

        # 用 sin 需要 import math，但我們避免多 import：用 pygame 的時間也行
        # 這裡用 self._float_t 累積時間做簡單 sin
        import math
        offset_y = int(math.sin(self._float_t * float_speed) * float_amp)

        self.shop_hint_icon.update_pos(
            Position(
                self.position.x + GameSettings.TILE_SIZE // 4,
                self.position.y - GameSettings.TILE_SIZE // 2 + offset_y,
            )
        )

    def can_interact(self, player_rect: pg.Rect) -> bool:
        r = self._get_rect()
        self.interact_rect.topleft = r.topleft
        return self.interact_rect.colliderect(player_rect)

    def interact(self, game_scene) -> None:
        game_scene.open_shop_overlay(self.shop_id)

    @override
    def update(self, dt: float) -> None:
        # 漂浮動畫時間累積
        self._float_t += float(dt)
        self._update_hint_icon_pos()

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)

        # ✅ icon 永遠顯示（不管 detected）
        self.shop_hint_icon.draw(screen, camera)

        # 文字提示：仍然只有靠近才顯示（不想要的話把 if 拿掉）
        if self.detected:
            self._draw_interact_hint(screen)

    def _draw_interact_hint(self, screen: pg.Surface) -> None:
        font = pg.font.SysFont(None, 20)
        text = font.render("Press E to shop", True, (255, 255, 255))

        bg_rect = pg.Rect(0, 0, text.get_width() + 16, text.get_height() + 8)
        bg_rect.midbottom = (GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT - 8)

        pg.draw.rect(screen, (0, 0, 0), bg_rect)
        pg.draw.rect(screen, (255, 255, 255), bg_rect, 1)
        screen.blit(text, (bg_rect.x + 8, bg_rect.y + 4))

    # -----------------------------
    # Storage
    # -----------------------------
    @classmethod
    def from_dict(cls, data: dict, game_manager: "GameManager") -> "ShopNPC":
        x = int(data.get("x", 0)) * GameSettings.TILE_SIZE
        y = int(data.get("y", 0)) * GameSettings.TILE_SIZE
        sprite = data.get("sprite", "ow10.png")
        shop_id = data.get("shop_id", "default")

        npc = cls(x, y, game_manager, sprite, shop_id=shop_id)

        facing_val = data.get("facing")
        if facing_val:
            try:
                npc.facing = Direction(str(facing_val))
            except Exception:
                npc.facing = None

        return npc

    def to_dict(self) -> dict:
        return {
            "x": self.position.x / GameSettings.TILE_SIZE,
            "y": self.position.y / GameSettings.TILE_SIZE,
            "facing": self.facing.value if self.facing else None,
            "shop_id": self.shop_id,
            "sprite": getattr(self, "sprite_name", None) or "ow10.png",
        }
