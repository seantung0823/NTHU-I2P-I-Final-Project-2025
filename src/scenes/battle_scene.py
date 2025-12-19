# src/scenes/battle_scene.py

from __future__ import annotations
import math
import re
import pygame as pg
from typing import override, TYPE_CHECKING

from src.scenes.scene import Scene
from src.utils import GameSettings
from src.core.services import scene_manager, input_manager, sound_manager
from src.sprites import BackgroundSprite, Animation

if TYPE_CHECKING:
    from src.data.bag import Bag


# =========================
#   ELEMENT SYSTEM
# =========================
ELEMENT_CHART = {
    "Water": {"strong": ["Fire"], "weak": ["Grass"]},
    "Fire": {"strong": ["Grass"], "weak": ["Water"]},
    "Grass": {"strong": ["Water"], "weak": ["Fire"]},
}

# =========================
#   EVOLUTION SYSTEM
# =========================
# 你提供的進化關係：
# 1→2→3
# 4/5/6 不會變化
# 7→8→9
# 10/11 不會變化
# 12→13→14
# 15→16
EVOLUTION_NEXT: dict[int, int] = {
    1: 2,
    2: 3,
    7: 8,
    8: 9,
    12: 13,
    13: 14,
    15: 16,
}


def battle_idle_sprite(species_id: int) -> str:
    """Animation 用：相對於 assets/images/ 的路徑"""
    return f"sprites/sprite{species_id}_idle.png"


def menu_icon_sprite(species_id: int) -> str:
    """Switch panel 用：相對於 assets/images/ 的路徑"""
    return f"sprites/sprite{species_id}.png"


