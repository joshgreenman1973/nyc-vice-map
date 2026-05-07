#!/usr/bin/env python3
"""Build merged GeoJSON + CSV of NYC liquor stores, legal cannabis dispensaries,
and licensed tobacco / e-cig retailers.

Sources (all public, no auth):
  - NYS Liquor Authority "Current Liquor Authority Active Licenses" (data.ny.gov, 9s3h-dpkz)
  - NYS Office of Cannabis Management "Current OCM Licenses" (data.ny.gov, jskf-tt3q)
  - NYC DCWP "Legally Operating Businesses" (data.cityofnewyork.us, w7w3-xahh)

Geocoding: NYC Department of City Planning GeoSearch (no key, NYC-tuned).

Outputs:
  docs/data/locations.geojson
  docs/data/locations.csv
  docs/data/methodology.json
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

NYC_COUNTIES = {"New York", "Kings", "Queens", "Bronx", "Richmond"}
COUNTY_TO_BOROUGH = {
    "New York": "Manhattan",
    "Kings": "Brooklyn",
    "Queens": "Queens",
    "Bronx": "Bronx",
    "Richmond": "Staten Island",
}

UA = "nyc-vice-map/1.0 (+https://github.com/vitalcity-nyc/nyc-vice-map)"


def fetch_json(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def paginate(base: str, page_size: int = 50000):
    """Yield rows from a Socrata endpoint, paginating with $limit/$offset."""
    offset = 0
    while True:
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}$limit={page_size}&$offset={offset}"
        batch = fetch_json(url)
        if not batch:
            break
        for row in batch:
            yield row
        if len(batch) < page_size:
            break
        offset += page_size


# ------------------------------- SLA liquor stores ---------------------------

SLA_LIQUOR_TYPES = {"Liquor Store", "Wine Store"}
SLA_BEER_TYPES = {"Grocery Store", "Drug Store"}


def _sla_row(r, category):
    geo = r.get("georeference") or {}
    coords = geo.get("coordinates") if geo.get("type") == "Point" else None
    lon, lat = (coords[0], coords[1]) if coords else (None, None)
    addr_parts = [r.get("actualaddressofpremises", ""), r.get("city", ""), "NY", r.get("zipcode", "")]
    return {
        "id": f"sla:{r.get('licensepermitid','')}",
        "category": category,
        "subcategory": r.get("description", ""),
        "name": r.get("legalname", "").title(),
        "address": ", ".join(p for p in addr_parts if p),
        "address_query": f"{r.get('actualaddressofpremises','')}, {r.get('city','')}, NY {r.get('zipcode','')}",
        "borough": COUNTY_TO_BOROUGH.get(r.get("premisescounty", ""), ""),
        "zip": r.get("zipcode", ""),
        "license_id": r.get("licensepermitid", ""),
        "license_status": "Active",
        "expiration_date": (r.get("expirationdate") or "")[:10],
        "lat": lat,
        "lon": lon,
        "source": "NYS Liquor Authority",
        "source_url": "https://data.ny.gov/d/9s3h-dpkz",
    }


def pull_sla(types, category, label):
    print(f"[{label}] pulling SLA active licenses...", file=sys.stderr)
    type_list = ",".join(f"'{t}'" for t in sorted(types))
    where = (
        f"description in ({type_list}) AND "
        "premisescounty in ('New York','Kings','Queens','Bronx','Richmond')"
    )
    base = (
        "https://data.ny.gov/resource/9s3h-dpkz.json?"
        f"$where={urllib.parse.quote(where)}"
    )
    rows = list(paginate(base))
    print(f"[{label}] {len(rows)} rows", file=sys.stderr)
    return [_sla_row(r, category) for r in rows]


def pull_liquor():
    return pull_sla(SLA_LIQUOR_TYPES, "liquor", "liquor")


def pull_beer():
    return pull_sla(SLA_BEER_TYPES, "beer", "beer")


# ------------------------------- OCM cannabis --------------------------------

CANNABIS_RETAIL_TYPES = {
    "Adult-Use Retail Dispensary License",
    "Adult-Use Conditional Retail Dispensary License",
    "Conditional Adult-Use Retail Dispensary License",
    "Adult-Use Microbusiness License",
    "Adult-Use Registered Organization Dispensary License",
}


def pull_cannabis():
    print("[cannabis] pulling OCM licenses...", file=sys.stderr)
    base = "https://data.ny.gov/resource/jskf-tt3q.json"
    rows = list(paginate(base))
    print(f"[cannabis] {len(rows)} total OCM rows", file=sys.stderr)
    out = []
    for r in rows:
        if r.get("license_type") not in CANNABIS_RETAIL_TYPES:
            continue
        if r.get("license_status") != "Active":
            continue
        if r.get("county") not in NYC_COUNTIES:
            continue
        # microbusinesses must have retail activity flagged
        if r.get("license_type") == "Adult-Use Microbusiness License":
            if r.get("retail_activities_sales_with") != "1" and r.get("retail_activities_sales_no") != "1":
                continue
        addr = r.get("address_line_1", "")
        addr2 = r.get("address_line_2", "") or ""
        city = r.get("city", "")
        zip_ = r.get("zip_code", "")
        full_addr = ", ".join(p for p in [addr, addr2, city, "NY", zip_] if p)
        out.append({
            "id": f"ocm:{r.get('license_number') or r.get('application_number','')}",
            "category": "cannabis",
            "subcategory": r.get("license_type", ""),
            "name": (r.get("dba") or r.get("entity_name") or "").strip(),
            "address": full_addr,
            "address_query": f"{addr}, {city}, NY {zip_}",
            "borough": COUNTY_TO_BOROUGH.get(r.get("county", ""), ""),
            "zip": zip_,
            "license_id": r.get("license_number", ""),
            "license_status": r.get("license_status", ""),
            "operational_status": r.get("operational_status", ""),
            "opened": (r.get("retail_date_opened_to_public") or "")[:10],
            "lat": None,
            "lon": None,
            "source": "NYS Office of Cannabis Management",
            "source_url": "https://data.ny.gov/d/jskf-tt3q",
        })
    print(f"[cannabis] {len(out)} active NYC retail rows", file=sys.stderr)
    return out


# ------------------------------- DCWP tobacco --------------------------------

def _to_float(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def pull_tobacco():
    """Pull DCWP tobacco + e-cig licenses, then dedupe by address.

    A single storefront can hold both a Tobacco Retail Dealer and an Electronic
    Cigarette Dealer license. Without dedup, that storefront appears twice on
    the map. We collapse co-located licenses into one feature with a combined
    subcategory ("Tobacco + e-cigarette").
    """
    from collections import defaultdict

    print("[tobacco] pulling DCWP licenses...", file=sys.stderr)
    where = (
        "license_status in ('Active','Ready for Renewal') AND "
        "business_category in ('Tobacco Retail Dealer','Electronic Cigarette Dealer')"
    )
    base = (
        "https://data.cityofnewyork.us/resource/w7w3-xahh.json?"
        f"$where={urllib.parse.quote(where)}"
    )
    rows = list(paginate(base))
    print(f"[tobacco] {len(rows)} raw license rows", file=sys.stderr)

    # Group by normalized address. Use BBL when available (most reliable);
    # otherwise normalized building + street + zip.
    def addr_key(r):
        bbl = (r.get("bbl") or "").strip()
        if bbl and bbl != "0":
            return ("bbl", bbl)
        building = (r.get("address_building") or "").strip().upper()
        street = (r.get("address_street_name") or "").strip().upper()
        zip_ = (r.get("address_zip") or "").strip()
        return ("addr", building, street, zip_)

    grouped = defaultdict(list)
    for r in rows:
        grouped[addr_key(r)].append(r)

    out = []
    for key, group in grouped.items():
        cats = sorted({r.get("business_category", "") for r in group})
        if len(cats) > 1:
            subcategory = "Tobacco + e-cigarette"
        else:
            subcategory = cats[0]

        # Prefer a record with valid coordinates as the canonical row
        primary = next(
            (r for r in group if _to_float(r.get("latitude")) and _to_float(r.get("longitude"))),
            group[0],
        )
        lat = _to_float(primary.get("latitude"))
        lon = _to_float(primary.get("longitude"))
        building = primary.get("address_building", "") or ""
        street = primary.get("address_street_name", "") or ""
        addr_line = (building + " " + street).strip()
        city = primary.get("address_city", "") or ""
        zip_ = primary.get("address_zip", "") or ""

        license_ids = "; ".join(sorted(r.get("license_nbr", "") for r in group if r.get("license_nbr")))
        statuses = sorted({r.get("license_status", "") for r in group if r.get("license_status")})

        out.append({
            "id": f"dcwp:{primary.get('license_nbr','')}",
            "category": "tobacco",
            "subcategory": subcategory,
            "name": (primary.get("dba_trade_name") or primary.get("business_name") or "").strip(),
            "address": ", ".join(p for p in [addr_line, city, "NY", zip_] if p),
            "address_query": f"{addr_line}, {city}, NY {zip_}",
            "borough": (primary.get("address_borough") or "").title(),
            "zip": zip_,
            "license_id": license_ids,
            "license_count": len(group),
            "license_status": ", ".join(statuses),
            "expiration_date": (primary.get("lic_expir_dd") or "")[:10],
            "lat": lat,
            "lon": lon,
            "source": "NYC Department of Consumer and Worker Protection",
            "source_url": "https://data.cityofnewyork.us/d/w7w3-xahh",
        })
    print(f"[tobacco] {len(out)} unique storefronts (after dedup)", file=sys.stderr)
    return out


# ------------------------------- Geocoding -----------------------------------

GEOCACHE_PATH = ROOT / "data" / "geocache.json"


def load_geocache():
    if GEOCACHE_PATH.exists():
        return json.loads(GEOCACHE_PATH.read_text())
    return {}


def save_geocache(cache):
    GEOCACHE_PATH.write_text(json.dumps(cache, indent=0))


def geocode(addr: str, cache: dict):
    key = addr.strip().upper()
    if key in cache:
        return cache[key]
    url = (
        "https://geosearch.planninglabs.nyc/v2/search?size=1&text="
        + urllib.parse.quote(addr)
    )
    try:
        data = fetch_json(url, timeout=30)
        feats = data.get("features") or []
        if feats:
            lon, lat = feats[0]["geometry"]["coordinates"]
            cache[key] = [lat, lon]
        else:
            cache[key] = None
    except Exception as e:  # noqa: BLE001
        print(f"  geocode error for {addr!r}: {e}", file=sys.stderr)
        cache[key] = None
    return cache[key]


def geocode_missing(rows):
    cache = load_geocache()
    needed = [r for r in rows if r.get("lat") is None or r.get("lon") is None]
    print(f"[geocode] {len(needed)} rows need geocoding", file=sys.stderr)
    hits = 0
    for i, r in enumerate(needed, 1):
        result = geocode(r["address_query"], cache)
        if result:
            r["lat"], r["lon"] = result
            hits += 1
        if i % 100 == 0:
            print(f"  geocoded {i}/{len(needed)} (hits {hits})", file=sys.stderr)
            save_geocache(cache)
        # be polite — GeoSearch is free; 50ms between calls
        if i % 20 == 0:
            time.sleep(0.05)
    save_geocache(cache)
    print(f"[geocode] {hits}/{len(needed)} successfully geocoded", file=sys.stderr)
    return rows


# ------------------------------- Output --------------------------------------

CSV_FIELDS = [
    "id", "category", "subcategory", "name", "address", "borough", "zip",
    "license_id", "license_status", "lat", "lon", "source", "source_url",
]


def write_outputs(rows, counts):
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {k: r.get(k) for k in r if k not in {"lat", "lon", "address_query"}},
            }
            for r in rows
            if r.get("lat") and r.get("lon")
        ],
    }
    (OUT / "locations.geojson").write_text(json.dumps(geo))
    print(f"[write] {len(geo['features'])} features -> locations.geojson", file=sys.stderr)

    with (OUT / "locations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("[write] locations.csv", file=sys.stderr)

    methodology = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
        "mapped_features": len(geo["features"]),
        "sources": [
            {
                "category": "Liquor stores",
                "name": "Current Liquor Authority Active Licenses",
                "agency": "New York State Liquor Authority",
                "endpoint": "https://data.ny.gov/d/9s3h-dpkz",
                "filter": "description IN ('Liquor Store','Wine Store') AND county in 5 NYC boroughs",
                "geocoding": "Built-in georeference field",
            },
            {
                "category": "Beer (groceries / delis / drug stores)",
                "name": "Current Liquor Authority Active Licenses",
                "agency": "New York State Liquor Authority",
                "endpoint": "https://data.ny.gov/d/9s3h-dpkz",
                "filter": "description IN ('Grocery Store','Drug Store') AND county in 5 NYC boroughs",
                "geocoding": "Built-in georeference field",
            },
            {
                "category": "Legal cannabis dispensaries",
                "name": "Current OCM Licenses",
                "agency": "New York State Office of Cannabis Management",
                "endpoint": "https://data.ny.gov/d/jskf-tt3q",
                "filter": "license_type in adult-use retail/microbusiness/RO dispensary types AND license_status='Active' AND county in 5 NYC boroughs",
                "geocoding": "NYC DCP GeoSearch (https://geosearch.planninglabs.nyc)",
            },
            {
                "category": "Tobacco / e-cigarette retailers",
                "name": "Legally Operating Businesses",
                "agency": "NYC Department of Consumer and Worker Protection",
                "endpoint": "https://data.cityofnewyork.us/d/w7w3-xahh",
                "filter": "business_category IN ('Tobacco Retail Dealer','Electronic Cigarette Dealer') AND license_status in ('Active','Ready for Renewal')",
                "geocoding": "Built-in latitude/longitude fields",
            },
        ],
        "limitations": [
            "A current license is not the same as a currently operating business. Some licensees close, move, or sell without notifying the regulator.",
            "Illegal/unlicensed cannabis or smoke shops are not in any of these datasets.",
            "Licensees can hold multiple license types at one address (e.g., a bodega may appear as both a liquor seller and a tobacco dealer at the same address).",
            "OCM addresses are geocoded via NYC DCP GeoSearch. A small share of records fail to geocode; those are excluded from the map but kept in the CSV.",
        ],
    }
    (OUT / "methodology.json").write_text(json.dumps(methodology, indent=2))
    print("[write] methodology.json", file=sys.stderr)


def main():
    liquor = pull_liquor()
    beer = pull_beer()
    cannabis = pull_cannabis()
    tobacco = pull_tobacco()

    all_rows = liquor + beer + cannabis + tobacco
    geocode_missing(all_rows)

    counts = {
        "liquor": len(liquor),
        "beer": len(beer),
        "cannabis": len(cannabis),
        "tobacco": len(tobacco),
        "total": len(all_rows),
    }
    write_outputs(all_rows, counts)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
