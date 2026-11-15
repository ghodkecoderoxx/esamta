
"""
Download files produced by an existing NASA Harmony subset job.

Install:
    pip install harmony-py earthaccess

Run from project root:
    python src/download_data.py

Optional:
    python src/download_data.py --job-id YOUR_JOB_ID
    python src/download_data.py --output-dir data/raw
    python src/download_data.py --force

Output:
    data/raw/<JOB_ID>/
"""

from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, unquote
from getpass import getpass
import argparse
import netrc
import sys

import earthaccess
from harmony import Client
from harmony.config import Environment


# ============================================================
# 1. CONFIGURATION
# ============================================================

DEFAULT_JOB_ID = "0d33d2e8-a461-456c-9407-e5b928fd6e36"

DEFAULT_OUTPUT_DIR = "data/raw"

EARTHDATA_HOST = "urs.earthdata.nasa.gov"

TERMINAL_STATUSES = {
    "successful",
    "complete_with_errors",
    "failed",
    "canceled",
    "cancelled",
}


# ============================================================
# 2. PROJECT PATHS
# ============================================================

def get_project_root():
    """
    Resolve the project root from this script's location.

    Expected structure:
        project/
            src/
                download_data.py
            data/
                raw/
    """

    return Path(__file__).resolve().parents[1]


def resolve_output_dir(output_dir, job_id):
    """
    Resolve the output directory relative to the project root
    unless an absolute path is provided.
    """

    project_root = get_project_root()

    output_dir = Path(output_dir)

    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    return (output_dir / job_id).resolve()


# ============================================================
# 3. EARTHDATA AUTHENTICATION
# ============================================================

def get_login_credentials():
    """
    Read credentials from .netrc where available.
    Otherwise, request credentials interactively.
    """

    login = None
    password = None

    try:
        credentials = netrc.netrc().authenticators(
            EARTHDATA_HOST
        )

        if credentials:
            login, _account, password = credentials

    except (
        FileNotFoundError,
        OSError,
        netrc.NetrcParseError,
    ):
        pass

    if not login or not password:
        print("Earthdata credentials not found in .netrc.")

        login = input("Earthdata Login username: ")
        password = getpass("Earthdata Login password: ")

    if not login or not password:
        raise ValueError(
            "Earthdata username and password are required."
        )

    return login, password


def create_harmony_client(login, password):
    """Create an authenticated NASA Harmony client."""

    print("\nConnecting to NASA Harmony...")

    client = Client(
        auth=(login, password),
        env=Environment.PROD,
    )

    print("Harmony client initialized.")

    return client


def authenticate_earthaccess():
    """
    Authenticate earthaccess for downloading Harmony result URLs.

    earthaccess may use its configured authentication method,
    such as .netrc or interactive authentication.
    """

    print("\nAuthenticating earthaccess...")

    auth = earthaccess.login(
        system=earthaccess.PROD
    )

    if not auth:
        raise RuntimeError(
            "Earthaccess authentication failed."
        )

    print("Earthaccess authentication successful.")


# ============================================================
# 4. HARMONY JOB MONITORING
# ============================================================

def print_job_messages(job):
    """Display available Harmony errors and warnings."""

    errors = job.get("errors")
    warnings = job.get("warnings")

    if errors:
        print("\nHARMONY ERRORS:")
        print("-" * 50)

        if isinstance(errors, (list, tuple)):
            for error in errors:
                print(error)
        else:
            print(errors)

    if warnings:
        print("\nHARMONY WARNINGS:")
        print("-" * 50)

        if isinstance(warnings, (list, tuple)):
            for warning in warnings:
                print(warning)
        else:
            print(warnings)

    if not errors and not warnings:
        print(
            "\nNo error or warning details were included "
            "in the returned job status."
        )


def wait_for_job(harmony_client, job_id):
    """
    Check the Harmony job.

    If still processing, wait and check its final status.
    Jobs marked complete_with_errors are allowed to proceed
    so that their available output files can be retrieved.
    """

    print("\nChecking Harmony job:", job_id)

    job = harmony_client.status(job_id)

    status = job.get("status", "unknown")

    print("Current status:", status)

    if status not in TERMINAL_STATUSES:

        print("\nJob is still processing. Waiting...")

        harmony_client.wait_for_processing(
            job_id,
            show_progress=True,
        )

        job = harmony_client.status(job_id)

        status = job.get("status", "unknown")

    print("\nFinal Harmony status:", status)

    print_job_messages(job)

    if status in {"failed", "canceled", "cancelled"}:
        raise RuntimeError(
            f"Harmony job terminated unsuccessfully: {status}"
        )

    if status == "complete_with_errors":
        print(
            "\nWARNING: Harmony completed with errors. "
            "Available files will still be downloaded, "
            "but their completeness must be verified."
        )

    elif status != "successful":
        raise RuntimeError(
            f"Unexpected Harmony job status: {status}"
        )

    return job


# ============================================================
# 5. RETRIEVE DOWNLOAD URLS
# ============================================================

def get_download_urls(harmony_client, job_id):
    """Retrieve and validate the result URLs."""

    print("\nRetrieving Harmony result URLs...")

    urls = list(
        harmony_client.result_urls(job_id)
    )

    if not urls:
        raise RuntimeError(
            "Harmony returned no result URLs."
        )

    # Remove duplicate URLs while preserving order.
    urls = list(dict.fromkeys(urls))

    print("Unique result URLs:", len(urls))

    return urls


