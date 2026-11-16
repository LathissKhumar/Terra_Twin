"""Ensure validated production datasets and source rasters are present and verified."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("terratwin.ensure_rasters")

DOWNLOAD_URLS: dict[str, str] = {
    # Mars HiRISE Jezero Crater stereo DTM (393 MB)
    "9e723a990ef2694474bbc2486039098c885d09b938e70b903d60c15cbf704008": (
        "https://www.uahirise.org/PDS/DTM/ESP/ORB_048800_048899/"
        "ESP_048842_1985_ESP_048908_1985/DTEEC_048842_1985_048908_1985_U01.IMG"
    ),
    # Mars MOLA MEGDR 128 px/deg median elevation tile (124 MB)
    "14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36": (
        "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.img"
    ),
    # Mars MOLA MEGDR counts tile (62 MB)
    "cfb4d7e3626106ef4ed2a466eb03a538feed9c163be99e860b7ae8700a8ecab5": (
        "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megc44n000hb.img"
    ),
    # Earth USGS 1M bare-earth DEM (240 MB)
    "e3453aef4b3b1b839a63073318fc5f78153b2f0ad26f35dfa958798e0d179fa5": (
        "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/"
        "ID_SouthernID_2018_D19/TIFF/USGS_1M_12_x36y481_ID_SouthernID_2018_D19.tif"
    ),
    # Earth Copernicus DEM GLO-30 (18, 77) (38 MB)
    "51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989": (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N18_00_E077_00_DEM/Copernicus_DSM_COG_10_N18_00_E077_00_DEM.tif"
    ),
    # Earth Copernicus DEM GLO-30 (43, -113) (34 MB)
    "665215ba1e9d87fc8c9654c60ffabb9907fc85fd1adfaf93ac3168512c7e2f13": (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N43_00_W113_00_DEM/Copernicus_DSM_COG_10_N43_00_W113_00_DEM.tif"
    ),
}

ANCILLARY_DOWNLOADS: list[tuple[str, str]] = [
    (
        "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.lbl",
        "raw/mars/MEGT44N000HB.lbl",
    ),
    (
        "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megc44n000hb.lbl",
        "raw/mars/MEGC44N000HB.lbl",
    ),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def download_stream(url: str, destination: Path, expected_hash: str | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(f"{destination.suffix}.part")
    logger.info("Downloading %s -> %s", url, destination.name)

    headers = {"User-Agent": "TerraTwin-DataEngine/0.1.0 (Planetary Analogue Platform)"}
    req = urllib.request.Request(url, headers=headers)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp, open(temp_path, "wb") as out:
                total_bytes = 0
                start_time = time.monotonic()
                while chunk := resp.read(1024 * 1024):
                    out.write(chunk)
                    total_bytes += len(chunk)
                elapsed = time.monotonic() - start_time
                speed_mb = (total_bytes / (1024 * 1024)) / max(elapsed, 0.1)
                logger.info(
                    "Downloaded %d MB in %.1fs (%.1f MB/s)",
                    total_bytes // (1024 * 1024),
                    elapsed,
                    speed_mb,
                )

            if expected_hash:
                actual_hash = sha256_file(temp_path)
                if actual_hash != expected_hash:
                    temp_path.unlink(missing_ok=True)
                    raise ValueError(
                        f"Checksum mismatch for {destination.name}: "
                        f"expected {expected_hash}, got {actual_hash}"
                    )

            temp_path.replace(destination)
            logger.info("Verified and placed: %s", destination)
            return
        except Exception as exc:
            logger.warning("Attempt %d/%d failed: %s", attempt, max_retries, exc)
            temp_path.unlink(missing_ok=True)
            if attempt < max_retries:
                time.sleep(2 * attempt)
            else:
                raise


def ensure_dataset(manifest_path: Path, data_dir: Path) -> bool:
    manifest = json.loads(manifest_path.read_text())
    dataset_id = manifest["id"]
    target_body = manifest.get("target_body", "mars")
    expected_hash = manifest["checksum_sha256"]

    target_dir = data_dir / "raw" / target_body
    target_dir.mkdir(parents=True, exist_ok=True)

    # Detect expected suffix
    source_url = manifest.get("source_url") or DOWNLOAD_URLS.get(dataset_id, "")
    suffix = ".img" if target_body == "mars" else ".tif"
    destination = target_dir / f"{dataset_id}{suffix}"

    # Check if already present and verified
    candidates = list(target_dir.glob(f"{dataset_id}.*"))
    for cand in candidates:
        if cand.is_file() and sha256_file(cand) == expected_hash:
            logger.info("Dataset %s is present and verified: %s", dataset_id[:16], cand.name)
            return True

    # Need download
    url = DOWNLOAD_URLS.get(dataset_id) or source_url
    if not url:
        logger.error("No source URL for dataset %s", dataset_id)
        return False

    download_stream(url, destination, expected_hash=expected_hash)
    return True


def ensure_aliases(data_dir: Path) -> None:
    mars_dir = data_dir / "raw" / "mars"
    aliases = [
        (
            "DTEEC_048842_1985_048908_1985_U01.IMG",
            "9e723a990ef2694474bbc2486039098c885d09b938e70b903d60c15cbf704008.img",
        ),
        (
            "MEGT44N000HB.IMG",
            "14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36.img",
        ),
        (
            "MEGC44N000HB.IMG",
            "cfb4d7e3626106ef4ed2a466eb03a538feed9c163be99e860b7ae8700a8ecab5.img",
        ),
    ]
    for alias_name, target_name in aliases:
        target_path = mars_dir / target_name
        alias_path = mars_dir / alias_name
        if target_path.exists() and not alias_path.exists():
            try:
                alias_path.symlink_to(target_name)
                logger.info("Created alias symlink: %s -> %s", alias_name, target_name)
            except OSError:
                import shutil

                shutil.copy2(target_path, alias_path)
                logger.info("Copied alias: %s -> %s", alias_name, target_name)


def run_provisioning(data_dir: Path) -> dict[str, Any]:
    """Execute complete dataset provisioning, download missing rasters, and verify checksums."""
    data_dir = data_dir.resolve()
    logger.info("Ensuring production rasters in: %s", data_dir)

    # 1. Ancillary downloads (PDS labels)
    for url, rel_dest in ANCILLARY_DOWNLOADS:
        dest = data_dir / rel_dest
        if not dest.exists():
            download_stream(url, dest)

    # 2. Dataset manifests
    manifests_dir = data_dir / "manifests"
    manifest_files = sorted(manifests_dir.glob("*.json"))
    ancillary_dir = manifests_dir / "ancillary"
    if ancillary_dir.exists():
        manifest_files.extend(sorted(ancillary_dir.glob("*.json")))

    if not manifest_files:
        raise FileNotFoundError(f"No manifest files found in {manifests_dir}")

    logger.info("Found %d dataset manifests to verify", len(manifest_files))
    results: list[dict[str, Any]] = []
    all_ok = True
    for mf in manifest_files:
        try:
            ok = ensure_dataset(mf, data_dir)
            if not ok:
                all_ok = False
            results.append({"manifest": mf.stem, "status": "verified" if ok else "failed"})
        except Exception as exc:
            logger.error("Failed to ensure dataset from %s: %s", mf.name, exc)
            all_ok = False
            results.append({"manifest": mf.stem, "status": "error", "error": str(exc)})

    # 3. Create aliases
    ensure_aliases(data_dir)

    if not all_ok:
        logger.error("One or more datasets failed to verify")
        return {
            "status": "degraded",
            "all_verified": False,
            "manifest_count": len(manifest_files),
            "results": results,
            "message": "One or more datasets failed to download or verify",
        }

    logger.info("All production datasets and rasters verified successfully!")
    return {
        "status": "success",
        "all_verified": True,
        "manifest_count": len(manifest_files),
        "results": results,
        "message": "All production datasets and rasters verified and provisioned successfully",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("DATA_DIR", "/app/data")),
        help="Path to TerraTwin data root",
    )
    args = parser.parse_args()
    result = run_provisioning(args.data_dir)
    if not result.get("all_verified", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
