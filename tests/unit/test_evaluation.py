from app.evaluation import rank_metrics


def test_passage_metrics_count_each_gold_target_once_and_use_first_relevant_rank():
    result = rank_metrics(["noise", "a", "b", "c"], [{"a", "b"}, {"c"}, {"missing"}])
    assert result == {"hit": 1, "recall": 2 / 3, "rr": 0.5}
    assert rank_metrics(["noise"], [{"a"}]) == {"hit": 0, "recall": 0, "rr": 0}
    assert rank_metrics(["noise"], []) is None
