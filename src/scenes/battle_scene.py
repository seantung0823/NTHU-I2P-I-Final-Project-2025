# src/scenes/battle_scene.py

from __future__ import annotations
import math
import pygame as pg
from typing import override

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.core.services import scene_manager, input_manager
from src.sprites import BackgroundSprite, Animation


class BattleScene(Scene):
    """
    BattleScene：
    - 放射轉場 (RADIAL)
    - 敵方放大 (ENEMY_ZOOM)
    - 我方放大 (PLAYER_ZOOM)
    - 回合制戰鬥：
        PLAYER_CHOICE → PLAYER_ATTACK → ENEMY_ATTACK → PLAYER_CHOICE
    - Fight / Run 有功能
    - Win / Run / Lose 直接回 game scene
    """

    background: BackgroundSprite

    @override
    def __init__(self) -> None:
        super().__init__()

        # 背景
        self.background = BackgroundSprite("backgrounds/background1.png")

        # 字體
        pg.font.init()
        self.font_small = pg.font.Font(None, 20)
        self.font_medium = pg.font.Font(None, 26)

        # 對話框
        self.dialog_height = 120
        self.dialog_rect = pg.Rect(
            0,
            GameSettings.SCREEN_HEIGHT - self.dialog_height,
            GameSettings.SCREEN_WIDTH,
            self.dialog_height,
        )

        # 訊息
        self.message_intro = "A wild monster appeared!"
        self.message_menu = "What will Florian do?"
        self.message = self.message_intro

        # ---------- 轉場動畫 ----------
        self.transition_duration = 0.6
        self.transition_timer = 0.0

        # ---------- 進場動畫 ----------
        self.phase: str = "RADIAL"
        self.enemy_zoom_duration = 0.5
        self.player_zoom_duration = 0.5
        self.enemy_zoom_timer = 0.0
        self.player_zoom_timer = 0.0

        self.enemy_scale_start = 0.3
        self.enemy_scale_end = 1.0
        self.player_scale_start = 0.3
        self.player_scale_end = 1.0

        # ---------- 簡易戰鬥數值 ----------
        self.player_name = "Florian"
        self.enemy_name = "Enemy"

        self.player_max_hp = 100
        self.player_hp = self.player_max_hp

        self.enemy_max_hp = 80
        self.enemy_hp = self.enemy_max_hp

        self.player_attack_power = 30
        self.enemy_attack_power = 20

        self.action_duration = 0.8
        self.action_timer = 0.0

        self.battle_result: str | None = None

        # ---------- 寶可夢動畫（雙方都用 sprite1） ----------
        self.enemy_anim = Animation(
            "sprites/sprite1_idle.png",
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim = Animation(
            "sprites/sprite1_idle.png",
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.enemy_anim.switch("idle")
        self.player_anim.switch("idle")

        # 位置
        self.enemy_pos = (
            GameSettings.SCREEN_WIDTH * 3 // 4,
            GameSettings.SCREEN_HEIGHT // 3,
        )
        self.player_pos = (
            GameSettings.SCREEN_WIDTH // 4,
            GameSettings.SCREEN_HEIGHT * 2 // 3 - self.dialog_height // 2,
        )

    # -------------------------------------------------
    # Scene lifecycle
    # -------------------------------------------------
    @override
    def enter(self) -> None:
        self.transition_timer = 0.0
        self.enemy_zoom_timer = 0.0
        self.player_zoom_timer = 0.0

        self.phase = "RADIAL"
        self.message = self.message_intro

        self.player_hp = self.player_max_hp
        self.enemy_hp = self.enemy_max_hp
        self.battle_result = None
        self.action_timer = 0.0

    # -------------------------------------------------
    # Update
    # -------------------------------------------------
    @override
    def update(self, dt: float) -> None:
        self.enemy_anim.update(dt)
        self.player_anim.update(dt)

        # ---------- 前置動畫 ----------
        if self.phase == "RADIAL":
            self.transition_timer += dt
            if self.transition_timer >= self.transition_duration:
                self.phase = "ENEMY_ZOOM"
            return

        if self.phase == "ENEMY_ZOOM":
            self.enemy_zoom_timer += dt
            if self.enemy_zoom_timer >= self.enemy_zoom_duration:
                self.phase = "PLAYER_ZOOM"
            return

        if self.phase == "PLAYER_ZOOM":
            self.player_zoom_timer += dt
            if self.player_zoom_timer >= self.player_zoom_duration:
                self.phase = "PLAYER_CHOICE"
                self.message = self.message_menu
            return

        # ---------- 玩家選擇 ----------
        if self.phase == "PLAYER_CHOICE":
            self._handle_player_choice()
            return

        # ---------- 玩家攻擊 ----------
        if self.phase == "PLAYER_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0

                if self.enemy_hp <= 0:
                    self.battle_result = "WIN"
                    self.phase = "END"
                    return

                self._start_enemy_attack()
            return

        # ---------- 敵人攻擊 ----------
        if self.phase == "ENEMY_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0

                if self.player_hp <= 0:
                    self.battle_result = "LOSE"
                    self.phase = "END"
                    return

                self.phase = "PLAYER_CHOICE"
                self.message = self.message_menu
            return

        # ---------- 結束戰鬥：直接回到 game_scene ----------
        if self.phase == "END":
            scene_manager.change_scene("game")
            return

    # -------------------------------------------------
    # 玩家選擇回合
    # -------------------------------------------------
    def _handle_player_choice(self) -> None:
        if input_manager.key_pressed(pg.K_f):
            self._player_attack()
            return

        if input_manager.key_pressed(pg.K_r):
            self._player_run()
            return

        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_menu_buttons():
                if rect.collidepoint(mx, my):
                    if label == "Fight":
                        self._player_attack()
                    elif label == "Run":
                        self._player_run()
                    return

    def _player_attack(self) -> None:
        damage = self.player_attack_power
        self.enemy_hp = max(0, self.enemy_hp - damage)

        self.message = (
            f"{self.player_name} used Fight! "
            f"Enemy HP: {self.enemy_hp}/{self.enemy_max_hp}"
        )

        self.phase = "PLAYER_ATTACK"
        self.action_timer = 0.0

    def _start_enemy_attack(self) -> None:
        damage = self.enemy_attack_power
        self.player_hp = max(0, self.player_hp - damage)

        self.message = (
            f"{self.enemy_name} attacked! "
            f"Your HP: {self.player_hp}/{self.player_max_hp}"
        )

        self.phase = "ENEMY_ATTACK"
        self.action_timer = 0.0

    def _player_run(self) -> None:
        self.battle_result = "RUN"
        self.message = "Got away safely!"
        self.phase = "END"

    # -------------------------------------------------
    # Draw
    # -------------------------------------------------
    @override
    def draw(self, screen: pg.Surface) -> None:
        self.background.draw(screen)

        self._draw_hp_boxes(screen)
        self._draw_monsters(screen)

        # 底部對話框
        pg.draw.rect(screen, (0, 0, 0), self.dialog_rect)

        text = self.font_medium.render(self.message, True, (255, 255, 255))
        screen.blit(text, (self.dialog_rect.left + 16, self.dialog_rect.top + 16))

        # 只有玩家選擇回合才畫選單
        if self.phase == "PLAYER_CHOICE":
            self._draw_menu_buttons(screen)

        if self.phase == "RADIAL":
            self._draw_radial_transition(screen)

    # -------------------------------------------------
    # HP 顯示
    # -------------------------------------------------
    def _draw_hp_boxes(self, screen: pg.Surface) -> None:
        box_w, box_h = 180, 60

        # 敵人 HP
        enemy_rect = pg.Rect(
            GameSettings.SCREEN_WIDTH - box_w - 20, 20, box_w, box_h
        )
        pg.draw.rect(screen, (255, 255, 255), enemy_rect)
        pg.draw.rect(screen, (0, 0, 0), enemy_rect, 2)

        name_text = self.font_small.render(self.enemy_name, True, (0, 0, 0))
        screen.blit(name_text, (enemy_rect.x + 8, enemy_rect.y + 8))

        hp_ratio = self.enemy_hp / self.enemy_max_hp
        bar_back = pg.Rect(enemy_rect.x + 8, enemy_rect.y + box_h - 20, box_w - 16, 10)
        pg.draw.rect(screen, (80, 80, 80), bar_back)
        bar = pg.Rect(bar_back.x, bar_back.y, int(bar_back.w * hp_ratio), 10)
        pg.draw.rect(screen, (0, 200, 0), bar)

        # 玩家 HP
        player_rect = pg.Rect(
            20, GameSettings.SCREEN_HEIGHT - self.dialog_height - box_h - 10, box_w, box_h
        )
        pg.draw.rect(screen, (255, 255, 255), player_rect)
        pg.draw.rect(screen, (0, 0, 0), player_rect, 2)

        pname_text = self.font_small.render(self.player_name, True, (0, 0, 0))
        screen.blit(pname_text, (player_rect.x + 8, player_rect.y + 8))

        p_hp_ratio = self.player_hp / self.player_max_hp
        p_bar_back = pg.Rect(player_rect.x + 8, player_rect.y + box_h - 20, box_w - 16, 10)
        pg.draw.rect(screen, (80, 80, 80), p_bar_back)
        p_bar = pg.Rect(p_bar_back.x, p_bar_back.y, int(p_bar_back.w * p_hp_ratio), 10)
        pg.draw.rect(screen, (0, 200, 0), p_bar)

    # -------------------------------------------------
    # 放大動畫
    # -------------------------------------------------
    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    def _draw_monsters(self, screen: pg.Surface) -> None:
        if self.phase == "RADIAL":
            enemy_scale = 0.0
            player_scale = 0.0
        elif self.phase == "ENEMY_ZOOM":
            t = min(self.enemy_zoom_timer / self.enemy_zoom_duration, 1.0)
            enemy_scale = self._lerp(self.enemy_scale_start, self.enemy_scale_end, t)
            player_scale = 0.0
        elif self.phase == "PLAYER_ZOOM":
            enemy_scale = self.enemy_scale_end
            t = min(self.player_zoom_timer / self.player_zoom_duration, 1.0)
            player_scale = self._lerp(self.player_scale_start, self.player_scale_end, t)
        else:  # 戰鬥中 or END
            enemy_scale = self.enemy_scale_end
            player_scale = self.player_scale_end

        if enemy_scale > 0:
            self._draw_scaled_animation(screen, self.enemy_anim, self.enemy_pos, enemy_scale)

        if player_scale > 0:
            self._draw_scaled_animation(screen, self.player_anim, self.player_pos, player_scale)

    def _draw_scaled_animation(self, screen, anim, center, scale):
        frames = anim.animations[anim.cur_row]
        idx = int((anim.accumulator / anim.loop) * anim.n_keyframes) % anim.n_keyframes
        frame = frames[idx]

        w, h = frame.get_size()
        surf = pg.transform.smoothscale(frame, (int(w * scale), int(h * scale)))
        rect = surf.get_rect(center=center)
        screen.blit(surf, rect)

    # -------------------------------------------------
    # 選單按鈕（四顆保留 → Fight / Item / Switch / Run）
    # -------------------------------------------------
    def _get_menu_buttons(self):
        labels = ["Fight", "Item", "Switch", "Run"]

        btn_w, btn_h = 140, 40
        gap = 20

        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        out = []
        for i, label in enumerate(labels):
            rect = pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h)
            out.append((rect, label))

        return out

    def _draw_menu_buttons(self, screen):
        for rect, label in self._get_menu_buttons():
            pg.draw.rect(screen, (230, 215, 190), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)

            txt = self.font_small.render(label, True, (0, 0, 0))
            screen.blit(txt, txt.get_rect(center=rect.center))

    # -------------------------------------------------
    # 放射轉場動畫
    # -------------------------------------------------
    def _draw_radial_transition(self, screen: pg.Surface) -> None:
        progress = min(self.transition_timer / self.transition_duration, 1.0)

        w, h = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        cx, cy = w // 2, h // 2

        slices = 8
        max_r = math.hypot(w, h)

        overlay = pg.Surface((w, h), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 255))

        for i in range(slices):
            base = 2 * math.pi * i / slices
            open_angle = (2 * math.pi / slices) * (1 - progress)

            a1 = base - open_angle / 2
            a2 = base + open_angle / 2

            p1 = (cx, cy)
            p2 = (cx + math.cos(a1) * max_r, cy + math.sin(a1) * max_r)
            p3 = (cx + math.cos(a2) * max_r, cy + math.sin(a2) * max_r)

            pg.draw.polygon(overlay, (0, 0, 0, 0), [p1, p2, p3])

        screen.blit(overlay, (0, 0))
