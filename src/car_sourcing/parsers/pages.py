"""Parsers des pages d'annonce.

Priorité aux données structurées embarquées dans la page :
- Leboncoin : JSON d'hydratation Next.js (`__NEXT_DATA__`), objet annonce avec `list_id`, `attributes`, `owner`.
- La Centrale et repli général : JSON-LD (`Car`, `Vehicle`, `Product`, `Offer`).
Aucune donnée structurée exploitable : `PageParseError`.
"""

from __future__ import annotations

from typing import Any

from car_sourcing.domain.models import Source
from car_sourcing.domain.text import normalize, normalize_fuel, normalize_gearbox, parse_decimal_fr, parse_int
from car_sourcing.parsers.base import (
    PageDetails,
    PageParseError,
    iter_dicts,
    json_ld,
    ld_types,
    script_json,
    soup_of,
    text_of,
)

VEHICLE_TYPES = {"Car", "Vehicle", "Product", "IndividualProduct", "Motorcycle"}


def _year(value: Any) -> int | None:
    n = parse_int(str(value)[:4]) if value is not None else None
    return n if n and 1950 <= n <= 2100 else None


def _seller(value: Any) -> str | None:
    if value is None:
        return None
    v = normalize(str(value))
    if v in {"pro", "professional", "professionnel", "autodealer", "organization", "cardealer", "part_pro"}:
        return "pro"
    if v in {"private", "particulier", "part", "person", "individual"}:
        return "particulier"
    return None


def _from_json_ld(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    vehicle = next((d for d in items if ld_types(d) & VEHICLE_TYPES), None)
    if vehicle is None:
        return out
    offers = vehicle.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else offers if isinstance(offers, dict) else {}
    seller = offer.get("seller") if isinstance(offer, dict) else None
    mileage = vehicle.get("mileageFromOdometer")
    area = offer.get("availableAtOrFrom") if isinstance(offer, dict) else None
    address = (area or {}).get("address") if isinstance(area, dict) else None
    image = vehicle.get("image")
    out.update(
        title=text_of(vehicle.get("name")),
        brand=text_of(vehicle.get("brand") or vehicle.get("manufacturer")),
        model=text_of(vehicle.get("model")),
        version=text_of(vehicle.get("vehicleConfiguration")),
        year=_year(
            vehicle.get("vehicleModelDate")
            or vehicle.get("productionDate")
            or vehicle.get("dateVehicleFirstRegistered")
        ),
        mileage_km=parse_int(mileage.get("value") if isinstance(mileage, dict) else mileage),
        fuel=normalize_fuel(text_of(vehicle.get("fuelType"))),
        gearbox=normalize_gearbox(text_of(vehicle.get("vehicleTransmission"))),
        price_eur=parse_int(offer.get("price")) if isinstance(offer, dict) else None,
        seller_type=_seller(text_of(ld_types(seller).pop()) if isinstance(seller, dict) else None),
        description=text_of(vehicle.get("description")),
        photo_url=text_of(image) if not isinstance(image, dict) else text_of(image.get("url")),
    )
    if isinstance(address, dict):
        out.update(
            city=text_of(address.get("addressLocality")), postal_code=text_of(address.get("postalCode"))
        )
    return out


def _lbc_ad(data: Any) -> dict[str, Any] | None:
    return next(
        (d for d in iter_dicts(data) if "list_id" in d and ("subject" in d or "attributes" in d)), None
    )


def _lbc_attributes(ad: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attrs = ad.get("attributes") or []
    return {str(a.get("key")): a for a in attrs if isinstance(a, dict) and a.get("key")}


def _attr(attrs: dict[str, dict[str, Any]], *keys: str, label: bool = False) -> str | None:
    for k in keys:
        a = attrs.get(k)
        if a:
            return text_of(a.get("value_label") if label and a.get("value_label") else a.get("value"))
    return None


def parse_leboncoin_page(html: str) -> PageDetails:
    soup = soup_of(html)
    ad = _lbc_ad(script_json(soup, "__NEXT_DATA__"))
    fields: dict[str, Any] = {}
    if ad is not None:
        attrs = _lbc_attributes(ad)
        price = ad.get("price")
        loc = ad.get("location") or {}
        owner = ad.get("owner") or {}
        images = ad.get("images") or {}
        urls = (images.get("urls_large") or images.get("urls") or []) if isinstance(images, dict) else []
        fields = {
            "title": text_of(ad.get("subject")),
            "description": ad.get("body") if isinstance(ad.get("body"), str) else None,
            "price_eur": parse_int(price[0] if isinstance(price, list) and price else price),
            "brand": _attr(attrs, "brand", "u_car_brand", label=True),
            "model": _attr(attrs, "model", "u_car_model", label=True),
            "version": _attr(attrs, "u_car_version", "vehicle_version", "version", label=True),
            "year": _year(_attr(attrs, "regdate", "vehicle_regdate")),
            "mileage_km": parse_int(_attr(attrs, "mileage", "vehicle_mileage")),
            "fuel": normalize_fuel(_attr(attrs, "fuel", "vehicle_fuel", label=True)),
            "gearbox": normalize_gearbox(_attr(attrs, "gearbox", "vehicle_gearbox", label=True)),
            "seller_type": _seller(owner.get("type") if isinstance(owner, dict) else None),
            "city": text_of(loc.get("city")) if isinstance(loc, dict) else None,
            "postal_code": text_of(loc.get("zipcode")) if isinstance(loc, dict) else None,
            "lat": parse_decimal_fr(loc.get("lat")) if isinstance(loc, dict) else None,
            "lon": parse_decimal_fr(loc.get("lng")) if isinstance(loc, dict) else None,
            "photo_url": text_of(urls[0]) if urls else None,
        }
    ld = _from_json_ld(json_ld(soup))
    merged = {k: fields.get(k) if fields.get(k) is not None else ld.get(k) for k in set(fields) | set(ld)}
    if not any(merged.get(k) is not None for k in ("price_eur", "year", "mileage_km", "description")):
        raise PageParseError(Source.LEBONCOIN, "aucune donnée structurée d'annonce dans la page")
    return PageDetails(**merged)


def parse_lacentrale_page(html: str) -> PageDetails:
    soup = soup_of(html)
    fields = _from_json_ld(json_ld(soup))
    # Données d'hydratation éventuelles : type de vendeur et localisation.
    for script in soup.find_all("script"):
        body = script.string or ""
        if "customerType" not in body and "zipCode" not in body:
            continue
        low = body.lower()
        if fields.get("seller_type") is None:
            if '"customertype":"pro"' in low.replace(" ", ""):
                fields["seller_type"] = "pro"
            elif '"customertype":"part' in low.replace(" ", ""):
                fields["seller_type"] = "particulier"
    if not any(fields.get(k) is not None for k in ("price_eur", "year", "mileage_km")):
        raise PageParseError(Source.LACENTRALE, "aucune donnée structurée d'annonce dans la page")
    return PageDetails(**fields)


def parse_page(source: Source, html: str) -> PageDetails:
    if source is Source.LEBONCOIN:
        return parse_leboncoin_page(html)
    if source is Source.LACENTRALE:
        return parse_lacentrale_page(html)
    raise PageParseError(source, "source sans parser de page")
