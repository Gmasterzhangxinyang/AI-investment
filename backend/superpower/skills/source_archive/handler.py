from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from superpower.runtime.context import AgentContext


class Skill:
    def run(self, context: AgentContext) -> dict[str, object]:
        root_dir = context.root_dir
        archive_dir = root_dir / "data" / "archive" / context.run_id
        archive_dir.mkdir(parents=True, exist_ok=True)

        sources = [
            ("ETF", context.get("etf_file")),
            ("TL", context.get("tl_file")),
        ]
        cb_file = context.maybe("cb_file")
        if cb_file is not None:
            sources.append(("CB", cb_file))

        records: list[dict[str, Any]] = []
        for source_type, raw_path in sources:
            path = Path(raw_path).expanduser().resolve()
            record = _fingerprint(source_type, path)
            if record["exists"]:
                archive_name = f"{source_type}_{path.name}"
                archive_path = archive_dir / archive_name
                shutil.copy2(path, archive_path)
                record["archive_path"] = str(archive_path)
            records.append(record)

        manifest = pd.DataFrame(records)
        manifest_path = archive_dir / "source_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "run_id": context.run_id,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "sources": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        context.put("source_manifest", manifest)
        context.put("source_manifest_path", manifest_path)
        return {
            "source_files": len(records),
            "existing_source_files": int(manifest["exists"].sum()) if not manifest.empty else 0,
            "source_manifest_path": str(manifest_path),
        }


def _fingerprint(source_type: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "source_type": source_type,
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "modified_at": "",
            "sha256": "",
            "archive_path": "",
        }

    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return {
        "source_type": source_type,
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "sha256": digest.hexdigest(),
        "archive_path": "",
    }
