"""S3 end-to-end test — paste into IPython / run with `%run test_s3_pipeline.py`."""

import logging

from hlspkg.config.loader import load_config
from hlspkg.core.pipeline import run_pipeline
from hlspkg.storage.s3 import S3Storage

# --- Parameters (edit these) ---


INPUT_BUCKET = "media-uploads-tessact"
INPUT_KEY = "30b76c0d-7061-430a-b99f-e2e4f95497db/01681a69-4138-4b53-bb73-f36d20da6b5c/01681a69-4138-4b53-bb73-f36d20da6b5c.mp4"

OUTPUT_BUCKET = "video-access-tem.tessact.com"
OUTPUT_PREFIX = "hls-output/01681a69-4138-4b53-bb73-f36d20da6b5c"

ASSET_ID = None   # auto-generated if None
VERSION = "v1"
FORCE_CPU = False  # False to auto-detect GPU (NVENC)

# --- Run ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

config = load_config()

input_storage = S3Storage(INPUT_BUCKET, "")
output_storage = S3Storage(OUTPUT_BUCKET, OUTPUT_PREFIX)

result = run_pipeline(
    input_key=INPUT_KEY,
    input_storage=input_storage,
    output_storage=output_storage,
    config=config,
    asset_id=ASSET_ID,
    version=VERSION,
    force_cpu=FORCE_CPU,
)

print(f"Published to: {result}")
