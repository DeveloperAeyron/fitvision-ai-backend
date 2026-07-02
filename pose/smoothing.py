from __future__ import annotations

import math

import numpy as np


class OneEuroFilter:
    # One-Euro filter (Casiez et al.): low lag on fast motion, low jitter when
    # still, by making the cutoff frequency adapt to the signal's speed.
    def __init__(self, freq: float, min_cutoff: float = 1.0, beta: float = 0.3,
                 d_cutoff: float = 1.0):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev = None
        self._dx_prev = None

    def _alpha(self, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        if self._x_prev is None:
            self._x_prev = x
            self._dx_prev = np.zeros_like(x)
            return x

        dx = (x - self._x_prev) * self.freq
        a_d = self._alpha(self.d_cutoff)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        a = self._alpha_array(cutoff)
        x_hat = a * x + (1 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        return x_hat

    def _alpha_array(self, cutoff: np.ndarray) -> np.ndarray:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)


class LandmarkSmoother:
    def __init__(self, freq: float):
        self._filter = OneEuroFilter(freq, min_cutoff=1.0, beta=0.3)

    def apply(self, landmarks: np.ndarray) -> np.ndarray:
        smoothed = landmarks.copy()
        smoothed[:, :2] = self._filter(landmarks[:, :2])
        return smoothed
