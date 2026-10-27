from app.retrieval.hybrid import named_source_topic


def test_named_title_prefix_removes_title_noise_and_preserves_concept():
    title = "Aster Analytics: Measuring a Marketplace"
    titles, topic = named_source_topic(
        "In Aster Analytics, how are buyers and engaged buyers defined?", [title]
    )
    assert titles == [title]
    assert "aster" not in topic and "analytics" not in topic
    assert "engaged" in topic and "buyers" in topic


def test_title_matching_is_token_bounded_not_fuzzy_authorization():
    assert named_source_topic("Aster AnalyticsExtra buyers", ["Aster Analytics"])[0] == []
    assert named_source_topic("profit goals", ["Good Strategy Bad Strategy"])[0] == []
    assert named_source_topic("according to Strategy", ["Strategy"])[0] == []
    assert (
        named_source_topic("What is a good strategy for hiring?", ["Good Strategy Bad Strategy"])[0]
        == []
    )


def test_comparison_keeps_both_named_sources():
    titles, topic = named_source_topic(
        "Compare Aster Analytics with Thinking in Systems on buyer stocks",
        ["Thinking in Systems", "Aster Analytics"],
    )
    assert set(titles) == {"Thinking in Systems", "Aster Analytics"}
    assert "buyer" in topic and "stocks" in topic
