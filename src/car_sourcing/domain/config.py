"""Configuration métier, lue dans le Google Sheet et validée avant tout run.

Une valeur invalide lève `ConfigError` : le run s'arrête et une alerte technique part,
plutôt que de filtrer avec une configuration fausse.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from car_sourcing.domain.text import normalize, parse_decimal_fr, parse_int

TRUE_VALUES = {"vrai", "true", "oui", "yes", "1", "x"}
FALSE_VALUES = {"faux", "false", "non", "no", "0", ""}


class ConfigError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prix_min_eur: int = Field(ge=0)
    prix_max_eur: int = Field(gt=0)
    km_max: int = Field(gt=0)
    km_par_an_max: int = Field(gt=0)
    vendeur_particulier_uniquement: bool
    taux_frais_pct: float = Field(ge=0, le=100)
    decote_negociation_pct: float = Field(ge=0, le=100)
    cout_transport_eur_km: float = Field(ge=0, le=10)
    base_code_postal: str = Field(pattern=r"^\d{5}$")
    marge_min_eur: int = Field(ge=0)
    marge_prioritaire_eur: int = Field(ge=0)
    comparables_min: int = Field(ge=1, le=100)
    fenetre_comparables_jours: int = Field(ge=7, le=365)
    regime_fiscal: Literal["particulier"]
    mots_cles_exclusion: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _coherence(self) -> Self:
        if self.prix_max_eur <= self.prix_min_eur:
            raise ValueError("prix_max_eur doit être supérieur à prix_min_eur")
        if self.marge_prioritaire_eur < self.marge_min_eur:
            raise ValueError("marge_prioritaire_eur doit être au moins égale à marge_min_eur")
        return self

    @property
    def version(self) -> str:
        """Empreinte stable du contenu : enregistrée avec chaque évaluation."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


_FIELD_KINDS: dict[str, str] = {
    "prix_min_eur": "int",
    "prix_max_eur": "int",
    "km_max": "int",
    "km_par_an_max": "int",
    "vendeur_particulier_uniquement": "bool",
    "taux_frais_pct": "dec",
    "decote_negociation_pct": "dec",
    "cout_transport_eur_km": "dec",
    "base_code_postal": "str",
    "marge_min_eur": "int",
    "marge_prioritaire_eur": "int",
    "comparables_min": "int",
    "fenetre_comparables_jours": "int",
    "regime_fiscal": "str",
}


def _coerce(key: str, raw: str, errors: list[str]) -> object:
    kind = _FIELD_KINDS[key]
    text = raw.strip()
    if kind != "bool" and not text:
        errors.append(f"{key} : valeur manquante")
        return None
    if key == "base_code_postal" and not re.fullmatch(r"\d{5}", text):
        errors.append(f"{key} : « {raw} » n'est pas un code postal à 5 chiffres")
        return None
    if key == "regime_fiscal" and text != "particulier":
        errors.append(f"{key} : seul « particulier » est disponible pour l'instant")
        return None
    if kind == "bool":
        low = normalize(text)
        if low in TRUE_VALUES:
            return True
        if low in FALSE_VALUES:
            return False
        errors.append(f"{key} : « {raw} » n'est pas VRAI ou FAUX")
        return None
    if kind == "int":
        if not re.fullmatch(r"-?[\d\s\u00a0\u202f.]+", text):
            errors.append(f"{key} : « {raw} » n'est pas un nombre entier")
            return None
        return parse_int(text.replace(".", ""))
    if kind == "dec":
        value = parse_decimal_fr(text)
        if value is None:
            errors.append(f"{key} : « {raw} » n'est pas un nombre")
        return value
    return text


def parse_sheet(param_rows: Sequence[Sequence[str]], keyword_rows: Iterable[Sequence[str]]) -> Config:
    """Construit la configuration depuis les onglets `parametres` (clé, valeur) et `mots_cles_exclusion`."""
    errors: list[str] = []
    values: dict[str, object] = {}
    for row in param_rows:
        if not row or not str(row[0]).strip():
            continue
        key = str(row[0]).strip()
        if key.lower() in {"cle", "clé", "parametre", "paramètre"}:
            continue  # ligne d'en-tête
        if key not in _FIELD_KINDS:
            errors.append(f"paramètre inconnu : {key}")
            continue
        raw = str(row[1]) if len(row) > 1 else ""
        values[key] = _coerce(key, raw, errors)
    missing = [k for k in _FIELD_KINDS if k not in values and not any(e.startswith(f"{k} ") for e in errors)]
    errors.extend(f"{k} : valeur manquante" for k in missing)

    seen: set[str] = set()
    keywords: list[str] = []
    for row in keyword_rows:
        if not row:
            continue
        word = str(row[0]).strip()
        if not word or normalize(word) in {"mot-cle", "mot cle", "mots-cles", "mot_cle"}:
            continue
        if normalize(word) not in seen:
            seen.add(normalize(word))
            keywords.append(word)
    if errors:
        raise ConfigError(errors)
    values["mots_cles_exclusion"] = tuple(keywords)
    try:
        return Config.model_validate(values)
    except ValidationError as exc:
        raise ConfigError(
            [f"{'.'.join(str(p) for p in e['loc']) or 'config'} : {e['msg']}" for e in exc.errors()]
        ) from exc


DEFAULT_PARAMETERS: list[tuple[str, str]] = [
    ("prix_min_eur", "2000"),
    ("prix_max_eur", "30000"),
    ("km_max", "200000"),
    ("km_par_an_max", "20000"),
    ("vendeur_particulier_uniquement", "VRAI"),
    ("taux_frais_pct", "10"),
    ("decote_negociation_pct", "6"),
    ("cout_transport_eur_km", "0,30"),
    ("base_code_postal", ""),
    ("marge_min_eur", "1000"),
    ("marge_prioritaire_eur", "2000"),
    ("comparables_min", "5"),
    ("fenetre_comparables_jours", "90"),
    ("regime_fiscal", "particulier"),
]
DEFAULT_KEYWORDS: list[str] = [
    "accidenté",
    "pour pièces",
    "moteur HS",
    "non roulant",
    "sans CT",
    "épave",
    "sinistré",
    "VEI",
    "boîte HS",
    "joint de culasse",
]