def get_filename_from_url(url):
    """Extract a filename from a result URL."""

    parsed = urlparse(str(url))

    filename = PurePosixPath(
        unquote(parsed.path)
    ).name

    if not filename:
        raise ValueError(
            f"Could not determine filename from URL: {url}"
        )

    return filename


# ============================================================
# 6. DOWNLOAD PLANNING
# ============================================================

def identify_downloads(urls, output_dir, force=False):
    """
    Identify files that need downloading.

    Existing non-empty files are skipped unless force=True.
    """

    output_dir = Path(output_dir)

    urls_to_download = []
    expected_files = []

    for url in urls:

        filename = get_filename_from_url(url)

        destination = output_dir / filename

        expected_files.append(destination)

        if (
            not force
            and destination.exists()
            and destination.stat().st_size > 0
        ):
            continue

        urls_to_download.append(url)

    return urls_to_download, expected_files


# ============================================================
# 7. DOWNLOAD FILES
# ============================================================

def download_files(urls, output_dir, force=False):
    """Download Harmony results and verify their local presence."""

    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\nOutput directory:")
    print(output_dir.resolve())

    urls_to_download, expected_files = identify_downloads(
        urls,
        output_dir,
        force=force,
    )

    print("\nExpected files:", len(expected_files))
    print("Files requiring download:", len(urls_to_download))
    print("Existing files to skip:", (
        len(expected_files) - len(urls_to_download)
    ))

    if urls_to_download:

        print("\nStarting download...")

        earthaccess.download(
            urls_to_download,
            str(output_dir),
        )

        print("\nDownload operation returned.")

    else:
        print("\nAll expected files already exist.")
        print("No additional download is necessary.")

    # --------------------------------------------------------
    # Verify downloaded files
    # --------------------------------------------------------

    valid_files = []
    missing_files = []
    empty_files = []

    for filepath in expected_files:

        if not filepath.exists():
            missing_files.append(filepath)

        elif filepath.stat().st_size == 0:
            empty_files.append(filepath)

        else:
            valid_files.append(filepath)

    print("\n" + "=" * 60)
    print("DOWNLOAD VERIFICATION")
    print("=" * 60)

    print("Expected files:", len(expected_files))
    print("Valid files:", len(valid_files))
    print("Missing files:", len(missing_files))
    print("Empty files:", len(empty_files))

    if missing_files:
        print("\nMISSING FILES:")

        for filepath in missing_files[:20]:
            print(filepath.name)

    if empty_files:
        print("\nEMPTY FILES:")

        for filepath in empty_files[:20]:
            print(filepath.name)

    return {
        "expected": len(expected_files),
        "valid": len(valid_files),
        "missing": missing_files,
        "empty": empty_files,
        "valid_files": valid_files,
    }


# ============================================================
# 8. MAIN PIPELINE
# ============================================================

def main(
    job_id=DEFAULT_JOB_ID,
    output_dir=DEFAULT_OUTPUT_DIR,
    force=False,
):

    print("=" * 60)
    print("NASA GPM IMERG DATA DOWNLOADER")
    print("=" * 60)

    print("Harmony job ID:", job_id)

    job_output_dir = resolve_output_dir(
        output_dir,
        job_id,
    )

    print("Target directory:", job_output_dir)

    # Step 1: Authentication
    login, password = get_login_credentials()

    harmony_client = create_harmony_client(
        login,
        password,
    )

    authenticate_earthaccess()

    # Step 2: Check Harmony job status
    wait_for_job(
        harmony_client,
        job_id,
    )

    # Step 3: Retrieve result URLs
    urls = get_download_urls(
        harmony_client,
        job_id,
    )

    # Step 4: Download and verify
    report = download_files(
        urls,
        job_output_dir,
        force=force,
    )

    # Step 5: Final summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)

    print("Harmony job:", job_id)
    print("Output directory:", job_output_dir)
    print("Expected files:", report["expected"])
    print("Valid files:", report["valid"])
    print("Missing files:", len(report["missing"]))
    print("Empty files:", len(report["empty"]))

    if report["missing"] or report["empty"]:

        print("\nWARNING: Download verification is incomplete.")

        return 1

    print("\nAll expected files are present and non-empty.")

    return 0


# ============================================================
# 9. COMMAND-LINE ENTRY POINT
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Download and verify files from an existing "
            "NASA Harmony subset job."
        )
    )

    parser.add_argument(
        "--job-id",
        default=DEFAULT_JOB_ID,
        help="Harmony job ID",
    )

    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Base output directory, relative to project root "
             "unless an absolute path is supplied.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload files even if non-empty local copies exist.",
    )

    args = parser.parse_args()

    try:

        exit_code = main(
            job_id=args.job_id,
            output_dir=args.output_dir,
            force=args.force,
        )

        sys.exit(exit_code)

    except KeyboardInterrupt:

        print("\nDownload interrupted by user.")
        sys.exit(130)

    except Exception as error:

        print("\nPIPELINE FAILED:")
        print(f"{type(error).__name__}: {error}")

        sys.exit(1)
