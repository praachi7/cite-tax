"""Reference detection and concordance mapping (no database)."""
from retrieval.db import id_terms
from retrieval.refs import detect
from retrieval.search import fuse


def targets(q: str, year: int) -> list[str]:
    return detect(q, year).targets


def test_old_section_number_maps_to_the_2025_act():
    assert "IT2025:s58(2)/T3" in targets("What is the 44ADA limit?", 2026)


def test_new_section_number_maps_back_to_the_1961_act():
    t = targets("section 58 presumptive scheme", 2025)
    assert "IT1961:s44ADA" in t
    assert not any(x.startswith("IT2025:") for x in t)


def test_same_number_in_the_years_own_act_is_kept():
    assert targets("rebate u/s 87A", 2025) == ["IT1961:s87A"]


def test_rules_and_forms_follow_the_year():
    assert "RULES2026:r76" in targets("rule 128 foreign tax credit", 2026)
    assert targets("Do I need Form 67?", 2026) == ["FORM44:all"]
    assert targets("Do I need Form 44?", 2025) == ["FORM67:all"]


def test_treaty_articles_are_detected():
    assert targets("Article 15 and the 90 day rule", 2026) == ["DTAA_US:art15"]


def test_ordinals_and_amounts_are_not_sections():
    assert targets("I worked 1st to 30th June and earned 50L", 2026) == []


def test_id_terms_make_section_numbers_searchable():
    assert id_terms("IT2025:s58(2)/T3").split() == ["IT2025", "s58", "2", "T3", "58"]


def test_rank_fusion_rewards_agreement():
    fused = fuse({"exact": ["a"], "dense": ["b", "a"], "keyword": ["b"]})
    assert fused["a"][1] == {"exact": 1, "dense": 2}
    assert fused["b"][0] > fused["a"][0]  # two first places beat a first and a second
