import re
from typing import Optional


def extract_text_from_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_text(file_path: str, content_type: str = "txt") -> str:
    if content_type == "pdf" or file_path.lower().endswith(".pdf"):
        return extract_text_from_pdf(file_path)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,;:!?()\-+*/=<>\"'$%#@&\[\]{}|\\/`\n]", "", text)
    text = text.strip()
    return text


def extract_sections(text: str) -> list[dict]:
    sections = []
    lines = text.split("\n")
    current_section = {"title": "General", "content": ""}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(#{1,6}\s+|\b[A-Z][A-Z\s]{3,}:?\s*$|^\d+\.\s+[A-Z])", stripped):
            if current_section["content"].strip():
                sections.append(current_section)
            title = re.sub(r"^(#{1,6}\s+|\d+\.\s+)", "", stripped).strip().rstrip(":")
            current_section = {"title": title, "content": ""}
        else:
            current_section["content"] += stripped + " "

    if current_section["content"].strip():
        sections.append(current_section)

    if not sections:
        sections = [{"title": "Full Text", "content": text}]

    return sections


def chunk_text(text: str, max_chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= max_chunk_size:
        raise ValueError("overlap must be less than max_chunk_size")

    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chunk_size
        chunk = text[start:end]

        last_period = chunk.rfind(".")
        if last_period > max_chunk_size * 0.5:
            chunk = chunk[: last_period + 1]
            end = start + last_period + 1

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if c]


def extract_strategy_rules(text: str) -> dict:
    rules = {
        "entry_rules": [],
        "exit_rules": [],
        "confirmation_rules": [],
        "invalidation_rules": [],
        "timeframe_requirements": [],
        "indicators": [],
        "market_structure_requirements": [],
        "risk_rules": [],
        "exceptions": [],
        "terminology": {},
        "examples": [],
    }

    text_lower = text.lower()

    entry_patterns = [
        r"(?:entry|enter|buy|sell|long|short)\s*(?:rules?|conditions?|when|if)[:\s]+([^.!?\n]+[.!?])",
    ]
    for pattern in entry_patterns:
        matches = re.findall(pattern, text_lower)
        rules["entry_rules"].extend(matches[:5])

    exit_patterns = [
        r"(?:exit|close|take profit|take_profit|tp|stop loss|sl|stop_loss)\s*(?:rules?|conditions?|when|if)[:\s]+([^.!?\n]+[.!?])",
    ]
    for pattern in exit_patterns:
        matches = re.findall(pattern, text_lower)
        rules["exit_rules"].extend(matches[:5])

    confirm_patterns = [
        r"(?:confirm|confirmation|validate|verify|check)\s*(?:with|using|by|that)[:\s]+([^.!?\n]+[.!?])",
    ]
    for pattern in confirm_patterns:
        matches = re.findall(pattern, text_lower)
        rules["confirmation_rules"].extend(matches[:5])

    invalidation_patterns = [
        r"(?:invalidat|disqualify|avoid|no trade|do not trade)\s*(?:when|if|if)[:\s]+([^.!?\n]+[.!?])",
    ]
    for pattern in invalidation_patterns:
        matches = re.findall(pattern, text_lower)
        rules["invalidation_rules"].extend(matches[:5])

    tf_patterns = [
        r"(?:timeframe|time frame|tf|chart)\s*(?:is|should be|must be|:)?\s*(\w+)",
    ]
    for pattern in tf_patterns:
        matches = re.findall(pattern, text_lower)
        rules["timeframe_requirements"].extend(matches[:5])

    indicator_keywords = ["rsi", "macd", "ema", "sma", "atr", "bollinger", "stochastic", "cci", "adx", "volume"]
    for kw in indicator_keywords:
        if kw in text_lower:
            rules["indicators"].append(kw)

    structure_keywords = [
        "higher high", "higher low", "lower high", "lower low",
        "break of structure", "bos", "change of character", "choch",
        "support", "resistance", "swing high", "swing low",
    ]
    for kw in structure_keywords:
        if kw in text_lower:
            rules["market_structure_requirements"].append(kw)

    risk_patterns = [
        r"(?:risk|risk per trade|risk management|max risk)[:\s]+([^.!?\n]+[.!?])",
    ]
    for pattern in risk_patterns:
        matches = re.findall(pattern, text_lower)
        rules["risk_rules"].extend(matches[:3])

    return rules


def process_strategy(
    text: str, filename: str
) -> dict:
    cleaned = clean_text(text)
    sections = extract_sections(cleaned)
    chunks = chunk_text(cleaned)
    rules = extract_strategy_rules(cleaned)

    source_type = "txt"
    if filename.lower().endswith(".pdf"):
        source_type = "pdf"
    elif filename.lower().endswith(".md"):
        source_type = "md"

    return {
        "source_type": source_type,
        "original_filename": filename,
        "cleaned_text": cleaned,
        "sections": sections,
        "chunks": chunks,
        "rules": rules,
        "metadata": {
            "total_sections": len(sections),
            "total_chunks": len(chunks),
            "text_length": len(cleaned),
            "extracted_rules": {k: len(v) for k, v in rules.items() if v},
        },
    }
