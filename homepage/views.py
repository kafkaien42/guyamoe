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
from django.db.models import Min, F, Max, Q

from homepage.middleware import ForwardParametersMiddleware
from reader.middleware import OnlineNowMiddleware
from reader.models import Chapter, Series, Volume, HitCount, Person, Group
from reader.views import series_page_data
from itertools import repeat


@staff_member_required
@cache_control(public=True, max_age=30, s_maxage=30)
def admin_home(request):
    online = cache.get("online_now")
    peak_traffic = cache.get("peak_traffic")

    groups = [str(group.name) for group in Group.objects.all()]
    authors = [str(author.name) for author in Person.objects.all()]
    return render(
        request,
        "homepage/admin_home.html",
        {
            "online": len(online) if online else 0,
            "peak_traffic": peak_traffic,
            "groups": groups,
            "authors": authors,
            "template": "home",
            "version_query": settings.STATIC_VERSION,
        },
    )


def chapters_data():
    chapters_page_dt = cache.get(f"chapters_page_dt")
    if not chapters_page_dt:
        # series = get_object_or_404(Series)
        chapters = Chapter.objects.order_by("-uploaded_on").select_related(
            "series", "group"
        )
        chapter_content_type = ContentType.objects.get(app_label="reader", model="chapter")
        chapters_hit_count = HitCount.objects.filter(content_type=chapter_content_type).all()
        id_to_hit_count = {int(hit_count.object_id) : int(hit_count.hits) for hit_count in chapters_hit_count}
        seriess = Series.objects.all()
        latest_chapter = chapters.latest("uploaded_on") if chapters else None
        chapter_list = []
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
                    id_to_hit_count.get(int(chapter.id), 0),
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
            ],
            "reader_modifier": "read/manga",
        }
        if settings.ALLOWS_DOWNLOAD_AS_ZIP:
            chapters_page_dt["available_features"].append("download")
        cache.set(f"chapters_page_dt", chapters_page_dt, 3600 * 12)
    return chapters_page_dt


def series_data(include_series=False, include_oneshots=False, author_slug=None, nsfw=False):
    assert include_series or include_oneshots, "You must include something."
    to_label = {
        (True, True): "ongoing",
        (False, True): "oneshots",
        (True, False): "series",
    }
    cache_label = f"{to_label[(include_series, include_oneshots)]}_{'nsfw' if nsfw else 'sfw'}_page_dt"
    if author_slug:
        cache_label += author_slug
    series_page_dt = cache.get(cache_label)
    if not series_page_dt:

        # Filter series we are not interested in based which page we are generating

        only_series_from_type = Series.objects.filter(is_nsfw=nsfw).filter(chapter__isnull=False)
        if not include_series or not include_oneshots:
            only_series_from_type = only_series_from_type.filter(is_oneshot=include_oneshots)
        if author_slug:
            only_series_from_type = only_series_from_type.filter(Q(author__slug=author_slug) | Q(artist__slug=author_slug))

        # Order all series by the upload time of their latest chapter
        latest_series = only_series_from_type.annotate(Max('chapter__uploaded_on')).order_by('-chapter__uploaded_on__max')

        # Find the first volume cover of each series that has a volume

        volumes = Volume.objects.select_related("series").all()
        series_to_first_volume = {}
        for volume in volumes:
            vol_num = int(volume.volume_number)
            if volume.series.id not in series_to_first_volume:
                series_to_first_volume[volume.series.id] = (vol_num, volume)
            elif series_to_first_volume[volume.series.id][0] > vol_num:
                series_to_first_volume[volume.series.id] = (vol_num, volume)

        series_list = []
        for series in latest_series:
            # For some stupid reason, there is no relationship between chapters and volumes
            volume = None
            if series.id in series_to_first_volume:
                volume = series_to_first_volume[series.id][1]
            has_cover = volume and volume.volume_cover and volume.volume_cover != ""
            a_series_list = {
                "name": series.name,
                "slug": series.slug,
                "series_url": f"/read/manga/{series.slug}/",
                "metadata": [],
                "has_cover": has_cover,
                "is_nsfw": series.is_nsfw
            }
            if has_cover:
                path, _, ext = str(volume.volume_cover).rpartition('.')
                volume_cover_webp = f"/media/{path}.webp"
                volume_cover_blur = f"/media/{path}_blur.{ext}"
                a_series_list["volume_cover"] = volume_cover_blur if series.is_nsfw else volume_cover_webp
                a_series_list["volume_cover_width"] = int(volume.volume_cover.width)
                a_series_list["volume_cover_height"] = int(volume.volume_cover.height)
            series_list.append(a_series_list)

        series_page_dt = {
            "series_list": series_list,
            "root_domain": settings.CANONICAL_ROOT_DOMAIN,
            "available_features": [
                "volumeCovers",
            ],
        }
        cache.set(cache_label, series_page_dt, 3600 * 12)
    return series_page_dt


@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_chapters(request):
    data = chapters_data()
    data["version_query"] = settings.STATIC_VERSION
    data["page_title"] = "Latest Chapters"
    return render(request, "homepage/show_chapters.html", data)


@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_ongoing(request):
    data = series_data(include_series=True, include_oneshots=True)
    data["version_query"] = settings.STATIC_VERSION
    # data["page_title"] = "Series"
    return render(request, "homepage/show_series.html", data)


@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_series(request):
    data = series_data(include_series=True)
    data["version_query"] = settings.STATIC_VERSION
    data["page_title"] = "Series"
    return render(request, "homepage/show_series.html", data)


@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_oneshots(request):
    data = series_data(include_oneshots=True)
    data["version_query"] = settings.STATIC_VERSION
    data["page_title"] = "Oneshots"
    return render(request, "homepage/show_series.html", data)

@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def all_nsfw(request):
    data = series_data(include_series=True, include_oneshots=True, nsfw=True)
    data["version_query"] = settings.STATIC_VERSION
    data["page_title"] = "NSFW"
    return render(request, "homepage/show_series.html", data)


@cache_control(public=True, max_age=300, s_maxage=300)
@decorator_from_middleware(OnlineNowMiddleware)
def author_series(request, author_slug: str):
    author_slug = str(author_slug)
    author = Person.objects.filter(slug=author_slug).first()
    if author:
        data = series_data(include_series=True, include_oneshots=True, author_slug=author_slug)
        data["version_query"] = settings.STATIC_VERSION
        data["page_title"] = f"{author.name} | All Series"
        data["available_features"].append("title")
        data["author"] = str(author.name)
        return render(request, "homepage/show_series.html", data)
    return render(request, "homepage/how_cute_404.html", status=404)


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
