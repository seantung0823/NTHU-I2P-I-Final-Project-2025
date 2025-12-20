# src/scenes/battle_scene.py

from __future__ import annotations
import math
import re
import secrets
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


# -------------------------
# Element inference by species_id (your mapping)
# -------------------------
SPECIES_ELEMENT: dict[int, str] = {
    # Grass
    1: "Grass", 2: "Grass", 3: "Grass", 4: "Grass", 5: "Grass", 15: "Grass", 16: "Grass",
    # Water
    6: "Water", 12: "Water", 13: "Water", 14: "Water",
    # Fire
    7: "Fire", 8: "Fire", 9: "Fire", 10: "Fire", 11: "Fire",
}


def infer_element_from_mon(mon: dict) -> str | None:
    """Infer element from a monster dict using (1) explicit 'element' then (2) species_id/sprite number mapping."""
    ele = mon.get("element")
    if isinstance(ele, str) and ele.strip():
        return ele.strip()

    # try infer species id from fields that already exist in this project
    sid = mon.get("species_id")
    if not isinstance(sid, int) or sid <= 0:
        sp = str(mon.get("sprite_path", "") or mon.get("sprite", "") or mon.get("battle_sprite", "") or "")
        m0 = re.search(r"menusprite(\d+)\.png", sp, re.IGNORECASE)
        if m0:
            try:
                sid = int(m0.group(1))
            except Exception:
                sid = None
        if not isinstance(sid, int):
            m1 = re.search(r"sprite(\d+)", sp, re.IGNORECASE)
            if m1:
                try:
                    sid = int(m1.group(1))
                except Exception:
                    sid = None

    if isinstance(sid, int) and sid in SPECIES_ELEMENT:
        return SPECIES_ELEMENT[sid]
    return None



def battle_idle_sprite(species_id: int) -> str:
    """Animation 用：相對於 assets/images/ 的路徑"""
    return f"sprites/sprite{species_id}_idle.png"




