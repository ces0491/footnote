"""Fitting by L-BFGS, for training only: multinomial logistic regression and a small network.

The services don't import this module; they read the fitted parameters (difficulty.py, state.py)
and evaluate them with numpy. scipy is a development dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class Fitted:
    mean: np.ndarray  # (features,) subtracted before scaling
    scale: np.ndarray  # (features,)
    coef: np.ndarray  # (features, classes)
    intercept: np.ndarray  # (classes,)
    iterations: int

    def logits(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.scale) @ self.coef + self.intercept

    def proba(self, x: np.ndarray) -> np.ndarray:
        z = self.logits(x)
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def softmax_regression(x: np.ndarray, y: np.ndarray, classes: int, l2: float, max_iter: int = 1000) -> Fitted:
    """Minimise the mean cross-entropy of a softmax over standardised x, plus l2/2 times the squared
    weights (intercepts unpenalised)."""
    x = np.asarray(x, dtype=np.float64)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    z = (x - mean) / scale
    n, d = z.shape
    onehot = np.zeros((n, classes))
    onehot[np.arange(n), y] = 1.0

    def loss(theta: np.ndarray) -> tuple[float, np.ndarray]:
        w = theta[: d * classes].reshape(d, classes)
        b = theta[d * classes :]
        logits = z @ w + b
        logits -= logits.max(axis=1, keepdims=True)
        log_p = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
        value = -float((onehot * log_p).sum()) / n + 0.5 * l2 * float((w**2).sum())
        g = (np.exp(log_p) - onehot) / n
        grad = np.concatenate([(z.T @ g + l2 * w).ravel(), g.sum(axis=0)])
        return value, grad

    result = minimize(loss, np.zeros(d * classes + classes), jac=True, method="L-BFGS-B", options={"maxiter": max_iter})
    theta = result.x
    return Fitted(
        mean=mean,
        scale=scale,
        coef=theta[: d * classes].reshape(d, classes),
        intercept=theta[d * classes :],
        iterations=int(result.nit),
    )


@dataclass(frozen=True)
class FittedNetwork:
    """A softmax over one hidden layer of tanh units."""

    mean: np.ndarray
    scale: np.ndarray
    hidden: np.ndarray  # (features, units)
    hidden_bias: np.ndarray  # (units,)
    coef: np.ndarray  # (units, classes)
    intercept: np.ndarray  # (classes,)
    iterations: int

    def proba(self, x: np.ndarray) -> np.ndarray:
        h = np.tanh(((x - self.mean) / self.scale) @ self.hidden + self.hidden_bias)
        z = h @ self.coef + self.intercept
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def softmax_network(
    x: np.ndarray, y: np.ndarray, classes: int, units: int, l2: float, max_iter: int = 400, seed: int = 0
) -> FittedNetwork:
    """Minimise the mean cross-entropy of a one-hidden-layer tanh network over standardised x, plus
    l2/2 times the squared weights (biases unpenalised). Seeded, so a refit gives the same network."""
    x = np.asarray(x, dtype=np.float64)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    z = (x - mean) / scale
    n, d = z.shape
    onehot = np.zeros((n, classes))
    onehot[np.arange(n), y] = 1.0
    sizes = [(d, units), (units,), (units, classes), (classes,)]
    bounds = np.cumsum([0] + [int(np.prod(s)) for s in sizes])

    def unpack(theta: np.ndarray) -> list[np.ndarray]:
        return [theta[bounds[i] : bounds[i + 1]].reshape(s) for i, s in enumerate(sizes)]

    def loss(theta: np.ndarray) -> tuple[float, np.ndarray]:
        w1, b1, w2, b2 = unpack(theta)
        h = np.tanh(z @ w1 + b1)
        logits = h @ w2 + b2
        logits -= logits.max(axis=1, keepdims=True)
        log_p = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
        value = -float((onehot * log_p).sum()) / n + 0.5 * l2 * (float((w1**2).sum()) + float((w2**2).sum()))
        g = (np.exp(log_p) - onehot) / n
        gh = (g @ w2.T) * (1.0 - h**2)
        grads = [z.T @ gh + l2 * w1, gh.sum(axis=0), h.T @ g + l2 * w2, g.sum(axis=0)]
        return value, np.concatenate([gr.ravel() for gr in grads])

    rng = np.random.default_rng(seed)
    start = np.concatenate(
        [
            rng.normal(0.0, 1.0 / np.sqrt(d), d * units),
            np.zeros(units),
            rng.normal(0.0, 1.0 / np.sqrt(units), units * classes),
            np.zeros(classes),
        ]
    )
    result = minimize(loss, start, jac=True, method="L-BFGS-B", options={"maxiter": max_iter})
    w1, b1, w2, b2 = unpack(result.x)
    return FittedNetwork(mean, scale, w1, b1, w2, b2, int(result.nit))


def binary_logistic(x: np.ndarray, y: np.ndarray, l2: float, max_iter: int = 1000) -> Fitted:
    """A two-class fit reported as one column: the log-odds of y = 1."""
    two = softmax_regression(x, y.astype(np.int64), 2, l2, max_iter)
    return Fitted(
        mean=two.mean,
        scale=two.scale,
        coef=(two.coef[:, 1] - two.coef[:, 0])[:, None],
        intercept=np.array([two.intercept[1] - two.intercept[0]]),
        iterations=two.iterations,
    )
