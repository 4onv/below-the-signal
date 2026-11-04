"""Small, asset-free underwater soundscape for BELOW THE SIGNAL.

Every sample is synthesized once at startup. A missing audio device simply
disables sound, so headphones and an available mixer are never prerequisites.
"""

from array import array
import math
import random

import pygame


_TAU = math.tau


class SoundEngine:
    """Own a quiet ambient loop and a handful of reusable procedural effects."""

    _ALIASES = {
        "ping": "sonar",
        "recorder": "pickup",
        "oxygen": "air",
        "won": "win",
        "lost": "hit",
    }

    def __init__(self):
        self.enabled = False
        self.muted = False
        self._owns_mixer = False
        self._sounds = {}
        self._channels = []
        self._clock = 0.0
        self._warning_at = -10.0
        self._heartbeat_in = 0.35
        self._ambient_level = 0.0
        self._heartbeat_level = 0.0
        try:
            mixer_state = pygame.mixer.get_init()
            if mixer_state is None:
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
                self._owns_mixer = True
                mixer_state = pygame.mixer.get_init()
            if mixer_state is None or mixer_state[1:] != (-16, 2):
                return
            self._rate = mixer_state[0]
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            pygame.mixer.set_reserved(4)
            self._channels = [pygame.mixer.Channel(i) for i in range(4)]
            for channel in self._channels:
                channel.set_volume(0.0)
            self._build_sounds()
            self._channels[0].play(self._sounds["bed"], loops=-1)
            self.enabled = True
            self._apply_volume()
        except (pygame.error, OSError, NotImplementedError):
            self.shutdown()

    def _sample(self, duration, synth, source_rate=4410):
        """Render low-bandwidth synthesis into the mixer's signed-16 format.

        These underwater tones stay below 1 kHz. Generating a modest number of
        source samples and holding each for a few output frames keeps startup
        quick without a NumPy dependency; the restrained bandwidth also suits
        the deliberately muffled soundscape.
        """
        samples = array("h")
        count = max(1, int(self._rate * duration))
        stride = max(1, self._rate // source_rate)
        for index in range(0, count, stride):
            left, right = synth(index / self._rate)
            # All synth voices below have deliberately bounded amplitudes.
            frame = [int(left * 32767), int(right * 32767)]
            samples.extend(frame * min(stride, count - index))
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _build_sounds(self):
        rng = random.Random(4619)
        filtered = [0.0, 0.0]

        def bed(t):
            # Integer numbers of tonal cycles fit inside this four-second loop.
            filtered[0] += 0.035 * (rng.uniform(-1, 1) - filtered[0])
            filtered[1] += 0.035 * (rng.uniform(-1, 1) - filtered[1])
            edge = min(1.0, t / 0.06, (4.0 - t) / 0.06)
            breath = 0.8 + 0.2 * math.cos(_TAU * 0.25 * t)
            low = 0.23 * math.sin(_TAU * 34 * t)
            mid = 0.10 * math.sin(_TAU * 57 * t)
            left = low + mid + 0.055 * math.sin(_TAU * 91 * t)
            right = low + mid + 0.055 * math.sin(_TAU * 91 * t + 0.6)
            return (
                edge * breath * (left + 0.35 * filtered[0]),
                edge * breath * (right + 0.35 * filtered[1]),
            )

        def sonar(t):
            value = 0.0
            for start, gain in ((0.0, 0.45), (0.29, 0.17), (0.59, 0.07)):
                age = t - start
                if age >= 0.0:
                    attack = min(1.0, age / 0.008)
                    phase = _TAU * (930 * age - 130 * age * age)
                    value += gain * attack * math.exp(-7.5 * age) * math.sin(phase)
            return value, value * 0.94

        def pickup(t):
            value = 0.0
            for start, frequency in ((0.0, 440.0), (0.12, 659.25)):
                age = t - start
                if age >= 0.0:
                    value += 0.34 * min(1.0, age / 0.012) * math.exp(-11 * age) * math.sin(_TAU * frequency * age)
            return value, value

        air_noise = [0.0]

        def air(t):
            air_noise[0] += 0.14 * (rng.uniform(-1, 1) - air_noise[0])
            envelope = math.sin(math.pi * t / 0.9) ** 2
            value = envelope * (0.45 * air_noise[0] + 0.10 * math.sin(_TAU * (150 * t + 50 * t * t)))
            return value, value

        def warning(t):
            value = 0.0
            for start in (0.0, 0.26):
                age = t - start
                if 0.0 <= age < 0.19:
                    envelope = math.sin(math.pi * age / 0.19) ** 2
                    value += 0.32 * envelope * math.sin(_TAU * (260 * age - 90 * age * age))
            return value, value

        impact_noise = [0.0]

        def hit(t):
            impact_noise[0] += 0.08 * (rng.uniform(-1, 1) - impact_noise[0])
            envelope = min(1.0, t / 0.012) * math.exp(-12 * t)
            value = envelope * (0.35 * math.sin(_TAU * 64 * t) + 0.55 * impact_noise[0])
            return value, value

        def win(t):
            value = 0.0
            for start, frequency in ((0.0, 220), (0.18, 277.18), (0.36, 329.63)):
                age = t - start
                if age >= 0.0:
                    value += 0.20 * min(1.0, age / 0.03) * math.exp(-3.6 * age) * math.sin(_TAU * frequency * age)
            tail = min(1.0, (1.5 - t) / 0.06)
            return value * tail, value * tail

        def ui(t):
            value = 0.26 * math.sin(math.pi * t / 0.065) ** 2 * math.sin(_TAU * 560 * t)
            return value, value

        def heartbeat(t):
            value = 0.0
            for start, gain in ((0.0, 0.45), (0.18, 0.28)):
                age = t - start
                if 0.0 <= age < 0.19:
                    envelope = math.sin(math.pi * age / 0.19) ** 2
                    value += gain * envelope * math.sin(_TAU * 57 * age)
            return value, value

        for name, duration, synth in (
            ("bed", 4.0, bed),
            ("sonar", 1.3, sonar),
            ("pickup", 0.65, pickup),
            ("air", 0.9, air),
            ("warning", 0.5, warning),
            ("hit", 0.55, hit),
            ("win", 1.5, win),
            ("ui", 0.065, ui),
            ("heartbeat", 0.42, heartbeat),
        ):
            self._sounds[name] = self._sample(duration, synth, 1400 if name == "bed" else 4410)

    def _apply_volume(self):
        if not self.enabled:
            return
        gain = 0.0 if self.muted else 1.0
        self._channels[0].set_volume(self._ambient_level * gain)
        self._channels[1].set_volume(self._heartbeat_level * gain)
        self._channels[2].set_volume(0.30 * gain)
        self._channels[3].set_volume(0.30 * gain)

    def update(self, dt, threat, oxygen, playing):
        """Blend ambience and pulse rate; threat is 0..1 and oxygen is 0..100."""
        if not self.enabled:
            return
        dt = max(0.0, min(float(dt), 0.25))
        self._clock += dt
        threat = max(0.0, min(1.0, float(threat)))
        oxygen = max(0.0, min(100.0, float(oxygen)))
        stress = max(threat, max(0.0, (30.0 - oxygen) / 30.0))
        target = 0.19 + 0.13 * stress if playing else 0.0
        self._ambient_level += (target - self._ambient_level) * (1.0 - math.exp(-2.0 * dt))
        self._heartbeat_level = 0.13 + 0.20 * stress if playing else 0.0
        try:
            if playing and stress > 0.35:
                self._heartbeat_in -= dt
                if self._heartbeat_in <= 0.0:
                    self._channels[1].play(self._sounds["heartbeat"])
                    self._heartbeat_in = 1.15 - 0.55 * stress
            else:
                self._heartbeat_in = 0.35
                if not playing:
                    self._channels[1].stop()
            self._apply_volume()
        except pygame.error:
            self.shutdown()

    def play(self, event_name):
        """Play a named cue; unknown names are deliberately harmless."""
        if not self.enabled:
            return
        name = self._ALIASES.get(event_name, event_name)
        if name not in self._sounds or name in ("bed", "heartbeat"):
            return
        if name == "warning":
            if self._clock - self._warning_at < 1.5:
                return
            self._warning_at = self._clock
        try:
            channel = self._channels[2 if name == "sonar" else 3]
            channel.play(self._sounds[name])
        except pygame.error:
            self.shutdown()

    def set_muted(self, muted):
        self.muted = bool(muted)
        try:
            self._apply_volume()
        except pygame.error:
            self.shutdown()

    def shutdown(self):
        """Stop this engine's channels. Safe before/after pygame.quit()."""
        self.enabled = False
        try:
            if pygame.mixer.get_init() is not None:
                for channel in self._channels:
                    channel.stop()
                if self._owns_mixer:
                    pygame.mixer.quit()
        except (pygame.error, OSError, NotImplementedError):
            pass
        self._channels.clear()
        self._sounds.clear()
