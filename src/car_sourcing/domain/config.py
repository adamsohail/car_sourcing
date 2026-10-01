"""Configuration métier, saisie dans l'interface, versionnée dans BigQuery et validée avant tout run.

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


def parse_rows(param_rows: Sequence[Sequence[str]], keyword_rows: Iterable[Sequence[str]]) -> Config:
    """Construit la configuration depuis des lignes (clé, valeur) et une liste de mots-clés."""
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
        messages = []
        for e in exc.errors():
            where = ".".join(str(p) for p in e["loc"]) or "config"
            messages.append(f"{where} : {str(e['msg']).removeprefix('Value error, ')}")
        raise ConfigError(messages) from exc


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


NO_CONFIG_MESSAGE = (
    "aucun réglage enregistré : ouvrez la page Réglages de l'interface et enregistrez-les une première fois"
)


def _as_text(value: object) -> str:
    if isinstance(value, bool):
        return "VRAI" if value else "FAUX"
    if value is None:
        return ""
    return str(value)


def config_from_payload(payload: dict[str, object]) -> Config:
    """Valide les réglages envoyés par l'interface ou relus dans BigQuery : {params: {...}, keywords: [...]}."""
    params = payload.get("params")
    keywords = payload.get("keywords")
    if not isinstance(params, dict) or not isinstance(keywords, list):
        raise ConfigError(["config : format attendu {params, keywords}"])
    rows = [(str(k), _as_text(v)) for k, v in params.items()]
    return parse_rows(rows, [[str(k)] for k in keywords])


def payload_from_config(config: Config) -> dict[str, object]:
    data = config.model_dump(mode="json")
    keywords = data.pop("mots_cles_exclusion")
    return {"params": data, "keywords": keywords}


def errors_by_field(errors: Sequence[str]) -> dict[str, str]:
    """« taux_frais_pct : … » -> {"taux_frais_pct": "…"} ; les erreurs générales vont sous « config »."""
    out: dict[str, str] = {}
    for error in errors:
        key, sep, message = error.partition(" : ")
        if not sep:
            out.setdefault("config", error)
            continue
        for field in [*_FIELD_KINDS, "mots_cles_exclusion"]:
            if key == field or key.startswith(field):
                out.setdefault(field, message)
                break
        else:
            # Erreurs de cohérence (« prix_max_eur doit être supérieur… ») : le champ cité en premier.
            found = sorted((message.find(f), f) for f in _FIELD_KINDS if f in message)
            field = found[0][1] if found else "config"
            out.setdefault(field, message)
    return out
