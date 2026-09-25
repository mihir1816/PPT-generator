from io import BytesIO

import pdfplumber
import pytesseract
from PIL import Image
from pytesseract import Output

from app.schemas.document import ContentBlock, ContentType, ProcessedDocument, SourceType
from app.services.parsers.base import BaseParser, ParseError

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp"}


def _ocr_image(image: Image.Image) -> tuple[list[ContentBlock], float]:
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    n = len(data["text"])
    grouped: dict[int, list[tuple[int, str]]] = {}
    confidences: list[float] = []
    for i in range(n):
        word = data["text"][i].strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        if not word or conf <= 50:
            continue
        confidences.append(conf)
        block_num = data["block_num"][i]
        line_num = data["line_num"][i]
        key = block_num
        grouped.setdefault(key, []).append((line_num, word))

    blocks: list[ContentBlock] = []
    for block_num in sorted(grouped.keys()):
        words_in_block = grouped[block_num]
        lines: dict[int, list[str]] = {}
        for line_num, word in words_in_block:
            lines.setdefault(line_num, []).append(word)
        text = "\n".join(" ".join(lines[k]) for k in sorted(lines.keys()))
        if text.strip():
            blocks.append(ContentBlock(type=ContentType.PARAGRAPH, text=text.strip()))

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return blocks, avg_conf


class OCRParser(BaseParser):
    def parse(self, file_bytes: bytes, filename: str, **kwargs) -> ProcessedDocument:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        all_blocks: list[ContentBlock] = []
        all_conf: list[float] = []
        page_count = 1

        try:
            if ext == "pdf":
                with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                    page_count = len(pdf.pages)
                    for page in pdf.pages:
                        page_image = page.to_image(resolution=200).original
                        blocks, conf = _ocr_image(page_image)
                        all_blocks.extend(blocks)
                        if conf:
                            all_conf.append(conf)
            else:
                image = Image.open(BytesIO(file_bytes))
                blocks, conf = _ocr_image(image)
                all_blocks.extend(blocks)
                if conf:
                    all_conf.append(conf)
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"OCR failed: {exc}", SourceType.IMAGE_OCR.value) from exc

        avg_confidence = sum(all_conf) / len(all_conf) if all_conf else 0.0
        raw_text = "\n\n".join(b.text for b in all_blocks)

        return ProcessedDocument(
            title=filename,
            source_type=SourceType.IMAGE_OCR,
            raw_text=raw_text,
            blocks=all_blocks,
            metadata={"ocr_confidence_avg": avg_confidence, "page_count": page_count},
        )
