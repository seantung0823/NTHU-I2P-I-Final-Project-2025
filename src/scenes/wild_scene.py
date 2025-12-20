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
import re
import copy


if TYPE_CHECKING:
    from src.data.bag import Bag


# -------------------------
# Sprite path helpers (match BattleScene conventions)
# -------------------------
def battle_idle_sprite(species_id: int) -> str:
    """Animation 用：相對於 assets/images/ 的路徑"""
    return f"sprites/sprite{species_id}_idle.png"


def menu_icon_sprite(species_id: int) -> str:
    """Switch panel 用：相對於 assets/images/ 的路徑"""
    return f"menu_sprites/menusprite{species_id}.png"



# =========================
#   ELEMENT SYSTEM (Wild)
# =========================
# Your element mapping:
# sprite 1,2,3,4,5,15,16 -> Grass
# sprite 6,12,13,14      -> Water
# sprite 7,8,9,10,11     -> Fire
SPECIES_ELEMENT: dict[int, str] = {
    1: "Grass", 2: "Grass", 3: "Grass", 4: "Grass", 5: "Grass",
    15: "Grass", 16: "Grass",
    6: "Water", 12: "Water", 13: "Water", 14: "Water",
    7: "Fire", 8: "Fire", 9: "Fire", 10: "Fire", 11: "Fire",
}

# Only the required elements for the assignment
ELEMENT_CHART: dict[str, dict[str, list[str]]] = {
    "Water": {"strong": ["Fire"], "weak": ["Grass"]},
    "Fire": {"strong": ["Grass"], "weak": ["Water"]},
    "Grass": {"strong": ["Water"], "weak": ["Fire"]},
}

def infer_element_from_species_id(species_id: int | None) -> str:
    if isinstance(species_id, int) and species_id > 0:
        return SPECIES_ELEMENT.get(species_id, "Normal")
    return "Normal"

