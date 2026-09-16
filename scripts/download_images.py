#!/usr/bin/env python3
"""Download a filtered set of images from a Caliper CSV report."""

import argparse
import csv
import fnmatch
import mimetypes
import pathlib
import re
import sys
import urllib.parse

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from caliper import USER_AGENT


def filename_for(row):
    """Build an image filename from the last path segment of its referrer."""
    referrer_path = urllib.parse.urlparse(row.get("referrer", "")).path.rstrip("/")
    slug = urllib.parse.unquote(pathlib.PurePosixPath(referrer_path).name)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-") or "image"

    image_path = urllib.parse.urlparse(row["url"]).path
    suffix = pathlib.PurePosixPath(image_path).suffix
    if not suffix:
        suffix = mimetypes.guess_extension(row.get("content_type", "")) or ""
    return slug + suffix


def available_path(directory, filename):
    """Return a non-existing path, adding a numeric suffix on collision."""
    path = directory / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    number = 2
    while True:
        path = directory / f"{stem}-{number}{suffix}"
        if not path.exists():
            return path
        number += 1


def matches_referrer(referrer, pattern):
    """Match a glob against either the referrer URL or its path."""
    parsed = urllib.parse.urlparse(referrer)
    return fnmatch.fnmatch(referrer, pattern) or fnmatch.fnmatch(
        parsed.path, pattern
    )


def download_images(report, url_substring, output_directory, referrer_pattern=None):
    output_directory.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    with report.open(newline="") as file:
        for row in csv.DictReader(file):
            if not row.get("content_type", "").startswith("image/"):
                continue
            if url_substring not in row["url"]:
                continue
            if referrer_pattern and not matches_referrer(
                row.get("referrer", ""), referrer_pattern
            ):
                continue
            if row["status_code"] and row["status_code"] != "200":
                continue

            destination = available_path(
                output_directory, filename_for(row)
            )
            print(f"{row['url']} -> {destination}")
            with session.get(row["url"], stream=True, timeout=30) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
            downloaded += 1
    session.close()
    return downloaded


def main():
    parser = argparse.ArgumentParser(
        description="Download images selected from a Caliper CSV report"
    )
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument(
        "url_substring",
        help="only download image URLs containing this substring",
    )
    parser.add_argument(
        "-o",
        "--output-directory",
        type=pathlib.Path,
        default=pathlib.Path("images"),
    )
    parser.add_argument(
        "--referrer-pattern",
        help="optional glob matched against each image referrer URL or path",
    )
    args = parser.parse_args()
    count = download_images(
        args.report,
        args.url_substring,
        args.output_directory,
        args.referrer_pattern,
    )
    print(f"Downloaded {count} image(s).")


if __name__ == "__main__":
    main()
