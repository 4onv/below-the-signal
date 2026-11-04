"""Below the Signal — an entirely procedural Python horror game."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from audio import SoundEngine
from model import World, TILE

VERSION = "1.0.0"
W, H = 1280, 800
INK = (6, 14, 20)
PANEL = (11, 25, 32)
LINE = (35, 66, 73)
WHITE = (223, 235, 226)
MUTED = (123, 151, 153)
TEAL = (100, 220, 186)
AMBER = (238, 181, 101)
RED = (229, 104, 103)
VIEW = pygame.Rect(24, 110, 900, 606)
LOGS = [
    ("01 / THE KNOCK", "We heard it on the hull for six nights. Three knocks. Always three. Then the crew started answering."),
    ("02 / THE VOICE", "The last transmission used my voice. I was standing beside the radio. My mouth was closed."),
    ("03 / THE SIGNAL", "The sonar was never finding it. We were teaching it where to look. Stop transmitting. Come home quietly."),
]


def mix(a, b, t):
    return tuple(max(0, min(255, int(x + (y - x) * t))) for x, y in zip(a, b))


class Game:
    def __init__(self, *, headless=False):
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        self.display = pygame.display.set_mode((W, H), pygame.RESIZABLE)
        pygame.display.set_caption("Below the Signal")
        icon = pygame.Surface((48, 48), pygame.SRCALPHA)
        pygame.draw.circle(icon, TEAL, (24, 24), 20, 2)
        pygame.draw.circle(icon, TEAL, (24, 24), 10, 1)
        pygame.draw.line(icon, WHITE, (24, 24), (37, 11), 3)
        pygame.display.set_icon(icon)
        self.screen = pygame.Surface((W, H))
        self.fonts = {}
        self.clock = pygame.time.Clock()
        self.running = True
        self.mode = "title"
        self.time = 0.0
        self.world = None
        self.buttons = []
        self.pulses = []
        self.discovered = set()
        self.revealed = {}
        self.logs = []
        self.toast = ""
        self.toast_time = 0
        self.pings = 0
        self.camera = [0.0, 0.0]
        self.heading = 0.0
        self.fullscreen = False
        self.headless = headless
        self.settings_path = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "BelowTheSignal" / "progress.json"
        self.settings = {"muted": False, "reduced_motion": False, "best_time": None, "completed": 0}
        if not headless:
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in ("muted", "reduced_motion"):
                        if isinstance(data.get(key), bool):
                            self.settings[key] = data[key]
                    if isinstance(data.get("best_time"), (int, float)) and data["best_time"] > 0:
                        self.settings["best_time"] = data["best_time"]
                    if isinstance(data.get("completed"), int):
                        self.settings["completed"] = max(0, data["completed"])
            except (OSError, ValueError, TypeError):
                pass
        self.audio = SoundEngine()
        self.audio.set_muted(self.settings["muted"])
        rng = random.Random(14)
        self.motes = [(rng.randrange(W), rng.randrange(H), rng.uniform(0.2, 1.0)) for _ in range(90)]
        self.noise = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 4):
            pygame.draw.line(self.noise, (0, 0, 0, 15), (0, y), (W, y))

    def font(self, size, bold=False):
        key = size, bold
        if key not in self.fonts:
            self.fonts[key] = pygame.font.Font(None, size)
            self.fonts[key].set_bold(bold)
        return self.fonts[key]

    def text(self, value, x, y, size=22, color=WHITE, bold=False, center=False):
        surface = self.font(size, bold).render(str(value), True, color)
        rect = surface.get_rect()
        if center:
            rect.center = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surface, rect)
        return rect

    def wrap(self, value, x, y, width, size=22, color=MUTED, spacing=5):
        words = value.split()
        line = ""
        for word in words:
            attempt = (line + " " + word).strip()
            if self.font(size).size(attempt)[0] > width and line:
                self.text(line, x, y, size, color)
                y += size + spacing
                line = word
            else:
                line = attempt
        if line:
            self.text(line, x, y, size, color)
            y += size + spacing
        return y

    def panel(self, rect, color=PANEL, border=LINE):
        pygame.draw.rect(self.screen, color, rect, border_radius=5)
        pygame.draw.rect(self.screen, border, rect, 1, border_radius=5)

    def mouse(self):
        x, y = pygame.mouse.get_pos()
        dw, dh = self.display.get_size()
        scale = min(dw / W, dh / H)
        return ((x - (dw - W * scale) / 2) / scale, (y - (dh - H * scale) / 2) / scale)

    def button(self, label, rect, action, primary=False):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(self.mouse())
        bg = TEAL if primary else ((26, 49, 56) if hover else PANEL)
        if primary and hover:
            bg = (142, 240, 206)
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, TEAL if hover else LINE, rect, 1, border_radius=4)
        self.text(label, rect.centerx, rect.centery, 23, INK if primary else WHITE, True, True)
        self.buttons.append((rect, action))

    def save(self):
        if self.headless:
            return
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
            temporary.replace(self.settings_path)
        except OSError:
            pass

    def start(self):
        self.world = World()
        self.pulses.clear()
        self.discovered.clear()
        self.revealed.clear()
        self.logs.clear()
        self.pings = 0
        self.heading = 0.0
        self.camera = [max(VIEW.w / 2, self.world.player_x), max(VIEW.h / 2, self.world.player_y)]
        self.mode = "playing"
        self.notify("SPACE: send a sonar pulse. E: recover a recording. Return here with all three.", 9)
        self.audio.play("ui")

    def notify(self, text, duration=5):
        self.toast = text
        self.toast_time = duration

    def action(self, action):
        if action in ("start", "retry"):
            self.start()
        elif action == "resume":
            self.mode = "playing"
        elif action == "pause":
            self.mode = "paused"
        elif action == "title":
            self.mode = "title"
        elif action == "quit":
            self.running = False
        elif action == "mute":
            self.settings["muted"] = not self.settings["muted"]
            self.audio.set_muted(self.settings["muted"])
            self.save()
        elif action == "motion":
            self.settings["reduced_motion"] = not self.settings["reduced_motion"]
            self.save()
        elif action == "fullscreen":
            self.fullscreen = not self.fullscreen
            flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
            self.display = pygame.display.set_mode((0, 0) if self.fullscreen else (W, H), flags)

    def input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.WINDOWFOCUSLOST and self.mode == "playing":
                self.mode = "paused"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, action in self.buttons:
                    if rect.collidepoint(self.mouse()):
                        self.action(action)
                        break
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    self.action("mute")
                elif event.key == pygame.K_F11:
                    self.action("fullscreen")
                elif event.key == pygame.K_j and self.mode in ("playing", "journal"):
                    self.mode = "playing" if self.mode == "journal" else "journal"
                elif event.key == pygame.K_ESCAPE:
                    if self.mode == "playing":
                        self.mode = "paused"
                    elif self.mode in ("paused", "journal"):
                        self.mode = "playing"
                    elif self.mode in ("won", "lost"):
                        self.mode = "title"
                elif event.key == pygame.K_RETURN and self.mode in ("title", "won", "lost"):
                    self.start()
                elif self.mode == "playing" and event.key == pygame.K_SPACE:
                    if self.world.ping():
                        self.pulses.append([self.world.player_x, self.world.player_y, 0.0])
                        self.pings += 1
                        self.notify("SIGNAL SENT / something is listening", 2.8)
                elif self.mode == "playing" and event.key == pygame.K_e:
                    before = self.world.collected
                    message = self.world.interact()
                    if self.world.collected > before:
                        self.logs.append(LOGS[min(before, 2)])
                        self.notify(LOGS[min(before, 2)][1], 10)
                    elif message:
                        self.notify(message)
                    else:
                        self.notify("Move close to a recording, air cylinder, or the docking hatch.", 2)

    def update(self, dt):
        self.time += dt
        if self.mode == "playing":
            keys = pygame.key.get_pressed()
            dx = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
            dy = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])
            sprint = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
            if dx or dy:
                self.heading = math.atan2(dy, dx)
            self.world.update(dt, dx, dy, sprint=sprint)
            self.toast_time = max(0, self.toast_time - dt)
            for pulse in self.pulses:
                pulse[2] += dt
                radius = pulse[2] * 430
                if radius < 660:
                    for gy, row in enumerate(self.world.grid):
                        for gx, _ in enumerate(row):
                            dist = math.hypot((gx + 0.5) * TILE - pulse[0], (gy + 0.5) * TILE - pulse[1])
                            if abs(dist - radius) < 45:
                                self.discovered.add((gx, gy))
                                self.revealed[(gx, gy)] = self.world.elapsed
            self.pulses = [p for p in self.pulses if p[2] < 2.8]
            for event in self.world.pop_events():
                self.audio.play(event)
                if event == "warning":
                    self.notify("LOW OXYGEN / find an emergency air cylinder", 4)
                elif event == "oxygen":
                    self.notify("EMERGENCY AIR / oxygen replenished", 3)
            factor = 1 if self.settings["reduced_motion"] else min(1, dt * 7)
            cx = max(VIEW.w / 2, min(self.world.width - VIEW.w / 2, self.world.player_x))
            cy = max(VIEW.h / 2, min(self.world.height - VIEW.h / 2, self.world.player_y))
            self.camera[0] += (cx - self.camera[0]) * factor
            self.camera[1] += (cy - self.camera[1]) * factor
            if self.world.state in ("won", "lost"):
                self.mode = self.world.state
                if self.mode == "won":
                    old = self.settings["best_time"]
                    self.settings["best_time"] = min(old, self.world.elapsed) if old else self.world.elapsed
                    self.settings["completed"] += 1
                    self.save()
        self.audio.update(dt, self.world.threat if self.world else 0,
                          self.world.oxygen if self.world else 100, self.mode == "playing")

    def background(self):
        self.screen.fill(INK)
        for x, y, speed in self.motes:
            offset = 0 if self.settings["reduced_motion"] else self.time * 8 * speed
            pygame.draw.circle(self.screen, (19, 40, 46), (int(x), int((y - offset) % H)), 1)

    def sonar_art(self, center=(940, 345), radius=255):
        cx, cy = center
        for rad in range(45, radius + 1, 45):
            pygame.draw.circle(self.screen, (29, 65, 68), center, rad, 1)
        for angle in range(0, 360, 30):
            a = math.radians(angle)
            pygame.draw.line(self.screen, (22, 47, 52), center, (cx + math.cos(a) * radius, cy + math.sin(a) * radius))
        t = 0.8 if self.settings["reduced_motion"] else self.time * 0.25
        for n in range(35):
            a = t - n * 0.008
            pygame.draw.line(self.screen, mix((10, 22, 28), TEAL, (1 - n / 35) * 0.5), center,
                             (cx + math.cos(a) * radius, cy + math.sin(a) * radius))
        rng = random.Random(34)
        for i in range(20):
            x, y = cx + rng.randint(-170, 170), cy + rng.randint(-170, 170)
            pygame.draw.rect(self.screen, (39, 74, 77), (x, y, rng.randrange(20, 70), rng.randrange(12, 42)), 1)
        pygame.draw.circle(self.screen, TEAL, center, 5)
        pygame.draw.circle(self.screen, RED, (cx - 102, cy + 79), 3)
        self.text("UNIDENTIFIED RETURN", cx - 170, cy + 104, 17, RED)
        self.text("DEPTH  /  2,840 M", cx - 80, cy + radius + 25, 19, MUTED)

    def title(self):
        self.text("A SHORT SONAR HORROR GAME", 60, 52, 20, TEAL)
        pygame.draw.line(self.screen, LINE, (60, 88), (1220, 88))
        self.text("BELOW", 56, 153, 103, WHITE, True)
        self.text("THE SIGNAL", 60, 240, 83, WHITE, True)
        self.text("THE DARK IS QUIET. KEEP IT THAT WAY.", 64, 333, 23, AMBER)
        self.wrap("The research vessel Nacre has been silent for 19 days. Three black-box recordings remain below. Bring them home.",
                  64, 391, 500, 25, MUTED, 6)
        self.button("BEGIN DESCENT     [ ENTER ]", (64, 518, 390, 60), "start", True)
        self.text("ONE WRECK  /  THREE RECORDINGS  /  ONE WAY OUT", 66, 596, 17, MUTED)
        self.sonar_art()
        pygame.draw.line(self.screen, LINE, (60, 653), (1220, 653))
        self.text("WASD / ARROWS", 64, 676, 19, TEAL)
        self.text("Move quietly", 64, 704, 21)
        self.text("SPACE", 284, 676, 19, TEAL)
        self.text("Sonar attracts it", 284, 704, 21)
        self.text("E", 522, 676, 19, TEAL)
        self.text("Recover / escape", 522, 704, 21)
        self.button("SOUND " + ("OFF" if self.settings["muted"] else "ON"), (820, 675, 160, 43), "mute")
        self.button("MOTION " + ("LOW" if self.settings["reduced_motion"] else "ON"), (994, 675, 200, 43), "motion")
        self.text(f"v{VERSION}  /  BUILT IN PYTHON", 64, 762, 16, MUTED)
        self.text("SHIFT sprint  /  ESC pause  /  F11 fullscreen", 820, 761, 17, MUTED)
        if not self.audio.enabled:
            self.text("Audio unavailable. All danger cues are also visual.", 64, 739, 17, AMBER)

    def to_screen(self, x, y):
        return (int(VIEW.centerx + x - self.camera[0]), int(VIEW.centery + y - self.camera[1]))

    def visibility(self, x, y):
        dist = math.hypot(x - self.world.player_x, y - self.world.player_y)
        near = max(0, 1 - dist / 185)
        key = int(x // TILE), int(y // TILE)
        age = self.world.elapsed - self.revealed.get(key, -999)
        echo = max(0, 1 - age / 5.2)
        return max(near, echo * 0.85)

    def world_view(self):
        self.panel(VIEW, (3, 11, 16))
        self.screen.set_clip(VIEW.inflate(-2, -2))
        wr = self.world
        left = max(0, int((self.camera[0] - VIEW.w / 2) // TILE) - 1)
        top = max(0, int((self.camera[1] - VIEW.h / 2) // TILE) - 1)
        right = min(len(wr.grid[0]), left + VIEW.w // TILE + 4)
        bottom = min(len(wr.grid), top + VIEW.h // TILE + 4)
        for gy in range(top, bottom):
            for gx in range(left, right):
                x, y = (gx + 0.5) * TILE, (gy + 0.5) * TILE
                visible = self.visibility(x, y)
                if visible > 0.05:
                    self.discovered.add((gx, gy))
                if (gx, gy) not in self.discovered:
                    continue
                sx, sy = self.to_screen(gx * TILE, gy * TILE)
                rect = pygame.Rect(sx, sy, TILE, TILE)
                if wr.grid[gy][gx] == "#":
                    pygame.draw.rect(self.screen, mix((10, 24, 30), (43, 85, 86), visible), rect)
                    pygame.draw.rect(self.screen, mix((16, 34, 40), (84, 157, 145), visible), rect, 1)
                    if visible > 0.25:
                        pygame.draw.line(self.screen, mix((16, 34, 40), (53, 108, 103), visible), (sx + 7, sy + 7), (sx + TILE - 7, sy + 7))
                else:
                    pygame.draw.rect(self.screen, mix((5, 16, 22), (16, 39, 44), visible), rect)
                    pygame.draw.rect(self.screen, mix((7, 19, 25), (24, 53, 57), visible), rect, 1)
                    if visible > 0.3 and (gx * 7 + gy * 3) % 11 == 0:
                        pygame.draw.line(self.screen, (33, 66, 66), (sx + 12, sy + 12), (sx + 31, sy + 34), 2)
        for label, tx, ty in (("DOCK 01", 4, 7), ("BRIDGE", 31, 8), ("PUMP ROOM", 4, 25), ("CARGO HOLD", 30, 25), ("MACHINERY", 17, 17)):
            wx, wy = tx * TILE, ty * TILE
            vis = self.visibility(wx, wy)
            if vis > 0.2:
                lx, ly = self.to_screen(wx, wy)
                self.text(label, lx, ly, 17, mix((12, 28, 33), MUTED, vis))
        ex, ey = self.to_screen(wr.exit_x, wr.exit_y)
        if self.visibility(wr.exit_x, wr.exit_y) > 0.08 or (int(wr.exit_x // TILE), int(wr.exit_y // TILE)) in self.discovered:
            pygame.draw.circle(self.screen, TEAL, (ex, ey), 23, 2)
            pygame.draw.rect(self.screen, TEAL, (ex - 10, ey - 14, 20, 28), 1)
            self.text("DOCKING HATCH", ex - 58, ey + 31, 16, TEAL)
        for item in wr.items:
            if item.collected:
                continue
            v = self.visibility(item.x, item.y)
            if v < 0.06:
                continue
            x, y = self.to_screen(item.x, item.y)
            color = mix(INK, AMBER if item.kind == "recorder" else TEAL, max(0.25, v))
            if item.kind == "recorder":
                pygame.draw.rect(self.screen, color, (x - 11, y - 8, 22, 16), 2, border_radius=3)
                pygame.draw.circle(self.screen, color, (x - 5, y), 2)
                pygame.draw.circle(self.screen, color, (x + 5, y), 2)
                self.text("BLACK BOX", x - 35, y + 18, 15, color)
            else:
                pygame.draw.rect(self.screen, color, (x - 6, y - 12, 12, 24), 2, border_radius=5)
                pygame.draw.line(self.screen, color, (x - 4, y - 15), (x + 4, y - 15), 2)
                self.text("AIR", x - 10, y + 20, 15, color)
        for x, y, age in self.pulses:
            radius = int(age * 430)
            if radius < 660:
                p = self.to_screen(x, y)
                col = mix((3, 11, 16), TEAL, max(0, 1 - radius / 700) * 0.75)
                pygame.draw.circle(self.screen, col, p, max(1, radius), 2)
                if radius > 14:
                    pygame.draw.circle(self.screen, mix(INK, col, 0.3), p, radius - 14, 1)
        mx, my = self.to_screen(wr.monster_x, wr.monster_y)
        monster_dist = math.hypot(wr.monster_x - wr.player_x, wr.monster_y - wr.player_y)
        mv = self.visibility(wr.monster_x, wr.monster_y)
        if mv > 0.2 or monster_dist < 130:
            color = mix((11, 24, 29), RED, max(0.25, mv))
            a = math.atan2(wr.player_y - wr.monster_y, wr.player_x - wr.monster_x)
            points = []
            for i in range(12):
                b = a + i * math.tau / 12
                r = 21 if i % 2 == 0 else 11
                points.append((mx + math.cos(b) * r, my + math.sin(b) * r))
            pygame.draw.polygon(self.screen, (9, 14, 19), points)
            pygame.draw.lines(self.screen, color, True, points, 1)
            for side in (-1, 1):
                pygame.draw.circle(self.screen, RED, (int(mx + math.cos(a) * 8 + math.sin(a) * 5 * side), int(my + math.sin(a) * 8 - math.cos(a) * 5 * side)), 2)
        px, py = self.to_screen(wr.player_x, wr.player_y)
        a = self.heading
        nose = (px + math.cos(a) * 17, py + math.sin(a) * 17)
        pygame.draw.circle(self.screen, (30, 65, 67), (px, py), 22, 1)
        pygame.draw.circle(self.screen, TEAL, (px, py), 10, 2)
        pygame.draw.line(self.screen, WHITE, (px, py), nose, 3)
        # The lamp cone is a direction cue, not a flashing screen effect.
        for side in (-1, 1):
            edge = a + side * 0.5
            pygame.draw.line(self.screen, (32, 64, 66), nose, (px + math.cos(edge) * 85, py + math.sin(edge) * 85))
        self.screen.set_clip(None)
        self.text("VISUAL FEED  /  NACRE", VIEW.x + 18, VIEW.y + 16, 18, MUTED)
        self.text("2,840 M", VIEW.right - 90, VIEW.y + 16, 18, MUTED)
        item = wr.nearest_interactable()
        if item:
            prompt = "E  /  EXTRACT" if item.kind == "exit" and wr.collected == 3 else "E  /  DOCKING HATCH" if item.kind == "exit" else "E  /  RECOVER RECORDING" if item.kind == "recorder" else "E  /  EMERGENCY OXYGEN"
            box = pygame.Rect(VIEW.centerx - 175, VIEW.bottom - 56, 350, 35)
            self.panel(box, (13, 33, 37), TEAL)
            self.text(prompt, box.centerx, box.centery, 21, TEAL, True, True)
        if wr.threat > 0.6:
            self.text("MOVEMENT DETECTED", VIEW.centerx, VIEW.y + 55, 22, RED, True, True)
            pygame.draw.rect(self.screen, mix(LINE, RED, wr.threat * 0.65), VIEW, 2, border_radius=5)

    def minimap(self, rect):
        self.panel(rect, (6, 18, 24))
        scale = min((rect.w - 20) / len(self.world.grid[0]), (rect.h - 16) / len(self.world.grid))
        ox = rect.centerx - len(self.world.grid[0]) * scale / 2
        oy = rect.centery - len(self.world.grid) * scale / 2
        for gx, gy in self.discovered:
            if self.world.grid[gy][gx] == ".":
                pygame.draw.rect(self.screen, (40, 79, 80), (ox + gx * scale, oy + gy * scale, max(1, scale - 0.5), max(1, scale - 0.5)))
        ex, ey = self.world.exit_x / TILE, self.world.exit_y / TILE
        pygame.draw.circle(self.screen, TEAL, (int(ox + ex * scale), int(oy + ey * scale)), 3, 1)
        px, py = self.world.player_x / TILE, self.world.player_y / TILE
        pygame.draw.circle(self.screen, WHITE, (int(ox + px * scale), int(oy + py * scale)), 3)

    def hud(self):
        wr = self.world
        self.text("BELOW THE SIGNAL", 26, 29, 34, WHITE, True)
        self.text("RECOVERY OPERATION  /  RESEARCH VESSEL NACRE", 27, 70, 17, MUTED)
        self.text(f"DIVE  {int(wr.elapsed)//60:02}:{int(wr.elapsed)%60:02}", 803, 39, 23, TEAL)
        self.button("PAUSE  [ ESC ]", (1055, 27, 200, 49), "pause")
        self.panel((946, 110, 310, 606))
        self.text("LIFE SUPPORT", 968, 133, 18, MUTED)
        self.text(f"{max(0, wr.oxygen):05.1f}", 966, 160, 52, WHITE if wr.oxygen > 25 else RED, True)
        self.text("O2 %", 1105, 180, 21, MUTED)
        pygame.draw.rect(self.screen, (24, 45, 51), (970, 218, 262, 6), border_radius=3)
        pygame.draw.rect(self.screen, TEAL if wr.oxygen > 25 else RED, (970, 218, int(262 * max(0, min(100, wr.oxygen)) / 100), 6), border_radius=3)
        self.text("RECOVERY MANIFEST", 970, 248, 18, MUTED)
        for i in range(3):
            y = 282 + i * 36
            color = TEAL if i < wr.collected else (79, 105, 109)
            pygame.draw.rect(self.screen, color, (970, y, 16, 16), 1, border_radius=2)
            if i < wr.collected:
                pygame.draw.line(self.screen, TEAL, (973, y + 8), (977, y + 12), 2)
                pygame.draw.line(self.screen, TEAL, (977, y + 12), (984, y + 3), 2)
            self.text(f"RECORDING  0{i+1}", 1000, y - 1, 22, color)
        self.text("RETURN TO THE HATCH" if wr.collected == 3 else "RECOVER ALL THREE", 970, 399, 20, AMBER)
        self.text("ACOUSTIC CONTACT", 970, 440, 17, MUTED)
        threat = min(1, max(0, wr.threat))
        status = "CLOSE" if threat > 0.65 else "DISTURBED" if threat > 0.25 else "QUIET"
        self.text(status, 970, 464, 26, RED if threat > 0.65 else AMBER if threat > 0.25 else TEAL, True)
        for i in range(30):
            motion = 1 if self.settings["reduced_motion"] else 0.45 + 0.55 * abs(math.sin(i * 0.91 + self.time * 4))
            height = 3 + int(motion * (4 + threat * 25))
            pygame.draw.rect(self.screen, RED if threat > 0.65 else TEAL, (970 + i * 9, 520 - height / 2, 4, height), border_radius=1)
        self.minimap(pygame.Rect(968, 550, 266, 145))
        self.text("WASD MOVE   SHIFT SPRINT   E INTERACT   J JOURNAL", 27, 739, 18, MUTED)
        cooldown = max(0, wr.ping_cooldown)
        self.text(f"SONAR  {cooldown:.1f}s" if cooldown > 0 else "SPACE  /  SONAR READY", 690, 739, 19, AMBER if cooldown else TEAL)
        self.text("M  SOUND " + ("OFF" if self.settings["muted"] else "ON"), 1090, 741, 17, MUTED)
        if self.toast_time > 0:
            rect = pygame.Rect(47, 628, 853, 65)
            self.panel(rect, (10, 25, 31), LINE)
            self.wrap(self.toast, rect.x + 16, rect.y + 12, rect.w - 30, 21, AMBER, 2)

    def overlay(self):
        self.buttons.clear()
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 6, 12, 215))
        self.screen.blit(shade, (0, 0))
        if self.mode == "journal":
            self.panel((290, 80, 700, 650), PANEL)
            self.text("RECOVERED TRANSMISSIONS", 640, 127, 34, WHITE, True, True)
            for i, (title, story) in enumerate(LOGS):
                y = 194 + i * 140
                self.text(title if i < self.world.collected else f"0{i+1} / SIGNAL MISSING", 330, y, 23, TEAL if i < self.world.collected else MUTED, True)
                if i < self.world.collected:
                    self.wrap(story, 330, y + 35, 610, 24, WHITE, 6)
                else:
                    self.text("Recover this recording from inside the wreck.", 330, y + 38, 22, MUTED)
            self.button("RESUME DIVE  [ J / ESC ]", (425, 646, 430, 49), "resume", True)
        elif self.mode == "paused":
            self.panel((390, 120, 500, 570), PANEL)
            self.text("HOLDING POSITION", 640, 166, 37, WHITE, True, True)
            self.text("The dive is paused. Take a breath.", 640, 208, 23, MUTED, center=True)
            self.button("RESUME DIVE", (440, 252, 400, 52), "resume", True)
            self.button("SOUND " + ("OFF" if self.settings["muted"] else "ON"), (440, 320, 400, 45), "mute")
            self.button("REDUCED MOTION " + ("ON" if self.settings["reduced_motion"] else "OFF"), (440, 378, 400, 45), "motion")
            self.button("TOGGLE FULLSCREEN", (440, 436, 400, 45), "fullscreen")
            self.button("ABANDON DIVE / TITLE", (440, 508, 400, 45), "title")
            self.button("QUIT GAME", (440, 566, 400, 45), "quit")
            self.text("Move away after a ping. It follows the sound.", 640, 652, 21, AMBER, center=True)
        else:
            won = self.mode == "won"
            self.text("RECOVERY COMPLETE" if won else "SIGNAL LOST", 640, 225, 66, TEAL if won else RED, True, True)
            reason = getattr(self.world, "death_reason", "")
            message = "You reach the surface with all three recordings. From inside the sealed black box, someone knocks. Three times." if won else "Your last breath disappears into the water. The wreck keeps its secrets." if reason == "oxygen" else "The knocking stops. Something takes hold of your tether. The surface never hears your last transmission."
            self.wrap(message, 365, 294, 550, 26, WHITE, 7)
            self.text(f"{self.world.collected}/3 RECORDINGS     {int(self.world.elapsed)//60:02}:{int(self.world.elapsed)%60:02} SUBMERGED     {self.pings} PINGS", 640, 423, 21, MUTED, center=True)
            if not won:
                self.text("Ping, relocate quietly, and use loops to break contact.", 640, 466, 23, AMBER, center=True)
            self.button("DIVE AGAIN  [ ENTER ]", (410, 528, 460, 56), "retry", True)
            self.button("RETURN TO TITLE", (410, 603, 220, 45), "title")
            self.button("QUIT", (650, 603, 220, 45), "quit")

    def render(self):
        self.buttons.clear()
        self.background()
        if self.mode == "title":
            self.title()
        else:
            self.world_view()
            self.hud()
            if self.mode != "playing":
                self.overlay()
        self.screen.blit(self.noise, (0, 0))
        dw, dh = self.display.get_size()
        scale = min(dw / W, dh / H)
        target = (max(1, int(W * scale)), max(1, int(H * scale)))
        self.display.fill((0, 0, 0))
        output = self.screen if target == (W, H) else pygame.transform.smoothscale(self.screen, target)
        self.display.blit(output, ((dw - target[0]) // 2, (dh - target[1]) // 2))
        pygame.display.flip()

    def run(self, frames=None):
        count = 0
        self.render()
        while self.running:
            dt = min(self.clock.tick(60) / 1000, 0.05)
            self.input()
            # Pause is deliberately an ordinary UI action so mouse and keyboard agree.
            self.update(dt)
            self.render()
            count += 1
            if frames and count >= frames:
                break
        self.audio.shutdown()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Below the Signal — a short sonar horror game")
    parser.add_argument("--smoke-test", action="store_true", help="Render representative states, then exit")
    parser.add_argument("--screenshots", type=Path, help="Save title, gameplay, pause and ending PNGs")
    args = parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    game = Game(headless=args.smoke_test)
    if args.smoke_test or args.screenshots:
        folder = args.screenshots
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
        for mode in ("title", "playing", "paused", "journal", "won", "lost"):
            if mode == "playing":
                game.start()
                game.world.ping()
                game.pulses.append([game.world.player_x, game.world.player_y, 0.0])
                for _ in range(100):
                    game.update(1 / 60)
            game.mode = mode
            game.render()
            if folder:
                pygame.image.save(game.screen, folder / ("screenshot.png" if mode == "playing" else f"{mode}.png"))
        game.audio.shutdown()
        pygame.quit()
        print("PASS: title, gameplay, pause, victory and loss rendered.")
        return
    game.run()


if __name__ == "__main__":
    main()
