# src/scenes/evo_scene.py
from __future__ import annotations

import re
import pygame as pg


class EvoScene:
    """
    Evolution selector (no effects):
    - Click a Pokemon in bag -> if can evolve and has Evolution Potion -> evolve immediately
    - Bag data is updated in-place (monster dict is modified)
    """

    # ---------- config ----------
    EVO_TABLE: dict[int, int] = {
        1: 2,
        2: 3,
        7: 8,
        8: 9,
        12: 13,
        13: 14,
        15: 16,
    }

    EVO_ITEM_ALIASES = {
        "evolution potion", "evo potion", "evolution_potion", "evo_potion"
    }

    # stats multipliers
    HP_MULT = 1.25
    ATK_MULT = 1.20
    DEF_MULT = 1.15
    LEVEL_PLUS = 1

    # UI
    _open: bool = False
    _bag = None
    _scroll: int = 0
    _page_size: int = 6

    _choice_rects: list[tuple[int, pg.Rect]] = []
    _cancel_rect: pg.Rect | None = None
    _up_rect: pg.Rect | None = None
    _down_rect: pg.Rect | None = None

    _msg: str | None = None
    _msg_timer: float = 0.0

    # -------------------------
    # helpers for bag data
    # -------------------------
    @staticmethod
    def _get_monsters(bag) -> list[dict]:
        # Your save uses bag["monsters"], but your runtime Bag object might store in _monsters_data
        mons = getattr(bag, "_monsters_data", None)
        if isinstance(mons, list):
            return mons
        mons = getattr(bag, "monsters", None)
        if isinstance(mons, list):
            return mons
        # fallback if bag itself is a dict
        if isinstance(bag, dict) and isinstance(bag.get("monsters"), list):
            return bag["monsters"]
        return []

    @staticmethod
    def _get_items(bag) -> list[dict]:
        items = getattr(bag, "_items_data", None)
        if isinstance(items, list):
            return items
        items = getattr(bag, "items", None)
        if isinstance(items, list):
            return items
        if isinstance(bag, dict) and isinstance(bag.get("items"), list):
            return bag["items"]
        return []

    @staticmethod
    def _norm(s: str) -> str:
        return str(s).strip().lower().replace("_", " ")

    @staticmethod
    def _to_int(v, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return default

    @staticmethod
    def _find_evo_item(items: list[dict]) -> dict | None:
        want = {EvoScene._norm(a) for a in EvoScene.EVO_ITEM_ALIASES}
        for it in items:
            if EvoScene._norm(it.get("name", "")) in want:
                return it
        return None

    @staticmethod
    def _extract_stage_id(mon: dict) -> int | None:
        """
        Accept:
          - menu_sprites/menusprite1.png
          - assets/images/sprites/sprite1_idle.png
          - sprite_path / sprite
        """
        sp = mon.get("sprite_path") or mon.get("sprite") or ""
        sp = str(sp)

        # menusprite(\d+).png
        m = re.search(r"menusprite(\d+)\.png", sp, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None

        # sprite(\d+)
        m = re.search(r"sprite(\d+)", sp, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None

        return None

    @staticmethod
    def _can_evolve(mon: dict) -> bool:
        sid = EvoScene._extract_stage_id(mon)
        return (sid is not None) and (sid in EvoScene.EVO_TABLE)

    @staticmethod
    def _evo_potion_count(bag) -> int:
        items = EvoScene._get_items(bag)
        it = EvoScene._find_evo_item(items)
        if not it:
            return 0
        return EvoScene._to_int(it.get("count", 0), 0)

    @staticmethod
    def _apply_evolution(bag, mon_idx: int) -> tuple[bool, str]:
        mons = EvoScene._get_monsters(bag)
        if not (0 <= mon_idx < len(mons)):
            return False, "invalid pokemon"

        items = EvoScene._get_items(bag)
        it = EvoScene._find_evo_item(items)
        if not it:
            return False, "no evolution potion"
        cnt = EvoScene._to_int(it.get("count", 0), 0)
        if cnt <= 0:
            return False, "no evolution potion"

        mon = mons[mon_idx]
        sid = EvoScene._extract_stage_id(mon)
        if sid is None:
            return False, "cannot parse sprite id from sprite_path"

        to_id = EvoScene.EVO_TABLE.get(sid)
        if not to_id:
            return False, "this pokemon cannot evolve"

        # consume potion
        it["count"] = cnt - 1

        # stats (your save has hp/max_hp/level; may not have attack/defense)
        old_level = EvoScene._to_int(mon.get("level", 1), 1)
        old_max_hp = EvoScene._to_int(mon.get("max_hp", mon.get("hp", 1)), 1)
        old_hp = EvoScene._to_int(mon.get("hp", old_max_hp), old_max_hp)

        old_atk = EvoScene._to_int(mon.get("attack", mon.get("atk", 10)), 10)
        old_def = EvoScene._to_int(mon.get("defense", mon.get("def", 10)), 10)

        new_level = old_level + EvoScene.LEVEL_PLUS
        new_max_hp = max(old_max_hp + 1, int(old_max_hp * EvoScene.HP_MULT))
        # keep hp ratio, but you said no effects; most games heal on evolve -> choose FULL HP
        new_hp = new_max_hp

        new_atk = max(old_atk + 1, int(old_atk * EvoScene.ATK_MULT))
        new_def = max(old_def + 1, int(old_def * EvoScene.DEF_MULT))

        mon["level"] = new_level
        mon["max_hp"] = new_max_hp
        mon["hp"] = new_hp

        # ensure keys exist for battle usage
        mon["attack"] = new_atk
        mon["defense"] = new_def

        # IMPORTANT: your save uses menu_sprites/menuspriteX.png
        mon["sprite_path"] = f"menu_sprites/menusprite{to_id}.png"
        mon["sprite"] = mon["sprite_path"]  # some scenes might read "sprite"

        # optional: record evolution lineage
        mon["evolved_from"] = sid
        mon["stage_id"] = to_id  # handy if you want later

        name = str(mon.get("name", "Pokemon"))
        return True, f"{name} evolved! (menusprite{sid} -> menusprite{to_id})"

    # -------------------------
    # Scene lifecycle
    # -------------------------
    @staticmethod
    def is_open() -> bool:
        return EvoScene._open

    @staticmethod
    def open(bag) -> None:
        EvoScene._open = True
        EvoScene._bag = bag
        EvoScene._scroll = 0
        EvoScene._choice_rects = []
        EvoScene._cancel_rect = None
        EvoScene._up_rect = None
        EvoScene._down_rect = None
        EvoScene._msg = None
        EvoScene._msg_timer = 0.0

    @staticmethod
    def close() -> None:
        EvoScene._open = False
        EvoScene._bag = None
        EvoScene._scroll = 0
        EvoScene._choice_rects = []
        EvoScene._cancel_rect = None
        EvoScene._up_rect = None
        EvoScene._down_rect = None
        EvoScene._msg = None
        EvoScene._msg_timer = 0.0

    @staticmethod
    def update(dt: float) -> None:
        if not EvoScene._open:
            return

        if EvoScene._msg_timer > 0:
            EvoScene._msg_timer -= dt
            if EvoScene._msg_timer <= 0:
                EvoScene._msg_timer = 0.0
                EvoScene._msg = None

        keys = pg.key.get_pressed()
        if keys[pg.K_ESCAPE]:
            EvoScene.close()

    @staticmethod
    def handle_click(pos: tuple[int, int]) -> None:
        if not EvoScene._open or EvoScene._bag is None:
            return

        if EvoScene._cancel_rect and EvoScene._cancel_rect.collidepoint(pos):
            EvoScene.close()
            return

        mons = EvoScene._get_monsters(EvoScene._bag)
        total = len(mons)
        max_scroll = max(0, total - EvoScene._page_size)

        if EvoScene._up_rect and EvoScene._up_rect.collidepoint(pos):
            EvoScene._scroll = max(0, EvoScene._scroll - EvoScene._page_size)
            return
        if EvoScene._down_rect and EvoScene._down_rect.collidepoint(pos):
            EvoScene._scroll = min(max_scroll, EvoScene._scroll + EvoScene._page_size)
            return

        for idx, rect in EvoScene._choice_rects:
            if rect.collidepoint(pos):
                ok, msg = EvoScene._apply_evolution(EvoScene._bag, idx)
                EvoScene._msg = msg
                EvoScene._msg_timer = 0.9
                if ok:
                    EvoScene.close()
                return

    @staticmethod
    def draw(screen: pg.Surface, center: tuple[int, int]) -> None:
        if not EvoScene._open or EvoScene._bag is None:
            return

        sw, sh = screen.get_size()

        dim = pg.Surface((sw, sh), pg.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        screen.blit(dim, (0, 0))

        pop = pg.Rect(0, 0, 560, 420)
        pop.center = center
        pg.draw.rect(screen, (250, 240, 200), pop, border_radius=12)
        pg.draw.rect(screen, (120, 90, 40), pop, 2, border_radius=12)

        font = pg.font.SysFont(None, 30)
        small = pg.font.SysFont(None, 22)
        mini = pg.font.SysFont(None, 18)

        potion_cnt = EvoScene._evo_potion_count(EvoScene._bag)
        title = f"Evolution (Potion: {potion_cnt})"
        screen.blit(font.render(title, True, (40, 40, 40)), (pop.x + 16, pop.y + 14))

        mons = EvoScene._get_monsters(EvoScene._bag)
        total = len(mons)

        EvoScene._choice_rects = []
        list_top = pop.y + 56
        row_h = 44
        row_gap = 8

        start = min(EvoScene._scroll, max(0, total))
        end = min(start + EvoScene._page_size, total)

        if total == 0:
            screen.blit(small.render("No Pokemon in bag.", True, (70, 60, 40)), (pop.x + 16, list_top))
        else:
            for vis_i, i in enumerate(range(start, end)):
                mon = mons[i]
                r = pg.Rect(pop.x + 16, list_top + vis_i * (row_h + row_gap), pop.width - 32, row_h)

                pg.draw.rect(screen, (255, 255, 255), r, border_radius=8)
                pg.draw.rect(screen, (120, 90, 40), r, 2, border_radius=8)

                name = str(mon.get("name", "???"))
                lv = EvoScene._to_int(mon.get("level", 1), 1)
                sid = EvoScene._extract_stage_id(mon)
                evolvable = EvoScene._can_evolve(mon)

                tag = "" if evolvable else " (no evo)"
                line = f"{name}  Lv.{lv}  id:{sid}{tag}"
                screen.blit(small.render(line, True, (40, 40, 40)), (r.x + 12, r.y + 12))

                EvoScene._choice_rects.append((i, r))

        # scroll buttons
        if total > EvoScene._page_size:
            up = pg.Rect(pop.right - 44, pop.y + 60, 28, 28)
            down = pg.Rect(pop.right - 44, pop.y + 60 + (EvoScene._page_size - 1) * (row_h + row_gap), 28, 28)

            pg.draw.rect(screen, (240, 230, 190), up, border_radius=6)
            pg.draw.rect(screen, (120, 90, 40), up, 2, border_radius=6)
            pg.draw.rect(screen, (240, 230, 190), down, border_radius=6)
            pg.draw.rect(screen, (120, 90, 40), down, 2, border_radius=6)

            screen.blit(mini.render("▲", True, (40, 40, 40)), mini.render("▲", True, (40, 40, 40)).get_rect(center=up.center))
            screen.blit(mini.render("▼", True, (40, 40, 40)), mini.render("▼", True, (40, 40, 40)).get_rect(center=down.center))

            EvoScene._up_rect = up
            EvoScene._down_rect = down

            page_txt = mini.render(f"{start+1}-{end} / {total}", True, (60, 50, 30))
            screen.blit(page_txt, (pop.x + 16, pop.bottom - 76))
        else:
            EvoScene._up_rect = None
            EvoScene._down_rect = None

        # cancel
        cancel = pg.Rect(pop.right - 110, pop.bottom - 46, 94, 30)
        pg.draw.rect(screen, (240, 230, 190), cancel, border_radius=8)
        pg.draw.rect(screen, (120, 90, 40), cancel, 2, border_radius=8)
        c_surf = small.render("Cancel", True, (40, 40, 40))
        screen.blit(c_surf, c_surf.get_rect(center=cancel.center))
        EvoScene._cancel_rect = cancel

        hint = mini.render("Click a Pokemon to evolve  |  ESC to cancel", True, (60, 50, 30))
        screen.blit(hint, (pop.x + 16, pop.bottom - 22))

        if EvoScene._msg:
            msg_surf = mini.render(str(EvoScene._msg), True, (40, 40, 40))
            screen.blit(msg_surf, (pop.x + 16, pop.bottom - 46))
