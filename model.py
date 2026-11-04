"""Deterministic, renderer-independent simulation for Below the Signal.

World coordinates are pixels. ``#`` cells are solid; ``.`` cells are floor.
The monster only knows a heard or last-seen position, never a hidden player's
current position. Nothing in this module requires pygame or third-party code.
"""

from collections import deque
from dataclasses import dataclass
import math


TILE = 48
PLAYER_SPEED = 118.0
SPRINT_SPEED = 176.0
PING_COOLDOWN = 2.5
INTERACT_RADIUS = 74.0


@dataclass
class Item:
    id: str
    kind: str
    x: float
    y: float
    collected: bool = False


def _center(x, y):
    return (x + 0.5) * TILE, (y + 0.5) * TILE


def _make_map():
    """Carve a fixed wreck with a perimeter loop and four central shortcuts."""
    cells = [["#"] * 38 for _ in range(28)]

    def room(x1, y1, x2, y2):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                cells[y][x] = "."

    for bounds in [(2, 2, 8, 7), (28, 2, 35, 8), (2, 18, 9, 25),
                   (27, 18, 35, 25), (13, 10, 23, 17)]:
        room(*bounds)
    for bounds in [(5, 5, 32, 6), (5, 5, 6, 23), (31, 5, 32, 23),
                   (5, 22, 32, 23), (16, 5, 17, 13), (5, 12, 16, 13),
                   (22, 12, 32, 13), (18, 16, 19, 23)]:
        room(*bounds)
    # Machinery provides cover without splitting any route.
    for x, y in [(15, 11), (15, 12), (20, 14), (20, 15), (30, 4),
                 (30, 5), (7, 20), (7, 21), (29, 21), (30, 21)]:
        cells[y][x] = "#"
    return ["".join(row) for row in cells]


