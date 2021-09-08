# progressbar extension

from collections import defaultdict

from rich import progress
from scrapy import signals
from scrapy.exceptions import NotConfigured


class SpiderProgressBar:
    """Progress bar tracking the number of requests queued
    and items scraped."""

    # currently written for a single spider

    def __init__(self):
        self.progress = progress.Progress(
            "{task.description}",
            progress.BarColumn(bar_width=None),  # full width
            "{task.completed}/{task.total}",
            "{task.percentage:>3.1f}%",
            progress.TimeElapsedColumn(),
            transient=True,
        )
        self.tasks = {}
        self.totals = defaultdict(int)
        self.items_scraped = defaultdict(int)

    @classmethod
    def from_crawler(cls, crawler):
        # first check if the extension should be enabled and raise
        # NotConfigured otherwise
        if not crawler.settings.getbool("PROGRESSBAR_ENABLED"):
            raise NotConfigured

        # instantiate the extension object
        ext = cls()

        # connect the extension object to signals
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(ext.request_scheduled, signal=signals.request_scheduled)
        crawler.signals.connect(ext.request_dropped, signal=signals.request_dropped)

        # return the extension object
        return ext

    def spider_opened(self, spider):
        self.progress.__enter__()  # open context manager usually called via "with"
        self.tasks[spider.name] = self.progress.add_task("Crawling...")

    def spider_closed(self, spider):
        pass
        # NOTE: leaving the progress bar open for now
        # so final display includes the total items / time

        # self.progress.stop_task(self.tasks[spider.name])
        # once all tasks have been removed, exit the progress bar
        # if self.progress.finished:
        # how to indicate successful exit?
        # self.progress.__exit__(exc_type=None, exc_val=0, exc_tb=None)

    def item_scraped(self, item, spider):
        # increment progress bar
        self.progress.advance(self.tasks[spider.name])

    def request_scheduled(self, request, spider):
        # when a new request is scheduled, increase the total
        # and update the progress bar
        self.totals[spider.name] += 1
        self.progress.update(self.tasks[spider.name], total=self.totals[spider.name])

    def request_dropped(self, request, spider):
        # when a request is dropped by the scheduler, decrease the total
        self.totals[spider.name] -= 1
        self.progress.update(self.tasks[spider.name], total=self.totals[spider.name])
