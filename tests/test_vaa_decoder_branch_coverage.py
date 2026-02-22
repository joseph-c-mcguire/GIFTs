"""Additional branch-focused unit tests for vaaDecoder."""

from __future__ import annotations

from unittest import mock

import pytest

from gifts.common import tpg
from gifts.vaaDecoder import Decoder


def _build_decoder_with_context() -> Decoder:
    decoder = Decoder()
    decoder.vaa = {"clouds": {"0": {"cldLyrs": []}}}
    decoder._fhr = "0"
    if not hasattr(decoder.lexer, "cur_token"):
        decoder.lexer.cur_token = mock.Mock()
    else:
        decoder.lexer.cur_token = mock.Mock(spec=decoder.lexer.cur_token)
    decoder.lexer.cur_token.name = "noashexp"
    return decoder


def test_postpolygon_box_conversion_and_longitude_normalization(monkeypatch):
    decoder = _build_decoder_with_context()

    def fake_compute_latlon(lat, lon, *_args):
        return f"{lat + 0.100:.3f} {lon + 20.000:.3f}"

    monkeypatch.setattr("gifts.vaaDecoder.deu.computeLatLon", fake_compute_latlon)
    monkeypatch.setattr("gifts.vaaDecoder.deu.isCCW", lambda _polygon: False)

    cloud_info = {
        "box": {"width": "10", "uom": "NM"},
        "pnts": ["10.000 170.000", "11.000 171.000", "12.000 172.000"],
    }

    decoder.postPolygon(cloud_info)

    assert len(cloud_info["pnts"]) >= 3
    assert any(float(point.split()[1]) < 0 for point in cloud_info["pnts"])


def test_postpolygon_handles_value_error_from_orientation_check(monkeypatch):
    decoder = _build_decoder_with_context()

    monkeypatch.setattr(
        "gifts.vaaDecoder.deu.isCCW",
        lambda _polygon: (_ for _ in ()).throw(ValueError("bad polygon")),
    )

    cloud_info = {"pnts": ["1.000 1.000", "2.000 2.000", "1.000 1.000"]}

    with mock.patch.object(decoder._Logger, "info") as info_log:
        decoder.postPolygon(cloud_info)

    info_log.assert_called()


def test_postpolygon_keyerror_guard_and_none_short_circuit():
    decoder = _build_decoder_with_context()

    decoder.postPolygon({})
    decoder.postPolygon(None)


def test_noash_initializes_bucket_and_cleans_temp_cloud():
    decoder = _build_decoder_with_context()
    decoder.vaa = {"clouds": {}}
    decoder._fhr = "6"
    decoder._cloud = {"dummy": "value"}

    decoder.noash()

    assert decoder.vaa["clouds"]["6"]["cldLyrs"][0]["nil"] == "noashexp"
    assert not hasattr(decoder, "_cloud")


def test_noash_appends_when_bucket_exists_and_cloud_list_empty():
    decoder = _build_decoder_with_context()
    decoder.vaa = {"clouds": {"6": {"cldLyrs": []}}}
    decoder._fhr = "6"

    decoder.noash()

    assert decoder.vaa["clouds"]["6"]["cldLyrs"][0]["nil"] == "noashexp"


def test_finish_appends_cloud_when_present_and_noops_otherwise(monkeypatch):
    decoder = _build_decoder_with_context()
    decoder._cloud = {"pnts": ["1.000 1.000", "1.000 1.000"]}

    called = {"post": 0}

    def fake_post_polygon(cloud_info):
        called["post"] += 1
        assert cloud_info is decoder._cloud

    monkeypatch.setattr(decoder, "postPolygon", fake_post_polygon)
    result = decoder.finish()

    assert called["post"] == 1
    assert result["clouds"]["0"]["cldLyrs"]

    decoder_without_cloud = _build_decoder_with_context()
    returned = decoder_without_cloud.finish()
    assert returned == decoder_without_cloud.vaa


