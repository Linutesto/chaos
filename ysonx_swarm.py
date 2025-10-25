#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSON-X Swarm Runtime (synthetic evolution demo)
Autonomous fractal agent spawning and mutation.
Author: Architecte du Chaos (ported)
License: Experimental Chaos License
"""

from __future__ import annotations

import argparse
import hashlib
import random
import time
from datetime import datetime
from pathlib import Path

from ysonx_cli import entropy_activation, reflexive_bias_shift, mutate_ysonx


class FractalAgent:
    def __init__(self, path: str, parent: 'FractalAgent' | None = None, generation: int = 0):
        self.path = path
        self.parent = parent
        self.generation = generation
        self.entropy = 0.0
        self.bias = 0.0
        self.id = f"{Path(path).stem}-G{generation}-{hashlib.md5(path.encode()).hexdigest()[:6]}"
        self.children: list[FractalAgent] = []

    def analyze(self) -> None:
        text = Path(self.path).read_text(encoding="utf-8")
        self.entropy = entropy_activation(text)
        self.bias = reflexive_bias_shift(self.entropy)

    def mutate(self) -> str:
        text = Path(self.path).read_text(encoding="utf-8")
        mutated = mutate_ysonx(text, self.entropy)
        out = f"{self.path}.{self.id}.mutated.ysonx"
        Path(out).write_text(mutated, encoding="utf-8")
        return out

    def spawn_child(self) -> 'FractalAgent':
        mutated_path = self.mutate()
        child = FractalAgent(mutated_path, parent=self, generation=self.generation + 1)
        self.children.append(child)
        return child

    def run(self, ticks: int = 5, branch_factor: int = 2) -> None:
        self.analyze()
        print(f"\n🧬 [AGENT {self.id}] Gen {self.generation} | Entropy={self.entropy:.3f} Bias={self.bias:.3f}")

        # Decision to spawn (synthetic trigger)
        if self.entropy > 0.65:
            for _ in range(branch_factor):
                child = self.spawn_child()
                print(f"👾  Spawned child → {child.id}")

        # Baton handoff simulation
        baton = hashlib.sha1(f"{self.id}{self.entropy}".encode()).hexdigest()[:12]
        print(f"🪬 Baton generated: {baton}")

        # Recursively run children
        for c in self.children:
            c.run(ticks=max(1, ticks - 1), branch_factor=branch_factor)


class FractalSwarm:
    def __init__(self, root_manifest: str):
        self.root_manifest = root_manifest
        self.root_agent = FractalAgent(root_manifest)

    def launch(self, ticks: int = 5, branch_factor: int = 2) -> None:
        print("🌌 Fractal Swarm initializing...")
        self.root_agent.run(ticks=ticks, branch_factor=branch_factor)
        print("🌿 Swarm completed.")


def cmd_launch(args: argparse.Namespace) -> int:
    swarm = FractalSwarm(args.file)
    swarm.launch(ticks=args.ticks, branch_factor=args.branch_factor)
    return 0


def cmd_autonomous(args: argparse.Namespace) -> int:
    swarm = FractalSwarm(args.file)
    cycle = 0
    while True:
        print(f"\n🌀 Evolution Cycle {cycle} — {datetime.utcnow().isoformat()}")
        swarm.launch(ticks=args.ticks, branch_factor=args.branch_factor)
        cycle += 1
        time.sleep(args.delay)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YSON-X Swarm :: Autonomous Fractal Agent Runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    launch_p = sub.add_parser("launch", help="Run a finite swarm evolution")
    launch_p.add_argument("file")
    launch_p.add_argument("--ticks", type=int, default=4)
    launch_p.add_argument("--branch-factor", type=int, default=2)
    launch_p.set_defaults(func=cmd_launch)

    auto_p = sub.add_parser("autonomous", help="Run infinite evolution swarm")
    auto_p.add_argument("file")
    auto_p.add_argument("--ticks", type=int, default=4)
    auto_p.add_argument("--branch-factor", type=int, default=2)
    auto_p.add_argument("--delay", type=float, default=5.0)
    auto_p.set_defaults(func=cmd_autonomous)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