class World:
    """A complete single run. Construct another World to restart.

    ``update(dt, dx, dy, sprint)`` accepts seconds and a movement vector.
    ``interact`` collects the closest reachable nearby object, or returns to
    the airlock after all three recorders. ``pop_events`` drains string events.
    The static grid and item positions are deliberately reproducible.
    """

    player_radius = 12.0
    monster_radius = 14.0

    def __init__(self):
        self.grid = _make_map()
        self.width = len(self.grid[0]) * TILE
        self.height = len(self.grid) * TILE
        self.player_x, self.player_y = _center(3, 3)
        self.exit_x, self.exit_y = self.player_x, self.player_y
        self.monster_x, self.monster_y = _center(32, 23)
        self.items = [
            Item("bridge", "recorder", *_center(34, 3)),
            Item("pump", "recorder", *_center(3, 24)),
            Item("hold", "recorder", *_center(34, 24)),
            Item("tank_bridge", "oxygen", *_center(28, 7)),
            Item("tank_engine", "oxygen", *_center(14, 16)),
            Item("tank_pump", "oxygen", *_center(8, 24)),
        ]
        self._exit = Item("airlock", "exit", self.exit_x, self.exit_y)
        self.oxygen = 100.0
        self.collected = 0
        self.elapsed = 0.0
        self.state = "playing"
        self.death_reason = ""
        self.threat = 0.0
        self.ping_cooldown = 0.0
        self.ping_age = 999.0
        self.last_ping = (self.player_x, self.player_y)
        self.monster_mode = "patrol"
        self.monster_awake = False
        self.sprinting = False
        self._events = []
        self._noise_timer = 0.0
        self._memory = 0.0
        self._target = None
        self._route = deque()
        self._repath = 0.0
        self._patrol_index = 0
        self._patrol = [(32, 20), (22, 13), (18, 22), (6, 22),
                        (16, 13), (32, 6)]
        self._oxygen_warned = False

    @property
    def stage(self):
        """Escalation stage, from zero to three recovered recorders."""
        return self.collected

    def walkable(self, tx, ty):
        return (0 <= ty < len(self.grid) and 0 <= tx < len(self.grid[0])
                and self.grid[ty][tx] != "#")

    def can_occupy(self, x, y, radius):
        """Circle-vs-wall collision, including the map boundary."""
        for ty in range(math.floor((y - radius) / TILE),
                        math.floor((y + radius) / TILE) + 1):
            for tx in range(math.floor((x - radius) / TILE),
                            math.floor((x + radius) / TILE) + 1):
                if self.walkable(tx, ty):
                    continue
                closest_x = max(tx * TILE, min(x, (tx + 1) * TILE))
                closest_y = max(ty * TILE, min(y, (ty + 1) * TILE))
                if math.hypot(x - closest_x, y - closest_y) < radius:
                    return False
        return True

    def path(self, start, goal):
        """Return inclusive tile-coordinate BFS path, or [] if unreachable."""
        if not self.walkable(*start) or not self.walkable(*goal):
            return []
        frontier = deque([start])
        previous = {start: None}
        while frontier:
            current = frontier.popleft()
            if current == goal:
                result = []
                while current is not None:
                    result.append(current)
                    current = previous[current]
                return result[::-1]
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nxt = current[0] + dx, current[1] + dy
                if nxt not in previous and self.walkable(*nxt):
                    previous[nxt] = current
                    frontier.append(nxt)
        return []

    def line_of_sight(self, ax, ay, bx, by):
        distance = math.hypot(bx - ax, by - ay)
        steps = max(1, math.ceil(distance / 8))
        for i in range(steps + 1):
            ratio = i / steps
            if not self.walkable(int((ax + (bx - ax) * ratio) // TILE),
                                 int((ay + (by - ay) * ratio) // TILE)):
                return False
        return True

    def _clear_motion(self, ax, ay, bx, by, radius):
        """Check a short creature movement segment, including its body width."""
        steps = max(1, math.ceil(math.hypot(bx - ax, by - ay) / 6))
        return all(self.can_occupy(ax + (bx - ax) * i / steps,
                                 ay + (by - ay) * i / steps, radius)
                   for i in range(steps + 1))

    def _hear(self, x, y, duration=12.0):
        self._target = (x, y)
        self._memory = duration
        self._route.clear()
        self._repath = 0.0
        if self.monster_mode != "hunt":
            self.monster_mode = "investigate"

    def ping(self):
        if self.state != "playing" or self.ping_cooldown > 0:
            return False
        self.ping_cooldown = PING_COOLDOWN
        self.ping_age = 0.0
        self.last_ping = self.player_x, self.player_y
        self._events.append("ping")
        # A sonar ping travels through the hull. The creature travels through
        # corridors instead, so slipping away after a ping is a viable tactic.
        self._hear(self.player_x, self.player_y, 15.0)
        return True

    def nearest_interactable(self):
        candidates = [item for item in self.items if not item.collected]
        candidates.append(self._exit)
        nearby = [item for item in candidates
                  if math.hypot(item.x - self.player_x,
                                item.y - self.player_y) <= INTERACT_RADIUS
                  and self.line_of_sight(self.player_x, self.player_y,
                                         item.x, item.y)]
        return min(nearby, key=lambda item: math.hypot(
            item.x - self.player_x, item.y - self.player_y), default=None)

    def interact(self):
        if self.state != "playing":
            return None
        item = self.nearest_interactable()
        if item is None:
            return None
        if item.kind == "exit":
            if self.collected == 3:
                self.state = "won"
                self.sprinting = False
                self._events.append("won")
                return "AIRLOCK SEALED. All three recordings recovered."
            return f"Recover all three recorders before extraction ({self.collected}/3)."
        if item.kind == "oxygen":
            if self.oxygen >= 99.0:
                return "Oxygen reserve full. Leave this tank for the return trip."
            item.collected = True
            self.oxygen = min(100.0, self.oxygen + 30.0)
            self._events.append("oxygen")
            return "Emergency oxygen connected. +30% reserve."
        item.collected = True
        self.collected += 1
        self._events.append("recorder")
        self.monster_awake = True
        self._hear(item.x, item.y, 18.0)
        if self.collected == 3:
            return "RECORDER 3/3. Return to the airlock. It heard the transfer."
        return f"RECORDER {self.collected}/3 recovered. Something heard the transfer."

    def pop_events(self):
        events, self._events = self._events, []
        return events

    def _move_player(self, dt, dx, dy, sprint):
        magnitude = math.hypot(dx, dy)
        if magnitude > 1:
            dx, dy = dx / magnitude, dy / magnitude
        self.sprinting = bool(sprint and magnitude > 0)
        speed = SPRINT_SPEED if self.sprinting else PLAYER_SPEED
        # Axis separation lets the player slide along walls, not stick to them.
        distance_x, distance_y = dx * speed * dt, dy * speed * dt
        steps = max(1, math.ceil(max(abs(distance_x), abs(distance_y)) / 6.0))
        for _ in range(steps):
            nx = self.player_x + distance_x / steps
            if self.can_occupy(nx, self.player_y, self.player_radius):
                self.player_x = nx
            ny = self.player_y + distance_y / steps
            if self.can_occupy(self.player_x, ny, self.player_radius):
                self.player_y = ny

    def _move_monster(self, dt):
        if not self.monster_awake:
            return
        distance = math.hypot(self.player_x - self.monster_x,
                              self.player_y - self.monster_y)
        sees_player = distance < 205 + self.collected * 18 and self.line_of_sight(
            self.monster_x, self.monster_y, self.player_x, self.player_y)
        if sees_player:
            if self.monster_mode != "hunt":
                self._events.append("spotted")
            self.monster_mode = "hunt"
            self._target = self.player_x, self.player_y
            self._memory = 8.0
        else:
            if self.monster_mode == "hunt":
                self.monster_mode = "investigate"
            self._memory = max(0.0, self._memory - dt)
            if self._memory <= 0:
                self.monster_mode = "patrol"
                goal = _center(*self._patrol[self._patrol_index])
                if math.hypot(goal[0] - self.monster_x,
                              goal[1] - self.monster_y) < 12:
                    self._patrol_index = (self._patrol_index + 1) % len(self._patrol)
                    goal = _center(*self._patrol[self._patrol_index])
                self._target = goal
        if self._target is None:
            return
        self._repath -= dt
        if self._repath <= 0:
            start = int(self.monster_x // TILE), int(self.monster_y // TILE)
            goal = int(self._target[0] // TILE), int(self._target[1] // TILE)
            route = self.path(start, goal)
            # A tile-center waypoint prevents cutting solid corners. Skip it
            # when the direct segment is safe, so repathing never makes the
            # creature repeatedly backtrack along a straight corridor.
            if route:
                self._route = deque(_center(*tile) for tile in route)
                if len(self._route) > 1:
                    nx, ny = self._route[1]
                    if self._clear_motion(self.monster_x, self.monster_y,
                                          nx, ny, self.monster_radius):
                        self._route.popleft()
                # Pursue the actual last-seen position inside its final tile.
                # Stopping at its center would leave safe spots in open rooms.
                gx, gy = self._route[-1]
                if self._clear_motion(gx, gy, *self._target, self.monster_radius):
                    self._route.append(self._target)
            else:
                self._route.clear()
            self._repath = 0.7
        speed = (106 if self.monster_mode == "hunt" else 68) + self.collected * 7
        budget = speed * dt
        while self._route and budget > 0:
            gx, gy = self._route[0]
            vx, vy = gx - self.monster_x, gy - self.monster_y
            dist = math.hypot(vx, vy)
            if dist < 0.01:
                self._route.popleft()
                continue
            step = min(budget, dist)
            nx, ny = self.monster_x + vx / dist * step, self.monster_y + vy / dist * step
            if not self.can_occupy(nx, ny, self.monster_radius):
                self._route.clear()
                self._repath = 0
                break
            self.monster_x, self.monster_y = nx, ny
            budget -= step
            if step >= dist:
                self._route.popleft()

    def _lose(self, reason):
        self.state = "lost"
        self.death_reason = reason
        self.sprinting = False
        self._events.append("lost")

    def update(self, dt, dx=0.0, dy=0.0, sprint=False):
        if self.state != "playing" or dt <= 0:
            return
        if not all(math.isfinite(value) for value in (dt, dx, dy)):
            raise ValueError("Time and movement must be finite")
        # Small simulation steps keep both collisions and AI independent of FPS.
        remaining = dt
        while remaining > 0.000001 and self.state == "playing":
            step = min(remaining, 0.05)
            remaining -= step
            self.elapsed += step
            self.ping_cooldown = max(0.0, self.ping_cooldown - step)
            self.ping_age += step
            self.monster_awake = self.monster_awake or self.elapsed >= 18.0
            self._move_player(step, dx, dy, sprint)
            self.oxygen = max(0.0, self.oxygen - step * (0.28 + 0.12 * self.sprinting))
            if self.oxygen <= 25 and not self._oxygen_warned:
                self._oxygen_warned = True
                self._events.append("warning")
            self._noise_timer -= step
            if self.sprinting and self._noise_timer <= 0:
                if math.hypot(self.player_x - self.monster_x,
                              self.player_y - self.monster_y) < 450:
                    self._hear(self.player_x, self.player_y, 8.0)
                self._noise_timer = 1.25
            self._move_monster(step)
            distance = math.hypot(self.player_x - self.monster_x,
                                  self.player_y - self.monster_y)
            raw_threat = max(0.0, min(1.0, (430 - distance) / 400))
            self.threat += (raw_threat - self.threat) * min(1.0, step * 4)
            if self.oxygen <= 0:
                self._lose("oxygen")
            elif (self.monster_awake and distance < self.player_radius + self.monster_radius
                  and self.line_of_sight(self.monster_x, self.monster_y,
                                         self.player_x, self.player_y)):
                self._lose("creature")
