import argparse
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests


PACKAGE_API_URL = "https://data.gov.ro/api/3/action/package_show"
DEFAULT_DATASET_URL = (
    "https://data.gov.ro/dataset/situatii_financiare_2024_actualizat"
)


def dataset_id_from_url(dataset_url: str) -> str:
    parts = [part for part in urlparse(dataset_url).path.split("/") if part]
    if len(parts) != 2 or parts[0] != "dataset" or not parts[1]:
        raise ValueError(
            "Dataset URL must have the form https://data.gov.ro/dataset/<id>"
        )
    return parts[1]


def get_resources(
    session: requests.Session, dataset_id: str
) -> list[dict[str, str]]:
    response = session.get(
        PACKAGE_API_URL,
        params={"id": dataset_id},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN API returned an unsuccessful response: {payload}")

    resources = payload["result"].get("resources", [])
    if not resources:
        raise RuntimeError(f"No resources found for dataset {dataset_id!r}")
    return resources


def download_resource(
    session: requests.Session,
    resource: dict[str, str],
    output_dir: Path,
    force: bool,
) -> None:
    name = Path(resource["name"]).name
    destination = output_dir / name
    if destination.exists() and not force:
        logging.info("Skipping existing file: %s", destination)
        return

    logging.info("Downloading %s", name)
    with session.get(resource["url"], stream=True, timeout=(30, 600)) as response:
        response.raise_for_status()
        temporary_destination = destination.with_suffix(destination.suffix + ".part")
        try:
            with temporary_destination.open("wb") as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        target.write(chunk)
            temporary_destination.replace(destination)
        except BaseException:
            temporary_destination.unlink(missing_ok=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarca resursele unui dataset data.gov.ro."
    )
    parser.add_argument("--dataset-url", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directorul specific sursei in care se salveaza fisierele.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Descarca din nou fisierele deja existente.",
    )
    args = parser.parse_args()

    dataset_id = dataset_id_from_url(args.dataset_url)
    if args.output_dir is None:
        args.output_dir = (
            Path(__file__).resolve().parents[2]
            / "dataset"
            / "data.gov.ro"
            / dataset_id
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "firme-bucuresti-data-downloader/1.0"
    resources = get_resources(session, dataset_id)
    logging.info("Dataset page: %s", args.dataset_url)
    logging.info("Found %d resources", len(resources))

    for resource in resources:
        download_resource(session, resource, args.output_dir, args.force)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
