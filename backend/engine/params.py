"""Parameter lookup by tax year. The Act is chosen here, from the data, never by the caller or an LLM."""
from __future__ import annotations

from typing import Any

from lawdata.loader import PARAMS_DIR, load_all_param_files
from lawdata.models import ParamFile


class UnsupportedTaxYear(ValueError):
    pass


class ParamSet:
    """The year file for one tax year plus the common settings, with citation lookup."""

    def __init__(self, year_file: ParamFile, common: ParamFile, year_name: str):
        self.year_file = year_file
        self.common = common
        self.version = year_name            # e.g. it2025_ty2026-27.yaml

    @property
    def act_id(self) -> str:
        return self.year_file.act_id.value

    @property
    def rules_id(self) -> str:
        return self.year_file.rules_id.value

    @property
    def tax_year(self) -> int:
        return self.year_file.tax_year

    @property
    def label(self) -> str:
        return self.year_file.label

    def _param(self, key: str):
        if key in self.year_file.params:
            return self.year_file.params[key]
        if key in self.common.params:
            return self.common.params[key]
        raise KeyError(f"unknown parameter {key!r} for {self.version}")

    def has(self, key: str) -> bool:
        return key in self.year_file.params or key in self.common.params

    def get(self, key: str) -> Any:
        return self._param(key).value

    def cite(self, key: str) -> list[str]:
        return list(self._param(key).sources)

    @classmethod
    def for_tax_year(cls, tax_year: int, directory=PARAMS_DIR) -> "ParamSet":
        files = load_all_param_files(directory)
        common = files["common.yaml"]
        for name, pf in files.items():
            if pf.tax_year == tax_year:
                return cls(pf, common, name)
        known = sorted(pf.tax_year for pf in files.values() if pf.tax_year is not None)
        raise UnsupportedTaxYear(f"no parameter file for tax year {tax_year}; available: {known}")

    @classmethod
    def all_years(cls, directory=PARAMS_DIR) -> dict[int, "ParamSet"]:
        files = load_all_param_files(directory)
        return {pf.tax_year: cls(pf, files["common.yaml"], n) for n, pf in files.items() if pf.tax_year is not None}
