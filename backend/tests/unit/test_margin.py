"""House margin → payout tables: every pick returns (1 - margin) of stakes."""

import pytest

from app.games.color.rules import ColourResult, configured_payout_x100
from app.games.margin import payout_config_for_margin, supports_margin
from app.games.wingo.rules import payouts_from_config


def _wingo_rtps(p):
    return {
        "COLOR": (4 * p["GREEN"] + p["COLOR_HALF"]) / 10,
        "VIOLET": 2 * p["VIOLET"] / 10,
        "NUMBER": p["NUMBER"] / 10,
        "SIZE": 5 * p["SIZE"] / 10,
    }


@pytest.mark.parametrize("edge_bp", [0, 200, 300, 500, 1000, 2000])
def test_wingo_every_pick_returns_one_minus_margin(edge_bp):
    config = payout_config_for_margin("wingo_1m", edge_bp)
    payouts_from_config(config)  # valid for the engine
    for pick, rtp in _wingo_rtps(config["payouts"]).items():
        # payouts are floored to 0.01x, so RTP is at most 1 - margin and never far below
        assert 1 - edge_bp / 10_000 - 0.01 <= rtp <= 1 - edge_bp / 10_000 + 1e-9, pick


def test_wingo_five_percent_matches_classic_table():
    assert payout_config_for_margin("wingo_30s", 500)["payouts"] == {
        "GREEN": 2.0, "RED": 2.0, "COLOR_HALF": 1.5, "VIOLET": 4.75, "NUMBER": 9.5, "SIZE": 1.9,
    }


@pytest.mark.parametrize("edge_bp", [0, 300, 1000])
def test_color_every_pick_returns_one_minus_margin(edge_bp):
    table = payout_config_for_margin("color", edge_bp)["payout_multipliers"]
    for colour, p_win in ((ColourResult.RED, 9 / 19), (ColourResult.GREEN, 9 / 19), (ColourResult.VIOLET, 1 / 19)):
        rtp = p_win * configured_payout_x100(colour, table) / 100
        assert 1 - edge_bp / 10_000 - 0.01 <= rtp <= 1 - edge_bp / 10_000 + 1e-9


def test_margin_too_high_for_wingo_is_rejected():
    with pytest.raises(ValueError, match="below 1x"):
        payout_config_for_margin("wingo_1m", 4000)


def test_formula_games_need_no_table_and_cricket_has_no_margin():
    assert payout_config_for_margin("aviator", 500) is None
    assert payout_config_for_margin("mines", 500) is None
    for game_id in ("aviator", "mines", "color", "teen_patti", "wingo_30s", "wingo_1m", "wingo_3m", "wingo_5m"):
        assert supports_margin(game_id)
    assert not supports_margin("cricket")


@pytest.mark.parametrize("edge_bp,payout", [(0, 2.0), (200, 1.96), (500, 1.9), (1000, 1.8)])
def test_teen_patti_winning_side_pays_two_times_one_minus_margin(edge_bp, payout):
    from app.games.teen_patti.rules import payout_from_config

    config = payout_config_for_margin("teen_patti", edge_bp)
    assert config == {"payout": payout}
    assert payout_from_config(config) == round(payout * 100)
