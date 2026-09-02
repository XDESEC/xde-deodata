from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from geodat_pb2 import GeoSiteList


ROSCOM_PREFIX = "ROSCOM-"
ROSCOM_JSON_PREFIX = "roscom-"

REQUIRED_LOYALSOLDIER = {
    "SOUNDCLOUD",
    "YOUTUBE",
    "GOOGLE-GEMINI",
}

REQUIRED_ROSCOM = {
    "ROSCOM-CATEGORY-ADS",
    "ROSCOM-CATEGORY-RU",
    "ROSCOM-WHITELIST",
}


DOMAIN_TYPE_PREFIX = {
    0: "keyword:",
    1: "regexp:",
    2: "domain:",
    3: "full:",
}


def load_geosite(
    path: Path,
) -> GeoSiteList:
    result = GeoSiteList()

    data = path.read_bytes()

    if not data:
        raise RuntimeError(
            f"{path} is empty"
        )

    try:
        result.ParseFromString(
            data
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to parse {path}: {exc}"
        ) from exc

    if not result.entry:
        raise RuntimeError(
            f"{path} contains no GeoSite entries"
        )

    return result


def normalized_code(
    value: str,
) -> str:
    return value.strip().upper()


def normalized_json_code(
    value: str,
) -> str:
    return value.strip().lower()


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(
            1024 * 1024
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def write_sha256_file(
    path: Path,
) -> Path:
    digest = sha256_file(
        path
    )

    checksum_path = Path(
        str(path) + ".sha256"
    )

    checksum_path.write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )

    return checksum_path


def write_json_atomic(
    path: Path,
    value: Any,
    *,
    compact: bool = False,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        path.with_suffix(
            path.suffix + ".tmp"
        )
    )

    if compact:
        content = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        content = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )

    temporary_path.write_text(
        content + "\n",
        encoding="utf-8",
    )

    if (
        not temporary_path.exists()
        or temporary_path.stat().st_size == 0
    ):
        raise RuntimeError(
            f"Generated {path.name} is empty"
        )

    temporary_path.replace(
        path
    )


def domain_to_xray_rule(
    domain: Any,
    *,
    category: str,
) -> str:
    domain_type = int(
        domain.type
    )

    prefix = DOMAIN_TYPE_PREFIX.get(
        domain_type
    )

    if prefix is None:
        raise RuntimeError(
            "Unknown geosite domain type "
            f"{domain_type} "
            f"in category {category!r}"
        )

    value = str(
        domain.value
    ).strip()

    if not value:
        raise RuntimeError(
            "Empty domain value "
            f"in category {category!r}"
        )

    return (
        f"{prefix}{value}"
    )


def build_roscom_expansions(
    roscom: GeoSiteList,
) -> dict[str, list[str]]:

    result: dict[
        str,
        list[str]
    ] = {}

    for entry in roscom.entry:
        source_code = (
            normalized_json_code(
                entry.code
            )
        )

        if not source_code:
            raise RuntimeError(
                "RoscomVPN contains "
                "an empty category code"
            )

        target_code = (
            ROSCOM_JSON_PREFIX
            + source_code
        )

        if target_code in result:
            raise RuntimeError(
                "Duplicate RoscomVPN "
                f"category: {target_code}"
            )

        domains: list[str] = []

        for domain in entry.domain:
            domains.append(
                domain_to_xray_rule(
                    domain,
                    category=target_code,
                )
            )

        # Dedupe с сохранением исходного порядка.
        domains = list(
            dict.fromkeys(
                domains
            )
        )

        result[
            target_code
        ] = domains

    return result


def validate_required_categories(
    *,
    hybrid_codes: set[str],
    roscom_expansions:
        dict[str, list[str]],
) -> None:
    missing_loyal = (
        REQUIRED_LOYALSOLDIER
        - hybrid_codes
    )

    if missing_loyal:
        raise RuntimeError(
            "Missing required Loyalsoldier "
            "categories: "
            + ", ".join(
                sorted(
                    missing_loyal
                )
            )
        )

    missing_roscom = (
        REQUIRED_ROSCOM
        - hybrid_codes
    )

    if missing_roscom:
        raise RuntimeError(
            "Missing required RoscomVPN "
            "categories: "
            + ", ".join(
                sorted(
                    missing_roscom
                )
            )
        )

    for dat_code in (
        REQUIRED_ROSCOM
    ):
        json_code = (
            dat_code.lower()
        )

        domains = (
            roscom_expansions.get(
                json_code
            )
        )

        if domains is None:
            raise RuntimeError(
                "Missing required RoscomVPN "
                "JSON expansion: "
                f"{json_code}"
            )

        if not domains:
            raise RuntimeError(
                "Required RoscomVPN "
                "JSON expansion is empty: "
                f"{json_code}"
            )


