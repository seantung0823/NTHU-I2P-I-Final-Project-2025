from __future__ import annotations
from src.utils import Logger, GameSettings, Position, Teleport
import json, os
import pygame as pg
from typing import TYPE_CHECKING
from json import JSONDecodeError

if TYPE_CHECKING:
    from src.maps.map import Map
    from src.entities.player import Player
    from src.entities.enemy_trainer import EnemyTrainer
    from src.data.bag import Bag


class GameManager:
    # Entities
    player: Player | None
    enemy_trainers: dict[str, list[EnemyTrainer]]
    bag: "Bag"

    # Map properties
    current_map_key: str
    maps: dict[str, Map]

    # Changing Scene properties
    should_change_scene: bool
    next_map: str

    # 新增：記錄每張地圖的初始/重生位置
    player_spawns: dict[str, Position]

    def __init__(
        self,
        maps: dict[str, Map],
        start_map: str,
        player: Player | None,
        enemy_trainers: dict[str, list[EnemyTrainer]],
        bag: Bag | None = None,
    ):
        from src.data.bag import Bag

        # Game Properties
        self.maps = maps
        self.current_map_key = start_map
        self.player = player
        self.enemy_trainers = enemy_trainers
        self.bag = bag if bag is not None else Bag([], [])

        # Check If you should change scene
        self.should_change_scene = False
        self.next_map = ""

        # 記錄每張地圖「最後一次離開時」玩家在哪
        self.last_positions: dict[str, Position] = {}

        # 記錄每張地圖的「spawn 位置」（from_dict 會填）
        self.player_spawns = {}

    @property
    def current_map(self) -> Map:
        return self.maps[self.current_map_key]

    @property
    def current_enemy_trainers(self) -> list[EnemyTrainer]:
        return self.enemy_trainers.get(self.current_map_key, [])

    @property
    def current_teleporter(self) -> list[Teleport]:
        return self.maps[self.current_map_key].teleporters

    def switch_map(self, target: str) -> None:
        if target not in self.maps:
            Logger.warning(f"Map '{target}' not loaded; cannot switch.")
            return

        # 如果有玩家，把目前地圖的最後位置記起來
        if self.player is not None:
            self.last_positions[self.current_map_key] = self.player.position.copy()

        self.next_map = target
        self.should_change_scene = True

    def try_switch_map(self) -> None:
        if self.should_change_scene:
            self.current_map_key = self.next_map
            self.next_map = ""
            self.should_change_scene = False

            if self.player:
                # 如果之前來過這張地圖，就回到「上次離開的位置」
                if self.current_map_key in self.last_positions:
                    self.player.position = self.last_positions[self.current_map_key].copy()
                # 否則用 spawn 當初始位置
                elif self.current_map_key in self.player_spawns:
                    spawn = self.player_spawns[self.current_map_key]
                    self.player.position = spawn.copy()
                else:
                    # 最後的保險：用 Map 自己的 spawn
                    spawn = self.maps[self.current_map_key].spawn
                    self.player.position = spawn.copy()

    def check_collision(self, rect: pg.Rect) -> bool:
        if self.maps[self.current_map_key].check_collision(rect):
            return True
        for entity in self.enemy_trainers.get(self.current_map_key, []):
            if rect.colliderect(entity.animation.rect):
                return True
        return False

    # =========================
    #         SAVE / LOAD
    # =========================
    def save(self, path: str) -> None:
        """
        比原本安全：
        1. 先呼叫 to_dict()，失敗了不會動到檔案
        2. 成功後寫入 path.tmp
        3. 全部成功才 os.replace 成正式存檔
        """
        tmp_path = path + ".tmp"

        try:
            data = self.to_dict()
        except Exception as e:
            Logger.warning(f"Failed to convert game state to dict: {e}")
            return

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, path)
            Logger.info(f"Game saved to {path}")
        except Exception as e:
            Logger.warning(f"Failed to save game: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @classmethod
    def load(cls, path: str) -> "GameManager | None":
        if not os.path.exists(path):
            Logger.error(f"No file found: {path}, ignoring load function")
            return None

        if os.path.getsize(path) == 0:
            Logger.error(f"Save file {path} is empty, ignoring load function")
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except JSONDecodeError as e:
            Logger.error(f"Save file {path} is corrupted: {e}")
            return None

        return cls.from_dict(data)

    # =========================
    #       SERIALIZATION
    # =========================
    def to_dict(self) -> dict[str, object]:
        """
        把整個遊戲狀態轉成「只包含 JSON 可以吃的型別」。
        """
        map_blocks: list[dict[str, object]] = []

        for key, m in self.maps.items():
            # 1. 地圖本身的資料
            block = m.to_dict()

            # 2. 該地圖的敵方訓練家
            block["enemy_trainers"] = [
                t.to_dict() for t in self.enemy_trainers.get(key, [])
            ]

            # 3. 該地圖的 spawn（如果有記錄）
            spawn_pos = self.player_spawns.get(key)

            if isinstance(spawn_pos, Position):
                block["player"] = {
                    "x": spawn_pos.x / GameSettings.TILE_SIZE,
                    "y": spawn_pos.y / GameSettings.TILE_SIZE,
                }
            else:
                # 沒有 player_spawns，就盡量從 Map 的 spawn 取
                if hasattr(m, "spawn") and isinstance(m.spawn, Position):
                    block["player"] = {
                        "x": m.spawn.x / GameSettings.TILE_SIZE,
                        "y": m.spawn.y / GameSettings.TILE_SIZE,
                    }

            map_blocks.append(block)

        return {
            "map": map_blocks,
            "current_map": self.current_map_key,
            "player": self.player.to_dict() if self.player is not None else None,
            "bag": self.bag.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GameManager":
        from src.maps.map import Map
        from src.entities.player import Player
        from src.entities.enemy_trainer import EnemyTrainer
        from src.data.bag import Bag as _Bag

        Logger.info("Loading maps")
        maps_data = data["map"]
        maps: dict[str, Map] = {}
        player_spawns: dict[str, Position] = {}
        trainers: dict[str, list[EnemyTrainer]] = {}

        # 先把 maps 建好，順便把每張地圖的 spawn 記起來
        for entry in maps_data:
            path = entry["path"]
            maps[path] = Map.from_dict(entry)

            sp = entry.get("player")
            if sp:
                player_spawns[path] = Position(
                    sp["x"] * GameSettings.TILE_SIZE,
                    sp["y"] * GameSettings.TILE_SIZE,
                )

            # 給 trainers 一個空 list，等一下再填
            trainers[path] = []

        current_map = data["current_map"]

        # 先建出 GameManager 本體（沒有 player、bag）
        gm = cls(
            maps,
            current_map,
            None,  # Player
            trainers,
            bag=None,
        )
        gm.current_map_key = current_map
        gm.player_spawns = player_spawns

        Logger.info("Loading enemy trainers")
        for m in data["map"]:
            path = m["path"]
            raw_data = m.get("enemy_trainers", [])
            gm.enemy_trainers[path] = [
                EnemyTrainer.from_dict(t, gm) for t in raw_data
            ]

        Logger.info("Loading Player")
        if data.get("player"):
            gm.player = Player.from_dict(data["player"], gm)

        Logger.info("Loading bag")
        if data.get("bag"):
            gm.bag = _Bag.from_dict(data["bag"])
        else:
            gm.bag = _Bag([], [])

        return gm
