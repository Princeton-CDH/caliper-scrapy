# SPDX-FileCopyrightText: 2024-present Center for Digital Humanities, Princeton University
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import argparse
import csv
import datetime
import pathlib
import urllib.parse

from inscriptis import get_text
from selectolax.parser import HTMLParser
from tqdm import tqdm
from spider_rs import Website

from caliper import __version__

# Provide user agent to identify this tool via user-agent header
USER_AGENT = f"caliper v{__version__} (+http://cdh.princeton.edu)"

# Supported content extraction formats
FORMAT_HTML = "html"
FORMAT_TEXT = "text"
SUPPORTED_FORMATS = (FORMAT_HTML, FORMAT_TEXT)


def parse_formats(value):
    """Parse a comma-separated --format value into an ordered, de-duplicated
    tuple of supported format names. Raises ValueError for unknown formats."""
    if not value:
        return ()
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    seen = []
    for p in parts:
        if p not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format {p!r}; choose from {', '.join(SUPPORTED_FORMATS)}"
            )
        if p not in seen:
            seen.append(p)
    return tuple(seen)


def content_column_names(formats):
    """Return CSV column names for the requested formats.

    - () -> ()
    - ("html",) and no other formats -> ("content",)   (legacy single column)
    - ("text",) and no other formats -> ("content_text",)
    - multiple formats -> ("content_html", "content_text", ...) in given order
    """
    if not formats:
        return ()
    if len(formats) == 1:
        if formats[0] == FORMAT_HTML:
            return ("content",)
        return (f"content_{formats[0]}",)
    return tuple(f"content_{f}" for f in formats)


class ReportSubscription:
    columns = [
        "url",
        "status_code",
        "title",
        "content_type",
        "last_modified",
        "content_length",
        "date",
        "size",
        "timestamp",
    ]

    def __init__(self, output, show_progress=True, selector=None, formats=()):
        self.selector = selector
        self.formats = tuple(formats)
        if selector:
            self._validate_selector(selector)
        self.filehandle = output.open("w")
        self.csvwriter = csv.writer(self.filehandle)
        extra = list(content_column_names(self.formats)) if selector else []
        self.csvwriter.writerow(self.columns + extra)

        # postfix automatically starts with a comma
        disable_progress = not show_progress
        self.status = tqdm(
            desc="Crawling", bar_format="{desc}{postfix}", disable=disable_progress
        )
        self.pbar = tqdm(bar_format="{n:,} urls {elapsed}", disable=disable_progress)
        self.page_count = 0

    @staticmethod
    def _validate_selector(selector):
        try:
            HTMLParser("<html></html>").css_first(selector)
        except ValueError as e:
            raise ValueError(f"Invalid CSS selector {selector!r}: {e}") from e

    def __call__(self, page):
        row = [
            page.url,
            page.status_code,
            # some titles (*cough* PPA) include leading/trailing whitesapce
            str(page.title()).strip(),
            page.headers.get("content-type"),
            page.headers.get("last-modified"),
            page.headers.get("content-length"),
            page.headers.get("date"),
            len(page.content),
            # timestamp in isoformat so we can filter csv more easily
            datetime.datetime.now(tz=datetime.UTC).isoformat(),
        ]
        if self.selector and self.formats:
            content_type = page.headers.get("content-type") or ""
            if "text/html" in content_type:
                extracted = self._extract_content(page)
            else:
                extracted = {fmt: "" for fmt in self.formats}
            for fmt in self.formats:
                row.append(extracted.get(fmt, ""))
        self.csvwriter.writerow(row)
        self.page_count += 1
        self.pbar.update(self.page_count)
        self.status.set_postfix_str(f"URL: {page.url}")

    def _extract_content(self, page):
        """Extract content from the matched element in the requested formats.

        Returns a dict mapping format name to extracted content. Always returns
        a dict with an entry for each requested format; missing matches or
        parse errors yield empty strings.
        """
        result = {fmt: "" for fmt in self.formats}
        try:
            if not page.content:
                return result
            node = HTMLParser(page.content).css_first(self.selector)
        except Exception:
            return result
        if node is None:
            return result
        node_html = node.html or ""
        if FORMAT_HTML in self.formats:
            result[FORMAT_HTML] = node_html
        if FORMAT_TEXT in self.formats:
            result[FORMAT_TEXT] = get_text(node_html).strip() if node_html else ""
        return result

    def __del__(self):
        if hasattr(self, "filehandle"):
            self.filehandle.close()
        if hasattr(self, "status"):
            self.status.close()
        if hasattr(self, "pbar"):
            self.pbar.close()


async def crawl(
    url, output, show_progress=True, selector=None, formats=(), html_only=False
):
    website = (
        Website(url)
        .with_full_resources(not html_only)
        .with_respect_robots_txt(True)
        .with_user_agent(USER_AGENT)
    )
    # if the URL has a non-root path, restrict crawling to that subtree
    base_path = urllib.parse.urlparse(url).path
    if base_path and base_path != "/":
        website = website.with_whitelist_url([base_path])
    website.crawl(
        ReportSubscription(
            output, show_progress=show_progress, selector=selector, formats=formats
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Crawl a website and generate a CSV report of contents"
    )
    parser.add_argument("url", help="URL for the site to be crawled")
    parser.add_argument(
        "output",
        help="filename where the crawl report should be saved",
        type=pathlib.Path,
    )
    parser.add_argument(
        "--progress",
        help="Show progress",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--select",
        help="CSS selector to extract content from each page into an additional column",
        default=None,
    )
    parser.add_argument(
        "--format",
        dest="format",
        help=(
            "Content format(s) to extract when --select is used; "
            "comma-separated list of: html, text. Defaults to html."
        ),
        default=None,
    )
    parser.add_argument(
        "--text",
        help="Shorthand for --format text (mutually exclusive with --format)",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--html-only",
        help="Crawl HTML pages only, skipping other resources (CSS, JS, images, etc.)",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    if args.text and args.format is not None:
        parser.error("--text and --format are mutually exclusive")

    try:
        if args.text:
            formats = (FORMAT_TEXT,)
        elif args.format is not None:
            formats = parse_formats(args.format)
        elif args.select:
            # backward-compatible default: HTML when --select is given alone
            formats = (FORMAT_HTML,)
        else:
            formats = ()
    except ValueError as e:
        raise SystemExit(e)

    try:
        asyncio.run(
            crawl(
                args.url,
                args.output,
                show_progress=args.progress,
                selector=args.select,
                formats=formats,
                html_only=args.html_only,
            )
        )
    except KeyboardInterrupt:
        raise SystemExit
    except ValueError as e:
        raise SystemExit(e)


if __name__ == "__main__":
    main()
