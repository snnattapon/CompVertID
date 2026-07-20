"""CompVertID — map Compound Discoverer output to KEGG IDs."""

__version__ = "0.1.2"

from .kegg_api import KeggClient
from .core import (
    normalize_formula,
    parse_formula_to_atoms,
    classify_formula_diff,
    clean_name,
    is_lipid_species,
    load_and_validate,
    map_dataframe,
    merge_and_dedupe,
    finalize,
    MissingColumnsError,
)
from .input_loader import (
    load_input,
    load_name_list,
    UnsupportedInputError,
)

__all__ = [
    "KeggClient",
    "normalize_formula",
    "parse_formula_to_atoms",
    "classify_formula_diff",
    "clean_name",
    "is_lipid_species",
    "load_and_validate",
    "map_dataframe",
    "merge_and_dedupe",
    "finalize",
    "MissingColumnsError",
    "load_input",
    "load_name_list",
    "UnsupportedInputError",
]