# Enemy species pool (your request)
ENEMY_SPECIES_POOL: list[int] = [3, 12, 9]

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

        self.player_attack_power = 15
        self.enemy_attack_power = 20


        # remember last random enemy to reduce repeats
        self._enemy_last_sid: int | None = None
        # 用來記錄目前玩家的 sprite 編號（進化要用）
        self.player_species_id: int | None = 1

        # ---------- 元素屬性 ----------
        self.player_element: str = "Water"
        self.enemy_element: str = infer_element_from_mon({"battle_sprite": "sprites/sprite8_idle.png"}) or "Fire"

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
    # Bag binding (guarantee BattleScene reads the SAME bag as BagScene)
    # -------------------------------------------------
    def _ensure_bag(self) -> None:
        """Best-effort to attach a Bag instance if caller forgot to pass it in.

        BattleScene should be created with BattleScene(bag=self.game_manager.bag).
        But to make it robust (and match your request: "保證可以抓背包資料"),
        we try to discover the bag from SceneManager / GameScene at runtime.

        This will NOT create fake data; it only tries to find the existing bag object.
        """
        if self.bag is not None:
            return

        candidates = []

        # Common "current scene" patterns
        for attr in ("current_scene", "scene", "_scene", "active_scene"):
            s = getattr(scene_manager, attr, None)
            if s is not None:
                candidates.append(s)

        # Common "get scene by name" patterns
        for meth in ("get_scene", "get", "find_scene"):
            fn = getattr(scene_manager, meth, None)
            if callable(fn):
                try:
                    s = fn("game")
                    if s is not None:
                        candidates.append(s)
                except Exception:
                    pass

        # Common "scenes dict" patterns
        for attr in ("scenes", "_scenes"):
            d = getattr(scene_manager, attr, None)
            if isinstance(d, dict):
                for key in ("game", "GameScene"):
                    s = d.get(key)
                    if s is not None:
                        candidates.append(s)

        # Try to locate bag from any candidate
        for s in candidates:
            gm = getattr(s, "game_manager", None)
            if gm is not None:
                b = getattr(gm, "bag", None)
                if b is not None:
                    self.bag = b
                    return
            b = getattr(s, "bag", None)
            if b is not None:
                self.bag = b
                return

    # -------------------------------------------------
    # Scene lifecycle
    # -------------------------------------------------
    @override
    def enter(self) -> None:
        self._ensure_bag()
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

            # 元素（若 monster 沒寫 element，就依 species_id/sprite 自動推斷）
            ele = infer_element_from_mon(active)
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

        
        # -------------------------------------------------
        # Enemy setup (random from ENEMY_SPECIES_POOL every battle enter)
        # -------------------------------------------------
        sid_e = self._pick_enemy_species()
        self.enemy_name = f"sprite{sid_e}"
        self.enemy_anim = Animation(
            battle_idle_sprite(sid_e),
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.enemy_anim.switch("idle")
        self.enemy_element = infer_element_from_mon({"species_id": sid_e, "battle_sprite": battle_idle_sprite(sid_e)}) or self.enemy_element
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
            return 1.2
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
        再看 sprite_path / sprite 裡有沒有：
        - menusprite12.png
        - sprite12
        再看 name 裡的數字
        """
        sid = mon.get("species_id")
        if isinstance(sid, int) and sid > 0:
            return sid

        sp = str(mon.get("sprite_path", "") or mon.get("sprite", "") or "")

        # ✅ NEW: menusprite(\d+).png
        m0 = re.search(r"menusprite(\d+)\.png", sp, re.IGNORECASE)
        if m0:
            return int(m0.group(1))

        # 原本的 sprite(\d+)
        m = re.search(r"sprite(\d+)", sp, re.IGNORECASE)
        if m:
            return int(m.group(1))

        name = str(mon.get("name", ""))
        m2 = re.search(r"(\d+)", name)
        if m2:
            return int(m2.group(1))

        return None









    def _pick_enemy_species(self) -> int:
        """Pick an enemy species id from ENEMY_SPECIES_POOL.
        Uses secrets.choice so it won't be affected by random.seed().
        If pool has >=2, try to avoid picking the same one twice in a row.
        """
        pool = [int(x) for x in ENEMY_SPECIES_POOL if int(x) > 0]
        if not pool:
            return 8
        if len(pool) == 1:
            self._enemy_last_sid = pool[0]
            return pool[0]

        # avoid repeats if possible
        sid = secrets.choice(pool)
        tries = 0
        while self._enemy_last_sid is not None and sid == self._enemy_last_sid and tries < 6:
            sid = secrets.choice(pool)
            tries += 1
        self._enemy_last_sid = sid
        return sid
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
    def _get_items_data(self) -> list[dict]:
        self._ensure_bag()
        """Try to fetch items list from Bag in a robust way.

        Supports:
        - bag._items_data (our standard)
        - bag.items / bag.get("items")
        - if bag has _resolve_bag(), call it once to refresh cached lists
        """
        if not self.bag:
            return []
        # if Bag has a resolver, try it once (safe)
        resolver = getattr(self.bag, "_resolve_bag", None)
        if callable(resolver):
            try:
                resolver()
            except Exception:
                pass

        items = getattr(self.bag, "_items_data", None)
        if isinstance(items, list):
            return items

        items = getattr(self.bag, "items", None)
        if isinstance(items, list):
            return items

        if isinstance(self.bag, dict) and isinstance(self.bag.get("items"), list):
            return self.bag["items"]

        return []

    # NOTE:
    # Item count / consume is handled by the alias-aware helpers below:
    #   - _get_item_count_any(...)
    #   - _consume_item_any(...)
    # We keep a single source of truth to avoid inconsistent behavior.


    def _get_party(self) -> list[dict]:
        self._ensure_bag()
        if not self.bag:
            return []

        mons = getattr(self.bag, "_monsters_data", None)
        if isinstance(mons, list):
            return mons

        mons = getattr(self.bag, "monsters", None)
        if isinstance(mons, list):
            return mons

        if isinstance(self.bag, dict) and isinstance(self.bag.get("monsters"), list):
            return self.bag["monsters"]

        return []



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
        # ESC 關閉
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_switch_menu = False
            self.message = self.message_menu
            return

        party = self._get_party()
        if not party:
            self.in_switch_menu = False
            self.message = "You have no Pokemon!"
            return

        # ✅ 重要：點擊區域要跟 _draw_switch_panel() 完全一致
        panel = self._get_switch_panel_rect()
        banner_h = 50
        gap = 12
        card_x = panel.x + 20
        card_w = 260  # 你 draw 時 banner_w = 260
        card_y0 = panel.y + 60

        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos

            for idx, mon in enumerate(party):
                y = card_y0 + idx * (banner_h + gap)
                rect = pg.Rect(card_x, y, card_w, banner_h)

                if not rect.collidepoint(mx, my):
                    continue

                # 1) 點到正在上場的那隻：不要關閉視窗，只提示
                if idx == self.active_party_index:
                    self.message = f"{party[idx].get('name', 'This one')} is already in battle."
                    return

                # 2) 不能切換已倒下的
                if int(mon.get("hp", 0)) <= 0:
                    self.message = f"{mon.get('name', 'That Pokemon')} has fainted!"
                    return

                # 3) ✅ 防呆：如果其實沒有任何「其他活著的」就不讓切
                #    （避免你的 _can_open_switch_menu 判斷太寬造成誤開）
                has_other_alive = False
                for j, m2 in enumerate(party):
                    if j != self.active_party_index and int(m2.get("hp", 0)) > 0:
                        has_other_alive = True
                        break
                if not has_other_alive:
                    self.in_switch_menu = False
                    self.message = "No other Pokemon to switch!"
                    return

                # ✅ 切換成功
                self.active_party_index = idx
                chosen = party[idx]

                # reset buffs
                self.attack_buff = 0
                self.defense_buff = 0

                # update hp
                max_hp = int(chosen.get("max_hp", self.player_max_hp))
                cur_hp = int(chosen.get("hp", max_hp))
                self.player_max_hp = max_hp
                self.player_hp = cur_hp

                # element（若 monster 沒寫 element，就依 species_id/sprite 自動推斷）
                ele = infer_element_from_mon(chosen)
                if isinstance(ele, str) and ele:
                    self.player_element = ele

                # species id / name
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

        for i, mon in enumerate(party):
            x = panel.x + 20
            y = panel.y + 60 + i * (banner_h + gap)

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
            max_hp = int(mon.get("max_hp", max(hp, 1)))
            ratio = hp / max_hp if max_hp > 0 else 0

            bar_x = x + 60
            bar_y = y + banner_h - 18
            bar_w = banner_w - 70
            bar_h = 12

            pg.draw.rect(screen, (0, 0, 0), (bar_x, bar_y, bar_w, bar_h), 1)
            inner = pg.Rect(bar_x + 2, bar_y + 2, int((bar_w - 4) * ratio), bar_h - 4)
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

    # =================================================
    # Item name normalization + alias-aware counts
    # =================================================
    # 你背包裡的道具名字可能會是：
    # - "Heal Potion" / "heal_potion" / "potion"
    # - "Strength Potion" / "strength_potion"
    # - "Defense Potion" / "defense_potion"
    #
    # 這裡做一個「同義名稱」的統一處理，讓 UI 顯示正確數量、也能順利消耗。

    HEAL_POTION_ALIASES = [
        "heal potion", "heal_potion", "potion", "Potion", "Heal Potion"
    ]
    STRENGTH_POTION_ALIASES = [
        "strength potion", "strength_potion", "Strength Potion"
    ]
    DEFENSE_POTION_ALIASES = [
        "defense potion", "defense_potion", "Defense Potion"
    ]

    def _norm_item_name(self, s: str) -> str:
        s = str(s).lower().strip().replace("_", " ")
        s = re.sub(r"\s+", " ", s)
        return s

    def _get_item_count_any(self, names: list[str]) -> int:
        if not self.bag:
            return 999
        items = self._get_items_data()
        if not isinstance(items, list):
            return 0
        aliases = {self._norm_item_name(n) for n in names if n}
        for it in items:
            nm = self._norm_item_name(it.get("name", ""))
            if nm in aliases:
                return int(it.get("count", 0))
        return 0

    def _consume_item_any(self, names: list[str]) -> bool:
        if not self.bag:
            return True
        items = self._get_items_data()
        if not isinstance(items, list):
            return False
        aliases = {self._norm_item_name(n) for n in names if n}
        for it in items:
            nm = self._norm_item_name(it.get("name", ""))
            if nm in aliases:
                cnt = int(it.get("count", 0))
                if cnt <= 0:
                    return False
                it["count"] = cnt - 1
                return True
        return False

    # -------------------------------------------------
    # Item menu buttons (3 items + cancel) with counts
    # -------------------------------------------------
    def _get_item_buttons(self):
        heal_cnt = self._get_item_count_any(self.HEAL_POTION_ALIASES)
        str_cnt = self._get_item_count_any(self.STRENGTH_POTION_ALIASES)
        def_cnt = self._get_item_count_any(self.DEFENSE_POTION_ALIASES)

        labels = [
            f"Heal Potion x{heal_cnt}",
            f"Strength Potion x{str_cnt}",
            f"Defense Potion x{def_cnt}",
            "Cancel",
        ]
        btn_w, btn_h = 190, 40
        gap = 16
        total_width = btn_w * len(labels) + gap * (len(labels) - 1)
        x_start = (GameSettings.SCREEN_WIDTH - total_width) // 2
        y = self.dialog_rect.top + 60

        return [
            (pg.Rect(x_start + i * (btn_w + gap), y, btn_w, btn_h), label)
            for i, label in enumerate(labels)
        ]

    def _draw_item_buttons(self, screen: pg.Surface) -> None:
        # 讓道具選單跟主選單長得一致（可點擊）
        for rect, label in self._get_item_buttons():
            pg.draw.rect(screen, (230, 215, 190), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)
            txt = self.font_small.render(label, True, (0, 0, 0))
            screen.blit(txt, txt.get_rect(center=rect.center))

    def _handle_item_menu(self) -> None:
        # ESC 關閉
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        # 1/2/3/4 快捷鍵
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

        # 點擊按鈕
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_item_buttons():
                if not rect.collidepoint(mx, my):
                    continue

                if label.startswith("Heal Potion"):
                    self._use_heal_potion()
                elif label.startswith("Strength Potion"):
                    self._use_strength_potion()
                elif label.startswith("Defense Potion"):
                    self._use_defense_potion()
                else:
                    self.in_item_menu = False
                    self.message = self.message_menu
                return
