from __future__ import annotations

from typing import Any

from .config import BodyConfig
from .stores import StateStore


ACTIONS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
           "wait": (0, 0), "eat": (0, 0)}


class GridWorld:
    """Simulator truth is private to this adapter; cognition gets observe() only."""

    def __init__(self, state: StateStore, config: BodyConfig):
        self.state, self.config = state, config
        if state.get("world.truth") is None:
            state.set("world.truth", {"width": 7, "height": 5,
                "walls": [[x, 0] for x in range(7)] + [[x, 4] for x in range(7)]
                         + [[0, y] for y in range(1, 4)] + [[6, y] for y in range(1, 4)] + [[3, 2]],
                "food": [[5, 2]], "position": [1, 2], "orientation": "east",
                "hunger": 0.6, "health": 1.0, "step": 0, "contact": False})

    @staticmethod
    def _line(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = start
        ex, ey = end
        dx, dy = abs(ex - x), -abs(ey - y)
        sx, sy = (1 if x < ex else -1), (1 if y < ey else -1)
        error = dx + dy
        cells = []
        while True:
            cells.append((x, y))
            if (x, y) == (ex, ey):
                return cells
            twice = 2 * error
            if twice >= dy:
                error += dy
                x += sx
            if twice <= dx:
                error += dx
                y += sy

    def observe(self) -> dict[str, Any]:
        truth = self.state.get("world.truth")
        position = tuple(truth["position"])
        walls = {tuple(p) for p in truth["walls"]}
        foods = {tuple(p) for p in truth["food"]}
        visible = []
        # v0.01 has omnidirectional local sight with occlusion, not a camera model.
        for y in range(truth["height"]):
            for x in range(truth["width"]):
                if abs(x - position[0]) + abs(y - position[1]) > self.config.vision_radius:
                    continue
                if any(cell in walls for cell in self._line(position, (x, y))[1:-1]):
                    continue
                visible.append({"position": [x, y], "kind": "wall" if (x, y) in walls else "food" if (x, y) in foods else "empty"})
        return {"step": truth["step"], "position": list(position), "orientation": truth["orientation"],
                "hunger": truth["hunger"], "health": truth["health"], "contact": truth["contact"],
                "visible": visible}

    def act(self, action: str) -> dict[str, Any]:
        if action not in ACTIONS:
            raise ValueError(f"Unsupported body action: {action}")
        truth = self.state.get("world.truth")
        before = list(truth["position"])
        delta = ACTIONS[action]
        target = [before[0] + delta[0], before[1] + delta[1]]
        blocked = target in truth["walls"] or not (0 <= target[0] < truth["width"] and 0 <= target[1] < truth["height"])
        ate = action == "eat" and before in truth["food"]
        if ate:
            truth["food"].remove(before)
            truth["hunger"] = max(0.0, truth["hunger"] - 0.8)
        elif action != "eat" and not blocked:
            truth["position"] = target
        if delta != (0, 0):
            truth["orientation"] = action
        truth["hunger"] = min(1.0, truth["hunger"] + self.config.hunger_per_action)
        if truth["hunger"] >= 1.0:
            truth["health"] = max(0.0, truth["health"] - 0.02)
        truth["step"] += 1
        truth["contact"] = bool(blocked and delta != (0, 0))
        self.state.set("world.truth", truth)
        return {"action": action, "before": before, "position": truth["position"],
                "hunger": truth["hunger"], "health": truth["health"], "blocked": truth["contact"],
                "ate": ate, "step": truth["step"], "target": target, "observation": self.observe()}

    def render(self, *, reveal: bool = False) -> str:
        truth = self.state.get("world.truth")
        known = self.state.get("body.map", {})
        position = self.state.get("body.sensed", {}).get("position", truth["position"])
        rows = []
        for y in range(truth["height"]):
            row = ""
            for x in range(truth["width"]):
                kind = known.get(f"{x},{y}", "unknown")
                if reveal:
                    kind = "wall" if [x, y] in truth["walls"] else "food" if [x, y] in truth["food"] else "empty"
                row += "@" if [x, y] == position else {"wall": "#", "food": "F", "empty": ".", "unknown": "?"}[kind]
            rows.append(row)
        return "\n".join(rows)