class BattleScene(Scene):
    """
    BattleScene：
    - 放射轉場 (RADIAL)
    - 敵方放大 (ENEMY_ZOOM)
    - 我方放大 (PLAYER_ZOOM)
    - 回合制戰鬥：
        PLAYER_CHOICE → PLAYER_ATTACK → ENEMY_ATTACK → PLAYER_CHOICE
    - Fight / Run 有功能
    - Item：開啟道具選單（Heal / Strength / Defense / Cancel）
        * Heal Potion：補血
        * Strength Potion：提升攻擊
        * Defense Potion：降低敵方攻擊造成的傷害
    - Switch：
        * 打開隊伍視窗，顯示 Bag 裡的寶可夢
        * 點選可以把場上的寶可夢換成那一隻，動畫也跟著換
    - 結束時顯示 You win / You lose / Got away safely
      約 1 秒後自動回 game scene

    ✅ 新增：
    - 元素剋制：Water/Fire/Grass（可從 monster dict 的 "element" 讀）
    - 三種道具：Heal / Strength / Defense
    - 進化：打贏後依照 EVOLUTION_NEXT 進化，換資源並提升數值
    """

    background: BackgroundSprite

    @override
    def __init__(self, bag: "Bag | None" = None) -> None:
        super().__init__()

        # ---------- Switch Menu Scroll ----------
        self.switch_scroll_y: int = 0          # 清單垂直捲動量（像素）
        self.switch_scroll_speed: int = 28     # 每次滾動的像素（可調）


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
        self.message_menu = "What will you do?"
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
        self.player_name = "sprite1"
        self.enemy_name = "Enemy"

        self.player_max_hp = 100
        self.player_hp = self.player_max_hp

        self.enemy_max_hp = 80
        self.enemy_hp = self.enemy_max_hp

        self.player_attack_power = 30
        self.enemy_attack_power = 20

        # 用來記錄目前玩家的 sprite 編號（進化要用）
        self.player_species_id: int | None = 1

        # ---------- 元素屬性 ----------
        self.player_element: str = "Water"
        self.enemy_element: str = "Fire"

        # ---------- 三種道具 Buff（每場戰鬥重置） ----------
        self.attack_buff: int = 0  # Strength Potion
        self.defense_buff: int = 0  # Defense Potion（降低敵傷）

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

        # reset switch scroll
        self.switch_scroll_y = 0


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

        # 每場戰鬥重置 buff
        self.attack_buff = 0
        self.defense_buff = 0

        self.battle_result = None
        self.action_timer = 0.0
        self.end_timer = 0.0
        self.in_item_menu = False
        self.in_switch_menu = False

        # 如果有接 Bag，用第一隻寶可夢更新名字、HP、動畫、元素
        party = self._get_party()
        if party:
            self.active_party_index = min(self.active_party_index, len(party) - 1)
            active = party[self.active_party_index]

            # HP
            max_hp = int(active.get("max_hp", self.player_max_hp))
            cur_hp = int(active.get("hp", max_hp))
            self.player_max_hp = max_hp
            self.player_hp = cur_hp

            # 元素
            ele = active.get("element")
            if isinstance(ele, str) and ele:
                self.player_element = ele

            # 推斷物種編號（進化用）
            sid = self._infer_species_id(active)
            self.player_species_id = sid

            # 名字：如果你希望永遠顯示 spriteX，就用這個
            if sid is not None:
                self.player_name = f"sprite{sid}"
            else:
                self.player_name = str(active.get("name", self.player_name))

            # 動畫依照 species_id 或 name 更新
            self._update_player_anim_for_mon(active)
        else:
            # 沒隊伍就用預設
            self.player_hp = self.player_max_hp
            self.player_species_id = self._infer_species_id({"name": self.player_name})
            self._update_player_anim_for_name(self.player_name)

        self.enemy_hp = self.enemy_max_hp

        # 播戰鬥 BGM
        sound_manager.play_bgm("RBY 107 Battle! (Trainer).ogg")

    # -------------------------------------------------
    # Update
    # -------------------------------------------------
    @override
    def update(self, dt: float) -> None:
        # clamp dt
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
                    # ✅ WIN → 嘗試進化
                    self._try_evolve()
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

        # ---------- 結束戰鬥 ----------
        if self.phase == "END":
            self.end_timer += step
            if self.end_timer >= self.end_duration:
                scene_manager.change_scene("game")
            return

    # -------------------------------------------------
    # Element helpers
    # -------------------------------------------------
    def _element_multiplier(self, atk: str, target: str) -> float:
        chart = ELEMENT_CHART.get(atk)
        if not chart:
            return 1.0
        if target in chart["strong"]:
            return 1.5
        if target in chart["weak"]:
            return 0.5
        return 1.0

    # -------------------------------------------------
    # Evolution helpers
    # -------------------------------------------------
    def _infer_species_id(self, mon: dict) -> int | None:
        """
        推斷 sprite 編號：
        優先 mon["species_id"] (int)
        再看 mon["sprite_path"] 裡有沒有 sprite12
        再看 mon["name"] 裡的數字
        """
        sid = mon.get("species_id")
        if isinstance(sid, int) and sid > 0:
            return sid

        sp = str(mon.get("sprite_path", ""))
        m = re.search(r"sprite(\d+)", sp, re.IGNORECASE)
        if m:
            return int(m.group(1))

        name = str(mon.get("name", ""))
        m2 = re.search(r"(\d+)", name)
        if m2:
            return int(m2.group(1))

        return None

    def _apply_evolution_stats(self) -> None:
        """
        進化後數值提升（你可調）：
        HP +25%，ATK +20%
        """
        self.player_max_hp = max(self.player_max_hp + 1, int(self.player_max_hp * 1.25))
        self.player_attack_power = max(
            self.player_attack_power + 1, int(self.player_attack_power * 1.20)
        )
        self.player_hp = self.player_max_hp

    def _evolve_to_species(self, new_sid: int) -> None:
        """換名字、換動畫、提升數值、同步回 Bag 資料"""
        self.player_species_id = new_sid
        self.player_name = f"sprite{new_sid}"

        # 數值提升
        self._apply_evolution_stats()

        # 換戰鬥動畫
        self.player_anim = Animation(
            battle_idle_sprite(new_sid),
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")

        # 同步寫回 Bag active monster（讓你回到遊戲時也維持進化）
        party = self._get_party()
        if party and 0 <= self.active_party_index < len(party):
            mon = party[self.active_party_index]
            mon["species_id"] = new_sid
            mon["name"] = f"sprite{new_sid}"
            # menu icon（Switch panel 用）
            mon["sprite_path"] = menu_icon_sprite(new_sid)
            # 同步血量
            mon["max_hp"] = self.player_max_hp
            mon["hp"] = self.player_hp
            # 如果你有把 attack 存在 monster dict，也同步
            mon["attack"] = self.player_attack_power

    def _try_evolve(self) -> None:
        cur = self.player_species_id
        if cur is None:
            return
        nxt = EVOLUTION_NEXT.get(cur)
        if not nxt:
            return
        self._evolve_to_species(nxt)
        self.message = f"{self.player_name} evolved!"

    # -------------------------------------------------
    # 玩家選擇回合
    # -------------------------------------------------
    def _handle_player_choice(self) -> None:
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

        # mouse buttons
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
    # Item 子選單：Heal / Strength / Defense / Cancel
    # -------------------------------------------------
    def _handle_item_menu(self) -> None:
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        # 1/2/3/4
        if input_manager.key_pressed(pg.K_1):
            self._use_heal_potion()
            return
        if input_manager.key_pressed(pg.K_2):
            self._use_strength_potion()
            return
        if input_manager.key_pressed(pg.K_3):
            self._use_defense_potion()
            return
        if input_manager.key_pressed(pg.K_4):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_item_buttons():
                if rect.collidepoint(mx, my):
                    if label == "Heal Potion":
                        self._use_heal_potion()
                    elif label == "Strength Potion":
                        self._use_strength_potion()
                    elif label == "Defense Potion":
                        self._use_defense_potion()
                    elif label == "Cancel":
                        self.in_item_menu = False
                        self.message = self.message_menu
                    return

    def _use_heal_potion(self) -> None:
        # 支援多種命名（你 Bag 裡可能是 Potion / Heal Potion）
        if not self._consume_item_any(
            ["heal potion", "heal_potion", "potion", "Potion", "Heal Potion"]
        ):
            self.message = "No Heal Potion left!"
            return

        heal_amount = 30
        old_hp = self.player_hp
        self.player_hp = min(self.player_max_hp, self.player_hp + heal_amount)
        real_heal = self.player_hp - old_hp

        # 同步回 bag
        party = self._get_party()
        if party and 0 <= self.active_party_index < len(party):
            party[self.active_party_index]["hp"] = self.player_hp

        self.message = f"You used a Heal Potion! (+{real_heal} HP)"
        self.in_item_menu = False

    def _use_strength_potion(self) -> None:
        if not self._consume_item_any(
            ["strength potion", "strength_potion", "Strength Potion"]
        ):
            self.message = "No Strength Potion left!"
            return

        self.attack_buff += 10
        self.message = "Attack increased! (+10)"
        self.in_item_menu = False

    def _use_defense_potion(self) -> None:
        if not self._consume_item_any(
            ["defense potion", "defense_potion", "Defense Potion"]
        ):
            self.message = "No Defense Potion left!"
            return

        self.defense_buff += 5
        self.message = "Defense increased! (-5 damage)"
        self.in_item_menu = False

    # -------------------------------------------------
    # Fight / Run / 攻擊結算
    # -------------------------------------------------
    def _player_attack(self) -> None:
        mult = self._element_multiplier(self.player_element, self.enemy_element)
        damage = int((self.player_attack_power + self.attack_buff) * mult)
        damage = max(1, damage)

        self.enemy_hp = max(0, self.enemy_hp - damage)

        eff = ""
        if mult > 1.0:
            eff = " It's super effective!"
        elif mult < 1.0:
            eff = " It's not very effective..."

        self.message = (
            f"{self.player_name} attacked! "
            f"({self.player_element} vs {self.enemy_element}) "
            f"-{damage} HP.{eff} "
            f"Enemy HP: {self.enemy_hp}/{self.enemy_max_hp}"
        )

        self.phase = "PLAYER_ATTACK"
        self.action_timer = 0.0

    def _start_enemy_attack(self) -> None:
        raw = self.enemy_attack_power
        damage = max(1, raw - self.defense_buff)

        self.player_hp = max(0, self.player_hp - damage)

        # 同步回 bag
        party = self._get_party()
        if party and 0 <= self.active_party_index < len(party):
            party[self.active_party_index]["hp"] = self.player_hp

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
    # Bag helpers + Party helpers
    # -------------------------------------------------
    def _get_item_count(self, name: str) -> int:
        if not self.bag:
            return 999
        items = getattr(self.bag, "_items_data", [])
        target = name.lower().strip()
        for it in items:
            if it.get("name", "").lower().strip() == target:
                return int(it.get("count", 0))
        return 0

    def _consume_item(self, name: str) -> bool:
        if not self.bag:
            return True

        items = getattr(self.bag, "_items_data", [])
        target = name.lower().strip()
        for it in items:
            if it.get("name", "").lower().strip() == target:
                cnt = int(it.get("count", 0))
                if cnt <= 0:
                    return False
                it["count"] = cnt - 1
                return True
        return False

    def _consume_item_any(self, names: list[str]) -> bool:
        if not self.bag:
            return True
        for nm in names:
            if self._consume_item(nm):
                return True
        return False

    def _get_party(self) -> list[dict]:
        if not self.bag:
            return []
        mons = getattr(self.bag, "_monsters_data", [])
        if not isinstance(mons, list):
            return []
        return mons

    def _can_open_switch_menu(self) -> bool:
        return len(self._get_party()) >= 2

    # -------------------------------------------------
    # Animation helpers
    # -------------------------------------------------
    def _update_player_anim_for_name(self, name: str) -> None:
        sid = self._infer_species_id({"name": name})
        if sid is not None:
            sprite_path = battle_idle_sprite(sid)
        else:
            sprite_path = "sprites/sprite1_idle.png"

        self.player_anim = Animation(
            sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")

    def _update_player_anim_for_mon(self, mon: dict) -> None:
        sid = self._infer_species_id(mon)
        if sid is not None:
            sprite_path = battle_idle_sprite(sid)
        else:
            sprite_path = "sprites/sprite1_idle.png"

        self.player_anim = Animation(
            sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")

    # -------------------------------------------------
    # Switch menu UI helpers
    # -------------------------------------------------
    def _get_switch_list_rect(self, panel: pg.Rect) -> pg.Rect:
        """
        Switch 視窗中「清單可視區域」(用來做 clip + 點擊判定)
        上方留 title，下方留一點 padding
        """
        margin_top = 60
        margin_bottom = 18
        return pg.Rect(panel.x + 20, panel.y + margin_top, panel.width - 40, panel.height - margin_top - margin_bottom)

    def _get_switch_max_scroll(self, party_count: int, row_h: int, list_rect: pg.Rect) -> int:
        total_h = party_count * row_h
        return max(0, total_h - list_rect.height)

    def _read_mouse_wheel(self) -> int:
        """
        不同專案 input_manager 可能有不同滾輪欄位：
        - mouse_wheel_y / wheel_y / scroll_y ...
        這裡用 getattr 安全讀，讀不到就當作 0
        回傳值：正/負（依你的 input_manager 定義）
        """
        for attr in ("mouse_wheel_y", "wheel_y", "scroll_y", "mouse_wheel"):
            v = getattr(input_manager, attr, 0)
            # 有些人做成 function mouse_wheel() -> int
            if callable(v):
                try:
                    v = v()
                except Exception:
                    v = 0
            if isinstance(v, int) and v != 0:
                return v
        return 0

    def _get_switch_panel_rect(self) -> pg.Rect:
        w, h = 420, 260
        x = (GameSettings.SCREEN_WIDTH - w) // 2
        y = (GameSettings.SCREEN_HEIGHT - h) // 2
        return pg.Rect(x, y, w, h)

    def _get_switch_card_rects(self, panel: pg.Rect, count: int) -> list[pg.Rect]:
        card_w = panel.width - 40
        card_h = 50
        x = panel.x + 20
        y_start = panel.y + 60
        gap = 12
        return [
            pg.Rect(x, y_start + i * (card_h + gap), card_w, card_h) for i in range(count)
        ]

    def _handle_switch_menu(self) -> None:
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_switch_menu = False
            self.message = self.message_menu
            return

        party = self._get_party()
        if not party:
            self.in_switch_menu = False
            self.message = "You have no Pokemon!"
            return

        panel = self._get_switch_panel_rect()
        list_rect = self._get_switch_list_rect(panel)

        # 這些要跟 draw 那邊一致
        banner_h = 50
        gap = 12
        row_h = banner_h + gap

        # ---------- Scroll input ----------
        # keyboard scroll
        if input_manager.key_pressed(pg.K_DOWN) or input_manager.key_pressed(pg.K_s):
            self.switch_scroll_y += self.switch_scroll_speed
        if input_manager.key_pressed(pg.K_UP) or input_manager.key_pressed(pg.K_w):
            self.switch_scroll_y -= self.switch_scroll_speed

        # mouse wheel scroll (如果你的 input_manager 有提供)
        wheel_y = self._read_mouse_wheel()
        if wheel_y != 0:
            # 有些專案 wheel_y 往上是 +1，有些是 -1
            # 這裡統一成：wheel_y > 0 → 往上捲（scroll_y 減少）
            if wheel_y > 0:
                self.switch_scroll_y -= self.switch_scroll_speed
            else:
                self.switch_scroll_y += self.switch_scroll_speed

        max_scroll = self._get_switch_max_scroll(len(party), row_h, list_rect)
        self.switch_scroll_y = max(0, min(self.switch_scroll_y, max_scroll))

        # ---------- Click to select ----------
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos

            # 只處理點在清單可視區域內的點擊
            if list_rect.collidepoint(mx, my):
                # 把可視座標轉成清單「真實座標」：加上 scroll
                local_y = (my - list_rect.y) + self.switch_scroll_y
                idx = local_y // row_h

                if 0 <= idx < len(party):
                    if idx == self.active_party_index:
                        self.in_switch_menu = False
                        self.message = f"{party[idx].get('name', 'This one')} is already in battle."
                        return

                    self.active_party_index = int(idx)
                    chosen = party[self.active_party_index]

                    # reset buffs
                    self.attack_buff = 0
                    self.defense_buff = 0

                    # update hp
                    max_hp = int(chosen.get("max_hp", self.player_max_hp))
                    cur_hp = int(chosen.get("hp", max_hp))
                    self.player_max_hp = max_hp
                    self.player_hp = cur_hp

                    # element
                    ele = chosen.get("element")
                    if isinstance(ele, str) and ele:
                        self.player_element = ele

                    # species id
                    sid = self._infer_species_id(chosen)
                    self.player_species_id = sid
                    if sid is not None:
                        self.player_name = f"sprite{sid}"
                    else:
                        self.player_name = str(chosen.get("name", self.player_name))

                    self._update_player_anim_for_mon(chosen)

                    self.in_switch_menu = False
                    self.message = f"Go! {self.player_name}!"

                    # zoom
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

        pg.draw.rect(screen, (0, 0, 0), self.dialog_rect)
        text = self.font_medium.render(self.message, True, (255, 255, 255))
        screen.blit(text, (self.dialog_rect.left + 16, self.dialog_rect.top + 16))

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
    # HP UI
    # -------------------------------------------------
    def _draw_hp_boxes(self, screen: pg.Surface) -> None:
        box_w, box_h = 180, 60

        enemy_rect = pg.Rect(GameSettings.SCREEN_WIDTH - box_w - 20, 20, box_w, box_h)
        pg.draw.rect(screen, (255, 255, 255), enemy_rect)
        pg.draw.rect(screen, (0, 0, 0), enemy_rect, 2)

        name_text = self.font_small.render(self.enemy_name, True, (0, 0, 0))
        screen.blit(name_text, (enemy_rect.x + 8, enemy_rect.y + 8))

        hp_ratio = self.enemy_hp / self.enemy_max_hp if self.enemy_max_hp > 0 else 0
        bar_back = pg.Rect(enemy_rect.x + 8, enemy_rect.y + box_h - 20, box_w - 16, 10)
        pg.draw.rect(screen, (80, 80, 80), bar_back)
        bar = pg.Rect(bar_back.x, bar_back.y, int(bar_back.w * hp_ratio), 10)
        pg.draw.rect(screen, (0, 200, 0), bar)

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

        p_ratio = self.player_hp / self.player_max_hp if self.player_max_hp > 0 else 0
        p_bar_back = pg.Rect(player_rect.x + 8, player_rect.y + box_h - 20, box_w - 16, 10)
        pg.draw.rect(screen, (80, 80, 80), p_bar_back)
        p_bar = pg.Rect(p_bar_back.x, p_bar_back.y, int(p_bar_back.w * p_ratio), 10)
        pg.draw.rect(screen, (0, 200, 0), p_bar)

    # -------------------------------------------------
    # Monster draw / zoom
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
        else:
            enemy_scale = self.enemy_scale_end
            player_scale = self.player_scale_end

        if enemy_scale > 0:
            self._draw_scaled_animation(screen, self.enemy_anim, self.enemy_pos, enemy_scale)
        if player_scale > 0:
            self._draw_scaled_animation(screen, self.player_anim, self.player_pos, player_scale)

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
        surf = pg.transform.smoothscale(frame, (int(w * scale), int(h * scale)))
        rect = surf.get_rect(center=center)
        screen.blit(surf, rect)

    # -------------------------------------------------
    # Main menu buttons
    # -------------------------------------------------
    def _get_menu_buttons(self):
        labels = ["Fight", "Item", "Switch", "Run"]
        btn_w, btn_h = 140, 40
        gap = 20
        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        return [
            (pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h), label)
            for i, label in enumerate(labels)
        ]

    def _draw_menu_buttons(self, screen: pg.Surface) -> None:
        for rect, label in self._get_menu_buttons():
            pg.draw.rect(screen, (230, 215, 190), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)
            txt = self.font_small.render(label, True, (0, 0, 0))
            screen.blit(txt, txt.get_rect(center=rect.center))

    # -------------------------------------------------
    # Item buttons
    # -------------------------------------------------
    def _get_item_buttons(self):
        labels = ["Heal Potion", "Strength Potion", "Defense Potion", "Cancel"]
        btn_w, btn_h = 140, 40
        gap = 16
        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        return [
            (pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h), label)
            for i, label in enumerate(labels)
        ]

    def _draw_item_buttons(self, screen: pg.Surface) -> None:
        for rect, label in self._get_item_buttons():
            pg.draw.rect(screen, (230, 215, 190), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)
            txt = self.font_small.render(label, True, (0, 0, 0))
            screen.blit(txt, txt.get_rect(center=rect.center))

    # -------------------------------------------------
    # Switch panel draw
    # -------------------------------------------------
    def _draw_switch_panel(self, screen: pg.Surface) -> None:
        party = self._get_party()
        if not party:
            return

        overlay = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        panel = self._get_switch_panel_rect()
        base_orange = (247, 182, 60)
        border_orange = (205, 132, 40)

        pg.draw.rect(screen, base_orange, panel)
        pg.draw.rect(screen, border_orange, panel, 3)

        title = self.font_medium.render("Choose a Pokemon", True, (255, 255, 255))
        screen.blit(title, (panel.x + 20, panel.y + 12))

        banner_img = pg.image.load("assets/images/UI/raw/UI_Flat_Banner03a.png").convert_alpha()
        banner_w, banner_h = 260, 50
        banner_img = pg.transform.smoothscale(banner_img, (banner_w, banner_h))

        icon_size = 40
        gap = 12
        row_h = banner_h + gap

        # 清單可視區域（用來 clip）
        list_rect = self._get_switch_list_rect(panel)

        # clamp scroll（避免 party 數量變動導致超出）
        max_scroll = self._get_switch_max_scroll(len(party), row_h, list_rect)
        self.switch_scroll_y = max(0, min(self.switch_scroll_y, max_scroll))

        # 只畫可視區域
        old_clip = screen.get_clip()
        screen.set_clip(list_rect)

        # 重要：畫的 y 要扣掉 scroll
        start_y = list_rect.y - self.switch_scroll_y

        for i, mon in enumerate(party):
            x = panel.x + 20
            y = start_y + i * row_h

            # 略過完全不在可視區域的 row（小優化）
            if y + banner_h < list_rect.top or y > list_rect.bottom:
                continue

            screen.blit(banner_img, (x, y))

            # icon：優先 mon["sprite_path"]，沒有就推斷 species_id
            sprite_rel = str(mon.get("sprite_path", "")).strip()
            if not sprite_rel:
                sid = self._infer_species_id(mon)
                if sid is not None:
                    sprite_rel = menu_icon_sprite(sid)

            sprite_path = f"assets/images/{sprite_rel}" if sprite_rel else "assets/images/menu_sprites/menusprite1.png"
            try:
                icon = pg.image.load(sprite_path).convert_alpha()
                icon = pg.transform.smoothscale(icon, (icon_size, icon_size))
            except Exception:
                icon = pg.Surface((icon_size, icon_size))
                icon.fill((200, 200, 200))

            screen.blit(icon, (x + 12, y + (banner_h - icon_size) // 2 - 4))

            name = mon.get("name", "???")
            name_text = self.font_small.render(str(name), True, (0, 0, 0))
            screen.blit(name_text, (x + 60, y + 6))

            lv = mon.get("level", 1)
            lv_text = self.font_small.render(f"Lv.{lv}", True, (0, 0, 0))
            screen.blit(lv_text, (x + banner_w - lv_text.get_width() - 10, y + 6))

            hp = int(mon.get("hp", 0))
            max_hp2 = int(mon.get("max_hp", max(hp, 1)))
            ratio = hp / max_hp2 if max_hp2 > 0 else 0

            bar_x = x + 60
            bar_y = y + banner_h - 18
            bar_w = banner_w - 70
            bar_h = 12

            pg.draw.rect(screen, (0, 0, 0), (bar_x, bar_y, bar_w, bar_h), 1)
            inner = pg.Rect(bar_x + 2, bar_y + 2, int((bar_w - 4) * ratio), bar_h - 4)
            pg.draw.rect(screen, (86, 176, 66), inner)

            hp_text = self.font_small.render(f"{hp}/{max_hp2}", True, (0, 0, 0))
            screen.blit(
                hp_text,
                (
                    bar_x + bar_w // 2 - hp_text.get_width() // 2,
                    bar_y + bar_h // 2 - hp_text.get_height() // 2,
                ),
            )

        # 還原 clip
        screen.set_clip(old_clip)

        # （可選）畫一個簡單 scrollbar（不影響功能）
        if max_scroll > 0:
            track = pg.Rect(panel.right - 16, list_rect.top, 6, list_rect.height)
            pg.draw.rect(screen, (60, 60, 60), track)

            thumb_h = max(24, int(list_rect.height * (list_rect.height / (list_rect.height + max_scroll))))
            thumb_y = list_rect.top + int((list_rect.height - thumb_h) * (self.switch_scroll_y / max_scroll))
            thumb = pg.Rect(track.x, thumb_y, track.width, thumb_h)
            pg.draw.rect(screen, (230, 230, 230), thumb)


    # -------------------------------------------------
    # Radial transition
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
