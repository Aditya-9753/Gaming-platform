"""CricAPI (CricketData.org) mapping, categories, winner parsing and quota-friendly caching."""

import time

import httpx
import pytest

from app.games.cricket.providers.cricapi import CricApiProvider, categorise, to_match

LIVE = {
    "id": "abc-1",
    "name": "India vs Australia, 2nd ODI, Australia tour of India, 2026",
    "matchType": "odi",
    "status": "India opt to bat",
    "venue": "Wankhede, Mumbai",
    "dateTimeGMT": "2026-10-02T08:30:00",
    "teams": ["India", "Australia"],
    "teamInfo": [{"name": "India", "img": "https://h.cricapi.com/img/india.png"}],
    "score": [{"r": 182, "w": 3, "o": 31.2, "inning": "India Inning 1"}],
    "matchStarted": True,
    "matchEnded": False,
}


def test_live_match_mapping():
    match = to_match(LIVE)
    assert match.match_id == "ca-abc-1"
    assert match.status == "LIVE"
    assert match.home_score == "182/3 (31.2)" and match.away_score is None
    assert match.metadata["category"] == "International"
    assert match.metadata["format"] == "ODI"
    assert match.metadata["logos"]["India"].endswith("india.png")


def test_finished_match_winner_and_no_result():
    won = to_match({**LIVE, "matchEnded": True, "status": "Australia won by 4 wkts"})
    assert won.status == "COMPLETED" and won.winner == "Australia" and not won.abandoned
    washed = to_match({**LIVE, "matchEnded": True, "status": "No result (due to rain)"})
    assert washed.winner is None and washed.abandoned


@pytest.mark.parametrize(
    "name,teams,kind,expected",
    [
        ("Mumbai Indians vs Chennai, 12th Match, Indian Premier League 2026", ["Mumbai Indians", "Chennai Super Kings"], "t20", "T20 Leagues"),
        ("India Women vs England Women, 1st T20I", ["India Women", "England Women"], "t20", "Women"),
        ("Mumbai vs Delhi, Elite Group A, Ranji Trophy", ["Mumbai", "Delhi"], "test", "Domestic"),
        ("Nepal vs Oman, 5th Match, CWC League 2", ["Nepal", "Oman"], "odi", "International"),
    ],
)
def test_categories(name, teams, kind, expected):
    assert categorise(name, teams, kind) == expected


@pytest.mark.asyncio
async def test_responses_are_cached_to_protect_quota():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "success", "data": [LIVE], "info": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = CricApiProvider("key", live_refresh=600, schedule_refresh=600, client=client)
        first = await provider.list_matches()
        await provider.list_matches()
        await provider.get_match("ca-abc-1")
    assert [m.match_id for m in first] == ["ca-abc-1"]
    assert sorted(calls) == ["/v1/currentMatches", "/v1/matches"]


@pytest.mark.asyncio
async def test_started_fixture_closes_even_if_cache_is_stale():
    upcoming = {**LIVE, "matchStarted": False, "dateTimeGMT": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 60))}

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"status": "success", "data": [upcoming]})
    )) as client:
        provider = CricApiProvider("key", client=client)
        [match] = await provider.list_matches()
    assert match.status == "LIVE"
