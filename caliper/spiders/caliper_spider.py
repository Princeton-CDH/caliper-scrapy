from datetime import datetime
import urllib.parse

import scrapy
import json


class CaliperSpider(scrapy.Spider):
    """Caliper spider. Requires starting url to be passed in.  Only urls
    within the same domain will be followed and included in the crawl.
    Example usage::

        scrapy crawl caliper -a url=https://cdh.princeton.edu -o cdh-datetime-vXX.jl

    """

    name = "caliper"
    handle_httpstatus_list = [200, 404, 401, 403, 410, 301, 302, 303, 500]

    iframes = []
    error_pages = []

    def __init__(self, *args, **kwargs):
        super(CaliperSpider, self).__init__(*args, **kwargs)
        start_url = kwargs.get('url')
        self.start_urls = [start_url]
        # parse starting url and store the domain;
        # used to keep crawl to within this site
        self.domain = urllib.parse.urlsplit(start_url).netloc

    def parse(self, response):
        # return information for the current url
        yield {
            'url': response.url,
            'status_code': response.status,
            # convert headers from binary to string to support json output
            'content_type': response.headers.get('Content-Type', '').decode(),
            'last_modified': response.headers.get('Last-Modified', '').decode(),
            'content_length': response.headers.get('Content-Length', '').decode(),
            'size': len(response.body),
            # 'links': 1,
            # note this only documents the first place we found it
            'referrer': response.request.meta.get('referrer', ''),
            # timestamp in isoformat so we can filter on it more easily
            'timestamp': datetime.utcnow().isoformat(),
        }

        # if content is html, look for links and other assets to crawl
        # find all links and included content:
        # header link, image, script, a, iframe
        is_texthtml = 'Content-Type' in response.headers and \
            'text/html' in response.headers.get('Content-Type').decode()

        if is_texthtml:
            urls = []
            # html links, excluding mail tos
            urls.extend([href.get() for href in response.css('a::attr(href)')
                         if not href.get().startswith('mailto:') and
                         not href.get().startswith('javascript:')])
            # header links (e.g., css, icons, etc)
            urls.extend([href.get() for href in response.css('link::attr(href)')])
            # javascript
            urls.extend([src.get() for src in response.css('script::attr(src)')])
            # iframe src: by definition, won't be within same domain...
            # but useful/important for reporting on websites
            for iframe_src in response.css('iframe::attr(src)'):
                self.iframes.append((response.url, iframe_src.get()))
            # should we follow iframes urls?
            # yield response.follow(iframe_src, callback=self.parse)

            # images are more complicated;
            # handle 1x/2x/media and lazy-loaded images
            for img in response.css('img'):
                srcset = img.attrib.get('srcset') or img.attrib.get('data-srcset')
                src = img.attrib.get('src') or img.attrib.get('data-src')
                if srcset:
                    # split on comma, strip whitespace,
                    # then split on whitespace to remove 2x or media query
                    for imgsrc in srcset.split(','):
                        urls.append(imgsrc.strip().split(' ')[0])
                if src:
                    urls.append(src)

            # filter urls to local or same domain as our starting url
            # keep within same site, not just subdomain
            site_urls = [url for url in urls if
                         not url.startswith('http') or
                         urllib.parse.urlsplit(url).netloc == self.domain]

            yield from response.follow_all(site_urls, callback=self.parse,
                                           meta={'referrer': response.url})

        if response.status in [301, 302, 303]:
            # when a redirect is crawled, follow
            # FIXME: restrict to on-site urls
            yield response.follow(response.headers.get('Location').decode(), callback=self.parse,
                                  meta={'referrer': response.url})

        if int(response.status) > 400:
            self.error_pages.append((response.url, response.status,
                                     response.request.meta.get('referrer', '')))


    def closed(self, reason):
        # TODO: improve reporting
        if self.iframes:
            print('\nIframes: (source url, iframe url)')
            for source_url, iframe in self.iframes:
                print('%s\t%s' % (source_url, iframe))
        if self.error_pages:
            print('\nErrors: (error url, status code, referrer)')
            for url, status_code, referrer in self.error_pages:
                print('%s\t%s\t%s' % (url, status_code, referrer))
