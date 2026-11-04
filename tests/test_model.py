"""Game-rule tests; no display, audio device, or third-party packages needed."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import PING_COOLDOWN, PLAYER_SPEED, TILE, World


class WorldTests(unittest.TestCase):
    def test_all_floor_and_objectives_connected_to_exit(self):
        world = World()
        start = int(world.exit_x // TILE), int(world.exit_y // TILE)
        for y, row in enumerate(world.grid):
            for x, cell in enumerate(row):
                if cell == ".":
                    self.assertTrue(world.path(start, (x, y)), (x, y))
        for item in world.items:
            self.assertTrue(world.can_occupy(item.x, item.y, world.player_radius))

    def test_player_cannot_tunnel_through_walls_even_at_low_fps(self):
        world = World()
        world.update(4.0, -1, 0, sprint=True)
        self.assertGreaterEqual(world.player_x, 2 * TILE + world.player_radius)
        self.assertTrue(world.can_occupy(world.player_x, world.player_y,
                                       world.player_radius))

    def test_diagonal_movement_has_same_speed(self):
        straight, diagonal = World(), World()
        sx, sy = straight.player_x, straight.player_y
        straight.update(0.25, 1, 0)
        diagonal.update(0.25, 1, 1)
        self.assertAlmostEqual(math.hypot(straight.player_x - sx, straight.player_y - sy),
                               math.hypot(diagonal.player_x - sx, diagonal.player_y - sy))

    def test_sonar_cooldown_and_fixed_last_heard_position(self):
        world = World()
        self.assertTrue(world.ping())
        heard = world.last_ping
        self.assertFalse(world.ping())
        world.update(PING_COOLDOWN + 0.01, 1, 0)
        self.assertEqual(world.last_ping, heard)
        self.assertEqual(world._target, heard)
        self.assertTrue(world.ping())
        self.assertEqual(world.pop_events(), ["ping", "ping"])
        self.assertEqual(world.pop_events(), [])

    def test_monster_paths_through_corridors_without_crossing_walls(self):
        world = World()
        world.monster_awake = True
        world._hear(world.player_x, world.player_y, 120)
        start = world.monster_x, world.monster_y
        for _ in range(1200):
            world.update(1 / 60)
            self.assertTrue(world.can_occupy(world.monster_x, world.monster_y,
                                           world.monster_radius))
        self.assertGreater(math.dist(start, (world.monster_x, world.monster_y)), 100)
        self.assertEqual(world.state, "playing")

    def test_monster_cannot_see_or_grab_player_through_wall(self):
        world = World()
        world.monster_x, world.monster_y = (15.5 * TILE, 10.5 * TILE)
        world.player_x, world.player_y = (15.5 * TILE, 13.5 * TILE)
        world.monster_awake = True
        self.assertFalse(world.line_of_sight(world.monster_x, world.monster_y,
                                            world.player_x, world.player_y))
        world.update(0.1)
        self.assertNotEqual(world.monster_mode, "hunt")
        self.assertEqual(world.state, "playing")

    def test_monster_reaches_visible_player_between_tile_centers(self):
        world = World()
        world.player_x, world.player_y = (4.9 * TILE, 4.9 * TILE)
        world.monster_x, world.monster_y = (3.5 * TILE, 4.5 * TILE)
        world.monster_awake = True
        world.update(2)
        self.assertEqual((world.state, world.death_reason), ("lost", "creature"))

    def test_all_three_recorders_required_then_airlock_wins(self):
        world = World()
        self.assertIn("0/3", world.interact())
        self.assertEqual(world.state, "playing")
        for item in world.items:
            if item.kind == "recorder":
                world.player_x, world.player_y = item.x, item.y
                self.assertIn("RECORDER", world.interact())
                self.assertTrue(item.collected)
                self.assertIsNone(world.interact())
        self.assertEqual(world.collected, 3)
        self.assertEqual(world.stage, 3)
        world.player_x, world.player_y = world.exit_x, world.exit_y
        self.assertIn("AIRLOCK SEALED", world.interact())
        self.assertEqual(world.state, "won")
        oxygen = world.oxygen
        world.update(10, 1, 1, True)
        self.assertEqual(world.oxygen, oxygen)
        self.assertFalse(world.ping())

    def test_oxygen_pickup_is_preserved_when_full_and_consumed_once(self):
        world = World()
        tank = next(item for item in world.items if item.kind == "oxygen")
        world.player_x, world.player_y = tank.x, tank.y
        world.interact()
        self.assertFalse(tank.collected)
        world.oxygen = 84
        world.interact()
        self.assertTrue(tank.collected)
        self.assertEqual(world.oxygen, 100)
        self.assertIsNone(world.interact())

    def test_oxygen_and_creature_can_end_run(self):
        world = World()
        world.oxygen = 0.1
        world.update(1)
        self.assertEqual((world.state, world.death_reason), ("lost", "oxygen"))
        self.assertEqual(world.pop_events().count("lost"), 1)
        world = World()
        world.monster_awake = True
        world.monster_x, world.monster_y = world.player_x, world.player_y
        world.update(0.01)
        self.assertEqual((world.state, world.death_reason), ("lost", "creature"))

    def test_sprinting_costs_more_oxygen(self):
        quiet, fast = World(), World()
        quiet.update(1, 1, 0)
        fast.update(1, 1, 0, sprint=True)
        self.assertAlmostEqual(quiet.oxygen, 99.72)
        self.assertAlmostEqual(fast.oxygen, 99.60)

    def test_complete_run_by_movement_and_sonar_without_teleporting(self):
        world = World()
        # Leave the bridge through its western entrance, using the central
        # loop to avoid walking back toward the creature investigating it.
        # This is a genuine movement replay, not position/state assignment.
        waypoints = [(34, 3, "bridge"), (28, 3, None), (28, 5, None),
                     (17, 5, None), (17, 13, None), (18, 22, None),
                     (27, 23, None), (34, 24, "hold"), (27, 24, None),
                     (27, 22, None), (18, 22, None), (3, 24, "pump"),
                     (5, 18, None), (5, 5, None), (3, 3, "airlock")]
        next_ping, pings = 0, 0
        for tx, ty, identity in waypoints:
            start = int(world.player_x // TILE), int(world.player_y // TILE)
            route = world.path(start, (tx, ty))
            self.assertTrue(route)
            for x, y in route:
                gx, gy = (x + 0.5) * TILE, (y + 0.5) * TILE
                for _ in range(150):
                    dx, dy = gx - world.player_x, gy - world.player_y
                    distance = math.hypot(dx, dy)
                    if distance < 0.01:
                        break
                    if world.elapsed >= next_ping:
                        self.assertTrue(world.ping())
                        pings += 1
                        next_ping = world.elapsed + 12
                    world.update(min(0.05, distance / PLAYER_SPEED),
                                 dx / distance, dy / distance)
                    self.assertEqual(world.state, "playing")
                self.assertLess(math.hypot(gx - world.player_x, gy - world.player_y), 0.01)
            if identity:
                self.assertEqual(world.nearest_interactable().id, identity)
                world.interact()
        self.assertEqual(world.state, "won")
        self.assertEqual(world.collected, 3)
        self.assertGreaterEqual(pings, 5)
        self.assertGreater(world.oxygen, 0)
        self.assertLess(world.elapsed, 90)


if __name__ == "__main__":
    unittest.main()
