from __future__ import annotations

from typing import List

import numpy as np
import tensorflow as tf


class TFLiteModel:
    def __init__(self, model_path: str, num_threads: int = 4):
        self.interpreter = tf.lite.Interpreter(
            model_path=model_path, num_threads=num_threads
        )
        self.interpreter.allocate_tensors()
        self._input = self.interpreter.get_input_details()[0]
        self._outputs = self.interpreter.get_output_details()

    @property
    def input_shape(self):
        return self._input["shape"]

    def infer(self, input_tensor: np.ndarray) -> List[np.ndarray]:
        self.interpreter.set_tensor(self._input["index"], input_tensor)
        self.interpreter.invoke()
        return [self.interpreter.get_tensor(o["index"]) for o in self._outputs]

    def output_by_last_dim(self, tensors, last_dim, ndim=None):
        # Select an output by its trailing dim so decoding survives output reordering.
        for t, meta in zip(tensors, self._outputs):
            if meta["shape"][-1] == last_dim and (ndim is None or t.ndim == ndim):
                return t
        raise ValueError(
            f"No output tensor with last dim {last_dim} (ndim={ndim}); "
            f"available shapes: {[list(m['shape']) for m in self._outputs]}"
        )