def merge_geosite(
    loyalsoldier_path: Path,
    roscom_path: Path,
    output_path: Path,
) -> None:
    loyal = load_geosite(
        loyalsoldier_path
    )

    roscom = load_geosite(
        roscom_path
    )

    output = GeoSiteList()

    codes: set[str] = set()


    for source_entry in loyal.entry:
        code = normalized_code(
            source_entry.code
        )

        if not code:
            raise RuntimeError(
                "Loyalsoldier contains "
                "an empty category code"
            )

        if code in codes:
            raise RuntimeError(
                "Duplicate Loyalsoldier "
                f"category: {code}"
            )

        target_entry = (
            output.entry.add()
        )

        target_entry.CopyFrom(
            source_entry
        )

        target_entry.code = code

        codes.add(
            code
        )


    roscom_added = 0

    for source_entry in roscom.entry:
        original_code = (
            normalized_code(
                source_entry.code
            )
        )

        if not original_code:
            raise RuntimeError(
                "RoscomVPN contains "
                "an empty category code"
            )

        target_code = (
            ROSCOM_PREFIX
            + original_code
        )

        if target_code in codes:
            raise RuntimeError(
                "Hybrid category collision: "
                f"{target_code}"
            )

        target_entry = (
            output.entry.add()
        )

        target_entry.CopyFrom(
            source_entry
        )

        target_entry.code = (
            target_code
        )

        codes.add(
            target_code
        )

        roscom_added += 1


    roscom_expansions = (
        build_roscom_expansions(
            roscom
        )
    )

    # ---------------------------------------------------------
    # 4. Validation
    # ---------------------------------------------------------

    validate_required_categories(
        hybrid_codes=codes,
        roscom_expansions=
            roscom_expansions,
    )

    if (
        len(output.entry)
        != len(loyal.entry)
        + len(roscom.entry)
    ):
        raise RuntimeError(
            "Hybrid category count mismatch"
        )

    if (
        roscom_added
        != len(roscom.entry)
    ):
        raise RuntimeError(
            "Not all RoscomVPN categories "
            "were added"
        )

    # ---------------------------------------------------------
    # 5. Write hybrid geosite.dat atomically
    # ---------------------------------------------------------

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        output_path.with_suffix(
            output_path.suffix
            + ".tmp"
        )
    )

    serialized = (
        output.SerializeToString(
            deterministic=True
        )
    )

    if not serialized:
        raise RuntimeError(
            "Generated geosite "
            "serialization is empty"
        )

    temporary_path.write_bytes(
        serialized
    )

    if (
        not temporary_path.exists()
        or temporary_path.stat().st_size == 0
    ):
        raise RuntimeError(
            "Generated geosite is empty"
        )

    temporary_path.replace(
        output_path
    )

    # ---------------------------------------------------------
    # 6. geosite.dat.sha256
    # ---------------------------------------------------------

    geosite_sha_path = (
        write_sha256_file(
            output_path
        )
    )

    # ---------------------------------------------------------
    # 7. roscom-domains.json
    # ---------------------------------------------------------

    roscom_domains_path = (
        output_path.parent
        / "roscom-domains.json"
    )

    write_json_atomic(
        roscom_domains_path,
        roscom_expansions,
        compact=True,
    )

    # ---------------------------------------------------------
    # 8. roscom-domains.json.sha256
    # ---------------------------------------------------------

    roscom_domains_sha_path = (
        write_sha256_file(
            roscom_domains_path
        )
    )

    # ---------------------------------------------------------
    # 9. Statistics
    # ---------------------------------------------------------

    total_roscom_domains = sum(
        len(domains)
        for domains
        in roscom_expansions.values()
    )

    required_expansion_sizes = {
        category.lower():
            len(
                roscom_expansions[
                    category.lower()
                ]
            )
        for category
        in sorted(
            REQUIRED_ROSCOM
        )
    }

    manifest = {
        "loyalsoldier_categories":
            len(loyal.entry),

        "roscom_categories":
            len(roscom.entry),

        "hybrid_categories":
            len(output.entry),

        "roscom_added":
            roscom_added,

        "geosite": {
            "file":
                output_path.name,

            "size":
                output_path.stat().st_size,

            "sha256":
                sha256_file(
                    output_path
                ),

            "sha256_file":
                geosite_sha_path.name,
        },

        "roscom_domains": {
            "file":
                roscom_domains_path.name,

            "categories":
                len(
                    roscom_expansions
                ),

            "rules":
                total_roscom_domains,

            "size":
                roscom_domains_path
                .stat()
                .st_size,

            "sha256":
                sha256_file(
                    roscom_domains_path
                ),

            "sha256_file":
                roscom_domains_sha_path.name,

            "required_category_sizes":
                required_expansion_sizes,
        },

        "required_loyalsoldier":
            sorted(
                REQUIRED_LOYALSOLDIER
            ),

        "required_roscom":
            sorted(
                REQUIRED_ROSCOM
            ),
    }

    # ---------------------------------------------------------
    # Для совместимости старые top-level
    # size / sha256.
    # ---------------------------------------------------------

    manifest[
        "size"
    ] = output_path.stat().st_size

    manifest[
        "sha256"
    ] = sha256_file(
        output_path
    )

    manifest_path = (
        output_path.parent
        / "manifest.json"
    )

    write_json_atomic(
        manifest_path,
        manifest,
        compact=False,
    )

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = (
        argparse.ArgumentParser(
            description=(
                "Merge Loyalsoldier and "
                "RoscomVPN geosite databases"
            )
        )
    )

    parser.add_argument(
        "--loyalsoldier",
        type=Path,
        required=True,
        help=(
            "Path to Loyalsoldier "
            "geosite.dat"
        ),
    )

    parser.add_argument(
        "--roscom",
        type=Path,
        required=True,
        help=(
            "Path to RoscomVPN "
            "geosite.dat"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help=(
            "Output hybrid "
            "geosite.dat path"
        ),
    )

    args = parser.parse_args()

    merge_geosite(
        loyalsoldier_path=
            args.loyalsoldier,

        roscom_path=
            args.roscom,

        output_path=
            args.output,
    )


if __name__ == "__main__":
    main()