# src/scenes/wild_scene.py

from __future__ import annotations
import math
import random
import pygame as pg
from typing import override, TYPE_CHECKING

from src.scenes.scene import Scene
from src.utils import GameSettings, Logger
from src.core.services import scene_manager, input_manager, sound_manager
from src.sprites import BackgroundSprite, Animation

if TYPE_CHECKING:
    from src.data.bag import Bag


class WildScene(Scene):
    """
    WildScene：
    - 流程：
        RADIAL -> ENEMY_ZOOM -> PLAYER_ZOOM -> PLAYER_CHOICE
        -> PLAYER_ATTACK / ENEMY_ATTACK / RUN_AWAY / BALL_THROW / BALL_SHAKE / END
    - Fight：簡單回合制（你打一拳、對方打一拳）
    - Item：開啟道具選單（Potion / Ball / Cancel）
        * Potion：從 Bag 裡扣一個 Potion，幫玩家補血
        * Ball：從 Bag 裡扣一顆 Pokeball，播放捕捉動畫，最後判定成功或失敗
    - Run：逃跑，顯示 Got away safely! 然後回到 game scene
    """

    background: BackgroundSprite

    @override
    def __init__(self, bag: "Bag | None" = None) -> None:
        super().__init__()

        # 可以為 None（如果沒有把 Bag 傳進來就只是「假用道具」）
        self.bag: "Bag | None" = bag

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
        self.message_intro = "A wild Florian appeared!"
        self.message_menu = "What will you do?"
        self.message = self.message_intro

        # ---------- 轉場動畫 ----------
        self.transition_duration = 0.6
        self.transition_timer = 0.0

        # ---------- 進場動畫 ----------
        # phase:
        # RADIAL / ENEMY_ZOOM / PLAYER_ZOOM /
        # PLAYER_CHOICE / PLAYER_ATTACK / ENEMY_ATTACK /
        # RUN_AWAY / BALL_THROW / BALL_SHAKE / END
        self.phase: str = "RADIAL"
        self.enemy_zoom_duration = 0.5
        self.player_zoom_duration = 0.5
        self.enemy_zoom_timer = 0.0
        self.player_zoom_timer = 0.0

        self.enemy_scale_start = 0.3
        self.enemy_scale_end = 1.0
        self.player_scale_start = 0.3
        self.player_scale_end = 1.0

        # ---------- 戰鬥數值 ----------
        self.player_name = "Florian"
        self.enemy_name = "Florian"

        self.player_max_hp = 100
        self.player_hp = self.player_max_hp

        self.enemy_max_hp = 80
        self.enemy_hp = self.enemy_max_hp

        # 攻擊 / 動畫計時
        self.action_duration = 0.8
        self.action_timer = 0.0

        # Ball 捕捉動畫用
        self.ball_timer = 0.0
        self.ball_throw_duration = 0.5   # 丟球飛行時間
        self.ball_shake_duration = 1.0   # 搖晃總時間
        self.ball_capture_success: bool = False

        # 敵方是否「在球裡」：會影響敵方寶可夢是否畫出來
        self.enemy_inside_ball: bool = False

        # 捕捉時敵方縮小動畫用
        self.enemy_capture_timer = 0.0
        self.enemy_capture_duration = 0.4  # 縮小到消失花的時間（秒）

        # END 畫面停留時間
        self.end_duration = 1.0
        self.end_timer = 0.0

        # 戰鬥結果：WIN / LOSE / RUN / CAUGHT
        self.battle_result: str | None = None

        # 是否正在 Item 選單裡
        self.in_item_menu: bool = False

        # ---------- 寶可夢動畫（雙方都用 sprite1_idle） ----------
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

        # 位置：敵方右上、我方左下
        self.enemy_pos = (
            GameSettings.SCREEN_WIDTH * 3 // 4,
            GameSettings.SCREEN_HEIGHT // 3,
        )
        self.player_pos = (
            GameSettings.SCREEN_WIDTH // 4,
            GameSettings.SCREEN_HEIGHT * 2 // 3 - self.dialog_height // 2,
        )

        # ---------- 球圖片（老師給的 ball.png） ----------
        self.ball_image: pg.Surface | None = None
        try:
            # 正確路徑在 assets/images/ingame_ui/ball.png
            raw_img = pg.image.load("assets/images/ingame_ui/ball.png").convert_alpha()
            # 可以調整大小，24x24 只是示範
            self.ball_image = pg.transform.smoothscale(raw_img, (24, 24))
        except Exception as e:
            Logger.warning(f"WildScene: failed to load ball image: {e}")
            self.ball_image = None

    # -------------------------------------------------
    # Scene lifecycle
    # -------------------------------------------------
    @override
    def enter(self) -> None:
        # 重設所有計時器與狀態
        self.transition_timer = 0.0
        self.enemy_zoom_timer = 0.0
        self.player_zoom_timer = 0.0

        self.phase = "RADIAL"
        self.message = self.message_intro
        self.in_item_menu = False

        # HP 先都滿
        self.player_hp = self.player_max_hp
        self.enemy_hp = self.enemy_max_hp

        self.battle_result = None
        self.action_timer = 0.0
        self.end_timer = 0.0
        self.ball_timer = 0.0
        self.enemy_inside_ball = False  # 重新進戰鬥，敵人還在外面
        self.enemy_capture_timer = 0.0

        # 進入野生戰鬥時換成對戰 BGM
        try:
            sound_manager.play_bgm("RBY 107 Battle! (Trainer).ogg")
        except Exception as e:
            Logger.warning(f"WildScene: failed to play BGM: {e}")

    @override
    def exit(self) -> None:
        pass

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

        # ---------- 玩家選擇：Fight / Item / Run ----------
        if self.phase == "PLAYER_CHOICE":
            self._handle_player_choice()
            return

        # ---------- 玩家攻擊動畫 ----------
        if self.phase == "PLAYER_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self._apply_player_attack()
            return

        # ---------- 敵人攻擊動畫 ----------
        if self.phase == "ENEMY_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self._apply_enemy_attack()
            return

        # ---------- 逃跑動畫 ----------
        if self.phase == "RUN_AWAY":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self.phase = "END"
                self.end_timer = 0.0
            return

        # ---------- 丟球動畫 ----------
        if self.phase == "BALL_THROW":
            self.ball_timer += dt
            if self.ball_timer >= self.ball_throw_duration:
                self.ball_timer = 0.0
                # 球飛到敵人位置，開始搖晃＋縮小動畫
                self.phase = "BALL_SHAKE"
                self.enemy_capture_timer = 0.0
                self.enemy_inside_ball = False  # 先讓敵人還看得到，會在 BALL_SHAKE 裡縮小到消失
            return

        # ---------- 球搖晃動畫（同時處理縮小吸進球裡） ----------
        if self.phase == "BALL_SHAKE":
            self.ball_timer += dt

            # 「被吸進球裡」縮小動畫：從 1.0 縮到 0
            if not self.enemy_inside_ball:
                self.enemy_capture_timer += dt
                if self.enemy_capture_timer >= self.enemy_capture_duration:
                    self.enemy_capture_timer = self.enemy_capture_duration
                    # 縮到 0 之後，就算是進球裡了 → 不再畫敵人
                    self.enemy_inside_ball = True

            # 球搖完之後再決定成功或失敗
            if self.ball_timer >= self.ball_shake_duration:
                self.ball_timer = 0.0
                if self.ball_capture_success:
                    # 成功：敵人留在球裡
                    self._add_captured_monster_to_bag()
                    self.battle_result = "CAUGHT"
                    self.message = "Gotcha! Florian was caught!"
                    self.phase = "END"
                    self.end_timer = 0.0
                else:
                    # 失敗：敵人從球裡跳出來
                    self.enemy_inside_ball = False
                    self.message = "Oh no! It broke free!"
                    self.phase = "PLAYER_CHOICE"
                    self.in_item_menu = False
            return

        # ---------- 結束：顯示結果，約 1 秒後回 game ----------
        if self.phase == "END":
            self.end_timer += dt
            if self.end_timer >= self.end_duration:
                scene_manager.change_scene("game")
            return

    # -------------------------------------------------
    # 玩家選擇：Fight / Item / Run
    # -------------------------------------------------
    def _handle_player_choice(self) -> None:
        # 先看有沒有在 item 子選單裡
        if self.in_item_menu:
            self._handle_item_menu()
            return

        # F = Fight(攻擊), R = Run
        if input_manager.key_pressed(pg.K_f):
            self._player_start_attack()
            return

        if input_manager.key_pressed(pg.K_r):
            self._player_run()
            return

        # I = Item（開啟 Item 選單）
        if input_manager.key_pressed(pg.K_i):
            self.in_item_menu = True
            self.message = "Choose an item."
            return

        # 滑鼠點主選單按鈕
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_menu_buttons():
                if rect.collidepoint(mx, my):
                    if label == "Fight":
                        self._player_start_attack()
                    elif label == "Item":
                        self.in_item_menu = True
                        self.message = "Choose an item."
                    elif label == "Run":
                        self._player_run()
                    return

    # -------------------------------------------------
    # Item 子選單：Potion / Ball / Cancel
    # -------------------------------------------------
    def _handle_item_menu(self) -> None:
        # ESC 或 Cancel → 回主選單
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        # 鍵盤快速鍵：1 = Potion, 2 = Ball, 3 = Cancel
        if input_manager.key_pressed(pg.K_1):
            self._use_potion()
            return
        if input_manager.key_pressed(pg.K_2):
            self._use_pokeball()
            return
        if input_manager.key_pressed(pg.K_3):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        # 滑鼠點 item 按鈕
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_item_buttons():
                if rect.collidepoint(mx, my):
                    if label == "Potion":
                        self._use_potion()
                    elif label == "Ball":
                        self._use_pokeball()
                    elif label == "Cancel":
                        self.in_item_menu = False
                        self.message = self.message_menu
                    return

    # ---------- 使用 Potion ----------
    def _use_potion(self) -> None:
        if self._get_item_count("potion") <= 0:
            self.message = "No Potion left!"
            return

        if not self._consume_item("potion"):
            self.message = "No Potion left!"
            return

        heal_amount = 30
        old_hp = self.player_hp
        self.player_hp = min(self.player_max_hp, self.player_hp + heal_amount)
        real_heal = self.player_hp - old_hp

        self.message = f"You used a Potion! (+{real_heal} HP)"
        self.in_item_menu = False  # 回到主選單（但仍然是 PLAYER_CHOICE）

    # ---------- 使用 Pokeball（含捕捉動畫） ----------
    def _use_pokeball(self) -> None:
        if self._get_item_count("pokeball") <= 0:
            self.message = "No Pokeball left!"
            return

        if not self._consume_item("pokeball"):
            self.message = "No Pokeball left!"
            return

        # 捕捉成功率：血越少成功率越高
        hp_ratio = self.enemy_hp / self.enemy_max_hp
        success_prob = 0.35 + (1.0 - hp_ratio) * 0.45  # 約 0.35 ~ 0.8
        self.ball_capture_success = (random.random() < success_prob)

        # 進入丟球動畫
        self.message = "You threw a ball!"
        self.in_item_menu = False
        self.phase = "BALL_THROW"
        self.ball_timer = 0.0

    # -------------------------------------------------
    # Fight / Run / 攻擊結算
    # -------------------------------------------------
    def _player_start_attack(self) -> None:
        """Fight 按鈕：開始玩家攻擊動畫階段"""
        self.message = "You attack the wild Florian!"
        self.phase = "PLAYER_ATTACK"
        self.action_timer = 0.0

    def _player_run(self) -> None:
        """Run 按鈕：逃跑"""
        self.battle_result = "RUN"
        self.message = "Got away safely!"
        self.phase = "RUN_AWAY"
        self.action_timer = 0.0

    # 真正結算玩家攻擊（扣敵人 HP）
    def _apply_player_attack(self) -> None:
        dmg = 20
        self.enemy_hp = max(0, self.enemy_hp - dmg)

        if self.enemy_hp <= 0:
            self.battle_result = "WIN"
            self.message = "The wild Florian fainted!"
            self.phase = "END"
            self.end_timer = 0.0
        else:
            # 換敵人攻擊
            self.message = "The wild Florian is attacking!"
            self.phase = "ENEMY_ATTACK"
            self.action_timer = 0.0

    # 真正結算敵人攻擊（扣玩家 HP）
    def _apply_enemy_attack(self) -> None:
        dmg = 12
        self.player_hp = max(0, self.player_hp - dmg)

        if self.player_hp <= 0:
            self.battle_result = "LOSE"
            self.message = "You fainted..."
            self.phase = "END"
            self.end_timer = 0.0
        else:
            # 回到玩家選擇階段
            self.message = self.message_menu
            self.phase = "PLAYER_CHOICE"

    # -------------------------------------------------
    # Bag 相關小工具
    # -------------------------------------------------
    def _get_item_count(self, name: str) -> int:
        """從 Bag 裡讀某個道具的數量（大小寫不分）。bag 為 None 時，當作一大堆。"""
        if not self.bag:
            return 999

        items = getattr(self.bag, "_items_data", [])
        target = name.lower()
        for it in items:
            if it.get("name", "").lower() == target:
                return int(it.get("count", 0))
        return 0

    def _consume_item(self, name: str) -> bool:
        """從 Bag 裡扣掉一個道具；成功回 True，沒得扣回 False。"""
        if not self.bag:
            return True  # 沒接 Bag 時就當作無限

        items = getattr(self.bag, "_items_data", [])
        target = name.lower()
        for it in items:
            if it.get("name", "").lower() == target:
                cnt = int(it.get("count", 0))
                if cnt <= 0:
                    return False
                it["count"] = cnt - 1
                return True
        return False

    def _add_captured_monster_to_bag(self) -> None:
        """把抓到的 Florian 加到 Bag 的 monsters 裡。"""
        if not self.bag:
            Logger.warning("WildScene: capture success but bag is None (monster not stored).")
            return

        monsters = getattr(self.bag, "_monsters_data", None)
        if monsters is None:
            Logger.warning("WildScene: bag has no _monsters_data (monster not stored).")
            return

        # 這裡用一個簡單範例，可以之後改成真的 wild 資料
        new_mon = {
            "name": "Florian",
            "hp": self.enemy_max_hp,
            "max_hp": self.enemy_max_hp,
            "level": 20,
            "sprite_path": "menu_sprites/menusprite1.png",
        }
        monsters.append(new_mon)
        Logger.info("WildScene: captured Florian added to bag!")

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

        # 玩家回合：畫主選單或 item 子選單
        if self.phase == "PLAYER_CHOICE":
            if self.in_item_menu:
                self._draw_item_buttons(screen)
            else:
                self._draw_menu_buttons(screen)

        # 丟球 / 搖晃時畫球
        if self.phase in ("BALL_THROW", "BALL_SHAKE"):
            self._draw_ball(screen)

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
            20,
            GameSettings.SCREEN_HEIGHT - self.dialog_height - box_h - 10,
            box_w,
            box_h,
        )
        pg.draw.rect(screen, (255, 255, 255), player_rect)
        pg.draw.rect(screen, (0, 0, 0), player_rect, 2)

        pname_text = self.font_small.render(self.player_name, True, (0, 0, 0))
        screen.blit(pname_text, (player_rect.x + 8, player_rect.y + 8))

        p_hp_ratio = self.player_hp / self.player_max_hp
        p_bar_back = pg.Rect(
            player_rect.x + 8,
            player_rect.y + box_h - 20,
            box_w - 16,
            10,
        )
        pg.draw.rect(screen, (80, 80, 80), p_bar_back)
        p_bar = pg.Rect(
            p_bar_back.x,
            p_bar_back.y,
            int(p_bar_back.w * p_hp_ratio),
            10,
        )
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
        else:  # 其他階段
            enemy_scale = self.enemy_scale_end
            player_scale = self.player_scale_end

        # 捕捉縮小動畫：在 BALL_SHAKE 初期，把敵人從 1.0 縮到 0
        if self.phase == "BALL_SHAKE" and not self.enemy_inside_ball:
            t = min(self.enemy_capture_timer / self.enemy_capture_duration, 1.0)
            shrink = 1.0 - t  # t: 0→1，shrink: 1→0
            enemy_scale *= shrink

        # 敵方：如果被「收進球裡」，就不畫出來
        if enemy_scale > 0 and not self.enemy_inside_ball:
            self._draw_scaled_animation(
                screen, self.enemy_anim, self.enemy_pos, enemy_scale
            )

        # 我方永遠畫
        if player_scale > 0:
            self._draw_scaled_animation(
                screen, self.player_anim, self.player_pos, player_scale
            )

    def _draw_scaled_animation(
        self,
        screen: pg.Surface,
        anim: Animation,
        center: tuple[int, int],
        scale: float,
    ) -> None:
        frames = anim.animations[anim.cur_row]
        idx = int((anim.accumulator / anim.loop) * anim.n_keyframes) % anim.n_keyframes
        frame = frames[idx]

        w, h = frame.get_size()
        surf = pg.transform.smoothscale(
            frame,
            (int(w * scale), int(h * scale)),
        )
        rect = surf.get_rect(center=center)
        screen.blit(surf, rect)

    # -------------------------------------------------
    # 丟球 & 搖晃動畫（優先用老師的 ball.png，載不到才用備用畫圖）
    # -------------------------------------------------
    def _draw_ball(self, screen: pg.Surface) -> None:
        """在 BALL_THROW / BALL_SHAKE 階段畫出球的動畫。"""

        # 起點：玩家寶可夢位置稍微往上
        start_x, start_y = self.player_pos
        start_y -= 40

        # 終點：敵人寶可夢位置再稍微往上
        end_x, end_y = self.enemy_pos
        end_y -= 50

        if self.phase == "BALL_THROW":
            t = min(self.ball_timer / self.ball_throw_duration, 1.0)
            # 線性插值位置
            x = self._lerp(start_x, end_x, t)
            y = self._lerp(start_y, end_y, t)
            # 做一點拋物線效果（往上拋）
            arc_height = 40
            y -= math.sin(math.pi * t) * arc_height
        else:  # BALL_SHAKE
            # 球固定在敵人上方，左右小幅晃動
            t = self.ball_timer / self.ball_shake_duration
            x = end_x + math.sin(t * 6 * math.pi) * 8  # 左右晃動
            y = end_y

        center = (int(x), int(y))

        # 優先用老師給的 ball.png
        if self.ball_image is not None:
            rect = self.ball_image.get_rect(center=center)
            screen.blit(self.ball_image, rect)
            return

        # 如果 ball.png 載不到，才用備用的圓形球（避免完全看不到）
        radius = 10
        # 外圈
        pg.draw.circle(screen, (0, 0, 0), center, radius + 1)
        # 下半部白色
        pg.draw.circle(screen, (255, 255, 255), center, radius)
        # 上半部紅色（半圓）
        rect = pg.Rect(center[0] - radius, center[1] - radius, radius * 2, radius)
        pg.draw.ellipse(screen, (220, 0, 0), rect)
        # 中間線
        pg.draw.line(
            screen,
            (0, 0, 0),
            (center[0] - radius, center[1]),
            (center[0] + radius, center[1]),
            2,
        )
        # 中央小圓
        pg.draw.circle(screen, (255, 255, 255), center, 3)
        pg.draw.circle(screen, (0, 0, 0), center, 3, 1)

    # -------------------------------------------------
    # 選單按鈕（主選單：Fight / Item / Switch / Run）
    # -------------------------------------------------
    def _get_menu_buttons(self):
        labels = ["Fight", "Item", "Switch", "Run"]

        btn_w, btn_h = 140, 40
        gap = 20

        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        out: list[tuple[pg.Rect, str]] = []
        for i, label in enumerate(labels):
            rect = pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h)
            out.append((rect, label))

        return out

    def _draw_menu_buttons(self, screen: pg.Surface) -> None:
        for rect, label in self._get_menu_buttons():
            pg.draw.rect(screen, (230, 215, 190), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)

            txt = self.font_small.render(label, True, (0, 0, 0))
            screen.blit(txt, txt.get_rect(center=rect.center))

    # -------------------------------------------------
    # Item 子選單按鈕（Potion / Ball / Cancel）
    # -------------------------------------------------
    def _get_item_buttons(self):
        labels = ["Potion", "Ball", "Cancel"]

        btn_w, btn_h = 140, 40
        gap = 20

        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        out: list[tuple[pg.Rect, str]] = []
        for i, label in enumerate(labels):
            rect = pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h)
            out.append((rect, label))
        return out

    def _draw_item_buttons(self, screen: pg.Surface) -> None:
        for rect, label in self._get_item_buttons():
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
