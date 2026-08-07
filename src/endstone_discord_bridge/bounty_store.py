from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict


@dataclass
class BountyStore:
    path: Path
    index: Dict[str, int] = field(default_factory=dict)        # target -> stacked total
    placements: Dict[str, str] = field(default_factory=dict)   # target -> last placer/funder
    board_message_id: int = 0                                  # Discord message id

    @classmethod
    def load(cls, path: Path) -> "BountyStore":
        if not path.exists():
            return cls(path=path)
        raw = path.read_text(encoding="utf-8")
        data = tomllib.loads(raw)
        # allow either top-level keys or a [bounties] table
        root = data.get("bounties", data)
        return cls(
            path=path,
            index=dict(root.get("index", {})),
            placements=dict(root.get("placements", {})),
            board_message_id=int(root.get("board_message_id", 0) or 0),
        )

    def save(self) -> None:
        def _quote(s: str) -> str:
            return json.dumps(s)

        def _val(v):
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, int):
                return str(v)
            if isinstance(v, float):
                return ("%f" % v).rstrip("0").rstrip(".")
            if isinstance(v, str):
                return _quote(v)
            if isinstance(v, dict):
                items = [f"{k} = {_val(vv)}" for k, vv in v.items()]
                return "{" + ", ".join(items) + "}"
            if isinstance(v, list):
                return "[" + ", ".join(_val(x) for x in v) + "]"
            return _quote(str(v))

        d = asdict(self)
        # do not serialize "path"
        d.pop("path", None)

        lines = []
        lines.append("[bounties]")
        for k in ("index", "placements", "board_message_id"):
            lines.append(f"{k} = {_val(d[k])}")
        lines.append("")
        out = "\n".join(lines)

        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(self.path)
