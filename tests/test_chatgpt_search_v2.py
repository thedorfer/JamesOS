from pathlib import Path

from jamesos.services.chatgpt_search_v2 import _parse_markdown_messages


def test_parse_markdown_messages_normalizes_roles_and_extracts_bodies(tmp_path: Path) -> None:
    path = tmp_path / "conversation.md"
    path.write_text(
        """# Test conversation

### user - 2025-09-26T22:02:10

Hello there

### assistant (gpt-5) - 2025-09-26T22:02:11

Hi! How can I help?

### tool - 2025-09-26T22:02:12

Tool output

### system - 2025-09-26T22:02:13

System prompt
""",
        encoding="utf-8",
    )

    rows = _parse_markdown_messages(path)

    assert len(rows) == 4
    assert [row["role"] for row in rows] == ["user", "assistant", "tool", "system"]
    assert rows[0]["text"] == "Hello there"
    assert rows[1]["text"] == "Hi! How can I help?"
    assert rows[1]["model"] == "gpt-5"
    assert rows[2]["text"] == "Tool output"
    assert rows[3]["text"] == "System prompt"
