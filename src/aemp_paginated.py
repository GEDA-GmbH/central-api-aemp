#!/usr/bin/env python3
"""
Download all paginated equipment snapshot records from the GEDA AEMP endpoint.

Depending on the fleet size getting all values might take some time.

Pagination:
1) Path-based pagination via /{page} (one-based)
2) Continue while the 'Links' array in the response contains a link with rel='next'
"""

import argparse
import json
import os
from urllib.parse import urlencode

import requests


# Runtime defaults.
DEFAULT_BASE_URL = "https://central.geda.de/api/aemp/equipment/status"
DEFAULT_OUTPUT_FILE = "aemp_fleet_snapshot.json"
DEFAULT_START_PAGE = 1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_ADD_METADATA = True
DEFAULT_MACHINE_IDENTIFIER = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch paginated AEMP equipment snapshot data and write it to JSON.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("AEMP_API_TOKEN"),
        help="Bearer token. If omitted, AEMP_API_TOKEN is used.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_FILE,
        help="Output JSON file path.",
    )

    return parser.parse_args()


def parse_json_payload(response: requests.Response) -> dict | list:
    """Return JSON body and fail with a clear message if invalid."""
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "json" not in content_type:
        raise ValueError(f"Unexpected Content-Type: {response.headers.get('Content-Type')}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("Response body is not valid JSON.") from exc

    if not isinstance(payload, (dict, list)):
        raise ValueError("Response JSON must be an object or list.")

    return payload


def build_page_url(
    base_url: str,
    page_number: int,
    add_metadata: bool = True,
    machine_identifier: str | None = None,
) -> str:
    """Build {base_url}/{page}?addMetadata=true[&machineIdentifier=...]."""
    base_url = base_url.rstrip("/")
    url = f"{base_url}/{page_number}"

    query: dict[str, str] = {}

    if add_metadata:
        query["addMetadata"] = "true"

    if machine_identifier:
        query["machineIdentifier"] = machine_identifier

    if query:
        url = f"{url}?{urlencode(query)}"

    return url


def extract_equipment(payload: dict | list) -> list[dict]:
    """Extract equipment list from standard or legacy response payloads."""
    if isinstance(payload, list):
        return payload

    equipment = payload.get("Equipment")
    if isinstance(equipment, list):
        return equipment

    equipment = payload.get("equipment")
    if isinstance(equipment, list):
        return equipment

    raise ValueError("Response does not contain Equipment[] or equipment[].")


def has_next_page(payload: dict | list) -> bool:
    """Determine whether there are more pages based on the 'Links' array in response."""
    if not isinstance(payload, dict):
        return False

    links = payload.get("Links")
    if links is None:
        links = payload.get("links")

    if isinstance(links, list):
        return any(
            isinstance(link, dict) and str(link.get("rel", "")).lower() == "next"
            for link in links
        )

    return False


def fetch_fleet_snapshot(
    base_url: str,
    token: str,
    start_page: int = DEFAULT_START_PAGE,
    add_metadata: bool = DEFAULT_ADD_METADATA,
    machine_identifier: str | None = DEFAULT_MACHINE_IDENTIFIER,
) -> list[dict]:
    """Fetch all paginated equipment records from the endpoint."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    all_equipment: list[dict] = []
    current_page = start_page
    current_url = build_page_url(
        base_url=base_url,
        page_number=current_page,
        add_metadata=add_metadata,
        machine_identifier=machine_identifier,
    )

    while current_url:
        print(f"Fetching page {current_page}: {current_url}")

        response = requests.get(
            current_url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            verify=True,
        )
        response.raise_for_status()

        payload = parse_json_payload(response)
        equipment = extract_equipment(payload)
        print(f"  Records: {len(equipment)}")

        if not equipment:
            print("  Empty page received. Stopping pagination.")
            break

        all_equipment.extend(equipment)

        if not has_next_page(payload):
            print("  No 'next' link found in response. Stopping pagination.")
            break

        current_page += 1
        current_url = build_page_url(
            base_url=base_url,
            page_number=current_page,
            add_metadata=add_metadata,
            machine_identifier=machine_identifier,
        )

    return all_equipment


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    if not args.token:
        print("Error: Missing API token. Use --token or set AEMP_API_TOKEN.")
        return 2

    try:
        equipment_records = fetch_fleet_snapshot(
            base_url=DEFAULT_BASE_URL,
            token=args.token,
            start_page=DEFAULT_START_PAGE,
            add_metadata=DEFAULT_ADD_METADATA,
            machine_identifier=DEFAULT_MACHINE_IDENTIFIER,
        )
    except Exception as exc:
        print(f"Error while fetching AEMP fleet snapshot: {exc}")
        return 1

    output = {
        "source": DEFAULT_BASE_URL,
        "addMetadata": DEFAULT_ADD_METADATA,
        "machineIdentifier": DEFAULT_MACHINE_IDENTIFIER,
        "equipmentCount": len(equipment_records),
        "Equipment": equipment_records,
    }

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"Wrote {len(equipment_records)} records to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())