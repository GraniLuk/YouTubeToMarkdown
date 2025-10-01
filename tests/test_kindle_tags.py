import textwrap
from pathlib import Path

import yaml

from yt2md.email.kindle import KINDLE_TAG, mark_sent_to_kindle


def _write_markdown(tmp_path: Path, front_matter: dict, body: str = "Body") -> Path:
    front = yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True).strip()
    content = textwrap.dedent(
        f"""---
{front}
---

{body}
"""
    )
    md_file = tmp_path / "note.md"
    md_file.write_text(content, encoding="utf-8")
    return md_file


def test_mark_sent_to_kindle_adds_tag(tmp_path: Path):
    md_file = _write_markdown(tmp_path, {"title": "Sample", "tags": ["#Summaries/ToRead"]})

    assert mark_sent_to_kindle(md_file)

    updated = md_file.read_text(encoding="utf-8")
    parts = updated.split("---", 2)
    metadata = yaml.safe_load(parts[1])
    assert KINDLE_TAG in metadata["tags"]


def test_mark_sent_to_kindle_idempotent(tmp_path: Path):
    md_file = _write_markdown(tmp_path, {"title": "Sample", "tags": ["#Summaries/ToKindle"]})

    assert mark_sent_to_kindle(md_file)
    # second call should keep single instance
    assert mark_sent_to_kindle(md_file)

    metadata = yaml.safe_load(md_file.read_text(encoding="utf-8").split("---", 2)[1])
    assert metadata["tags"].count(KINDLE_TAG) == 1


def test_mark_sent_to_kindle_creates_tags_array(tmp_path: Path):
    md_file = _write_markdown(tmp_path, {"title": "Sample"})

    mark_sent_to_kindle(md_file)

    metadata = yaml.safe_load(md_file.read_text(encoding="utf-8").split("---", 2)[1])
    assert metadata["tags"] == [KINDLE_TAG]
