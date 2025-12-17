from __future__ import annotations
import pygame as pg
from enum import Enum
from dataclasses import dataclass
from typing import override

from .entity import Entity
from src.sprites import Sprite
from src.core import GameManager
from src.core.services import input_manager, scene_manager
from src.utils import GameSettings, Direction, Position, PositionCamera


class EnemyTrainerClassification(Enum):
    STATIONARY = "stationary"


@dataclass
class IdleMovement:
    def update(self, enemy_trainer: "EnemyTrainer", dt: float) -> None:
        return


class EnemyTrainer(Entity):
    classification: EnemyTrainerClassification
    max_tiles: int | None
    _movement: IdleMovement

    # line of sight
    los_direction: Direction
    warning_sign: Sprite
    detected: bool

    # dialog
    show_confirm_dialog: bool  # 是否顯示確認視窗

    # 兩個按鈕的 hitbox（給滑鼠點擊用）
    _confirm_rect: pg.Rect | None
    _cancel_rect: pg.Rect | None

    @override
    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        classification: EnemyTrainerClassification = EnemyTrainerClassification.STATIONARY,
        max_tiles: int | None = 2,
        facing: Direction | None = None,
        sprite_name: str = "ow1.png",  # ✅ 新增：可指定 ow2/ow3...
    ) -> None:

        # ✅ 把 sprite_name 傳給 Entity，Entity 才會真的用對圖
        super().__init__(x, y, game_manager, sprite_name)
        self.sprite_name = sprite_name  # 用於存檔/除錯

        self.classification = classification
        self.max_tiles = max_tiles

        if classification == EnemyTrainerClassification.STATIONARY:
            self._movement = IdleMovement()
            if facing is None:
                raise ValueError(
                    "Idle EnemyTrainer requires a 'facing' Direction at instantiation"
                )
            self._set_direction(facing)
        else:
            raise ValueError("Invalid classification")

        # 驚嘆號圖示
        self.warning_sign = Sprite(
            "exclamation.png",
            (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2),
        )
        self.warning_sign.update_pos(
            Position(
                x + GameSettings.TILE_SIZE // 4,
                y - GameSettings.TILE_SIZE // 2,
            )
        )

        self.detected = False
        self.show_confirm_dialog = False

        # 一開始沒有按鈕 hitbox
        self._confirm_rect = None
        self._cancel_rect = None

    # -----------------------------
    # Basic behavior
    # -----------------------------
    def _set_direction(self, direction: Direction) -> None:
        self.direction = direction
        if direction == Direction.RIGHT:
            self.animation.switch("right")
        elif direction == Direction.LEFT:
            self.animation.switch("left")
        elif direction == Direction.DOWN:
            self.animation.switch("down")
        else:
            self.animation.switch("up")
        self.los_direction = self.direction

    @override
    def update(self, dt: float) -> None:
        self._movement.update(self, dt)

        # 檢查玩家是否撞到敵人
        self._has_los_to_player()

        # 這一幀有沒有「剛打開視窗」
        opened_this_frame = False

        # 如果已經偵測到，且目前沒有視窗 → 按 E 才開視窗
        if self.detected and not self.show_confirm_dialog:
            if input_manager.key_pressed(pg.K_e):
                self.show_confirm_dialog = True
                opened_this_frame = True

        # 如果已經有視窗，且不是這一幀才剛打開 → 才處理確認 / 取消
        if self.show_confirm_dialog and not opened_this_frame:
            self._handle_confirm_dialog_input()

        # 位置更新
        self.animation.update_pos(self.position)
        self.warning_sign.update_pos(
            Position(
                self.position.x + GameSettings.TILE_SIZE // 4,
                self.position.y - GameSettings.TILE_SIZE // 2,
            )
        )

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)

        if self.detected:
            self.warning_sign.draw(screen, camera)
            if not self.show_confirm_dialog:
                self._draw_interact_hint(screen)

        if self.show_confirm_dialog:
            self._draw_confirm_dialog(screen)

    # -----------------------------
    # LOS / detection
    # -----------------------------
    def _get_rect(self) -> pg.Rect:
        return pg.Rect(
            int(self.position.x),
            int(self.position.y),
            GameSettings.TILE_SIZE,
            GameSettings.TILE_SIZE,
        )

    def _has_los_to_player(self) -> None:
        player = self.game_manager.player
        if player is None:
            self.detected = False
            self.show_confirm_dialog = False
            return

        enemy_rect = self._get_rect()
        player_rect = player.get_rect()

        # 先用碰撞範圍簡化：靠很近才算
        expanded = enemy_rect.inflate(4, 4)
        if not expanded.colliderect(player_rect):
            self.detected = False
            self.show_confirm_dialog = False
            return

        # 再用 facing 判定是不是「從正面接近」
        px, py = player_rect.center
        ex, ey = enemy_rect.center

        from_front = False
        if self.los_direction == Direction.UP:
            from_front = py < ey
        elif self.los_direction == Direction.DOWN:
            from_front = py > ey
        elif self.los_direction == Direction.LEFT:
            from_front = px < ex
        elif self.los_direction == Direction.RIGHT:
            from_front = px > ex

        self.detected = from_front
        if not self.detected:
            self.show_confirm_dialog = False

    # -----------------------------
    # UI: hint + confirm dialog
    # -----------------------------
    def _draw_interact_hint(self, screen: pg.Surface) -> None:
        font = pg.font.SysFont(None, 20)
        text = font.render("Press E to battle", True, (255, 255, 255))

        bg_rect = pg.Rect(0, 0, text.get_width() + 16, text.get_height() + 8)
        bg_rect.midbottom = (
            GameSettings.SCREEN_WIDTH // 2,
            GameSettings.SCREEN_HEIGHT - 8,
        )

        pg.draw.rect(screen, (0, 0, 0), bg_rect)
        pg.draw.rect(screen, (255, 255, 255), bg_rect, 1)
        screen.blit(text, (bg_rect.x + 8, bg_rect.y + 4))

    def _draw_confirm_dialog(self, screen: pg.Surface) -> None:
        panel_w, panel_h = 260, 130
        panel_rect = pg.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (
            GameSettings.SCREEN_WIDTH // 2,
            GameSettings.SCREEN_HEIGHT // 2,
        )

        overlay = pg.Surface(
            (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT),
            pg.SRCALPHA,
        )
        overlay.fill((0, 0, 0, 100))
        screen.blit(overlay, (0, 0))

        pg.draw.rect(screen, (30, 30, 30), panel_rect)
        pg.draw.rect(screen, (255, 255, 255), panel_rect, 2)

        font = pg.font.SysFont(None, 22)
        small_font = pg.font.SysFont(None, 18)

        title = font.render("Start a battle?", True, (255, 255, 255))
        screen.blit(
            title,
            title.get_rect(center=(panel_rect.centerx, panel_rect.y + 35)),
        )

        txt_confirm = font.render("Confirm", True, (255, 255, 255))
        hint_confirm = small_font.render("(E)", True, (255, 255, 255))
        confirm_width = max(txt_confirm.get_width(), hint_confirm.get_width())

        txt_cancel = font.render("Cancel", True, (255, 255, 255))
        hint_cancel = small_font.render("(Esc)", True, (255, 255, 255))
        cancel_width = max(txt_cancel.get_width(), hint_cancel.get_width())

        content_w = max(confirm_width, cancel_width)
        btn_w = content_w + 20
        btn_h = 34
        gap = 20

        btn_confirm = pg.Rect(0, 0, btn_w, btn_h)
        btn_cancel = pg.Rect(0, 0, btn_w, btn_h)

        btn_confirm.center = (
            panel_rect.centerx - (btn_w // 2 + gap // 2),
            panel_rect.y + 90,
        )
        btn_cancel.center = (
            panel_rect.centerx + (btn_w // 2 + gap // 2),
            panel_rect.y + 90,
        )

        for rect in (btn_confirm, btn_cancel):
            pg.draw.rect(screen, (70, 70, 70), rect)
            pg.draw.rect(screen, (255, 255, 255), rect, 2)

        screen.blit(
            txt_confirm,
            txt_confirm.get_rect(
                center=(btn_confirm.centerx, btn_confirm.centery - 6)
            ),
        )
        screen.blit(
            hint_confirm,
            hint_confirm.get_rect(
                center=(btn_confirm.centerx, btn_confirm.centery + 8)
            ),
        )

        screen.blit(
            txt_cancel,
            txt_cancel.get_rect(center=(btn_cancel.centerx, btn_cancel.centery - 6)),
        )
        screen.blit(
            hint_cancel,
            hint_cancel.get_rect(center=(btn_cancel.centerx, btn_cancel.centery + 8)),
        )

        self._confirm_rect = btn_confirm
        self._cancel_rect = btn_cancel

    def _handle_confirm_dialog_input(self) -> None:
        # 按 E 或 Enter：確認 → 進 battle
        if input_manager.key_pressed(pg.K_e) or input_manager.key_pressed(pg.K_RETURN):
            self.show_confirm_dialog = False
            self.detected = False
            scene_manager.change_scene("battle")
            return

        # Esc：取消
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.show_confirm_dialog = False
            return

        # 滑鼠左鍵點擊
        mouse_buttons = pg.mouse.get_pressed()
        if mouse_buttons[0]:
            mx, my = pg.mouse.get_pos()

            if self._confirm_rect and self._confirm_rect.collidepoint(mx, my):
                self.show_confirm_dialog = False
                self.detected = False
                scene_manager.change_scene("battle")
                return

            if self._cancel_rect and self._cancel_rect.collidepoint(mx, my):
                self.show_confirm_dialog = False
                return

    # -----------------------------
    # Storage
    # -----------------------------
    @classmethod
    @override
    def from_dict(cls, data: dict, game_manager: GameManager) -> "EnemyTrainer":
        classification = EnemyTrainerClassification(
            data.get("classification", "stationary")
        )
        max_tiles = data.get("max_tiles")

        facing_val = data.get("facing")
        facing: Direction | None = None
        if facing_val is not None:
            if isinstance(facing_val, str):
                facing = Direction[facing_val]
            elif isinstance(facing_val, Direction):
                facing = facing_val

        if facing is None and classification == EnemyTrainerClassification.STATIONARY:
            facing = Direction.DOWN

        # ✅ 新增：讀 sprite（沒寫就 ow1）
        sprite_name = data.get("sprite", "ow1.png")

        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            game_manager,
            classification,
            max_tiles,
            facing,
            sprite_name,
        )

    @override
    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = super().to_dict()
        base["classification"] = self.classification.value
        base["facing"] = self.direction.name
        base["max_tiles"] = self.max_tiles
        base["sprite"] = getattr(self, "sprite_name", "ow1.png")  # ✅ 新增
        return base
