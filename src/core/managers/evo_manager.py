# src/core/evo_manager.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvoRule:
    to_id: int
    to_name: str
    to_sprite_idle: str
    to_sprite_attack: str | None = None
    to_sprite_base: str | None = None
    hp_mult: float = 1.25
    atk_mult: float = 1.20
    def_mult: float = 1.15
    level_plus: int = 1


class EvoManager:
    """
    Centralized evolution logic.

    This manager:
      - checks/consumes Evolution Potion from bag._items_data
      - evolves a selected pokemon in bag._monsters_data (in-place update)
      - swaps to different assets (spriteX_*.png) and boosts stats

    Expected bag data:
      - bag._items_data: list[dict]  e.g. [{"name":"evo_potion","count":1}, ...]
      - bag._monsters_data: list[dict]  e.g. [{"id":1,"name":"...","max_hp":60,"attack":10,"sprite_path":"..."}]
    """

    # -------------------------
    # Evolution Chains (YOUR RULES)
    # 1→2→3, 7→8→9, 12→13→14, 15→16
    # Others: no evolution
    # -------------------------
    RULES: dict[int, EvoRule] = {
        1: EvoRule(
            to_id=2,
            to_name="Monster2",
            to_sprite_idle="assets/images/sprites/sprite2_idle.png",
            to_sprite_attack="assets/images/sprites/sprite2_attack.png",
            to_sprite_base="assets/images/sprites/sprite2.png",
            hp_mult=1.25,
            atk_mult=1.20,
            def_mult=1.15,
            level_plus=1,
        ),
        2: EvoRule(
            to_id=3,
            to_name="Monster3",
            to_sprite_idle="assets/images/sprites/sprite3_idle.png",
            to_sprite_attack="assets/images/sprites/sprite3_attack.png",
            to_sprite_base="assets/images/sprites/sprite3.png",
            hp_mult=1.20,
            atk_mult=1.18,
            def_mult=1.12,
            level_plus=1,
        ),
        7: EvoRule(
            to_id=8,
            to_name="Monster8",
            to_sprite_idle="assets/images/sprites/sprite8_idle.png",
            to_sprite_attack="assets/images/sprites/sprite8_attack.png",
            to_sprite_base="assets/images/sprites/sprite8.png",
            hp_mult=1.25,
            atk_mult=1.20,
            def_mult=1.15,
            level_plus=1,
        ),
        8: EvoRule(
            to_id=9,
            to_name="Monster9",
            to_sprite_idle="assets/images/sprites/sprite9_idle.png",
            to_sprite_attack="assets/images/sprites/sprite9_attack.png",
            to_sprite_base="assets/images/sprites/sprite9.png",
            hp_mult=1.20,
            atk_mult=1.18,
            def_mult=1.12,
            level_plus=1,
        ),
        12: EvoRule(
            to_id=13,
            to_name="Monster13",
            to_sprite_idle="assets/images/sprites/sprite13_idle.png",
            to_sprite_attack="assets/images/sprites/sprite13_attack.png",
            to_sprite_base="assets/images/sprites/sprite13.png",
            hp_mult=1.25,
            atk_mult=1.20,
            def_mult=1.15,
            level_plus=1,
        ),
        13: EvoRule(
            to_id=14,
            to_name="Monster14",
            to_sprite_idle="assets/images/sprites/sprite14_idle.png",
            to_sprite_attack="assets/images/sprites/sprite14_attack.png",
            to_sprite_base="assets/images/sprites/sprite14.png",
            hp_mult=1.20,
            atk_mult=1.18,
            def_mult=1.12,
            level_plus=1,
        ),
        15: EvoRule(
            to_id=16,
            to_name="Monster16",
            to_sprite_idle="assets/images/sprites/sprite16_idle.png",
            to_sprite_attack="assets/images/sprites/sprite16_attack.png",
            to_sprite_base="assets/images/sprites/sprite16.png",
            hp_mult=1.25,
            atk_mult=1.20,
            def_mult=1.15,
            level_plus=1,
        ),
    }

    EVO_ITEM_ALIASES = {"evolution potion", "evo potion", "evolution_potion", "evo_potion"}

    # -------------------------
    # helpers
    # -------------------------
    @staticmethod
    def _norm(s: str) -> str:
        return str(s).strip().lower().replace("_", " ")

    @staticmethod
    def _to_int(v: Any, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _find_item(bag: Any, aliases: set[str]) -> dict | None:
        items = getattr(bag, "_items_data", []) or []
        want = {EvoManager._norm(a) for a in aliases}
        for it in items:
            if EvoManager._norm(it.get("name", "")) in want:
                return it
        return None

    @staticmethod
    def get_evo_potion_count(bag: Any) -> int:
        it = EvoManager._find_item(bag, EvoManager.EVO_ITEM_ALIASES)
        if not it:
            return 0
        return EvoManager._to_int(it.get("count", 0), 0)

    # -------------------------
    # identify current monster id
    # -------------------------
    @staticmethod
    def _infer_id(mon: dict) -> int | None:
        # 1) preferred explicit id
        mid = mon.get("id", None)
        if isinstance(mid, int):
            return mid
        if isinstance(mid, str) and mid.isdigit():
            return int(mid)

        # 2) try parse from sprite_path like ".../sprite7_idle.png"
        sp = str(mon.get("sprite_path") or mon.get("sprite") or "")
        sp = sp.lower()
        # find "sprite" then digits
        idx = sp.find("sprite")
        if idx >= 0:
            j = idx + len("sprite")
            digits = []
            while j < len(sp) and sp[j].isdigit():
                digits.append(sp[j])
                j += 1
            if digits:
                try:
                    return int("".join(digits))
                except Exception:
                    pass

        # 3) if name is like "sprite7" or "7"
        nm = str(mon.get("name", "")).strip().lower()
        if nm.isdigit():
            return int(nm)
        if nm.startswith("sprite") and nm[6:].isdigit():
            return int(nm[6:])

        return None

    @staticmethod
    def can_evolve(mon: dict) -> bool:
        mid = EvoManager._infer_id(mon)
        return (mid is not None) and (mid in EvoManager.RULES)

    # -------------------------
    # main API
    # -------------------------
    @staticmethod
    def evolve_with_potion(bag: Any, mon_idx: int) -> tuple[bool, str]:
        mons = getattr(bag, "_monsters_data", [])
        if not isinstance(mons, list) or not (0 <= mon_idx < len(mons)):
            return False, "invalid pokemon"

        it = EvoManager._find_item(bag, EvoManager.EVO_ITEM_ALIASES)
        if not it:
            return False, "no evolution potion"
        cnt = EvoManager._to_int(it.get("count", 0), 0)
        if cnt <= 0:
            return False, "no evolution potion"

        mon = mons[mon_idx]
        mid = EvoManager._infer_id(mon)
        if mid is None:
            return False, "pokemon id not found"

        rule = EvoManager.RULES.get(mid)
        if not rule:
            return False, "this pokemon cannot evolve"

        # consume potion
        it["count"] = cnt - 1

        # ---- stats boost (safe, support common key styles) ----
        old_level = EvoManager._to_int(mon.get("level", 1), 1)

        old_max_hp = EvoManager._to_int(mon.get("max_hp", mon.get("hp", 1)), 1)
        old_hp = EvoManager._to_int(mon.get("hp", old_max_hp), old_max_hp)

        # support attack/atk
        old_atk = EvoManager._to_int(mon.get("attack", mon.get("atk", 10)), 10)
        # support defense/def
        old_def = EvoManager._to_int(mon.get("defense", mon.get("def", 10)), 10)

        new_level = old_level + rule.level_plus
        new_max_hp = max(old_max_hp + 1, int(old_max_hp * rule.hp_mult))
        hp_ratio = (old_hp / old_max_hp) if old_max_hp > 0 else 1.0
        new_hp = min(new_max_hp, max(1, int(new_max_hp * hp_ratio)))
        new_atk = max(old_atk + 1, int(old_atk * rule.atk_mult))
        new_def = max(old_def + 1, int(old_def * rule.def_mult))

        # ---- apply evolution (in-place update) ----
        mon["id"] = rule.to_id
        mon["name"] = rule.to_name
        mon["level"] = new_level
        mon["max_hp"] = new_max_hp
        mon["hp"] = new_max_hp  # evolve heals to full

        if "attack" in mon:
            mon["attack"] = new_atk
        else:
            mon["atk"] = new_atk

        if "defense" in mon:
            mon["defense"] = new_def
        else:
            mon["def"] = new_def

        # asset swap (must be different assets)
        mon["sprite_path"] = rule.to_sprite_idle
        mon["sprite"] = rule.to_sprite_idle  # many scenes use "sprite"
        if rule.to_sprite_attack:
            mon["attack_sprite"] = rule.to_sprite_attack
        if rule.to_sprite_base:
            mon["base_sprite"] = rule.to_sprite_base

        mon["evolved_from_id"] = mid

        return True, f"Evolved to {rule.to_name} (sprite{rule.to_id})!"
