"""Data models for CiteTax's "law as data" files.

Three kinds of file are described here:

* the source registry  (corpus/registry.yaml)      -> SourceEntry
* the sources manifest (corpus/sources_manifest.yaml) -> ManifestEntry
* parameter files      (params/*.yaml)              -> ParamFile

Conventions (also written up in params/README.md):

* Tax years are keyed by the calendar year in which they START:
  FY 2025-26 -> 2025, Tax Year 2026-27 -> 2026.
* Money is a whole number of rupees. Percentages are written as a plain
  number of percent (50 means 50%).
* Dates are ISO (YYYY-MM-DD).
* Every value cites at least one source by citation ID, e.g. IT2025:s58(2)/T3.
"""
from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# SOURCE:provision[/part], for example IT2025:s58(2)/T3, RULES2026:r76(7)(a),
# DTAA_US:art15(1)(b), CBDT_FAQ_PRES:Q17, IRC:s861(a)(3)
CITATION_RE = re.compile(r"^[A-Z][A-Z0-9_]*:[A-Za-z0-9_().\-]+(/[A-Za-z0-9_().\-]+)*$")
# dotted lower-case keys, for example presumptive.limit.default
PARAM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ActId(str, Enum):
    IT1961 = "IT1961"
    IT2025 = "IT2025"
    RULES1962 = "RULES1962"
    RULES2026 = "RULES2026"
    FA2025 = "FA2025"
    FA2026 = "FA2026"
    DTAA_US = "DTAA_US"
    IRC = "IRC"
    IRS = "IRS"
    CBDT = "CBDT"
    CGST = "CGST"


class DocType(str, Enum):
    statute = "statute"
    rule = "rule"
    notification = "notification"
    form = "form"
    faq = "faq"
    treaty = "treaty"
    protocol = "protocol"
    mou = "mou"
    us_statute = "us_statute"
    us_guidance = "us_guidance"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceEntry(_Strict):
    """One row of the source registry: one source file and its tags."""

    id: str
    # Namespace used in citation IDs (prefix before the colon). Several files may share one.
    cite_prefix: str
    file: str
    title: str
    act_id: ActId
    doc_type: DocType
    # 1 statute and rules; 2 notifications and forms; 3 treaty and protocol;
    # 4 guidance (CBDT FAQs, IRS publications, technical explanation);
    # 5 secondary commentary (never cited as authority).
    authority_rank: int = Field(ge=1, le=5)
    # First and last tax year (start-year key) the document applies to.
    # None means open-ended on that side.
    tax_year_first: Optional[int] = None
    tax_year_last: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    publisher: str
    note: Optional[str] = None

    @field_validator("id", "cite_prefix")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not SOURCE_ID_RE.match(v):
            raise ValueError(f"{v!r} must be UPPER_SNAKE_CASE")
        return v


class ManifestEntry(_Strict):
    """One row of the sources manifest: where a file came from, and its checksum."""

    id: str
    file: str
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    url: Optional[str] = None
    url_note: Optional[str] = None


class Status(str, Enum):
    verified = "verified"            # read from the primary text in sources/
    secondary = "secondary"          # supported only by secondary sources
    to_verify = "to_verify"          # not yet checked against the primary text
    design_choice = "design_choice"  # a product setting, not law (no citation needed)


class Param(_Strict):
    """One value in a parameter file, with its evidence."""

    value: Any
    unit: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    status: Status
    note: Optional[str] = None
    verified_by: list[str] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def _citation_format(cls, v: list[str]) -> list[str]:
        for c in v:
            if not CITATION_RE.match(c):
                raise ValueError(f"bad citation ID {c!r}; expected SOURCE:provision[/part]")
        return v

    @model_validator(mode="after")
    def _needs_a_source_unless_design_choice(self) -> "Param":
        if self.status != Status.design_choice and not self.sources:
            raise ValueError("a parameter that is not a design_choice needs at least one source")
        return self


