import random as r
from collections import OrderedDict, defaultdict
from datetime import datetime

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.decorators import decorator_from_middleware
from django.views.decorators.cache import cache_control
from django.db.models import Min, F, Max

from homepage.middleware import ForwardParametersMiddleware
from reader.middleware import OnlineNowMiddleware
from reader.models import Chapter, Series, Volume
from reader.views import series_page_data


@staff_member_required
@cache_control(public=True, max_age=30, s_maxage=30)
def admin_home(request):
    online = cache.get("online_now")
    peak_traffic = cache.get("peak_traffic")
    return render(
        request,
        "homepage/admin_home.html",
        {
            "online": len(online) if online else 0,
            "peak_traffic": peak_traffic,
            "template": "home",
            "version_query": settings.STATIC_VERSION,
        },
    )

cache_control(public=True, max_age=60, s_maxage=60)
def chapters_data():
    chapters_page_dt = cache.get(f"chapters_page_dt")
    if not chapters_page_dt:
        # series = get_object_or_404(Series)
        chapters = Chapter.objects.order_by("-uploaded_on").select_related(
            "series", "group"
        )
        seriess = Series.objects.all()
        latest_chapter = chapters.latest("uploaded_on") if chapters else None
        chapter_list = []
        volume_dict = defaultdict(list)
        for chapter in chapters:
            u = chapter.uploaded_on
            chapter_list.append(
                [
                    chapter.clean_chapter_number(),
                    chapter.clean_chapter_number(),
                    chapter.title,
                    chapter.slug_chapter_number(),
                    chapter.group.name,
                    [u.year, u.month - 1, u.day, u.hour, u.minute, u.second],
                    chapter.volume or "null",
                    chapter.series.name,
                    chapter.series.slug,
                ]
            )
            volume_dict[chapter.volume].append(
                [
                    chapter.clean_chapter_number(),
                    chapter.slug_chapter_number(),
                    chapter.group.name,
                    [u.year, u.month - 1, u.day, u.hour, u.minute, u.second],
                ]
            )
        unique_series = []
        for series in seriess:
            unique_series.append([series.slug, f"read/manga/{series.slug}/", series.name])
        chapters_page_dt = {
            "metadata": [
                [
                    "Last Updated",
                    f"Ch. {latest_chapter.clean_chapter_number() if latest_chapter else ''} - {datetime.utcfromtimestamp(latest_chapter.uploaded_on.timestamp()).strftime('%Y-%m-%d') if latest_chapter else ''}",
                ],
            ],
            "chapter_list": chapter_list,
            "root_domain": settings.CANONICAL_ROOT_DOMAIN,
            "unique_series": unique_series,
            "available_features": [
                "detailed",
                "rss",
                "download",
            ],
            "reader_modifier": "read/manga",
        }
        cache.set(f"chapters_page_dt", chapters_page_dt, 3600 * 12)
    return chapters_page_dt


cache_control(public=True, max_age=60, s_maxage=60)
def series_data():
    series_page_dt = cache.get(f"series_page_dt")
    if not series_page_dt:
        # series = get_object_or_404(Series)
        # volumes = Volume.objects.select_related(
        #     "series"
        # ).values('series').annotate(Min('volume_number'))

        # min_vol = Volume.objects.order_by('series').values('series').annotate(Min('volume_number'))
        # volumes = Volume.objects.select_related("series").filter(volume_number__in=min_vol.values_list('volume_number__min', flat=True))
        series_latest_uploaded = Chapter.objects.order_by('series').values('series').annotate(Max('uploaded_on'))
        latest_chapters = Chapter.objects.select_related("series").filter(uploaded_on__in=series_latest_uploaded.values_list('uploaded_on__max', flat=True)).order_by("-uploaded_on")

        series_list = []
        for chapter in latest_chapters:
            # For some stupid reason, there is no relationship between chapters and volumes
            volume = Volume.objects.filter(volume_number=chapter.volume, series=chapter.series).first()
            if not volume:
                print("Cannot find volume for chapter", chapter)
                continue
            series_list.append({
                "name": chapter.series.name,
                "slug": chapter.series.slug,
                "series_url": f"/read/manga/{chapter.series.slug}/",
                "metadata" : [
                    f"Last Updated Ch. {chapter.clean_chapter_number()} - {datetime.utcfromtimestamp(chapter.uploaded_on.timestamp()).strftime('%Y-%m-%d')}"
                    ],
                "volume_cover": f"/media/{volume.volume_cover}",
                "volume_cover_webp": f"/media/{str(volume.volume_cover).rsplit('.', 1)[0]}.webp",
                })
        series_page_dt = {
            "series_list": series_list,
            "root_domain": settings.CANONICAL_ROOT_DOMAIN,
            "available_features": [
                "volumeCovers",
            ],
            # "reader_modifier": "read/manga",
        }
        cache.set(f"series_page_dt", series_page_dt, 3600 * 12)
    return series_page_dt


cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_chapters(request):
    data = chapters_data()
    data["version_query"] = settings.STATIC_VERSION
    return render(request, "homepage/show_chapters.html", data)


cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_series(request):
    data = series_data()
    data["version_query"] = settings.STATIC_VERSION
    return render(request, "homepage/show_series.html", data)


@cache_control(public=True, max_age=3600, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def about(request):
    return render(
        request,
        "homepage/about.html",
        {
            "relative_url": "about/",
            "template": "about",
            "page_title": "About",
            "version_query": settings.STATIC_VERSION,
        },
    )


@decorator_from_middleware(ForwardParametersMiddleware)
def random(request):
    random_opts = cache.get("random_opts")
    if not random_opts:
        random_opts = [
            (ch.series.slug, ch.slug_chapter_number())
            for ch in Chapter.objects.all().select_related("series")]
        cache.set("random_opts", random_opts, 3600 * 96)
    series_slug, chap_slug = r.choice(random_opts)
    return redirect(
        "reader-manga-chapter",
        series_slug,
        chap_slug,
        "1",
    )


def handle404(request, exception):
    return render(request, "homepage/how_cute_404.html", status=404)
