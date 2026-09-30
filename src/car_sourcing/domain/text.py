"""Normalisation de texte et recherche de mots-clés (insensible à la casse et aux accents)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_SPACES = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces uniques. Sert aux comparaisons (marque, modèle, mots-clés)."""
    return _SPACES.sub(" ", strip_accents(text).lower()).strip()


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(part) for part in normalize(keyword).split(" "))
    # Mots entiers : ni lettre ni chiffre de part et d'autre.
    return re.compile(rf"(?<![^\W_]){body}(?![^\W_])")


def find_keyword(texts: Iterable[str | None], keywords: Iterable[str]) -> str | None:
    """Renvoie le premier mot-clé trouvé (dans l'ordre de la liste), ou None."""
    haystacks = [normalize(t) for t in texts if t]
    for keyword in keywords:
        if not normalize(keyword):
            continue
        pattern = _keyword_pattern(keyword)
        if any(pattern.search(h) for h in haystacks):
            return keyword
    return None


def parse_int(value: object) -> int | None:
    """Extrait un entier d'une valeur comme '12 500 €', '78 000 km', 2019 ou '2019'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    digits = re.sub(r"[^\d]", "", str(value).split(",")[0])
    return int(digits) if digits else None


def parse_decimal_fr(value: object) -> float | None:
    """'0,30' -> 0.3 ; '10' -> 10.0 ; '' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"[\s\u00a0\u202f€%]", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


_FUEL_ALIASES: dict[str, str] = {
    "essence": "Essence",
    "sp95": "Essence",
    "sp98": "Essence",
    "petrol": "Essence",
    "gasoline": "Essence",
    "diesel": "Diesel",
    "gazole": "Diesel",
    "gasoil": "Diesel",
    "hybride": "Hybride",
    "hybrid": "Hybride",
    "hybride rechargeable": "Hybride",
    "electrique": "Électrique",
    "electric": "Électrique",
    "electricite": "Électrique",
    "gpl": "GPL",
    "bicarburation essence gpl": "GPL",
    "bi-fuel": "GPL",
    "lpg": "GPL",
}


def normalize_fuel(value: str | None) -> str | None:
    if not value:
        return None
    key = normalize(value)
    if key in _FUEL_ALIASES:
        return _FUEL_ALIASES[key]
    for alias, canonical in _FUEL_ALIASES.items():
        if alias in key:
            return canonical
    return "Autre"


def normalize_gearbox(value: str | None) -> str | None:
    if not value:
        return None
    key = normalize(value)
    if key.startswith("auto") or "automatique" in key or key in {"a", "bva", "dsg", "edc", "eat8", "cvt"}:
        return "Automatique"
    if key.startswith("manu") or key in {"m", "bvm"}:
        return "Manuelle"
    return None
