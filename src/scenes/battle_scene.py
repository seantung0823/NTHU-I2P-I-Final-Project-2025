# src/scenes/battle_scene.py

from __future__ import annotations
import math
import pygame as pg
from typing import override, TYPE_CHECKING

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.core.services import scene_manager, input_manager, sound_manager
from src.sprites import BackgroundSprite, Animation

if TYPE_CHECKING:
    from src.data.bag import Bag

# 不同寶可夢名字對應到戰鬥用動畫的 sprite sheet（備用）
PLAYER_ANIM_SHEETS: dict[str, str] = {
    "florian": "sprites/sprite1_idle.png",
    "solada": "sprites/sprite3_idle.png",
    "capybu": "sprites/sprite8_idle.png",
}


class BattleScene(Scene):
    """
    BattleScene：
    - 放射轉場 (RADIAL)
    - 敵方放大 (ENEMY_ZOOM)
    - 我方放大 (PLAYER_ZOOM)
    - 回合制戰鬥：
        PLAYER_CHOICE → PLAYER_ATTACK → ENEMY_ATTACK → PLAYER_CHOICE
    - Fight / Run 有功能
    - Item：開啟道具選單（Potion / Ball / Cancel）
        * Potion：從 Bag 裡扣一個 Potion，幫玩家補血
        * Ball：在訓練家戰鬥中不能使用 → 只顯示提示文字
    - Switch：
        * 打開隊伍視窗，顯示 Bag 裡的寶可夢
        * 點選可以把場上的寶可夢換成那一隻，動畫也跟著換
    - 結束時顯示 You win / You lose / Got away safely
      約 1 秒後自動回 game scene
    """

    background: BackgroundSprite

    @override
    def __init__(self, bag: "Bag | None" = None) -> None:
        super().__init__()

        # 可以為 None，沒接 Bag 時就當作道具有很多（跟 WildScene 一樣的處理）
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

        # 攻擊訊息停留時間
        self.action_duration = 0.8
        self.action_timer = 0.0

        # 結束畫面停留時間
        self.end_duration = 1.0
        self.end_timer = 0.0

        # 戰鬥結果：WIN / LOSE / RUN
        self.battle_result: str | None = None

        # 是否正在 Item / Switch 選單裡
        self.in_item_menu: bool = False
        self.in_switch_menu: bool = False

        # 目前上場的是隊伍中的第幾隻（0 = 第一隻）
        self.active_party_index: int = 0

        # ---------- 寶可夢動畫（雙方） ----------
        self.enemy_anim = Animation(
            "sprites/sprite8_idle.png",
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
        self.end_timer = 0.0
        self.in_item_menu = False
        self.in_switch_menu = False

        # 如果有接 Bag，用第一隻寶可夢更新名字、HP、動畫
        party = self._get_party()
        if party:
            self.active_party_index = min(self.active_party_index, len(party) - 1)
            active = party[self.active_party_index]
            self.player_name = str(active.get("name", self.player_name))
            max_hp = int(active.get("max_hp", self.player_max_hp))
            cur_hp = int(active.get("hp", max_hp))
            self.player_max_hp = max_hp
            self.player_hp = cur_hp
            # 依照怪物資料更新動畫
            self._update_player_anim_for_mon(active)
        else:
            # 沒隊伍就用預設名字對應動畫
            self._update_player_anim_for_name(self.player_name)

        # 播戰鬥 BGM
        sound_manager.play_bgm("RBY 107 Battle! (Trainer).ogg")

    # -------------------------------------------------
    # Update
    # -------------------------------------------------
    @override
    def update(self, dt: float) -> None:
        # 這裡把動畫用到的 dt clamp 起來，避免第一次進場 dt 超大
        step = min(dt, 0.05)

        self.enemy_anim.update(step)
        self.player_anim.update(step)

        # ---------- 前置動畫 ----------
        if self.phase == "RADIAL":
            self.transition_timer += step
            if self.transition_timer >= self.transition_duration:
                self.transition_timer = self.transition_duration
                self.phase = "ENEMY_ZOOM"
            return

        if self.phase == "ENEMY_ZOOM":
            self.enemy_zoom_timer += step
            if self.enemy_zoom_timer >= self.enemy_zoom_duration:
                self.enemy_zoom_timer = self.enemy_zoom_duration
                self.phase = "PLAYER_ZOOM"
            return

        if self.phase == "PLAYER_ZOOM":
            self.player_zoom_timer += step
            if self.player_zoom_timer >= self.player_zoom_duration:
                self.player_zoom_timer = self.player_zoom_duration
                self.phase = "PLAYER_CHOICE"
                self.message = self.message_menu
            return

        # ---------- 玩家選擇 ----------
        if self.phase == "PLAYER_CHOICE":
            self._handle_player_choice()
            return

        # ---------- 玩家攻擊 ----------
        if self.phase == "PLAYER_ATTACK":
            self.action_timer += step
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0

                if self.enemy_hp <= 0:
                    self.battle_result = "WIN"
                    self.message = "You win!"
                    self.phase = "END"
                    self.end_timer = 0.0
                    return

                self._start_enemy_attack()
            return

        # -------- 敵人攻擊 ----------
        if self.phase == "ENEMY_ATTACK":
            self.action_timer += step
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0

                if self.player_hp <= 0:
                    self.battle_result = "LOSE"
                    self.message = "You lose..."
                    self.phase = "END"
                    self.end_timer = 0.0
                    return

                self.phase = "PLAYER_CHOICE"
                self.message = self.message_menu
            return

        # ---------- 結束戰鬥：顯示結果，約 1 秒後自動回到 game_scene ----------
        if self.phase == "END":
            self.end_timer += step
            if self.end_timer >= self.end_duration:
                scene_manager.change_scene("game")
            return

    # -------------------------------------------------
    # 玩家選擇回合
    # -------------------------------------------------
    def _handle_player_choice(self) -> None:
        # 如果在 Item / Switch 子選單裡，優先處理那邊
        if self.in_item_menu:
            self._handle_item_menu()
            return
        if self.in_switch_menu:
            self._handle_switch_menu()
            return

        # F = Fight, R = Run, I = Item, S = Switch
        if input_manager.key_pressed(pg.K_f):
            self._player_attack()
            return

        if input_manager.key_pressed(pg.K_r):
            self._player_run()
            return

        if input_manager.key_pressed(pg.K_i):
            # 開啟 Item 選單
            self.in_item_menu = True
            self.message = "Choose an item."
            return

        if input_manager.key_pressed(pg.K_s):
            if self._can_open_switch_menu():
                self.in_switch_menu = True
                self.message = "Choose a Pokemon to switch."
            else:
                self.message = "No other Pokemon to switch!"
            return

        # 滑鼠點選按鈕
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_menu_buttons():
                if rect.collidepoint(mx, my):
                    if label == "Fight":
                        self._player_attack()
                    elif label == "Item":
                        self.in_item_menu = True
                        self.message = "Choose an item."
                    elif label == "Switch":
                        if self._can_open_switch_menu():
                            self.in_switch_menu = True
                            self.message = "Choose a Pokemon to switch."
                        else:
                            self.message = "No other Pokemon to switch!"
                    elif label == "Run":
                        self._player_run()
                    return

    # -------------------------------------------------
    # Item 子選單：Potion / Ball / Cancel
    # -------------------------------------------------
    def _handle_item_menu(self) -> None:
        # ESC → 回主選單
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

    # ---------- 使用 Potion（補血） ----------
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
        # 跟 WildScene 一樣：目前當作「不耗回合」，仍停在 PLAYER_CHOICE
        self.in_item_menu = False

    # ---------- 使用 Pokeball ----------
    def _use_pokeball(self) -> None:
        # 訓練家戰鬥裡不能丟球，直接提示玩家
        self.message = "You can't use a ball in a trainer battle!"
        # 不扣道具，當作只是看了一下選單
        self.in_item_menu = False

    # -------------------------------------------------
    # Fight / Run / 攻擊結算
    # -------------------------------------------------
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
        self.end_timer = 0.0

    # -------------------------------------------------
    # Bag 相關小工具（跟 WildScene 同一套）+ 隊伍工具
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

    # 隊伍 / Switch 相關 ----------------------------------------
    def _get_party(self) -> list[dict]:
        """從 Bag 讀出玩家隊伍列表，沒有 Bag 則回傳空陣列。"""
        if not self.bag:
            return []
        mons = getattr(self.bag, "_monsters_data", [])
        if not isinstance(mons, list):
            return []
        return mons

    def _can_open_switch_menu(self) -> bool:
        """至少要有兩隻寶可夢才有意義打開 Switch 選單。"""
        party = self._get_party()
        return len(party) >= 2

    def _update_player_anim_for_name(self, name: str) -> None:
        """依照寶可夢名字更換場上動畫 sprite sheet（備用）。"""
        key = name.lower()
        sprite_path = PLAYER_ANIM_SHEETS.get(key, "sprites/sprite1_idle.png")
        self.player_anim = Animation(
            sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")

    def _get_switch_panel_rect(self) -> pg.Rect:
        """中間那個橘色選寶可夢視窗的範圍。"""
        w, h = 420, 260
        x = (GameSettings.SCREEN_WIDTH - w) // 2
        y = (GameSettings.SCREEN_HEIGHT - h) // 2
        return pg.Rect(x, y, w, h)

    def _get_switch_card_rects(self, panel: pg.Rect, count: int) -> list[pg.Rect]:
        """依照隊伍數量，算出每一張卡片的 rect。"""
        card_w = panel.width - 40
        card_h = 50
        x = panel.x + 20
        y_start = panel.y + 60
        gap = 12
        rects: list[pg.Rect] = []
        for i in range(count):
            rects.append(pg.Rect(x, y_start + i * (card_h + gap), card_w, card_h))
        return rects

    def _update_player_anim_for_mon(self, mon: dict) -> None:
        """
        依照寶可夢「名字」來決定戰鬥用動畫 sprite sheet。
        傳給 Animation 的路徑要是相對於 assets/images/。
        """
        name = str(mon.get("name", "")).lower()
        # 優先用名字對應的表，找不到就用預設
        sprite_path = PLAYER_ANIM_SHEETS.get(name, "sprites/sprite1_idle.png")

        self.player_anim = Animation(
            sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")



    def _handle_switch_menu(self) -> None:
        # ESC → 關閉選單
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_switch_menu = False
            self.message = self.message_menu
            return

        party = self._get_party()
        if not party:
            self.in_switch_menu = False
            self.message = "You have no Pokemon!"
            return

        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            panel = self._get_switch_panel_rect()
            card_rects = self._get_switch_card_rects(panel, len(party))
            for idx, rect in enumerate(card_rects):
                if rect.collidepoint(mx, my):
                    if idx == self.active_party_index:
                        # 點到的是目前上場的那隻
                        self.in_switch_menu = False
                        self.message = (
                            f"{party[idx].get('name', 'This one')} is already in battle."
                        )
                        return

                    # 換上新的寶可夢
                    self.active_party_index = idx
                    chosen = party[idx]

                    self.player_name = str(chosen.get("name", self.player_name))
                    max_hp = int(chosen.get("max_hp", self.player_max_hp))
                    cur_hp = int(chosen.get("hp", max_hp))
                    self.player_max_hp = max_hp
                    self.player_hp = cur_hp

                    self._update_player_anim_for_mon(chosen)

                    self.in_switch_menu = False
                    self.message = f"Go! {self.player_name}!"

                    # 跑出場放大動畫
                    self.player_zoom_timer = 0.0
                    self.phase = "PLAYER_ZOOM"
                    return

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

        # 玩家選擇回合：畫主選單或 item / switch 子選單
        if self.phase == "PLAYER_CHOICE":
            if self.in_item_menu:
                self._draw_item_buttons(screen)
            elif self.in_switch_menu:
                self._draw_switch_panel(screen)
            else:
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
        bar_back = pg.Rect(
            enemy_rect.x + 8, enemy_rect.y + box_h - 20, box_w - 16, 10
        )
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
        else:  # 戰鬥中 or END
            enemy_scale = self.enemy_scale_end
            player_scale = self.player_scale_end

        if enemy_scale > 0:
            self._draw_scaled_animation(
                screen, self.enemy_anim, self.enemy_pos, enemy_scale
            )

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
    # 選單按鈕（四顆保留 → Fight / Item / Switch / Run）
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
    # Switch 隊伍視窗（仿 BagScene 卡片）
    # -------------------------------------------------
    def _draw_switch_panel(self, screen: pg.Surface) -> None:
        party = self._get_party()
        if not party:
            return

        # 半透明黑背景
        overlay = pg.Surface(
            (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA
        )
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        # 視窗
        panel = self._get_switch_panel_rect()
        base_orange = (247, 182, 60)
        border_orange = (205, 132, 40)

        pg.draw.rect(screen, base_orange, panel)
        pg.draw.rect(screen, border_orange, panel, 3)

        # 標題
        title = self.font_medium.render("Choose a Pokemon", True, (255, 255, 255))
        screen.blit(title, (panel.x + 20, panel.y + 12))

        # 卡片 banner
        banner_img = pg.image.load(
            "assets/images/UI/raw/UI_Flat_Banner03a.png"
        ).convert_alpha()
        banner_w, banner_h = 260, 50
        banner_img = pg.transform.smoothscale(banner_img, (banner_w, banner_h))

        icon_size = 40
        gap = 12

        # 每一隻的卡片位置
        for i, mon in enumerate(party):
            x = panel.x + 20
            y = panel.y + 60 + i * (banner_h + gap)

            # Banner
            screen.blit(banner_img, (x, y))

            # 頭像
            sprite_rel = mon.get("sprite_path", "")
            sprite_path = (
                f"assets/images/{sprite_rel}"
                if sprite_rel
                else "assets/images/menu_sprites/menusprite1.png"
            )
            try:
                icon = pg.image.load(sprite_path).convert_alpha()
                icon = pg.transform.smoothscale(icon, (icon_size, icon_size))
            except Exception:
                icon = pg.Surface((icon_size, icon_size))
                icon.fill((200, 200, 200))

            screen.blit(icon, (x + 12, y + (banner_h - icon_size) // 2 - 4))

            # 名稱
            name = mon.get("name", "???")
            name_text = self.font_small.render(name, True, (0, 0, 0))
            screen.blit(name_text, (x + 60, y + 6))

            # Lv
            lv = mon.get("level", 1)
            lv_text = self.font_small.render(f"Lv.{lv}", True, (0, 0, 0))
            screen.blit(
                lv_text, (x + banner_w - lv_text.get_width() - 10, y + 6)
            )

            # HP Bar
            hp = mon.get("hp", 0)
            max_hp = mon.get("max_hp", max(hp, 1))
            ratio = hp / max_hp if max_hp > 0 else 0

            bar_x = x + 60
            bar_y = y + banner_h - 18
            bar_w = banner_w - 70
            bar_h = 12

            pg.draw.rect(screen, (0, 0, 0), (bar_x, bar_y, bar_w, bar_h), 1)
            inner = pg.Rect(
                bar_x + 2,
                bar_y + 2,
                int((bar_w - 4) * ratio),
                bar_h - 4,
            )
            pg.draw.rect(screen, (86, 176, 66), inner)

            hp_text = self.font_small.render(f"{hp}/{max_hp}", True, (0, 0, 0))
            screen.blit(
                hp_text,
                (
                    bar_x + bar_w // 2 - hp_text.get_width() // 2,
                    bar_y + bar_h // 2 - hp_text.get_height() // 2,
                ),
            )

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
