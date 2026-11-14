import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.exceptions import DatasetAcquisitionError, InvalidRasterError
from app.engines.data_ingestion.ingestion import download_to_path, ingest_file, sha256_file


def raster(path, *, crs="EPSG:4326", nodata=-9999):
    fill = nodata if nodata is not None else 0
    data = np.array([[12, 13, 14], [15, fill, 17], [18, 19, 20]], dtype="int16")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=3,
        height=3,
        count=1,
        dtype="int16",
        crs=crs,
        transform=from_origin(10, 20, 0.01, 0.01),
        nodata=nodata,
    ) as ds:
        ds.write(data, 1)
    return data


def ingest(path, root):
    return ingest_file(
        path,
        data_dir=root,
        target_body="earth",
        provider="test fixture",
        product="documented GeoTIFF contract fixture",
        vertical_units="m",
        vertical_reference="test fixture vertical reference",
        attribution="test only",
    )


def test_success_manifest_checksum_nodata_duplicate_and_immutable(tmp_path):
    src = tmp_path / "source.tif"
    raster(src)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    manifest = ingest(src, tmp_path / "data")
    stored = tmp_path / "data/raw/earth" / f"{before}.tif"
    assert manifest.checksum_sha256 == sha256_file(stored) == before
    assert manifest.nodata == -9999 and manifest.width == 3 and manifest.crs == "EPSG:4326"
    with rasterio.open(stored) as ds:
        assert ds.read(1, masked=True).mask.sum() == 1
    assert ingest(src, tmp_path / "data").id == manifest.id
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    assert (tmp_path / "data/manifests" / f"{before}.json").exists()


@pytest.mark.parametrize("crs,nodata", [(None, -9999), ("EPSG:4326", None)])
def test_reject_missing_crs_or_nodata(tmp_path, crs, nodata):
    src = tmp_path / "bad.tif"
    raster(src, crs=crs, nodata=nodata)
    with pytest.raises(InvalidRasterError):
        ingest(src, tmp_path / "data")


def test_reject_nonfinite_valid_pixels(tmp_path):
    src = tmp_path / "nan.tif"
    with rasterio.open(
        src,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=-9999,
    ) as ds:
        ds.write(np.array([[1, np.nan], [3, 4]], dtype="float32"), 1)
    with pytest.raises(InvalidRasterError, match="non-finite"):
        ingest(src, tmp_path / "data")


def test_download_checksum_failure_removes_partial(tmp_path, monkeypatch):
    from io import BytesIO

    from app.engines.data_ingestion import ingestion

    class Response(BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(ingestion.urllib.request, "urlopen", lambda *a, **k: Response(b"partial"))
    dest = tmp_path / "x.tif"
    with pytest.raises(DatasetAcquisitionError, match="checksum"):
        download_to_path("https://example.org/x", dest, expected_sha256="0" * 64)
    assert not dest.exists() and not list(tmp_path.iterdir())


def test_reject_http_download_and_duplicate_destination(tmp_path, monkeypatch):
    from io import BytesIO

    from app.engines.data_ingestion import ingestion

    with pytest.raises(ValueError, match="HTTPS"):
        download_to_path("http://example.org/x", tmp_path / "x")

    class Response(BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(ingestion.urllib.request, "urlopen", lambda *a, **k: Response(b"data"))
    dest = tmp_path / "x"
    download_to_path("https://example.org/x", dest)
    with pytest.raises(FileExistsError):
        download_to_path("https://example.org/x", dest)


def test_interrupted_download_removes_temporary_file(tmp_path, monkeypatch):
    from io import BytesIO

    from app.engines.data_ingestion import ingestion

    class InterruptedResponse(BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def read(self, size=-1):
            if self.tell():
                raise OSError("connection interrupted")
            return super().read(8)

    monkeypatch.setattr(
        ingestion.urllib.request,
        "urlopen",
        lambda *args, **kwargs: InterruptedResponse(b"partial stream"),
    )
    dest = tmp_path / "interrupted.tif"
    with pytest.raises(DatasetAcquisitionError, match="download failed"):
        download_to_path("https://example.org/data.tif", dest)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_truncated_download_content_length_is_rejected(tmp_path, monkeypatch):
    from io import BytesIO

    from app.engines.data_ingestion import ingestion

    class TruncatedResponse(BytesIO):
        headers = {"Content-Length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        ingestion.urllib.request,
        "urlopen",
        lambda *args, **kwargs: TruncatedResponse(b"short"),
    )
    dest = tmp_path / "truncated.tif"
    with pytest.raises(DatasetAcquisitionError, match="before Content-Length"):
        download_to_path("https://example.org/data.tif", dest)
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_reject_corrupt_raster_and_unknown_extension(tmp_path):
    corrupt = tmp_path / "corrupt.tif"
    corrupt.write_bytes(b"not a TIFF")
    with pytest.raises(InvalidRasterError):
        ingest(corrupt, tmp_path / "data")

    unsupported = tmp_path / "source.txt"
    unsupported.write_bytes(b"not raster")
    with pytest.raises(InvalidRasterError, match="extension"):
        ingest(unsupported, tmp_path / "data")


def test_real_source_derived_sample_rasters_are_documented_and_ingest(tmp_path):
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "data"
    provenance = json.loads((fixture_dir / "sample-provenance.json").read_text())
    samples = {entry["path"]: entry for entry in provenance["samples"]}
    cases = [
        (
            "mola_megt44n000hb_jezero_window.tif",
            "mars",
            False,
        ),
        (
            "copernicus_glo30_n18_e077_window.tif",
            "earth",
            True,
        ),
    ]
    for filename, body, allow_missing_nodata in cases:
        source = fixture_dir / filename
        details = samples[filename]
        assert sha256_file(source) == details["sample_sha256"]
        assert details["source_sha256"]
        with rasterio.open(source) as dataset:
            assert (dataset.width, dataset.height) == (64, 64)
            assert dataset.crs is not None
            values = dataset.read(1)
            valid = dataset.read_masks(1) > 0
            assert np.isfinite(values[valid]).all()
        before = sha256_file(source)
        manifest = ingest_file(
            source,
            data_dir=tmp_path / "ingested",
            target_body=body,
            provider=details["provider"],
            product=details["product_id"],
            vertical_units="m",
            vertical_reference=details["vertical_reference"],
            source_url=details["source_url"],
            attribution=details["provider"],
            allow_missing_nodata=allow_missing_nodata,
            product_metadata={"sample_source_sha256": details["source_sha256"]},
        )
        assert manifest.width == manifest.height == 64
        assert manifest.checksum_sha256 == before
        assert sha256_file(source) == before