def test_dtg_rollover_paths_for_obs_and_dayhour():
    decoder = _build_decoder_with_context()

    decoder.lexer.cur_token.name = "dtg"
    decoder.dtg("DTG: 20251231/2359Z")

    decoder.lexer.cur_token.name = "obsdtg"
    decoder.dtg("OBS VA DTG: 01/0010Z")

    decoder._fhr = "6"
    decoder.vaa["clouds"]["6"] = {"dtg": "", "cldLyrs": []}
    decoder.lexer.cur_token.name = "dayhour"
    decoder.dtg("01/0100Z")

    assert decoder.vaa["clouds"]["0"]["dtg"].startswith("2026-01-01")
    assert decoder.vaa["clouds"]["6"]["dtg"].startswith("2026-01-01")


def test_vloc_parses_when_minutes_missing():
    decoder = _build_decoder_with_context()
    decoder.vloc("PSN: N14 W090")
    assert decoder.vaa["volcanoLocation"] == "14.000 -90.000"


def test_details_sets_eruption_date_with_full_date_components():
    decoder = _build_decoder_with_context()
    decoder.vaa["issueTime"] = {
        "tms": [2025, 1, 1, 0, 0, 0, 0, 0, 0],
        "str": "2025-01-01T00:00:00Z",
    }

    decoder.details("ERUPTION DETAILS: ERUPTION STARTED 20241231/2359Z")

    assert decoder.vaa["eruptionDate"].startswith("2024-12-31T23:59")


def test_layer_and_coordinate_methods_cover_transition_paths(monkeypatch):
    decoder = _build_decoder_with_context()
    decoder._cloud = {"pnts": ["1.000 1.000", "1.000 1.000"]}
    monkeypatch.setattr(decoder, "postPolygon", lambda *_args, **_kwargs: None)

    decoder.lexer.cur_token.name = "top"
    decoder.top("TOP FL100")

    decoder.lexer.cur_token.name = "midlyr"
    decoder.midlyr("FL200/100")
    assert decoder._cloud["bottom"] == "100"
    assert decoder._cloud["top"] == "200"

    decoder.lexer.cur_token.name = "sfc"
    decoder.sfc("SFC/FL150")

    decoder.lexer.cur_token.name = "box"
    decoder.box("50KM WID LINE BTN")

    decoder.lexer.cur_token.name = "latlon"
    decoder.latlon("N14 W090")
    assert decoder._cloud["pnts"]

    decoder.lexer.cur_token.name = "movement"
    decoder.movement("MOV N 10KT")
    assert decoder._cloud["movement"]["spd"] == "10"


def test_movement_raises_wrongtoken_for_unknown_cardinal(monkeypatch):
    decoder = _build_decoder_with_context()
    decoder._cloud = {}
    decoder.lexer.cur_token.name = "movement"

    fake_match = mock.Mock()
    fake_match.group.side_effect = lambda key: {
        1: "Q",
        2: "20",
        "uom": "KT",
    }[key]

    fake_token = mock.Mock()
    fake_token.match.return_value = fake_match
    monkeypatch.setitem(decoder.lexer.tokens, "movement", [fake_token])

    with pytest.raises(tpg.WrongToken):
        decoder.movement("MOV Q 20KT")


def test_vanotid_sets_bottom_when_missing_and_handles_attribute_error(monkeypatch):
    decoder = _build_decoder_with_context()
    decoder.vaa = {"clouds": {"0": {"cldLyrs": []}}}
    decoder._fhr = "0"
    decoder.lexer.cur_token.name = "vanotid"

    decoder.vanotid("WINDS SFC 090/20KT")
    assert decoder.vaa["clouds"]["0"]["cldLyrs"]
    assert decoder.vaa["clouds"]["0"]["cldLyrs"][0]["movement"]["bottom"] == "SFC"

    class NoGroupdictMatch:
        def end(self):
            return 3

    class NoGroupdictRegex:
        def __init__(self):
            self.calls = 0

        def search(self, *_args, **_kwargs):
            if self.calls == 0:
                self.calls += 1
                return NoGroupdictMatch()
            return None

    decoder.vaa = {"clouds": {"0": {"cldLyrs": []}}}
    decoder._reWinds = NoGroupdictRegex()
    decoder.vanotid("ANY")
    assert decoder.vaa["clouds"]["0"]["cldLyrs"][0]["movement"] is None
