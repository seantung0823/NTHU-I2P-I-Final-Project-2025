import pygame as pg
from src.utils.definition import Monster, Item

class Bag:
    _monsters_data: list[Monster]
    _items_data: list[Item]

    def __init__(self, monsters_data=None, items_data=None):
        # ✅ 防呆：確保一定是 list
        self._monsters_data = monsters_data if isinstance(monsters_data, list) else []
        self._items_data = items_data if isinstance(items_data, list) else []

    def update(self, dt: float):
        pass

    def draw(self, screen: pg.Surface):
        pass

    def to_dict(self) -> dict[str, object]:
        return {
            "monsters": list(self._monsters_data),
            "items": list(self._items_data),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Bag":
        monsters = data.get("monsters", [])
        items = data.get("items", [])

        # ✅ 防呆：確保 monsters/items 是 list
        if not isinstance(monsters, list):
            monsters = []
        if not isinstance(items, list):
            items = []

        # ✅ 防呆：過濾掉非 dict 的髒資料（避免讀到奇怪型別導致戰鬥判定失敗）
        monsters = [m for m in monsters if isinstance(m, dict)]
        items = [it for it in items if isinstance(it, dict)]

        return cls(monsters, items)
