from typing import Optional


class Channel:
    def __init__(
        self,
        id: str,
        language_code: str,
        output_language: str,
        category: str,
        name: str,
        title_filters: Optional[list[str]] = None,
        skip_shorts: bool = False,
        is_playlist: Optional[bool] = None,
    ):
        self.id = id
        self.language_code = language_code
        self.output_language = output_language
        self.category = category
        self.name = name
        self.title_filters = title_filters or []
        self.skip_shorts = skip_shorts
        if is_playlist is not None:
            self.is_playlist = bool(is_playlist)
        else:
            self.is_playlist = (
                id.startswith("PL")
                or id.startswith("UU")
                or id.startswith("FL")
                or id.startswith("RD")
                or id.startswith("WL")
                or "list=" in id
                or "playlist" in id
            )
