from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from geodat_pb2 import GeoSiteList


ROSCOM_PREFIX = "ROSCOM-"

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


def load_geosite(path: Path) -> GeoSiteList:
    result = GeoSiteList()

    data = path.read_bytes()

    if not data:
        raise RuntimeError(
            f"{path} is empty"
        )

    result.ParseFromString(data)

    if not result.entry:
        raise RuntimeError(
            f"{path} contains no GeoSite entries"
        )

    return result


def normalized_code(value: str) -> str:
    return value.strip().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


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

    # ---------------------------------------------------------
    # 1. Loyalsoldier копируем без изменения названий.
    # ---------------------------------------------------------

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

        target_entry = output.entry.add()
        target_entry.CopyFrom(
            source_entry
        )

        # Современный Xray работает с category codes
        # в upper-case при загрузке.
        target_entry.code = code

        codes.add(code)

    # ---------------------------------------------------------
    # 2. RoscomVPN добавляен с отдельным namespace.
    #
    # category-ads ->
    # ROSCOM-CATEGORY-ADS
    #
    # youtube ->
    # ROSCOM-YOUTUBE
    # ---------------------------------------------------------

    roscom_added = 0

    for source_entry in roscom.entry:
        original_code = normalized_code(
            source_entry.code
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

        target_entry = output.entry.add()
        target_entry.CopyFrom(
            source_entry
        )
        target_entry.code = target_code

        codes.add(target_code)
        roscom_added += 1

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    missing_loyal = (
        REQUIRED_LOYALSOLDIER
        - codes
    )

    if missing_loyal:
        raise RuntimeError(
            "Missing required Loyalsoldier "
            "categories: "
            + ", ".join(
                sorted(missing_loyal)
            )
        )

    missing_roscom = (
        REQUIRED_ROSCOM
        - codes
    )

    if missing_roscom:
        raise RuntimeError(
            "Missing required RoscomVPN "
            "categories: "
            + ", ".join(
                sorted(missing_roscom)
            )
        )

    # ---------------------------------------------------------
    # Write atomically
    # ---------------------------------------------------------

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        output_path.with_suffix(
            output_path.suffix + ".tmp"
        )
    )

    temporary_path.write_bytes(
        output.SerializeToString()
    )

    if temporary_path.stat().st_size == 0:
        raise RuntimeError(
            "Generated geosite is empty"
        )

    temporary_path.replace(
        output_path
    )

    manifest = {
        "loyalsoldier_categories":
            len(loyal.entry),

        "roscom_categories":
            len(roscom.entry),

        "hybrid_categories":
            len(output.entry),

        "roscom_added":
            roscom_added,

        "size":
            output_path.stat().st_size,

        "sha256":
            sha256_file(output_path),

        "required_loyalsoldier":
            sorted(
                REQUIRED_LOYALSOLDIER
            ),

        "required_roscom":
            sorted(
                REQUIRED_ROSCOM
            ),
    }

    manifest_path = (
        output_path.parent
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--loyalsoldier",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--roscom",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
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