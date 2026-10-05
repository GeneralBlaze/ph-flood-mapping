from shapely.geometry import LineString

from analysis.street_story import compose_story, rim_summary, streets_along

# Route heading east along latitude 4.8, ~11 m per 0.0001 degree.
ROUTE = [(7.0000 + i * 0.0003, 4.8) for i in range(10)]  # ~300 m long, points every ~33 m
ROADS = [
    {"name": "Okoro Street", "line": LineString([(6.9995, 4.8), (7.0016, 4.8)])},        # route runs along it
    {"name": "Ada George Road", "line": LineString([(7.0021, 4.79), (7.0021, 4.81)])},    # route crosses it
    {"name": None, "line": LineString([(7.0, 4.7999), (7.003, 4.7999)])},                 # unnamed: ignored
    {"name": "Far Road", "line": LineString([(7.1, 4.9), (7.2, 4.9)])},
]


def test_streets_along_lists_streets_in_order_with_follow_or_cross():
    assert streets_along(ROUTE, ROADS, tolerance_m=15) == [
        {"name": "Okoro Street", "role": "follows", "first_index": 0},
        {"name": "Ada George Road", "role": "crosses", "first_index": 7},
    ]


def test_rim_summary_sorts_streets_from_lowest():
    lows = [{"name": "High Street", "height_m": 2.4}, {"name": "Low Lane", "height_m": -0.8},
            {"name": "Mid Road", "height_m": 0.2}]

    assert [r["name"] for r in rim_summary(lows, limit=2)] == ["Low Lane", "Mid Road"]


def test_story_when_water_must_rise_over_a_barrier():
    story = compose_story(
        rise_m=1.6, barrier_street="Okoro Street", streets=[{"name": "Okoro Street", "role": "follows", "first_index": 0},
                                                             {"name": "Ada George Road", "role": "crosses", "first_index": 7}],
        route_m=650, buildings_by_street={"Okoro Street": 12, None: 3}, rim=[{"name": "Low Lane", "height_m": -0.8},
                                                                             {"name": "High Street", "height_m": 2.4}],
    )

    assert story == [
        "Water has to rise about 1.6 m before it can flow out, at the low point on Okoro Street. "
        "This is a hollow with no natural way out at ground level.",
        "From there it should follow Okoro Street and cross Ada George Road to the nearest drainage channel, about 650 m away.",
        "15 buildings stand on or beside that route, 12 of them along Okoro Street.",
        "Lower than the flooded ground: Low Lane (0.8 m). Water should be able to reach it, so check for a blocked "
        "or missing drain in between.",
        "Higher than the flooded ground: High Street (2.4 m).",
    ]


def test_story_when_ground_falls_away():
    story = compose_story(rise_m=0.2, barrier_street=None, streets=[], route_m=300, buildings_by_street={}, rim=[])

    assert story == [
        "The ground falls away from here, so water should run off on its own. Water that stays points to "
        "blocked or undersized drains or culverts rather than the lie of the land.",
        "It should reach the nearest drainage channel about 300 m away, without following a named street.",
        "No buildings found on that route.",
    ]


def test_story_for_site_on_a_drainage_line_skips_the_route():
    story = compose_story(rise_m=0.0, barrier_street=None, streets=[], route_m=31, buildings_by_street={},
                          rim=[{"name": "Trans Woji Road", "height_m": 0.2}])

    assert story == [
        "The site sits on a natural drainage line, so water should flow straight away. Water that stays points "
        "to a blocked or undersized drain or culvert.",
        "About level with the flooded ground: Trans Woji Road.",
    ]


def test_buildings_street_named_only_when_a_real_share():
    story = compose_story(rise_m=0.0, barrier_street=None, streets=[], route_m=500,
                          buildings_by_street={"Elelenwo Road": 1, None: 51}, rim=[])

    assert story[2] == "52 buildings stand on or beside that route."


def test_several_lower_streets_use_plural():
    story = compose_story(rise_m=0.0, barrier_street=None, streets=[], route_m=500, buildings_by_street={},
                          rim=[{"name": "A Road", "height_m": -2.3}, {"name": "B Road", "height_m": -1.1}])

    assert story[3] == ("Lower than the flooded ground: A Road (2.3 m), B Road (1.1 m). Water should be able to reach "
                        "them, so check for blocked or missing drains in between.")
