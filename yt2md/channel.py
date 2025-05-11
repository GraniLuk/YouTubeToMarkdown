class Channel:
    def __init__(
        self,
        id: str,
        language_code: str,
        output_language: str,
        category: str,
        name: str,
        title_filters: list = None,
    ):
        self.id = id
        self.language_code = language_code
        self.output_language = output_language
        self.category = category
        self.name = name
        self.title_filters = title_filters or []
