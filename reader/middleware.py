from django.core.cache import cache
from .users_cache_lib import get_user_ip

class OnlineNowMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ### Install and test with memcache first
        user_ip = get_user_ip(request)
        online = cache.get("online_now")
        peak_traffic = cache.get("peak_traffic")
        if not peak_traffic:
            peak_traffic = 0
        if online:
            online = set([ip for ip in online if cache.get(ip)])
        else:
            online = set([])
        cache.set(user_ip, user_ip, 600)
        online.add(user_ip)
        if len(online) > peak_traffic:
            peak_traffic = len(online)
        cache.set("online_now", online, 600)
        cache.set("peak_traffic", peak_traffic, 3600 * 8)
        request.online_now = len(online)
        request.peak_traffic = peak_traffic
        response = self.get_response(request)
        return response