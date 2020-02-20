from typing import Union, Pattern

import tornado.web
import tornado.routing
from riptide_proxy.server.http import ProxyHttpHandler
import tornado.httpclient

import gc
from guppy import hpy


h=hpy()


def get_profiling_route(hostname):
    return [
        (HostnameMatcher(r'/', hostname), ProfileHttpHandler, {}),
    ]


class ProfileHttpHandler(tornado.web.RequestHandler):

    SUPPORTED_METHODS = ("GET")

    def compute_etag(self):
        return None  # disable tornado Etag

    async def get(self):
        """
        Print the current heap usage
        :return:
        """
        heap = h.heap()
        self.write("<code><pre>")
        self.write("\n\n=== gc: INSTANCES OF ProxyHttpHandler ==\n")
        self.write(f"{sum(1 for o in gc.get_referrers(ProxyHttpHandler))}\n")
        self.write("\n\n=== gc: INSTANCES OF AsyncHTTPClient ==\n")
        self.write(f"{sum(1 for o in gc.get_referrers(tornado.httpclient.AsyncHTTPClient))}\n")

        self.write("\n\n=== DEFAULT VIEW ==\n")
        self.write(str(heap))

        self.write("\n\n=== BYTYPE VIEW ==\n")
        self.write(str(heap.bytype))

        self.write("\n\n=== BYRCS VIEW ==\n")
        self.write(str(heap.byrcs))

        for i in range(0, 5):
            if i <= len(heap.bytype):
                self.write(f"\n\n=== BYRCRS[{i}].byclodo ==\n")
                self.write(str(heap.byrcs[i].byclodo))

        for i in range(0, 5):
            if i <= len(heap.bytype):
                self.write(f"\n\n=== BYRCRS[{i}].byid ==\n")
                self.write(str(heap.byrcs[i].byid))

        for i in range(0, 5):
            if i <= len(heap.bytype):
                self.write(f"\n\n=== BYRCRS[{i}].byvia ==\n")
                self.write(str(heap.byrcs[i].byvia))

        for i in range(0, 5):
            if i <= len(heap.bytype):
                self.write(f"\n\n=== BYRCRS[{i}].referents ==\n")
                self.write(str(heap.byrcs[i].referents))


class HostnameMatcher(tornado.routing.PathMatches):

    def __init__(self, path_pattern: Union[str, Pattern], hostname: str) -> None:
        self.hostname = hostname
        super().__init__(path_pattern)

    def match(self, request):
        """ Match path and hostname """
        if request.host_name != self.hostname:
            return None
        return super().match(request)
