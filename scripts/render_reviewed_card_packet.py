#!/usr/bin/env python3
"""Write the bounded reviewed-card evidence packet for a specification generator."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from neurolab.research_storage import render_reviewed_card_packet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "it-research" / "reviewed-research-cards.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maximum-cards", type=int, default=12)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    packet = render_reviewed_card_packet(
        os.environ.get("DATABASE_URL", ""), maximum_cards=arguments.maximum_cards
    )
    output = arguments.output.resolve()
    runtime = (PROJECT_ROOT / "runtime").resolve()
    if runtime not in output.parents:
        raise RuntimeError("card packet output must stay under the ignored runtime directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(packet, encoding="utf-8")
    print("reviewed_research_cards: packet_written")


if __name__ == "__main__":
    main()
