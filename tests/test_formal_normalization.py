from experiment.normalization import transcribe


def test_literal_ambiguity_and_unparsed():
    raw = "preamble\n## 用例 1\n编号：a1\n标题：One\n标题：Two\n优先级：p1\n步骤：\n1. Upload\n2. Confirm\n未知字段：retained\n"
    result = transcribe(raw)
    case = result["normalized"][0]
    assert result["raw"] == raw and result["usable"] is True
    assert case["title"] is None and case["module"] is None
    assert case["priority"] == "p1" and case["suggested_code"] == "a1"
    assert case["steps"] == "1. Upload\n2. Confirm"
    assert result["conversion_log"]["ambiguous_field_count"] == 1
    assert result["conversion_log"]["unparsed_spans"]


def test_no_boundaries_is_unusable():
    result = transcribe("unstructured body\n")
    assert result["usable"] is False and result["normalized"] == []
