"""Architecture-independent, reproducible sampling and open-loop arrival schedules."""
from __future__ import annotations

import math
import random

from .contracts import Event, digest


def select_tasks(task_ids, count, seed):
    ids = sorted(task_ids)
    if len(set(ids)) != len(ids) or not 0 < count <= len(ids):
        raise ValueError("Unique task ids and an available positive sample count are required")
    # Random keys avoid dependence on input order; persist the resulting manifest regardless.
    return sorted(ids, key=lambda task: digest({"seed": seed, "task": task}))[:count]


def schedule(tasks, *, seed=0, mode="burst", burst_size=4, interval_s=60.0, rate_per_s=None):
    if not tasks or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Workloads need a nonempty unique task set")
    if type(burst_size) is not int or burst_size <= 0 or not math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("Burst size and interval must be positive")
    if mode not in {"burst", "poisson", "fixed"}:
        raise ValueError("Use burst, poisson or fixed open-loop arrivals")
    if mode == "poisson" and (rate_per_s is None or not math.isfinite(rate_per_s) or rate_per_s <= 0):
        raise ValueError("Poisson arrivals require a positive rate")
    rng = random.Random(seed)
    ordered = list(tasks)
    rng.shuffle(ordered)
    arrival = 0.0
    events = []
    for i, task in enumerate(ordered):
        if mode == "burst":
            arrival = (i // burst_size) * interval_s
        elif mode == "fixed":
            arrival = i * interval_s
        elif i:
            arrival += rng.expovariate(rate_per_s)
        events.append(Event(id="request:" + task["id"], thread="task:" + task["id"], text=task["instruction"],
                            task_id=task["id"], arrival_s=arrival))
    return {"schema_version": 1, "mode": mode, "seed": seed, "events": [e.__dict__ for e in events]}
