"""CLI entry point using Click."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from hlspkg.config.loader import load_config
from hlspkg.core.pipeline import run_pipeline
from hlspkg.exceptions import HlsPkgError
from hlspkg.storage import resolve_storage


@click.command()
@click.argument("input_key")
@click.option(
    "--input-storage",
    default=None,
    help="Input source: local path or s3://bucket/prefix. If omitted, INPUT_KEY is treated as a direct file path.",
)
@click.option(
    "--output",
    required=True,
    help="Output destination: local path or s3://bucket/prefix.",
)
@click.option("--asset-id", default=None, help="Asset identifier (default: auto-generated).")
@click.option("--version", default="v1", help="Version string (default: v1).")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True, path_type=Path), help="Override config YAML.")
@click.option("--crf", default=None, type=int, help="Override video CRF value.")
@click.option("--segment-duration", default=None, type=int, help="Override segment duration (seconds).")
@click.option("--renditions", default=None, type=str, help="Comma-separated rendition heights (e.g. '1080,720,480').")
@click.option("--cpu", "force_cpu", is_flag=True, help="Force CPU encoding (skip GPU auto-detection).")
@click.option("-v", "--verbose", is_flag=True, help="Debug logging.")
def main(
    input_key: str,
    input_storage: str | None,
    output: str,
    asset_id: str | None,
    version: str,
    config_path: Path | None,
    crf: int | None,
    segment_duration: int | None,
    renditions: str | None,
    force_cpu: bool,
    verbose: bool,
) -> None:
    """Transcode and package a video as CMAF HLS for VOD streaming."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Build CLI overrides dict
    cli_overrides: dict = {}
    if crf is not None:
        cli_overrides["crf"] = crf
    if segment_duration is not None:
        cli_overrides["segment_duration"] = segment_duration
    if renditions is not None:
        cli_overrides["renditions"] = [int(h.strip()) for h in renditions.split(",")]

    try:
        config = load_config(
            override_path=config_path,
            cli_overrides=cli_overrides or None,
        )

        # Resolve storage backends
        if input_storage is None:
            # Treat input_key as a direct file path
            input_path = Path(input_key).resolve()
            in_storage = resolve_storage(str(input_path.parent))
            resolved_key = input_path.name
        else:
            in_storage = resolve_storage(input_storage)
            resolved_key = input_key

        out_storage = resolve_storage(output)

        result = run_pipeline(
            input_key=resolved_key,
            input_storage=in_storage,
            output_storage=out_storage,
            config=config,
            asset_id=asset_id,
            version=version,
            force_cpu=force_cpu,
        )

        click.echo(f"Done: {result}")

    except HlsPkgError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
