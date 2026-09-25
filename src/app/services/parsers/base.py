from abc import ABC, abstractmethod

from app.schemas.document import ProcessedDocument


class ParseError(Exception):
    def __init__(
        self,
        message: str,
        source_type: str,
        partial_result: ProcessedDocument | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.source_type = source_type
        self.partial_result = partial_result


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        raise NotImplementedError
