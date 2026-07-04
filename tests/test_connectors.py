from scripts.connectors.gsi_elevation import (
    elevation_tile_url,
    looks_like_elevation_tile,
)
from scripts.connectors.gsi_tiles import is_png, standard_tile_url
from scripts.connectors.hazard_tiles import flood_tile_url, tile_response_is_valid
from scripts.connectors.jma_forecast import forecast_url, is_forecast_json
from scripts.connectors.ksj_geojson import administrative_area_page_url, is_geojson


def test_gsi_tile_connector_builds_url_and_detects_png() -> None:
    assert standard_tile_url().endswith("/10/909/403.png")
    assert is_png(b"\x89PNG\r\n\x1a\ncontent")


def test_gsi_tile_connector_rejects_non_png() -> None:
    assert is_png(b"not a png") is False


def test_gsi_elevation_connector_builds_url_and_detects_payload() -> None:
    assert elevation_tile_url().endswith("/14/14549/6451.png")
    assert looks_like_elevation_tile(b"\x89PNG\r\n\x1a\ncontent")


def test_gsi_elevation_connector_rejects_empty_payload() -> None:
    assert looks_like_elevation_tile(b"") is False


def test_hazard_tile_builds_url() -> None:
    assert flood_tile_url().endswith("/10/909/403.png")


def test_hazard_tile_accepts_missing_tile_as_valid() -> None:
    assert tile_response_is_valid(404, b"")


def test_hazard_tile_accepts_valid_png_response() -> None:
    assert tile_response_is_valid(200, b"\x89PNG\r\n\x1a\ncontent")


def test_hazard_tile_rejects_error_status_with_no_png() -> None:
    assert tile_response_is_valid(500, b"error") is False


def test_hazard_tile_rejects_ok_status_with_non_png_body() -> None:
    assert tile_response_is_valid(200, b"not a png") is False


def test_jma_forecast_json_shape() -> None:
    payload = b'[{"publishingOffice":"JMA","timeSeries":[]}]'
    assert forecast_url("130000").endswith("/130000.json")
    assert is_forecast_json(payload)


def test_jma_forecast_rejects_non_list_payload() -> None:
    assert is_forecast_json(b'{"publishingOffice":"JMA"}') is False


def test_jma_forecast_rejects_invalid_json() -> None:
    assert is_forecast_json(b"not json") is False


def test_jma_forecast_rejects_list_missing_required_key() -> None:
    assert is_forecast_json(b'[{"timeSeries":[]}]') is False


def test_geojson_detection() -> None:
    assert is_geojson(b'{"type":"FeatureCollection","features":[]}')


def test_geojson_detection_accepts_feature_type() -> None:
    assert is_geojson(b'{"type":"Feature","geometry":null}')


def test_geojson_detection_rejects_non_geojson_type() -> None:
    assert is_geojson(b'{"type":"Other"}') is False


def test_geojson_detection_rejects_invalid_json() -> None:
    assert is_geojson(b"not json") is False


def test_ksj_geojson_page_url() -> None:
    assert administrative_area_page_url().startswith("https://nlftp.mlit.go.jp/ksj/")
