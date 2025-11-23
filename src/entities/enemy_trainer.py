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
    def update(self, enemy: "EnemyTrainer", dt: float) -> None:
        return


class EnemyTrainer(Entity):
    classification: EnemyTrainerClassification
    max_tiles: int | None
    _movement: IdleMovement
    warning_sign: Sprite
    detected: bool
    los_direction: Direction
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
    ) -> None:

        super().__init__(x, y, game_manager)

        self.classification = classification
        self.max_tiles = max_tiles

        if classification == EnemyTrainerClassification.STATIONARY:
            self._movement = IdleMovement()
            if facing is None:
                raise ValueError("Idle EnemyTrainer requires a 'facing' Direction at instantiation")
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
    # 設定敵人面向 & 對應動畫
    # -----------------------------
    def _set_direction(self, direction: Direction) -> None:
        """
        根據傳入的 facing 方向切換敵人動畫，並記錄目前朝向。
        """
        self.direction = direction

        if direction == Direction.RIGHT:
            self.animation.switch("right")
        elif direction == Direction.LEFT:
            self.animation.switch("left")
        elif direction == Direction.DOWN:
            self.animation.switch("down")
        else:
            # 預設當作向上
            self.animation.switch("up")

        self.los_direction = self.direction

    # -----------------------------
    # UPDATE
    # -----------------------------
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

        # 更新動畫位置
        self.animation.update_pos(self.position)

        # 更新驚嘆號在頭上的位置
        self.warning_sign.update_pos(
            Position(
                self.position.x + GameSettings.TILE_SIZE // 4,
                self.position.y - GameSettings.TILE_SIZE // 2,
            )
        )

    # -----------------------------
    # DRAW
    # -----------------------------
    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)

        # 有偵測到 → 畫驚嘆號
        if self.detected:
            self.warning_sign.draw(screen, camera)

            # 若沒有打開確認視窗 → 畫提示文字
            if not self.show_confirm_dialog:
                self._draw_interact_hint(screen)

        # 顯示確認視窗（實際上 GameScene 最後還會再畫一次蓋在最上層）
        if self.show_confirm_dialog:
            self._draw_confirm_dialog(screen)

        # Debug：只畫敵人本體紅框
        if GameSettings.DRAW_HITBOXES:
            rect = self._get_enemy_rect()
            pg.draw.rect(screen, (255, 0, 0), camera.transform_rect(rect), 1)

    # -----------------------------
    # 取得敵人紅框（碰撞框）
    # -----------------------------
    def _get_enemy_rect(self) -> pg.Rect:
        return pg.Rect(
            int(self.position.x),
            int(self.position.y),
            GameSettings.TILE_SIZE,
            GameSettings.TILE_SIZE,
        )

    # -----------------------------
    # 玩家有沒有撞到敵人本體？
    # -----------------------------
    def _has_los_to_player(self) -> None:
        player = self.game_manager.player
        if player is None:
            self.detected = False
            self.show_confirm_dialog = False
            return

        enemy_rect = self._get_enemy_rect()
        player_rect = player.get_rect()

        # 增加 4px 讓邊碰邊也算撞到
        expanded_enemy = enemy_rect.inflate(4, 4)

        # 先檢查有沒有「碰到」
        if not expanded_enemy.colliderect(player_rect):
            self.detected = False
            self.show_confirm_dialog = False
            return

        # 真的有碰到，再來判斷玩家有沒有在「面向的那一側」
        px, py = player_rect.center
        ex, ey = enemy_rect.center

        from_front = False

        # 這裡用 self.los_direction / self.direction 都可以
        if self.los_direction == Direction.UP:
            # 玩家在敵人上方才算
            from_front = py < ey
        elif self.los_direction == Direction.DOWN:
            # 玩家在敵人下方才算
            from_front = py > ey
        elif self.los_direction == Direction.LEFT:
            # 玩家在敵人左邊才算
            from_front = px < ex
        elif self.los_direction == Direction.RIGHT:
            # 玩家在敵人右邊才算
            from_front = px > ex

        self.detected = from_front

        # 只要條件不符合，就關掉視窗
        if not self.detected:
            self.show_confirm_dialog = False

    # -----------------------------
    # 底部提示文字
    # -----------------------------
    def _draw_interact_hint(self, screen: pg.Surface) -> None:
        font = pg.font.SysFont(None, 20)
        text = font.render("Press E to start a battle", True, (255, 255, 255))

        bg_rect = pg.Rect(0, 0, text.get_width() + 16, text.get_height() + 8)
        bg_rect.midbottom = (GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT - 8)

        pg.draw.rect(screen, (0, 0, 0), bg_rect)
        pg.draw.rect(screen, (255, 255, 255), bg_rect, 1)
        screen.blit(text, (bg_rect.x + 8, bg_rect.y + 4))

    # -----------------------------
    # 確認視窗（畫面 + 按鈕 hitbox）
    # -----------------------------
    def _draw_confirm_dialog(self, screen: pg.Surface) -> None:
        panel_w, panel_h = 260, 130
        panel_rect = pg.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (
            GameSettings.SCREEN_WIDTH // 2,
            GameSettings.SCREEN_HEIGHT // 2,
        )

        # 半透明背景
        overlay = pg.Surface(
            (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT),
            pg.SRCALPHA,
        )
        overlay.fill((0, 0, 0, 100))
        screen.blit(overlay, (0, 0))

        # 視窗本體
        pg.draw.rect(screen, (30, 30, 30), panel_rect)
        pg.draw.rect(screen, (255, 255, 255), panel_rect, 2)

        font = pg.font.SysFont(None, 22)
        small_font = pg.font.SysFont(None, 18)

        title = font.render("Enter battle with this trainer?", True, (255, 255, 255))
        screen.blit(
            title,
            title.get_rect(center=(panel_rect.centerx, panel_rect.y + 35)),
        )

        # ===== 按鈕寬度根據文字自動算，保證左右有 padding =====
        txt_confirm = font.render("Confirm", True, (255, 255, 255))
        hint_confirm = small_font.render("(E)", True, (255, 255, 255))
        confirm_width = max(txt_confirm.get_width(), hint_confirm.get_width())

        txt_cancel = font.render("Cancel", True, (255, 255, 255))
        hint_cancel = small_font.render("(Esc)", True, (255, 255, 255))
        cancel_width = max(txt_cancel.get_width(), hint_cancel.get_width())

        # 兩個裡面挑最寬的，再加左右 padding
        content_w = max(confirm_width, cancel_width)
        btn_w = content_w + 20  # 左右各 10px padding
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

        # 畫按鈕框
        for rect in (btn_confirm, btn_cancel):
            pg.draw.rect(screen, (70, 70, 70), rect)
            pg.draw.rect(screen, (255, 255, 255), rect, 2)

        # Confirm 按鈕文字（兩行）
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

        # Cancel 按鈕文字（兩行）
        screen.blit(
            txt_cancel,
            txt_cancel.get_rect(
                center=(btn_cancel.centerx, btn_cancel.centery - 6)
            ),
        )
        screen.blit(
            hint_cancel,
            hint_cancel.get_rect(
                center=(btn_cancel.centerx, btn_cancel.centery + 8)
            ),
        )

        # 把這兩個 rect 存起來，給滑鼠點擊用
        self._confirm_rect = btn_confirm
        self._cancel_rect = btn_cancel

    # -----------------------------
    # 視窗輸入處理（鍵盤 + 滑鼠）
    # -----------------------------
    def _handle_confirm_dialog_input(self) -> None:
        # 鍵盤：確認 → E 或 Enter
        if input_manager.key_pressed(pg.K_e) or input_manager.key_pressed(pg.K_RETURN):
            self.show_confirm_dialog = False
            self.detected = False
            scene_manager.change_scene("battle")
            return

        # 鍵盤：取消 → Esc
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
        classification = EnemyTrainerClassification(data.get("classification", "stationary"))
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

        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            game_manager,
            classification,
            max_tiles,
            facing,
        )

    @override
    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = super().to_dict()
        base["classification"] = self.classification.value
        base["facing"] = self.direction.name
        base["max_tiles"] = self.max_tiles
        return base
