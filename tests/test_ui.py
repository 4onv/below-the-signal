"""Exercise real UI input, simulation, and audio using SDL's dummy devices."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from main import Game
from model import PING_COOLDOWN


class GameIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Patch per test rather than setting module-wide SDL variables: callers
        # that subsequently open the actual game must retain their own drivers.
        environment = mock.patch.dict(os.environ, {
            "SDL_VIDEODRIVER": "dummy",
            "SDL_AUDIODRIVER": "dummy",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        pygame.quit()
        self.addCleanup(pygame.quit)
        self.game = Game(headless=True)
        self.game.settings_path = Path(self.scratch.name) / "progress.json"
        pygame.event.clear()

    def tearDown(self):
        try:
            self.game.audio.shutdown()
        finally:
            pygame.quit()

    def press(self, key):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        self.game.input()

    def start(self):
        self.press(pygame.K_RETURN)
        self.assertEqual(self.game.mode, "playing")
        self.assertEqual(self.game.world.state, "playing")

    def recover_recorders(self):
        # Movement/pathfinding is covered by the model's complete-run replay.
        # Here real nearby objects exercise the E-key -> interact -> journal path.
        for item in self.game.world.items:
            if item.kind == "recorder":
                self.game.world.player_x, self.game.world.player_y = item.x, item.y
                self.press(pygame.K_e)

    def test_enter_starts_a_renderable_new_dive(self):
        self.assertEqual(self.game.mode, "title")
        self.assertIsNone(self.game.world)
        self.game.render()
        self.start()
        self.game.render()
        self.assertEqual(self.game.world.oxygen, 100)
        self.assertEqual(self.game.world.collected, 0)
        self.assertEqual(self.game.world.elapsed, 0)

    def test_space_sends_sonar_and_respects_cooldown(self):
        self.start()
        self.press(pygame.K_SPACE)
        self.assertEqual(self.game.pings, 1)
        self.assertEqual(len(self.game.pulses), 1)
        self.assertGreater(self.game.world.ping_cooldown, 0)
        self.press(pygame.K_SPACE)
        self.assertEqual(self.game.pings, 1)
        self.assertEqual(len(self.game.pulses), 1)
        self.game.update(PING_COOLDOWN + 0.01)
        self.press(pygame.K_SPACE)
        self.assertEqual(self.game.pings, 2)
        self.game.render()

    def test_e_recovers_a_real_recorder_once_and_adds_its_journal_entry(self):
        self.start()
        item = next(item for item in self.game.world.items if item.kind == "recorder")
        self.game.world.player_x, self.game.world.player_y = item.x, item.y
        self.press(pygame.K_e)
        self.game.update(0)
        self.assertTrue(item.collected)
        self.assertEqual(self.game.world.collected, 1)
        self.assertEqual(len(self.game.logs), 1)
        self.assertIn("THE KNOCK", self.game.logs[0][0])
        self.assertEqual(self.game.toast, self.game.logs[0][1])
        self.press(pygame.K_e)
        self.assertEqual(self.game.world.collected, 1)
        self.assertEqual(len(self.game.logs), 1)

    def test_escape_freezes_simulation_and_resuming_advances_it(self):
        self.start()
        self.game.update(0.25)
        before = self.game.world.oxygen, self.game.world.elapsed
        self.press(pygame.K_ESCAPE)
        self.assertEqual(self.game.mode, "paused")
        self.press(pygame.K_SPACE)
        self.game.update(2.0)
        self.game.render()
        self.assertEqual((self.game.world.oxygen, self.game.world.elapsed), before)
        self.assertEqual(self.game.pings, 0)
        self.press(pygame.K_ESCAPE)
        self.assertEqual(self.game.mode, "playing")
        self.game.update(0.25)
        self.assertLess(self.game.world.oxygen, before[0])
        self.assertGreater(self.game.world.elapsed, before[1])

    def test_m_toggles_actual_audio_without_writing_headless_settings(self):
        self.assertTrue(self.game.audio.enabled)
        self.press(pygame.K_m)
        self.assertTrue(self.game.settings["muted"])
        self.assertTrue(self.game.audio.muted)
        self.assertFalse(self.game.settings_path.exists())
        self.press(pygame.K_m)
        self.assertFalse(self.game.settings["muted"])
        self.assertFalse(self.game.audio.muted)

    def test_journal_pauses_the_dive_and_j_resumes(self):
        self.start()
        self.game.update(0.25)
        before = self.game.world.oxygen, self.game.world.elapsed
        self.press(pygame.K_j)
        self.assertEqual(self.game.mode, "journal")
        self.game.update(2.0)
        self.game.render()
        self.assertEqual((self.game.world.oxygen, self.game.world.elapsed), before)
        self.press(pygame.K_j)
        self.assertEqual(self.game.mode, "playing")
        self.game.update(0.25)
        self.assertGreater(self.game.world.elapsed, before[1])

    def test_journal_overlay_blocks_clicks_on_the_underlying_pause_button(self):
        self.start()
        self.game.render()
        pause_rect = next(rect for rect, action in self.game.buttons if action == "pause")
        self.press(pygame.K_j)
        self.game.render()
        with mock.patch("pygame.mouse.get_pos", return_value=pause_rect.center):
            pygame.event.post(pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=pause_rect.center))
            self.game.input()
        self.assertEqual(self.game.mode, "journal")

    def test_enter_after_real_loss_resets_mission_and_session_ui(self):
        self.start()
        self.press(pygame.K_SPACE)
        self.game.update(0.1)
        self.recover_recorders()
        old_world = self.game.world
        old_world.oxygen = 0.01
        self.game.update(0.25)
        self.assertEqual(self.game.mode, "lost")
        self.game.render()
        self.press(pygame.K_RETURN)
        self.assertEqual(self.game.mode, "playing")
        self.assertIsNot(self.game.world, old_world)
        self.assertEqual(self.game.world.oxygen, 100)
        self.assertEqual(self.game.world.elapsed, 0)
        self.assertEqual(self.game.world.collected, 0)
        self.assertEqual(self.game.world.ping_cooldown, 0)
        self.assertEqual(self.game.pings, 0)
        for collection in (self.game.logs, self.game.pulses,
                           self.game.discovered, self.game.revealed):
            self.assertFalse(collection)

    def test_actual_extraction_shows_victory_and_records_progress_only_in_memory(self):
        self.start()
        self.game.update(0.25)
        self.recover_recorders()
        self.assertEqual(self.game.world.collected, 3)
        self.assertEqual(len(self.game.logs), 3)
        self.game.world.player_x = self.game.world.exit_x
        self.game.world.player_y = self.game.world.exit_y
        self.press(pygame.K_e)
        self.assertEqual(self.game.world.state, "won")
        self.game.update(0)
        self.game.render()
        self.assertEqual(self.game.mode, "won")
        self.assertEqual(self.game.settings["completed"], 1)
        self.assertEqual(self.game.settings["best_time"], self.game.world.elapsed)
        self.assertFalse(self.game.settings_path.exists())
        self.game.update(2.0)
        self.assertEqual(self.game.settings["completed"], 1)
        self.assertEqual(self.game.settings["best_time"], self.game.world.elapsed)


if __name__ == "__main__":
    unittest.main()
