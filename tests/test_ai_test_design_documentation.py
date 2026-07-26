from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_test_design_documentation_covers_architecture_safety_and_demo_flow():
    content = read_text("docs/ai/test_design_assistant.md")
    required_sections = (
        "Feature positioning",
        "Data flow",
        "Provider architecture",
        "Mock and DeepSeek",
        "Strict output schema",
        "Deterministic quality scoring",
        "Human review workflow",
        "Accept and reject rules",
        "Prompt-injection protection",
        "Data boundary",
        "Failure and rollback",
        "Demo flow",
        "Limitations",
        "Interview talking points",
    )

    for heading in required_sections:
        assert heading in content
    assert "AI output is a draft" in content
    assert "real company" in content
    assert "does not auto-create" in content
    assert "test-design-v1" in content


def test_readme_links_to_test_design_guide_without_copying_full_document():
    content = read_text("README.md")

    assert "AI Test Design Assistant" in content
    assert "docs/ai/test_design_assistant.md" in content
    assert content.count("Prompt injection") <= 3
