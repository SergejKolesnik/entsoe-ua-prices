"""Standalone gas benchmark experiment: raw local artifacts and JSON, never SQL."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from .parsers.gas_indices import parse_ceghix, parse_ueex, parse_ueex_margin
from .sources.gas_indices import fetch_gas_index
from .sources.base import RawResponse


def run(
    output: Path,
    replay_dir: Path | None = None,
    *,
    retrieved_at: datetime | None = None,
) -> dict:
    """Fetch both sources, preserve raw evidence, then validate the entire batch.

    A new directory is required to prevent overwriting an earlier snapshot.
    Failures leave raw evidence and an error manifest, never partial normalized data.
    """
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"mode": "replay" if replay_dir else "dry-run", "database_writes": False, "sources": {}}
    observations = []
    try:
        for source, parser in (("ceghix", parse_ceghix), ("ueex", parse_ueex), ("ueex_margin", parse_ueex_margin)):
            if replay_dir is None:
                raw = fetch_gas_index(source)
                retrieved = retrieved_at or datetime.now(timezone.utc)
                if retrieved.tzinfo is None or retrieved.utcoffset() is None:
                    raise ValueError("retrieved_at must be timezone-aware")
            else:
                evidence = json.loads((replay_dir / "manifest.json").read_text(encoding="utf-8"))["sources"][source]
                content = (replay_dir / f"{source}.raw").read_bytes()
                if sha256(content).hexdigest() != evidence["sha256"]:
                    raise ValueError(f"Replay hash mismatch: {source}")
                raw = RawResponse(content, evidence["content_type"], 200, evidence["url"])
                retrieved = datetime.fromisoformat(evidence["retrieved_at"])
            (output / f"{source}.raw").write_bytes(raw.content)
            manifest["sources"][source] = {
                "url": raw.source_url, "content_type": raw.content_type,
                "retrieved_at": retrieved.isoformat(), "sha256": sha256(raw.content).hexdigest(),
            }
            result = parser(raw, retrieved)
            manifest["sources"][source].update(
                accepted=len(result.observations), missing_prices=result.missing_prices,
                unsupported_contracts=result.unsupported_contracts,
                unsupported_vat_rows=result.unsupported_vat_rows,
            )
            observations.extend(asdict(row) for row in result.observations)
        manifest["status"] = "validated"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "observations.json").write_text(json.dumps(observations, default=str, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    """Run only on explicit invocation with a new local artifact directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--replay-dir", type=Path, help="Revalidate saved raw evidence without network access")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, args.replay_dir), indent=2))


if __name__ == "__main__":
    main()
