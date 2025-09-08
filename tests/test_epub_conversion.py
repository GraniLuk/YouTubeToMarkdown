import os
import shutil
import textwrap
import uuid
from pathlib import Path
import pytest

try:
    from yt2md.email.epub import md_to_epub, EpubOptions, PandocNotAvailableError
except Exception as e:  # pragma: no cover
    pytest.skip(f"EPUB module not importable: {e}", allow_module_level=True)

pandoc_path = shutil.which("pandoc")

pytestmark = pytest.mark.skipif(pandoc_path is None, reason="pandoc not installed")


def test_md_to_epub_basic(tmp_path: Path):
    md_file = tmp_path / "sample.md"
    md_file.write_text(textwrap.dedent(
        f"""---\ntitle: Test Doc\nauthor: Test Author\n---\n\n# Heading\n\nSome content with **bold** text and a list.\n\n- Item 1\n- Item 2\n\nIdentifier: {uuid.uuid4()}\n"""
    ), encoding="utf-8")

    out = md_to_epub(md_file)
    assert out.exists()
    assert out.suffix == ".epub"
    # Basic size heuristic (> 1KB) to ensure content & container structure
    assert out.stat().st_size > 1024


def test_md_to_epub_custom_output(tmp_path: Path):
    md_file = tmp_path / "custom.md"
    md_file.write_text("# Title\n\nBody.", encoding="utf-8")
    target = tmp_path / "out" / "book.epub"
    out = md_to_epub(md_file, output_path=target, options=EpubOptions(title="Custom"))
    assert out == target
    assert out.exists()


def test_md_missing_raises(tmp_path: Path):
    missing = tmp_path / "missing.md"
    with pytest.raises(FileNotFoundError):
        md_to_epub(missing)


def test_pandoc_missing(monkeypatch, tmp_path: Path):
    if pandoc_path is None:
        pytest.skip("pandoc already missing in environment")
    # Force _find_pandoc failure by clearing PATH
    from yt2md.email.epub import converter as conv_mod
    monkeypatch.setattr(conv_mod, "_PANDOC_CACHE", {"checked": False, "available": False, "path": None})
    monkeypatch.setenv("PATH", "")
    md_file = tmp_path / "file.md"
    md_file.write_text("# X", encoding="utf-8")
    with pytest.raises(PandocNotAvailableError):
        md_to_epub(md_file)
