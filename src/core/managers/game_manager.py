from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import TYPE_CHECKING

import pygame as pg

from src.utils import Logger, GameSettings, Position, Teleport

import os


if TYPE_CHECKING:
    from src.maps.map import Map
    from src.entities.player import Player
    from src.entities.enemy_trainer import EnemyTrainer
    from src.entities.shop_npc import ShopNPC
    from src.data.bag import Bag


class GameManager:
    player: "Player | None"
    enemy_trainers: dict[str, list["EnemyTrainer"]]
    shop_npcs: dict[str, list["ShopNPC"]]
    bag: "Bag"

    current_map_key: str
    maps: dict[str, "Map"]

    should_change_scene: bool
    next_map: str

    player_spawns: dict[str, Position]

    def __init__(
        self,
        maps: dict[str, "Map"],
        start_map: str,
        player: "Player | None",
        enemy_trainers: dict[str, list["EnemyTrainer"]],
        bag: "Bag | None" = None,
        shop_npcs: dict[str, list["ShopNPC"]] | None = None,
    ):
        from src.data.bag import Bag as _Bag

        self.maps = maps
        self.current_map_key = start_map
        self.player = player

        self.enemy_trainers = enemy_trainers
        self.shop_npcs = shop_npcs if shop_npcs is not None else {}

        self.bag = bag if bag is not None else _Bag([], [])

        self.should_change_scene = False
        self.next_map = ""

        self.last_positions: dict[str, Position] = {}
        self.player_spawns: dict[str, Position] = {}

        # ===== Teleport 控制 =====
        self.from_teleport: bool = False
        self._tp_cooldown_until_ms: int = 0
        self._tp_from_map: str | None = None

        # ===== 來源 → 目的 專用落點 =====
        # gym → map：回到 gym 門口 (24, 24)（你原本寫法保留）
        self.teleport_overrides: dict[tuple[str, str], Position] = {
            ("gym.tmx", "map.tmx"): Position(
                24 * GameSettings.TILE_SIZE,
                24 * GameSettings.TILE_SIZE,
            ),
        }

    # --------------------------------------------------
    # Properties
    # --------------------------------------------------
    @property
    def current_map(self) -> "Map":
        return self.maps[self.current_map_key]

    @property
    def current_enemy_trainers(self) -> list["EnemyTrainer"]:
        return self.enemy_trainers.get(self.current_map_key, [])

    @property
    def current_shop_npcs(self) -> list["ShopNPC"]:
        return self.shop_npcs.get(self.current_map_key, [])

    @property
    def current_teleporter(self) -> list[Teleport]:
        return self.maps[self.current_map_key].teleporters

    # --------------------------------------------------
    # Map switching
    # --------------------------------------------------
    def switch_map(self, target: str) -> None:
        if target not in self.maps:
            Logger.warning(f"Map '{target}' not loaded.")
            return

        if self.player is not None:
            self.last_positions[self.current_map_key] = self.player.position.copy()

        self.next_map = target
        self.should_change_scene = True

    # --------------------------------------------------
    # Teleport helpers
    # --------------------------------------------------
    def _get_teleport_tile(self, tp: Teleport) -> tuple[int, int] | None:
        if hasattr(tp, "x") and hasattr(tp, "y"):
            return int(tp.x), int(tp.y)

        for name in ("tile", "tile_pos", "grid"):
            if hasattr(tp, name):
                p = getattr(tp, name)
                if isinstance(p, Position):
                    return int(p.x), int(p.y)

        for name in ("position", "pos"):
            if hasattr(tp, name):
                p = getattr(tp, name)
                if isinstance(p, Position):
                    return (
                        int(p.x // GameSettings.TILE_SIZE),
                        int(p.y // GameSettings.TILE_SIZE),
                    )
        return None

    def _get_teleport_destination(self, tp: Teleport) -> str | None:
        for name in ("destination", "target", "to_map"):
            if hasattr(tp, name):
                v = getattr(tp, name)
                if isinstance(v, str):
                    return v
        return None

    def _trigger_teleport_if_match_tile(self, tx: int, ty: int) -> bool:
        now = pg.time.get_ticks()
        if now < self._tp_cooldown_until_ms:
            return False

        for tp in self.current_teleporter:
            tile = self._get_teleport_tile(tp)
            if tile != (tx, ty):
                continue

            dest = self._get_teleport_destination(tp)
            if not dest:
                continue

            self.from_teleport = True
            self._tp_from_map = self.current_map_key
            self.switch_map(dest)
            self._tp_cooldown_until_ms = now + 350
            return True

        return False

    # --------------------------------------------------
    # Main update
    # --------------------------------------------------
    def try_switch_map(self) -> None:
        if self.player:
            cx = self.player.position.x + GameSettings.TILE_SIZE / 2
            cy = self.player.position.y + GameSettings.TILE_SIZE / 2
            tx = int(cx // GameSettings.TILE_SIZE)
            ty = int(cy // GameSettings.TILE_SIZE)
            if self._trigger_teleport_if_match_tile(tx, ty):
                return

        if not self.should_change_scene:
            return

        self.current_map_key = self.next_map
        self.next_map = ""
        self.should_change_scene = False

        if not self.player:
            return

        # ===== teleport 切圖 =====
        if self.from_teleport:
            key = (self._tp_from_map or "", self.current_map_key)

            if key in self.teleport_overrides:
                self.player.position = self.teleport_overrides[key].copy()
            elif self.current_map_key in self.player_spawns:
                self.player.position = self.player_spawns[self.current_map_key].copy()
            else:
                self.player.position = self.maps[self.current_map_key].spawn.copy()

            self.from_teleport = False
            self._tp_from_map = None
            self._tp_cooldown_until_ms = pg.time.get_ticks() + 350
            return

        # ===== 非 teleport =====
        if self.current_map_key in self.last_positions:
            self.player.position = self.last_positions[self.current_map_key].copy()
        elif self.current_map_key in self.player_spawns:
            self.player.position = self.player_spawns[self.current_map_key].copy()
        else:
            self.player.position = self.maps[self.current_map_key].spawn.copy()

    # --------------------------------------------------
    # Collision (撞門邊也能 TP)
    # --------------------------------------------------
    def check_collision(self, rect: pg.Rect) -> bool:
        now = pg.time.get_ticks()

        blocked_by_map = self.maps[self.current_map_key].check_collision(rect)

        if blocked_by_map and now >= self._tp_cooldown_until_ms:
            for tp in self.current_teleporter:
                tile = self._get_teleport_tile(tp)
                if not tile:
                    continue

                tx, ty = tile
                tp_rect = pg.Rect(
                    tx * GameSettings.TILE_SIZE,
                    ty * GameSettings.TILE_SIZE,
                    GameSettings.TILE_SIZE,
                    GameSettings.TILE_SIZE,
                )

                if rect.colliderect(tp_rect):
                    dest = self._get_teleport_destination(tp)
                    if dest:
                        self.from_teleport = True
                        self._tp_from_map = self.current_map_key
                        self.switch_map(dest)
                        self._tp_cooldown_until_ms = now + 350
                    return True

        return blocked_by_map

    # =========================
    #         SAVE / LOAD
    # =========================
    def save(self, path: str) -> None:
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
        map_blocks: list[dict[str, object]] = []

        for key, m in self.maps.items():
            block = m.to_dict()

            block["enemy_trainers"] = [
                t.to_dict() for t in self.enemy_trainers.get(key, [])
            ]
            block["shop_npcs"] = [
                s.to_dict() for s in self.shop_npcs.get(key, [])
            ]

            spawn_pos = self.player_spawns.get(key)

            if isinstance(spawn_pos, Position):
                block["player"] = {
                    "x": spawn_pos.x / GameSettings.TILE_SIZE,
                    "y": spawn_pos.y / GameSettings.TILE_SIZE,
                }
            else:
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
        import os
        from src.maps.map import Map
        from src.entities.player import Player
        from src.entities.enemy_trainer import EnemyTrainer
        from src.entities.shop_npc import ShopNPC
        from src.data.bag import Bag as _Bag
        from src.utils import GameSettings, Position, Teleport

        Logger.info("Loading maps")
        maps_data = data["map"]

        maps: dict[str, Map] = {}
        player_spawns: dict[str, Position] = {}
        trainers: dict[str, list[EnemyTrainer]] = {}
        shops: dict[str, list[ShopNPC]] = {}

        # ---------- helper：統一 key = 檔名 ----------
        def norm_key(path: str) -> str:
            return os.path.basename(path)

        # 1) 先建立 maps / spawns 的字典（key 全部用檔名）
        for entry in maps_data:
            raw_path = entry["path"]
            key = norm_key(raw_path)

            # 讓 Map 自己照原本方式讀 tmx，但我們存進 dict 用 key（檔名）
            maps[key] = Map.from_dict(entry)

            sp = entry.get("player")
            if sp:
                player_spawns[key] = Position(
                    sp["x"] * GameSettings.TILE_SIZE,
                    sp["y"] * GameSettings.TILE_SIZE,
                )

            trainers[key] = []
            shops[key] = []

        # 2) current_map 也要 normalize
        current_map = norm_key(data["current_map"])

        # 3) 建 GameManager
        gm = cls(
            maps,
            current_map,
            None,
            trainers,
            bag=None,
            shop_npcs=shops,
        )
        gm.current_map_key = current_map
        gm.player_spawns = player_spawns

        # 4) teleport.destination 也要 normalize（避免 switch_map 找不到 key）
        for k, m in gm.maps.items():
            # 你 Map 內 teleporters 是 Teleport 物件（或類似）
            for tp in getattr(m, "teleporters", []):
                if hasattr(tp, "destination") and isinstance(tp.destination, str):
                    tp.destination = norm_key(tp.destination)

        Logger.info("Loading enemy trainers / shop npcs")
        for entry in maps_data:
            key = norm_key(entry["path"])

            raw_trainers = entry.get("enemy_trainers", [])
            gm.enemy_trainers[key] = [EnemyTrainer.from_dict(t, gm) for t in raw_trainers]

            raw_shops = entry.get("shop_npcs", [])
            gm.shop_npcs[key] = [ShopNPC.from_dict(s, gm) for s in raw_shops]

        Logger.info("Loading Player")
        if data.get("player"):
            gm.player = Player.from_dict(data["player"], gm)

        Logger.info("Loading bag")
        if data.get("bag"):
            gm.bag = _Bag.from_dict(data["bag"])
        else:
            gm.bag = _Bag([], [])

        return gm
