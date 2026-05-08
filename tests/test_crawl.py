# SPDX-FileCopyrightText: 2024-present Center for Digital Humanities, Princeton University
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import csv
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from caliper.crawl import ReportSubscription, USER_AGENT, crawl, main


def make_page(
    url="https://example.com/page",
    status_code=200,
    title="Page Title",
    headers=None,
    content=b"hello",
):
    page = MagicMock()
    page.url = url
    page.status_code = status_code
    page.title.return_value = title
    page.headers = headers if headers is not None else {}
    page.content = content
    return page


@pytest.fixture
def output(tmp_path):
    return tmp_path / "report.csv"


@pytest.fixture
def subscription(output):
    return ReportSubscription(output, show_progress=False)


class TestReportSubscription:
    def test_csv_header(self, subscription, output):
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[0] == [
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

    def test_writes_page_data(self, subscription, output):
        page = make_page(
            url="https://example.com/about",
            status_code=200,
            title="About",
            headers={
                "content-type": "text/html; charset=utf-8",
                "last-modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                "content-length": "4321",
                "date": "Wed, 08 May 2026 12:00:00 GMT",
            },
            content=b"x" * 750,
        )
        subscription(page)
        subscription.filehandle.flush()

        rows = list(csv.reader(output.open()))
        assert len(rows) == 2
        url, status, title, ctype, last_mod, clen, date, size, ts = rows[1]
        assert url == "https://example.com/about"
        assert status == "200"
        assert title == "About"
        assert ctype == "text/html; charset=utf-8"
        assert last_mod == "Wed, 01 Jan 2025 00:00:00 GMT"
        assert clen == "4321"
        assert date == "Wed, 08 May 2026 12:00:00 GMT"
        assert size == "750"

    def test_strips_title_whitespace(self, subscription, output):
        subscription(make_page(title="  \n  Padded Title \t "))
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        assert rows[1][2] == "Padded Title"

    def test_timestamp_is_iso_format(self, subscription, output):
        subscription(make_page())
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        ts = rows[1][8]
        # isoformat produces e.g. "2026-05-08T12:00:00+00:00"
        assert "T" in ts
        assert ts.endswith("+00:00")

    def test_page_count_increments(self, subscription):
        assert subscription.page_count == 0
        subscription(make_page())
        assert subscription.page_count == 1
        subscription(make_page())
        assert subscription.page_count == 2

    def test_missing_headers_written_as_empty(self, subscription, output):
        subscription(make_page(headers={}))
        subscription.filehandle.flush()
        rows = list(csv.reader(output.open()))
        _, _, _, ctype, last_mod, clen, date, _, _ = rows[1]
        assert ctype == ""
        assert last_mod == ""
        assert clen == ""
        assert date == ""


@pytest.fixture
def mock_website():
    with patch("caliper.crawl.Website") as mock_cls:
        instance = MagicMock()
        for method in ("with_full_resources", "with_respect_robots_txt",
                       "with_user_agent", "with_whitelist_url"):
            getattr(instance, method).return_value = instance
        mock_cls.return_value = instance
        yield mock_cls, instance


class TestCrawl:
    def test_website_initialized_with_url(self, tmp_path, mock_website):
        mock_cls, _ = mock_website
        asyncio.run(crawl("https://example.com/", tmp_path / "out.csv", show_progress=False))
        mock_cls.assert_called_once_with("https://example.com/")

    def test_website_options_configured(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com/", tmp_path / "out.csv", show_progress=False))
        instance.with_full_resources.assert_called_once_with(True)
        instance.with_respect_robots_txt.assert_called_once_with(True)
        instance.with_user_agent.assert_called_once_with(USER_AGENT)

    def test_whitelist_applied_for_subpath(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com/blog/", tmp_path / "out.csv", show_progress=False))
        instance.with_whitelist_url.assert_called_once_with(["/blog/"])

    def test_whitelist_applied_for_path_without_trailing_slash(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com/licenses", tmp_path / "out.csv", show_progress=False))
        instance.with_whitelist_url.assert_called_once_with(["/licenses"])

    def test_no_whitelist_for_root_slash(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com/", tmp_path / "out.csv", show_progress=False))
        instance.with_whitelist_url.assert_not_called()

    def test_no_whitelist_for_bare_domain(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com", tmp_path / "out.csv", show_progress=False))
        instance.with_whitelist_url.assert_not_called()

    def test_crawl_called_with_subscription(self, tmp_path, mock_website):
        _, instance = mock_website
        asyncio.run(crawl("https://example.com/", tmp_path / "out.csv", show_progress=False))
        instance.crawl.assert_called_once()
        assert isinstance(instance.crawl.call_args[0][0], ReportSubscription)


class TestMain:
    def test_calls_crawl_with_url_and_output(self, tmp_path):
        output = tmp_path / "out.csv"
        with patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl, \
             patch("sys.argv", ["caliper", "https://example.com", str(output)]):
            main()
        mock_crawl.assert_called_once_with(
            "https://example.com", pathlib.Path(str(output)), show_progress=True
        )

    def test_progress_defaults_to_true(self, tmp_path):
        output = tmp_path / "out.csv"
        with patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl, \
             patch("sys.argv", ["caliper", "https://example.com", str(output)]):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["show_progress"] is True

    def test_no_progress_flag(self, tmp_path):
        output = tmp_path / "out.csv"
        with patch("caliper.crawl.crawl", new_callable=AsyncMock) as mock_crawl, \
             patch("sys.argv", ["caliper", "--no-progress", "https://example.com", str(output)]):
            main()
        _, kwargs = mock_crawl.call_args
        assert kwargs["show_progress"] is False

    def test_keyboard_interrupt_raises_systemexit(self, tmp_path):
        output = tmp_path / "out.csv"
        with patch("caliper.crawl.crawl", new_callable=AsyncMock, side_effect=KeyboardInterrupt), \
             patch("sys.argv", ["caliper", "https://example.com", str(output)]):
            with pytest.raises(SystemExit):
                main()