def element_multiplier(attacker: str, defender: str) -> float:
    atk = str(attacker or "Normal")
    dfd = str(defender or "Normal")
    if dfd in ELEMENT_CHART.get(atk, {}).get("strong", []):
        return 1.2
    if dfd in ELEMENT_CHART.get(atk, {}).get("weak", []):
        return 0.5
    return 1.0

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

    ✅ 新增（不影響舊用法）：
    - 可選擇傳入 encounter 來決定敵人
      encounter 格式範例：
      {
        "enemy": {"name": "Pikachu", "max_hp": 70, "sprite": "sprites/pika_idle.png"},
        # 或
        "enemy_pool": [
            {"name": "...", "max_hp": ..., "sprite": "..."},
            ...
        ]
      }
    """

    background: BackgroundSprite

    @override
    def __init__(self, bag: "Bag | None" = None, encounter: dict | None = None) -> None:
        super().__init__()

        # 可以為 None（如果沒有把 Bag 傳進來就只是「假用道具」）
        self.bag: "Bag | None" = bag

        # ✅ 新增：保存 encounter（沒有傳也沒關係）
        self.encounter = encounter or {}

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

        # ---------- 戰鬥數值 ----------
        self.player_name = "Florian"
        self.player_max_hp = 100
        self.player_hp = self.player_max_hp

        # ---------- Party / Switch ----------
        # 目前上場的是隊伍中的第幾隻（0 = 第一隻）
        self.active_party_index: int = 0

        # 是否正在 Switch 選單裡
        self.in_switch_menu: bool = False

        # Switch list scroll (以「index」方式捲動，避免依賴滑鼠滾輪事件)
        self.switch_top_index: int = 0
        self.switch_visible_rows: int = 4

        # ---------- 三種道具 Buff（每場野外戰鬥重置） ----------
        self.attack_buff: int = 0   # Strength Potion
        self.defense_buff: int = 0  # Defense Potion（降低敵人攻擊傷害）

        # ✅ 新增：決定敵人資料（兼容：沒傳 encounter 就跟以前一樣）
        enemy_default = {"name": "Florian", "max_hp": 80, "sprite": "sprites/sprite1_idle.png"}

        enemy_data = None
        if isinstance(self.encounter.get("enemy"), dict):
            enemy_data = self.encounter.get("enemy")
        else:
            pool = self.encounter.get("enemy_pool")
            if isinstance(pool, list) and len(pool) > 0:
                enemy_data = random.choice(pool)

        if not isinstance(enemy_data, dict):
            enemy_data = enemy_default

        self.enemy_name = str(enemy_data.get("name", enemy_default["name"]))
        self.enemy_max_hp = int(enemy_data.get("max_hp", enemy_default["max_hp"]))
        self.enemy_hp = self.enemy_max_hp
        self.enemy_sprite_path = str(enemy_data.get("sprite", enemy_default["sprite"]))

        # Update enemy species_id / menu sprite / element
        self.enemy_species_id = None
        m = re.search(r"sprite(\d+)_", self.enemy_sprite_path.replace("\\", "/"))
        if m:
            try:
                self.enemy_species_id = int(m.group(1))
            except Exception:
                self.enemy_species_id = None

        if self.enemy_species_id is not None:
            self.enemy_menu_sprite_path = f"menu_sprites/menusprite{self.enemy_species_id}.png"
        else:
            self.enemy_menu_sprite_path = "menu_sprites/menusprite1.png"

        ele = enemy_data.get("element") if isinstance(enemy_data, dict) else None
        if isinstance(ele, str) and ele:
            self.enemy_element = ele
        else:
            self.enemy_element = infer_element_from_species_id(self.enemy_species_id)

        
                # ✅ 保存本次遭遇的 enemy_data（避免之後抓到時資訊丟失）
        self._enemy_data = copy.deepcopy(enemy_data)

        # ✅ 由 battle sprite 推斷 species_id（例如 sprites/sprite3_idle.png -> 3）
        self.enemy_species_id: int | None = None
        m = re.search(r"sprite(\d+)_", self.enemy_sprite_path.replace("\\", "/"))
        if m:
            try:
                self.enemy_species_id = int(m.group(1))
            except Exception:
                self.enemy_species_id = None

        # ✅ menu icon 路徑（讓背包/切換顯示正確）
        # 你專案裡 menu icon 看起來是 menu_sprites/menuspriteX.png
        if self.enemy_species_id is not None:
            self.enemy_menu_sprite_path = f"menu_sprites/menusprite{self.enemy_species_id}.png"
        else:
            self.enemy_menu_sprite_path = "menu_sprites/menusprite1.png"


        # ---------- Element (auto infer, same logic as BattleScene) ----------
        ele = enemy_data.get("element") if isinstance(enemy_data, dict) else None
        if isinstance(ele, str) and ele:
            self.enemy_element = ele
        else:
            self.enemy_element = infer_element_from_species_id(self.enemy_species_id)

        # Player element will be resolved from bag party in enter()
        self.player_element = "Normal"


        # 訊息（改成動態敵人）
        self.message_intro = f"A wild {self.enemy_name} appeared!"
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

        # ---------- 寶可夢動畫 ----------
        # ✅ enemy 改成用 enemy_sprite_path（不影響原本，預設還是 sprite1_idle）
        self.enemy_anim = Animation(
            self.enemy_sprite_path,
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
            raw_img = pg.image.load("assets/images/ingame_ui/ball.png").convert_alpha()
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

        self.in_switch_menu = False
        self.switch_top_index = 0
        self.attack_buff = 0
        self.defense_buff = 0


        # HP：若有 Bag，就用目前上場的寶可夢；否則用預設
        party = self._get_party()
        if party:
            self.active_party_index = min(self.active_party_index, len(party) - 1)
            active = party[self.active_party_index]

            max_hp = int(active.get("max_hp", self.player_max_hp))
            cur_hp = int(active.get("hp", max_hp))
            self.player_max_hp = max_hp
            self.player_hp = cur_hp

            # 名字與動畫
            sid = self._infer_species_id(active)
            if sid is not None:
                self.player_name = f"sprite{sid}"
            else:
                self.player_name = str(active.get("name", self.player_name))
            self._update_player_anim_for_mon(active)

            # Element (auto infer)
            ele = active.get("element")
            if isinstance(ele, str) and ele:
                self.player_element = ele
            else:
                self.player_element = infer_element_from_species_id(sid)
        else:
            self.player_hp = self.player_max_hp
            self._update_player_anim_for_name(self.player_name)
            self.player_element = "Normal"

        self.enemy_hp = self.enemy_max_hp

        self.battle_result = None
        self.action_timer = 0.0
        self.end_timer = 0.0
        self.ball_timer = 0.0
        self.enemy_inside_ball = False
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

        if self.phase == "PLAYER_CHOICE":
            self._handle_player_choice()
            return

        if self.phase == "PLAYER_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self._apply_player_attack()
            return

        if self.phase == "ENEMY_ATTACK":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self._apply_enemy_attack()
            return

        if self.phase == "RUN_AWAY":
            self.action_timer += dt
            if self.action_timer >= self.action_duration:
                self.action_timer = 0.0
                self.phase = "END"
                self.end_timer = 0.0
            return

        if self.phase == "BALL_THROW":
            self.ball_timer += dt
            if self.ball_timer >= self.ball_throw_duration:
                self.ball_timer = 0.0
                self.phase = "BALL_SHAKE"
                self.enemy_capture_timer = 0.0
                self.enemy_inside_ball = False
            return

        if self.phase == "BALL_SHAKE":
            self.ball_timer += dt

            if not self.enemy_inside_ball:
                self.enemy_capture_timer += dt
                if self.enemy_capture_timer >= self.enemy_capture_duration:
                    self.enemy_capture_timer = self.enemy_capture_duration
                    self.enemy_inside_ball = True

            if self.ball_timer >= self.ball_shake_duration:
                self.ball_timer = 0.0
                if self.ball_capture_success:
                    self._add_captured_monster_to_bag()
                    self.battle_result = "CAUGHT"
                    self.message = f"Gotcha! {self.enemy_name} was caught!"
                    self.phase = "END"
                    self.end_timer = 0.0
                else:
                    self.enemy_inside_ball = False
                    self.message = "Oh no! It broke free!"
                    self.phase = "PLAYER_CHOICE"
                    self.in_item_menu = False
            return

        if self.phase == "END":
            self.end_timer += dt
            if self.end_timer >= self.end_duration:
                scene_manager.change_scene("game")
            return

    # -------------------------------------------------
    # 玩家選擇：Fight / Item / Run
    # -------------------------------------------------
    def _handle_player_choice(self) -> None:
        # 子選單優先
        if self.in_item_menu:
            self._handle_item_menu()
            return
        if self.in_switch_menu:
            self._handle_switch_menu()
            return

        # 快捷鍵
        if input_manager.key_pressed(pg.K_f):
            self._player_start_attack()
            return

        if input_manager.key_pressed(pg.K_r):
            self._player_run()
            return

        if input_manager.key_pressed(pg.K_i):
            self.in_item_menu = True
            self.message = "Choose an item."
            return

        # S：Switch
        if input_manager.key_pressed(pg.K_s):
            if self._can_open_switch_menu():
                self.in_switch_menu = True
                self.switch_top_index = 0
                self.message = "Choose a Pokemon."
            else:
                self.message = "No other Pokemon to switch!"
            return

        # 點擊主選單按鈕
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_menu_buttons():
                if not rect.collidepoint(mx, my):
                    continue
                if label == "Fight":
                    self._player_start_attack()
                elif label == "Item":
                    self.in_item_menu = True
                    self.message = "Choose an item."
                elif label == "Switch":
                    if self._can_open_switch_menu():
                        self.in_switch_menu = True
                        self.switch_top_index = 0
                        self.message = "Choose a Pokemon."
                    else:
                        self.message = "No other Pokemon to switch!"
                elif label == "Run":
                    self._player_run()
                return


        # -------------------------------------------------
    # Item 子選單：Potion / Ball / Cancel
    # -------------------------------------------------
    def _handle_item_menu(self) -> None:
        # ESC：回主選單
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        # 1~5
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
            self._use_pokeball()
            return
        if input_manager.key_pressed(pg.K_5):
            self.in_item_menu = False
            self.message = self.message_menu
            return

        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for rect, label in self._get_item_buttons():
                if not rect.collidepoint(mx, my):
                    continue
                if label == "Heal Potion":
                    self._use_heal_potion()
                elif label == "Strength Potion":
                    self._use_strength_potion()
                elif label == "Defense Potion":
                    self._use_defense_potion()
                elif label == "Ball":
                    self._use_pokeball()
                elif label == "Cancel":
                    self.in_item_menu = False
                    self.message = self.message_menu
                return


    def _use_heal_potion(self) -> None:
        if not self._consume_item_any(self.HEAL_POTION_ALIASES):
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
        if not self._consume_item_any(self.STRENGTH_POTION_ALIASES):
            self.message = "No Strength Potion left!"
            return

        self.attack_buff += 10
        self.message = "Attack increased! (+10)"
        self.in_item_menu = False

    def _use_defense_potion(self) -> None:
        if not self._consume_item_any(self.DEFENSE_POTION_ALIASES):
            self.message = "No Defense Potion left!"
            return

        self.defense_buff += 5
        self.message = "Defense increased! (-5 damage)"
        self.in_item_menu = False

    def _use_pokeball(self) -> None:
        if self._get_item_count_any(self.POKEBALL_ALIASES) <= 0:
            self.message = "No Pokeball left!"
            return

        if not self._consume_item_any(self.POKEBALL_ALIASES):
            self.message = "No Pokeball left!"
            return

        # ✅ 修正：避免除以 0
        hp_ratio = (self.enemy_hp / self.enemy_max_hp) if self.enemy_max_hp > 0 else 1.0
        success_prob = 0.35 + (1.0 - hp_ratio) * 0.45
        self.ball_capture_success = (random.random() < success_prob)

        self.message = "You threw a ball!"
        self.in_item_menu = False
        self.phase = "BALL_THROW"
        self.ball_timer = 0.0

    # -------------------------------------------------
    # Fight / Run / 攻擊結算
    # -------------------------------------------------
    def _player_start_attack(self) -> None:
        self.message = f"You attack the wild {self.enemy_name}!"
        self.phase = "PLAYER_ATTACK"
        self.action_timer = 0.0

    def _player_run(self) -> None:
        self.battle_result = "RUN"
        self.message = "Got away safely!"
        self.phase = "RUN_AWAY"
        self.action_timer = 0.0

    def _apply_player_attack(self) -> None:
        base = max(1, 20 + int(self.attack_buff))
        mult = element_multiplier(getattr(self, "player_element", "Normal"), getattr(self, "enemy_element", "Normal"))
        dmg = max(1, int(base * mult))
        self.enemy_hp = max(0, self.enemy_hp - dmg)

        if self.enemy_hp <= 0:
            self.battle_result = "WIN"
            extra = ""
            if mult > 1.0001:
                extra = " It's super effective!"
            elif mult < 0.9999:
                extra = " It's not very effective..."
            self.message = f"The wild {self.enemy_name} fainted!{extra}"
            self.phase = "END"
            self.end_timer = 0.0
        else:
            extra = ""
            if mult > 1.0001:
                extra = " It's super effective!"
            elif mult < 0.9999:
                extra = " It's not very effective..."
            self.message = f"The wild {self.enemy_name} is attacking!{extra}"
            self.phase = "ENEMY_ATTACK"
            self.action_timer = 0.0

    def _apply_enemy_attack(self) -> None:
        base = max(1, 12 - int(self.defense_buff))
        mult = element_multiplier(getattr(self, "enemy_element", "Normal"), getattr(self, "player_element", "Normal"))
        dmg = max(1, int(base * mult))
        self.player_hp = max(0, self.player_hp - dmg)

        # 同步回 bag
        party = self._get_party()
        if party and 0 <= self.active_party_index < len(party):
            party[self.active_party_index]["hp"] = self.player_hp

        if self.player_hp <= 0:
            self.battle_result = "LOSE"
            self.message = "You fainted..."
            self.phase = "END"
            self.end_timer = 0.0
        else:
            self.message = self.message_menu
            self.phase = "PLAYER_CHOICE"

    # -------------------------------------------------
    # Bag / Party helpers (alias-aware)
    # -------------------------------------------------
    HEAL_POTION_ALIASES = ["heal potion", "heal_potion", "potion", "Potion", "Heal Potion"]
    STRENGTH_POTION_ALIASES = ["strength potion", "strength_potion", "Strength Potion"]
    DEFENSE_POTION_ALIASES = ["defense potion", "defense_potion", "Defense Potion"]
    POKEBALL_ALIASES = ["pokeball", "poke ball", "ball", "Pokeball", "PokeBall"]

    def _norm_item_name(self, s: str) -> str:
        s = str(s).lower().strip().replace("_", " ")
        s = re.sub(r"\s+", " ", s)
        return s

    def _get_items_data(self) -> list[dict]:
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

    def _get_party(self) -> list[dict]:
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

    def _get_item_count_any(self, names: list[str]) -> int:
        if not self.bag:
            return 999
        items = self._get_items_data()
        aliases = {self._norm_item_name(n) for n in names if n}
        for it in items:
            if self._norm_item_name(it.get("name", "")) in aliases:
                return int(it.get("count", 0))
        return 0

    def _consume_item_any(self, names: list[str]) -> bool:
        if not self.bag:
            return True
        items = self._get_items_data()
        aliases = {self._norm_item_name(n) for n in names if n}
        for it in items:
            if self._norm_item_name(it.get("name", "")) in aliases:
                cnt = int(it.get("count", 0))
                if cnt <= 0:
                    return False
                it["count"] = cnt - 1
                return True
        return False

    def _infer_species_id(self, mon: dict) -> int | None:
        sid = mon.get("species_id")
        if isinstance(sid, int) and sid > 0:
            return sid

        sp = str(mon.get("sprite_path", "") or mon.get("sprite", "") or "")
        m0 = re.search(r"menusprite(\d+)\.png", sp, re.IGNORECASE)
        if m0:
            return int(m0.group(1))

        m = re.search(r"sprite(\d+)", sp, re.IGNORECASE)
        if m:
            return int(m.group(1))

        name = str(mon.get("name", ""))
        m2 = re.search(r"(\d+)", name)
        if m2:
            return int(m2.group(1))

        return None

    # -------------------------------------------------
    # Animation helpers (player)
    # -------------------------------------------------
    def _update_player_anim_for_name(self, name: str) -> None:
        sid = self._infer_species_id({"name": name})
        sprite_path = battle_idle_sprite(sid) if sid is not None else "sprites/sprite1_idle.png"

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
        sprite_path = battle_idle_sprite(sid) if sid is not None else "sprites/sprite1_idle.png"

        self.player_anim = Animation(
            sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.player_anim.switch("idle")

    # -------------------------------------------------
    # Capture result stored to bag (kept as your logic, but uses enemy info)
    # -------------------------------------------------
    def _add_captured_monster_to_bag(self) -> None:
        if not self.bag:
            Logger.warning("WildScene: capture success but bag is None (monster not stored).")
            return

        monsters = getattr(self.bag, "_monsters_data", None)
        if monsters is None:
            Logger.warning("WildScene: bag has no _monsters_data (monster not stored).")
            return

        new_mon = {
            "name": self.enemy_name,
            "hp": self.enemy_max_hp,
            "max_hp": self.enemy_max_hp,
            "level": 20,
            "species_id": self.enemy_species_id,
            "sprite_path": getattr(self, "enemy_menu_sprite_path", "menu_sprites/menusprite1.png"),
            "battle_sprite": self.enemy_sprite_path,
            "element": getattr(self, "enemy_element", "Normal"),
        }

        monsters.append(new_mon)
        Logger.info(
            f"WildScene: captured {self.enemy_name} added to bag! (species_id={self.enemy_species_id})"
        )


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

        if self.phase in ("BALL_THROW", "BALL_SHAKE"):
            self._draw_ball(screen)

        if self.phase == "RADIAL":
            self._draw_radial_transition(screen)

    def _draw_hp_boxes(self, screen: pg.Surface) -> None:
        box_w, box_h = 180, 60

        enemy_rect = pg.Rect(GameSettings.SCREEN_WIDTH - box_w - 20, 20, box_w, box_h)
        pg.draw.rect(screen, (255, 255, 255), enemy_rect)
        pg.draw.rect(screen, (0, 0, 0), enemy_rect, 2)

        name_text = self.font_small.render(self.enemy_name, True, (0, 0, 0))
        screen.blit(name_text, (enemy_rect.x + 8, enemy_rect.y + 8))

        hp_ratio = (self.enemy_hp / self.enemy_max_hp) if self.enemy_max_hp > 0 else 0.0
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

        p_hp_ratio = (self.player_hp / self.player_max_hp) if self.player_max_hp > 0 else 0.0
        p_bar_back = pg.Rect(player_rect.x + 8, player_rect.y + box_h - 20, box_w - 16, 10)
        pg.draw.rect(screen, (80, 80, 80), p_bar_back)
        p_bar = pg.Rect(p_bar_back.x, p_bar_back.y, int(p_bar_back.w * p_hp_ratio), 10)
        pg.draw.rect(screen, (0, 200, 0), p_bar)

    # -------------------------------------------------
    # 放大動畫（以下全部保留你的原本邏輯）
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

        if self.phase == "BALL_SHAKE" and not self.enemy_inside_ball:
            t = min(self.enemy_capture_timer / self.enemy_capture_duration, 1.0)
            shrink = 1.0 - t
            enemy_scale *= shrink

        if enemy_scale > 0 and not self.enemy_inside_ball:
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
    # 丟球 & 搖晃動畫（保留你原本）
    # -------------------------------------------------
    def _draw_ball(self, screen: pg.Surface) -> None:
        start_x, start_y = self.player_pos
        start_y -= 40

        end_x, end_y = self.enemy_pos
        end_y -= 50

        if self.phase == "BALL_THROW":
            t = min(self.ball_timer / self.ball_throw_duration, 1.0)
            x = self._lerp(start_x, end_x, t)
            y = self._lerp(start_y, end_y, t)
            arc_height = 40
            y -= math.sin(math.pi * t) * arc_height
        else:
            t = self.ball_timer / self.ball_shake_duration
            x = end_x + math.sin(t * 6 * math.pi) * 8
            y = end_y

        center = (int(x), int(y))

        if self.ball_image is not None:
            rect = self.ball_image.get_rect(center=center)
            screen.blit(self.ball_image, rect)
            return

        radius = 10
        pg.draw.circle(screen, (0, 0, 0), center, radius + 1)
        pg.draw.circle(screen, (255, 255, 255), center, radius)
        rect = pg.Rect(center[0] - radius, center[1] - radius, radius * 2, radius)
        pg.draw.ellipse(screen, (220, 0, 0), rect)
        pg.draw.line(screen, (0, 0, 0), (center[0] - radius, center[1]), (center[0] + radius, center[1]), 2)
        pg.draw.circle(screen, (255, 255, 255), center, 3)
        pg.draw.circle(screen, (0, 0, 0), center, 3, 1)

    # -------------------------------------------------
    # 選單按鈕（保留你原本：Fight / Item / Switch / Run）
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
    # Switch menu (wild)
    # -------------------------------------------------
    def _can_open_switch_menu(self) -> bool:
        party = self._get_party()
        if len(party) < 2:
            return False

        # 必須有「其他」還活著的
        for i, mon in enumerate(party):
            if i != self.active_party_index and int(mon.get("hp", 0)) > 0:
                return True
        return False

    def _get_switch_panel_rect(self) -> pg.Rect:
        w, h = 460, 320
        x = (GameSettings.SCREEN_WIDTH - w) // 2
        y = (GameSettings.SCREEN_HEIGHT - h) // 2
        return pg.Rect(x, y, w, h)

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

        # 捲動（鍵盤）
        if input_manager.key_pressed(pg.K_UP):
            self.switch_top_index = max(0, self.switch_top_index - 1)
        if input_manager.key_pressed(pg.K_DOWN):
            max_top = max(0, len(party) - self.switch_visible_rows)
            self.switch_top_index = min(max_top, self.switch_top_index + 1)

        panel = self._get_switch_panel_rect()
        card_x = panel.x + 20
        card_w = panel.width - 40
        card_h = 50
        gap = 12
        card_y0 = panel.y + 60

        visible = min(self.switch_visible_rows, len(party))
        if input_manager.mouse_pressed(pg.BUTTON_LEFT):
            mx, my = input_manager.mouse_pos
            for row in range(visible):
                idx = self.switch_top_index + row
                if idx >= len(party):
                    break
                rect = pg.Rect(card_x, card_y0 + row * (card_h + gap), card_w, card_h)
                if not rect.collidepoint(mx, my):
                    continue

                # 點到正在上場的
                if idx == self.active_party_index:
                    self.message = f"{party[idx].get('name', 'This one')} is already in battle."
                    return

                # 不能切換已倒下
                if int(party[idx].get("hp", 0)) <= 0:
                    self.message = f"{party[idx].get('name', 'That Pokemon')} has fainted!"
                    return

                # 其實沒有其他活著的就不讓切
                if not self._can_open_switch_menu():
                    self.in_switch_menu = False
                    self.message = "No other Pokemon to switch!"
                    return

                # ✅ 切換成功
                self.active_party_index = idx
                chosen = party[idx]

                # reset buffs
                self.attack_buff = 0
                self.defense_buff = 0

                max_hp = int(chosen.get("max_hp", self.player_max_hp))
                cur_hp = int(chosen.get("hp", max_hp))
                self.player_max_hp = max_hp
                self.player_hp = cur_hp

                sid = self._infer_species_id(chosen)
                if sid is not None:
                    self.player_name = f"sprite{sid}"
                else:
                    self.player_name = str(chosen.get("name", self.player_name))

                self._update_player_anim_for_mon(chosen)

                # Element (auto infer)
                ele = chosen.get("element")
                if isinstance(ele, str) and ele:
                    self.player_element = ele
                else:
                    self.player_element = infer_element_from_species_id(sid)


                self.in_switch_menu = False
                self.message = f"Go! {self.player_name}!"
                return

    def _draw_switch_panel(self, screen: pg.Surface) -> None:
        party = self._get_party()
        if not party:
            return

        overlay = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        panel = self._get_switch_panel_rect()
        pg.draw.rect(screen, (247, 182, 60), panel)
        pg.draw.rect(screen, (205, 132, 40), panel, 3)

        title = self.font_medium.render("Choose a Pokemon", True, (255, 255, 255))
        screen.blit(title, (panel.x + 20, panel.y + 12))

        card_x = panel.x + 20
        card_w = panel.width - 40
        card_h = 50
        gap = 12
        card_y0 = panel.y + 60

        visible = min(self.switch_visible_rows, len(party))
        for row in range(visible):
            idx = self.switch_top_index + row
            if idx >= len(party):
                break
            mon = party[idx]

            rect = pg.Rect(card_x, card_y0 + row * (card_h + gap), card_w, card_h)

            # highlight current
            if idx == self.active_party_index:
                pg.draw.rect(screen, (255, 230, 140), rect)
            else:
                pg.draw.rect(screen, (255, 255, 255), rect)
            pg.draw.rect(screen, (0, 0, 0), rect, 2)

            # icon
            sprite_rel = str(mon.get("sprite_path", "")).strip()
            if not sprite_rel:
                sid = self._infer_species_id(mon)
                if sid is not None:
                    sprite_rel = menu_icon_sprite(sid)
            sprite_path = f"assets/images/{sprite_rel}" if sprite_rel else "assets/images/menu_sprites/menusprite1.png"
            try:
                icon = pg.image.load(sprite_path).convert_alpha()
                icon = pg.transform.smoothscale(icon, (40, 40))
                screen.blit(icon, (rect.x + 8, rect.y + 5))
            except Exception:
                pass

            nm = str(mon.get("name", f"mon{idx+1}"))
            hp = int(mon.get("hp", 0))
            mhp = int(mon.get("max_hp", max(hp, 1)))
            text = self.font_small.render(f"{nm}  HP {hp}/{mhp}", True, (0, 0, 0))
            screen.blit(text, (rect.x + 60, rect.y + 16))

        # hint
        hint = self.font_small.render("UP/DOWN to scroll, ESC to close", True, (255, 255, 255))
        screen.blit(hint, (panel.x + 20, panel.bottom - 24))

    def _get_item_buttons(self):
        labels = ["Heal Potion", "Strength Potion", "Defense Potion", "Ball", "Cancel"]

        btn_w, btn_h = 140, 40
        gap = 12

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
    # 放射轉場動畫（保留你原本）
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
    
    def _refresh_enemy_from_encounter(self) -> None:
        enemy_default = {"name": "Florian", "max_hp": 80, "sprite": "sprites/sprite1_idle.png"}

        enemy_data = None
        if isinstance(self.encounter.get("enemy"), dict):
            enemy_data = self.encounter["enemy"]
        else:
            pool = self.encounter.get("enemy_pool")
            if isinstance(pool, list) and len(pool) > 0:
                enemy_data = random.choice(pool)

        if not isinstance(enemy_data, dict):
            enemy_data = enemy_default

        self.enemy_name = str(enemy_data.get("name", enemy_default["name"]))
        self.enemy_max_hp = int(enemy_data.get("max_hp", enemy_default["max_hp"]))
        self.enemy_hp = self.enemy_max_hp
        self.enemy_sprite_path = str(enemy_data.get("sprite", enemy_default["sprite"]))

        # Update enemy species_id / menu sprite / element
        self.enemy_species_id = None
        m = re.search(r"sprite(\d+)_", self.enemy_sprite_path.replace("\\", "/"))
        if m:
            try:
                self.enemy_species_id = int(m.group(1))
            except Exception:
                self.enemy_species_id = None

        if self.enemy_species_id is not None:
            self.enemy_menu_sprite_path = f"menu_sprites/menusprite{self.enemy_species_id}.png"
        else:
            self.enemy_menu_sprite_path = "menu_sprites/menusprite1.png"

        ele = enemy_data.get("element") if isinstance(enemy_data, dict) else None
        if isinstance(ele, str) and ele:
            self.enemy_element = ele
        else:
            self.enemy_element = infer_element_from_species_id(self.enemy_species_id)


        # 更新開場文字
        self.message_intro = f"A wild {self.enemy_name} appeared!"
        self.message = self.message_intro

        # 重新建立敵人動畫（不動玩家動畫）
        self.enemy_anim = Animation(
            self.enemy_sprite_path,
            rows=["idle"],
            n_keyframes=4,
            size=(GameSettings.TILE_SIZE * 3, GameSettings.TILE_SIZE * 3),
            loop=0.6,
        )
        self.enemy_anim.switch("idle")
