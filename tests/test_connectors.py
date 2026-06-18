from scripts.connectors.gsi_tiles import is_png, standard_tile_url
from scripts.connectors.hazard_tiles import tile_response_is_valid
from scripts.connectors.jma_forecast import forecast_url, is_forecast_json
from scripts.connectors.ksj_geojson import is_geojson


def test_gsi_tile_connector_builds_url_and_detects_png() -> None:
    assert standard_tile_url().endswith("/10/909/403.png")
    assert is_png(b"\x89PNG\r\n\x1a\ncontent")


def test_hazard_tile_accepts_missing_tile_as_valid() -> None:
    assert tile_response_is_valid(404, b"")


def test_jma_forecast_json_shape() -> None:
    payload = b'[{"publishingOffice":"JMA","timeSeries":[]}]'
    assert forecast_url("130000").endswith("/130000.json")
    assert is_forecast_json(payload)


def test_geojson_detection() -> None:
    assert is_geojson(b'{"type":"FeatureCollection","features":[]}')
