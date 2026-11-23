"""Phase C: corpus chunk files, citation resolution and coverage (no database needed)."""
from lawdata.chunks import Chunk, Resolver, load_all_chunks
from lawdata.loader import load_registry
from lawdata.validate import check_chunks, chunk_coverage, cited_ids

CHUNKS = load_all_chunks()
BY_ID = {c.id: c for c in CHUNKS}


def _chunk(cid: str, text: str = "x", **kw) -> Chunk:
    return Chunk(id=cid, source_id=cid.split(":")[0], breadcrumb="b", text=text, authority_rank=1, **kw)


def test_chunk_files_are_consistent():
    assert check_chunks() == []


def test_every_cited_id_resolves_to_a_chunk():
    assert len(cited_ids()) > 100
    assert chunk_coverage() == []


def test_no_chunk_mixes_the_two_acts():
    for c in CHUNKS:
        if c.id.startswith("IT1961:"):
            assert c.tax_year_last == 2025 and c.tax_year_first is None, c.id
        if c.id.startswith("IT2025:"):
            assert c.tax_year_first == 2026 and c.tax_year_last is None, c.id


def test_finance_act_passages_are_tagged_to_one_act_year():
    assert (BY_ID["FA2026:s2(6)"].tax_year_first, BY_ID["FA2026:s2(6)"].tax_year_last) == (2025, 2025)
    assert (BY_ID["FA2026:s3(15)"].tax_year_first, BY_ID["FA2026:s3(15)"].tax_year_last) == (2026, 2026)


def test_tables_are_typed_by_hand():
    tables = [c for c in CHUNKS if c.is_table]
    assert {"IT2025:s58(2)/T3", "IT2025:s263(1)/T3", "FA2026:sch1-partIB-paraA(I)"} <= {c.id for c in tables}
    assert all(c.extraction.value != "auto" for c in tables)


def test_key_passages_say_what_the_engine_relies_on():
    assert "50% of the gross receipts" in BY_ID["IT2025:s58(2)/T3"].text
    assert "fifty lakh" in BY_ID["IT1961:s44ADA(1)"].text
    assert "90 days" in BY_ID["DTAA_US:art15(1)"].text
    assert "31st August" in BY_ID["IT2025:s263(1)/T3"].text
    assert "information technology" in BY_ID["IT2025:s62(4)"].text


def test_every_registry_source_in_scope_has_chunks():
    prefixes = {c.id.split(":")[0] for c in CHUNKS}
    for s in load_registry():
        if s.id in {"IRS_F8833", "IRS_1099", "CBDT_FAQ_TRANS", "FA2025"}:
            continue  # in the registry, not needed by any citation yet
        assert s.cite_prefix in prefixes, s.id


# ---- resolver rules (synthetic chunks)

def test_resolver_exact_and_covers():
    r = Resolver([_chunk("IT2025:s58(2)/T3", covers=["IT2025:s58(2)/T3(a)"])])
    assert r.resolve("IT2025:s58(2)/T3").id == "IT2025:s58(2)/T3"
    assert r.resolve("IT2025:s58(2)/T3(a)").id == "IT2025:s58(2)/T3"
    assert r.resolve("IT2025:s58(2)/T4") is None


def test_resolver_ancestor_and_all():
    r = Resolver([_chunk("IT2025:s408(2)"), _chunk("FORM44:p1")])
    assert r.resolve("IT2025:s408").id == "IT2025:s408(2)"
    assert r.resolve("FORM44:all").id == "FORM44:p1"
    assert r.resolve("FORM67:all") is None
    assert r.resolve("IT2025:s40") is None  # a prefix of the digits is not an ancestor


def test_resolver_descendant_needs_the_label_in_the_text():
    r = Resolver([_chunk("RULES2026:r164(6)", text="(a) has assets outside India; (c) has income from outside India")])
    assert r.resolve("RULES2026:r164(6)(c)") is not None
    assert r.resolve("RULES2026:r164(6)(z)") is None
