from types import SimpleNamespace
from app.retrieval.hybrid import named_source_topic, source_role_intents, source_role_order


def test_role_search_separates_definition_and_qualification_without_book_rules():
    core, roles = source_role_intents(
        "What is a leverage point, and does it always help?", "leverage OR point OR always OR help"
    )
    assert core == "leverage point"
    assert [r[0] for r in roles] == ["definition", "qualification"]
    assert source_role_intents("Compare these examples", "buyer OR seller")[1] == []
    assert (
        source_role_intents("Why can it make things worse?", "leverage OR point")[1][0][0]
        == "direction"
    )


def test_explicit_qualification_is_not_outvoted_by_repeated_generic_negations():
    explicit = (
        SimpleNamespace(
            id="a",
            text="The bar raiser cannot be quantified: it is impossible to quantify its contribution.",
        ),
        None,
        None,
        0.1,
    )
    repeated = (
        SimpleNamespace(id="b", text="The bar raiser cannot do this and not that. " * 100),
        None,
        None,
        1.0,
    )
    assert source_role_order([repeated, explicit], "qualification", "bar raiser")[0] == explicit


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
