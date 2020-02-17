import tornado.web

from riptide_mission_control.server.starter import HostnameMatcher
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
        self.write("<code><pre>\n=== DEFAULT VIEW ==\n")
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

