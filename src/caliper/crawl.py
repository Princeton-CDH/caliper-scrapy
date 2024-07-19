import asyncio
import argparse
import csv
import datetime
import pathlib
from signal import SIGINT, SIGTERM

from tqdm import tqdm
from spider_rs import Website

# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = "caliper (+http://cdh.princeton.edu)"
# TODO: include version


class ReportSubscription:
    def __init__(self, output, show_progress=True):
        self.filehandle = output.open("w")
        self.csvwriter = csv.writer(self.filehandle)
        self.csvwriter.writerow(
            [
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
        )

        # postfix automatically starts with a comma
        disable_progress = not show_progress
        self.status = tqdm(
            desc="Crawling", bar_format="{desc}{postfix}", disable=disable_progress
        )
        self.pbar = tqdm(bar_format="{n:,} urls {elapsed}", disable=disable_progress)
        self.page_count = 0

    def __call__(self, page):
        self.csvwriter.writerow(
            [
                page.url,
                page.status_code,
                # some titles (*cough* PPA) include leading/trailing whitesapce
                page.title().strip(),
                page.headers.get("content-type"),
                page.headers.get("last-modified"),
                page.headers.get("content-length"),
                page.headers.get("date"),
                len(page.raw_content),
                # timestamp in isoformat so we can filter csv more easily
                datetime.datetime.now(tz=datetime.UTC).isoformat(),
            ]
        )
        self.page_count += 1
        self.pbar.update(self.page_count)
        self.status.set_postfix_str(f"URL: {page.url}")

    def __del__(self):
        self.filehandle.close()
        # self.status.set_postfix_str("") # clear last url or leave?
        self.status.close()
        self.pbar.close()


async def crawl(url, output, show_progress=True):
    # second arg indicates we want raw content
    # crawl all resources found, not just web pages
    website = (
        Website(url, True)
        .with_full_resources(True)
        .with_respect_robots_txt(True)
        .with_user_agent(USER_AGENT)
    )

    # handle ctrl-c
    loop = asyncio.get_running_loop()
    for signal_enum in [SIGINT, SIGTERM]:
        #        loop.add_signal_handler(signal_enum, loop.stop)
        loop.add_signal_handler(signal_enum, website.stop)

    website.crawl(ReportSubscription(output, show_progress=show_progress))


def main():
    parser = argparse.ArgumentParser(
        description="Crawl a website and generate a CSV report of contents"
    )
    parser.add_argument("url", help="URL for the site to be crawled")
    parser.add_argument(
        "output",
        help="filename where the filtered corpus should be saved",
        type=pathlib.Path,
    )
    parser.add_argument(
        "--progress",
        help="Show progress",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    asyncio.run(crawl(args.url, args.output, show_progress=args.progress))


if __name__ == "__main__":
    main()
