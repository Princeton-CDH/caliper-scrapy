# SPDX-FileCopyrightText: 2024-present Center for Digital Humanities, Princeton University
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import argparse
import csv
import datetime
import pathlib
import urllib.parse

from selectolax.parser import HTMLParser
from tqdm import tqdm
from spider_rs import Website

from caliper import __version__

# Provide user agent to identify this tool via user-agent header
USER_AGENT = f"caliper v{__version__} (+http://cdh.princeton.edu)"


_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


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

    def __init__(self, output, show_progress=True, selector=None, text=False):
        self.selector = selector
        self.text = text
        if selector:
            self._validate_selector(selector)
        self.filehandle = output.open("w")
        self.csvwriter = csv.writer(self.filehandle)
        self.csvwriter.writerow(self.columns + (["content"] if selector else []))

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
        if self.selector:
            content_type = page.headers.get("content-type") or ""
            row.append(
                self._extract_content(page) if "text/html" in content_type else ""
            )
        self.csvwriter.writerow(row)
        self.page_count += 1
        self.pbar.update(self.page_count)
        self.status.set_postfix_str(f"URL: {page.url}")

    @staticmethod
    def _node_to_text(node):
        parts = []
        for child in node.traverse(include_text=True):
            if child.tag == "-text":
                parts.append(child.text_content or "")
            elif child.tag == "br" or child.tag in _BLOCK_TAGS:
                if parts and not parts[-1].endswith("\n"):
                    parts.append("\n")
        return "".join(parts)

    def _extract_content(self, page):
        try:
            if not page.content:
                return ""
            node = HTMLParser(page.content).css_first(self.selector)
        except Exception:
            return ""
        if node is None:
            return ""
        if self.text:
            return self._node_to_text(node)
        return node.html or ""

    def __del__(self):
        if hasattr(self, "filehandle"):
            self.filehandle.close()
        if hasattr(self, "status"):
            self.status.close()
        if hasattr(self, "pbar"):
            self.pbar.close()


async def crawl(
    url, output, show_progress=True, selector=None, text=False, html_only=False
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
            output, show_progress=show_progress, selector=selector, text=text
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
        "--text",
        help="Extract plain text instead of HTML (requires --select)",
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
    try:
        asyncio.run(
            crawl(
                args.url,
                args.output,
                show_progress=args.progress,
                selector=args.select,
                text=args.text,
                html_only=args.html_only,
            )
        )
    except KeyboardInterrupt:
        raise SystemExit
    except ValueError as e:
        raise SystemExit(e)


if __name__ == "__main__":
    main()