class ConcordanceKind(str, Enum):
    section = "section"
    rule = "rule"
    form = "form"


class ConcordanceEntry(_Strict):
    """Maps a provision of the old regime to the provision that replaces it.

    One old provision may map to several new ones, and several old ones may map
    to one new one (for example s.234B and s.234C both map to s.425).
    """

    old_ref: str
    new_ref: str
    kind: ConcordanceKind
    topic: str
    status: Status
    verified_by: list[str] = Field(default_factory=list)
    note: Optional[str] = None

    @field_validator("old_ref", "new_ref")
    @classmethod
    def _citation_format(cls, v: str) -> str:
        if not CITATION_RE.match(v):
            raise ValueError(f"bad citation ID {v!r}; expected SOURCE:provision[/part]")
        return v


ASSUMPTION_ID_RE = re.compile(r"^A-\d+$")


class AssumptionStatus(str, Enum):
    resolved = "resolved"    # the sources settle it; the flag is only a safety switch
    contested = "contested"  # the sources do not settle it; the interface must show both readings


class Reading(_Strict):
    """One possible interpretation of a point the sources leave open."""

    key: str
    statement: str
    citations: list[str] = Field(default_factory=list)
    flag_value: Any  # the value config_flag takes if this reading is applied

    @field_validator("citations")
    @classmethod
    def _citation_format(cls, v: list[str]) -> list[str]:
        for c in v:
            if not CITATION_RE.match(c):
                raise ValueError(f"bad citation ID {c!r}; expected SOURCE:provision[/part]")
        return v


class Assumption(_Strict):
    """A documented, conservative position on a point of law the sources do not settle."""

    id: str
    question: str
    status: AssumptionStatus
    readings: list[Reading] = Field(min_length=1)
    default: str                 # key of the reading applied by default
    default_reason: str          # why this default is the conservative one
    config_flag: str
    config_default: Any
    used_by: list[str] = Field(default_factory=list)   # parameter keys this assumption affects
    secondary_references: list[str] = Field(default_factory=list)
    note: Optional[str] = None

    @field_validator("id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not ASSUMPTION_ID_RE.match(v):
            raise ValueError(f"assumption id {v!r} must look like A-5")
        return v

    @field_validator("config_flag")
    @classmethod
    def _flag_format(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"config flag {v!r} must be lower_snake_case")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> "Assumption":
        keys = [r.key for r in self.readings]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate reading keys")
        if self.default not in keys:
            raise ValueError(f"default {self.default!r} is not one of the readings {keys}")
        chosen = next(r for r in self.readings if r.key == self.default)
        if chosen.flag_value != self.config_default:
            raise ValueError("config_default must equal the default reading's flag_value")
        if self.status == AssumptionStatus.contested and len(self.readings) < 2:
            raise ValueError("a contested assumption needs at least two readings")
        return self


class ParamScope(str, Enum):
    india_tax_year = "india_tax_year"  # one file per Act and tax year; all such files share one key set
    common = "common"                  # treaty, US, GST and product settings; not tied to an Act


class ParamFile(_Strict):
    """Law data for one Act and one tax year, or the common (year-independent) settings."""

    scope: ParamScope = ParamScope.india_tax_year
    act_id: Optional[ActId] = None
    rules_id: Optional[ActId] = None
    label: str
    tax_year: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    params: dict[str, Param]

    @model_validator(mode="after")
    def _year_files_need_identity(self) -> "ParamFile":
        if self.scope == ParamScope.india_tax_year:
            missing = [n for n in ("act_id", "rules_id", "tax_year", "valid_from") if getattr(self, n) is None]
            if missing:
                raise ValueError(f"an india_tax_year file needs {', '.join(missing)}")
        return self

    @field_validator("params")
    @classmethod
    def _key_format(cls, v: dict[str, Param]) -> dict[str, Param]:
        for k in v:
            if not PARAM_KEY_RE.match(k):
                raise ValueError(f"bad parameter key {k!r}; use dotted lower_snake_case")
        return v
