import pytest
from app.strategies.ingestion import (
    clean_text, extract_sections, chunk_text,
    extract_strategy_rules, process_strategy,
)


class TestCleanText:
    def test_removes_extra_whitespace(self):
        result = clean_text("Hello   world  \n\n  test")
        assert "  " not in result

    def test_preserves_meaningful_text(self):
        result = clean_text("Entry when RSI < 30 and price above support")
        assert "RSI" in result
        assert "support" in result


class TestExtractSections:
    def test_heading_detection(self):
        text = "# Entry Rules\nBuy when RSI oversold\n# Exit Rules\nSell when RSI overbought"
        sections = extract_sections(text)
        assert len(sections) >= 2
        titles = [s["title"] for s in sections]
        assert any("Entry" in t for t in titles)

    def test_no_headings(self):
        text = "This is a strategy with no headings."
        sections = extract_sections(text)
        assert len(sections) >= 1


class TestChunkText:
    def test_short_text(self):
        text = "Short strategy."
        chunks = chunk_text(text, max_chunk_size=100, overlap=20)
        assert len(chunks) == 1

    def test_long_text(self):
        text = "Sentence. " * 200
        chunks = chunk_text(text, max_chunk_size=500)
        assert len(chunks) > 1

    def test_no_empty_chunks(self):
        text = "A" * 1000
        chunks = chunk_text(text, max_chunk_size=200, overlap=50)
        assert all(len(c) > 0 for c in chunks)

    def test_rejects_non_positive_max_chunk_size(self):
        with pytest.raises(ValueError):
            chunk_text("test", max_chunk_size=0)

    def test_rejects_negative_overlap(self):
        with pytest.raises(ValueError):
            chunk_text("test", max_chunk_size=200, overlap=-1)

    def test_rejects_overlap_equal_to_chunk_size(self):
        with pytest.raises(ValueError):
            chunk_text("test", max_chunk_size=200, overlap=200)

    def test_rejects_overlap_greater_than_chunk_size(self):
        with pytest.raises(ValueError):
            chunk_text("test", max_chunk_size=200, overlap=250)


class TestExtractStrategyRules:
    def test_entry_rules(self):
        text = "Entry rules: Buy when RSI below 30 and price touches support."
        rules = extract_strategy_rules(text)
        assert len(rules["entry_rules"]) >= 1

    def test_exit_rules(self):
        text = "Exit rules: Take profit at 2:1 risk reward ratio."
        rules = extract_strategy_rules(text)
        assert len(rules["exit_rules"]) >= 1

    def test_indicators(self):
        text = "Use RSI and MACD to confirm entry signals."
        rules = extract_strategy_rules(text)
        assert "rsi" in rules["indicators"]
        assert "macd" in rules["indicators"]

    def test_market_structure(self):
        text = "Look for higher highs and higher low structure."
        rules = extract_strategy_rules(text)
        assert "higher high" in rules["market_structure_requirements"]

    def test_timeframe(self):
        text = "Timeframe: 4H chart for primary analysis."
        rules = extract_strategy_rules(text)
        assert len(rules["timeframe_requirements"]) >= 1


class TestProcessStrategy:
    def test_basic_processing(self):
        text = "# My Strategy\nEntry when RSI < 30.\nExit when RSI > 70."
        result = process_strategy(text, "strategy.txt")
        assert result["source_type"] == "txt"
        assert len(result["sections"]) >= 1
        assert len(result["chunks"]) >= 1
        assert "rules" in result
        assert "metadata" in result

    def test_pdf_type_detection(self):
        text = "Some content"
        result = process_strategy(text, "strategy.pdf")
        assert result["source_type"] == "pdf"

    def test_md_type_detection(self):
        text = "# Strategy"
        result = process_strategy(text, "strategy.md")
        assert result["source_type"] == "md"
