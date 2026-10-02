import pytest

from kaching.analysis.sector import resolve_etf, suggest_etf


def info(sector=None, industry=None, quote_type="EQUITY"):
    return {"sector": sector, "industry": industry, "quote_type": quote_type}


def test_industry_beats_sector():
    assert suggest_etf(info("Technology", "Semiconductors")) == ("SMH", "industry")


def test_unmapped_industry_falls_back_to_sector():
    assert suggest_etf(info("Consumer Defensive", "Beverages - Non-Alcoholic")) == ("XLP", "sector")


def test_unknown_sector_has_no_suggestion():
    assert suggest_etf(info("Mystery", "Unknown")) is None
    assert suggest_etf(info()) is None
    assert suggest_etf(None) is None


@pytest.mark.parametrize("quote_type", ["ETF", "MUTUALFUND", "INDEX"])
def test_etfs_and_funds_have_no_sector_etf(quote_type):
    assert suggest_etf(info("Technology", "Semiconductors", quote_type)) is None
    assert resolve_etf("SMH", info("Technology", "Semiconductors", quote_type)) is None


def test_override_wins_and_still_reports_the_suggestion():
    resolved = resolve_etf("WGMI", info("Financial Services", "Capital Markets"))
    assert resolved == {"etf": "WGMI", "source": "override", "suggested": "XLF"}


def test_no_override_uses_suggestion():
    assert resolve_etf(None, info("Technology", "Semiconductors")) == {
        "etf": "SMH", "source": "industry", "suggested": "SMH"}


def test_override_without_any_suggestion():
    assert resolve_etf("BKCH", info()) == {"etf": "BKCH", "source": "override", "suggested": None}
    assert resolve_etf(None, info()) is None
