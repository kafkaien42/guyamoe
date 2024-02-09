import hashlib
import json
import os
import time
from typing import Optional
import zipfile
from datetime import datetime

import natsort
from discord import Embed, RequestsWebhookAdapter, Webhook
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt
import api.exporters.tumblr as tumblr

from reader.models import Chapter, ChapterIndex, Group, Series, Volume, Person
from reader.users_cache_lib import get_user_ip


from .api import (
    all_groups,
    chapter_post_process,
    clear_pages_cache,
    clear_series_cache,
    create_chapter_obj,
    get_chapter_preferred_sort,
    series_data_cache,
    zip_chapter,
)


@cache_control(public=True, max_age=30, s_maxage=30)
def get_series_data(request, series_slug):
    series_api_data = cache.get(f"series_api_data_{series_slug}")
    if not series_api_data:
        series_api_data = series_data_cache(series_slug)
    return HttpResponse(json.dumps(series_api_data), content_type="application/json")


@cache_control(public=True, max_age=900, s_maxage=900)
def get_all_series(request):
    """get_all_series/ endpoint """
    all_series_data = cache.get("all_series_data")
    if not all_series_data:
        all_series = Series.objects.all().select_related("author", "artist")
        all_series_data = {}
        for series in all_series:
            vols = Volume.objects.filter(series=series).order_by("-volume_number")
            cover_vol_url = ""
            for vol in vols:
                if vol.volume_cover:
                    cover_vol_url = f"/media/{vol.volume_cover}"
                    break
            chapters = Chapter.objects.filter(series=series, is_public=True)
            last_updated = None
            for ch in chapters:
                if not last_updated or ch.uploaded_on > last_updated:
                    last_updated = ch.uploaded_on
            all_series_data[series.name] = {
                "author": series.author.name,
                "artist": series.artist.name,
                "description": series.synopsis,
                "slug": series.slug,
                "cover": cover_vol_url,
                "groups": all_groups(),
                "last_updated": int(datetime.timestamp(last_updated))
                if last_updated
                else 0,
            }
        cache.set("all_series_data", all_series_data, 3600 * 12)
    return HttpResponse(json.dumps(all_series_data), content_type="application/json")


@cache_control(public=True, max_age=7200, s_maxage=7200)
def get_groups(request, series_slug):
    groups_data = cache.get(f"groups_data_{series_slug}")
    if not groups_data:
        groups_data = {
            str(ch.group.id): ch.group.name
            for ch in Chapter.objects.filter(series__slug=series_slug, is_public=True).select_related(
                "group"
            )
        }
        cache.set(f"groups_data_{series_slug}", groups_data, 3600 * 12)
    return HttpResponse(
        json.dumps({"groups": groups_data}), content_type="application/json"
    )


@cache_control(public=True, max_age=7200, s_maxage=7200)
def get_all_groups(request):
    return HttpResponse(json.dumps(all_groups()), content_type="application/json")


@cache_control(public=True, max_age=21600, s_maxage=21600)
def download_chapter(request, series_slug, chapter):
    group = request.GET.get("group", None)
    chapter_number = float(chapter.replace("-", "."))
    if not group:
        ch_obj = None
        ch_qs = Chapter.objects.filter(
            series__slug=series_slug, chapter_number=chapter_number
        )
        if not ch_qs:
            return HttpResponseBadRequest()
        preferred_sort = get_chapter_preferred_sort(ch_qs.first())
        if preferred_sort:
            for group in preferred_sort:
                ch_obj = ch_qs.filter(group__id=int(group)).first()
                if ch_obj:
                    break
        if not ch_obj:
            ch_obj = ch_qs.first()
    else:
        if not group.isdigit():
            return HttpResponseBadRequest()
        ch_obj = Chapter.objects.get(
            series__slug=series_slug,
            chapter_number=chapter_number,
            group__id=int(group),
        )
    group = str(ch_obj.group.id)
    chapter_dir = os.path.join(
        settings.MEDIA_ROOT, "manga", series_slug, "chapters", ch_obj.folder
    )
    zip_chapter_file = f"{group}_{ch_obj.slug_chapter_number()}.zip"
    zip_path = os.path.join(chapter_dir, zip_chapter_file)
    if os.path.exists(zip_path) and not (
        time.time() - os.stat(zip_path).st_mtime > (3600 * 8)
    ):
        with open(os.path.join(chapter_dir, zip_chapter_file), "rb") as f:
            zip_file = f.read()
    else:
        zip_file, _, _ = zip_chapter(ch_obj)
    resp = HttpResponse(zip_file, content_type="application/x-zip-compressed")
    resp[
        "Content-Disposition"
    ] = f"attachment; filename={ch_obj.slug_chapter_number()}.zip"
    return resp


def sort_naturally_input_filenames(filenames):
    # Let's hope that natsort can deal with all the silly number conversions it receives.
    return natsort.natsorted(filenames, alg=natsort.PATH | natsort.IGNORECASE | natsort.FLOAT)


def is_valid_regular_file(filepath: str):
    # Must have an extension, not be part of Mac OS's hidden file and not have relative folder
    return '.' in filepath and '__MACOSX' not in filepath and '../' not in filepath


def save_zip_file(input_zip_file, chapter_folder, group_folder):
    with zipfile.ZipFile(input_zip_file) as zip_file:
        all_pages = sort_naturally_input_filenames(zip_file.namelist())
        
        # remove invalid file path
        all_pages = list(filter(is_valid_regular_file, all_pages))
    
        padding = len(str(len(all_pages)))
        for idx, page in enumerate(all_pages):
            print(page)
            extension = page.rsplit(".", 1)[1]
            page_file = f"{str(idx+1).zfill(padding)}.{extension}"
            with open(
                os.path.join(chapter_folder, group_folder, page_file), "wb"
            ) as f:
                f.write(zip_file.read(page))


def get_webhook_id_token_from_url(webhook_url: str):
    """
    Input: https://discord.com/api/webhooks/1042230246973374564/2WdWK9Xsk0ki-MbgQllx5q6p0XNDs3FuzgpVVcCN-58bVKOxHOGmQwFT94vu6JQqi-oq
    Output: 1042230246973374564, 2WdWK9Xsk0ki-MbgQllx5q6p0XNDs3FuzgpVVcCN-58bVKOxHOGmQwFT94vu6JQqi-oq
    """
    url_components = webhook_url.rstrip('/').split('/')
    return int(url_components[-2]), url_components[-1]


def post_prerelease_to_discord(uri_scheme: str, chapter):
    if not settings.DISCORD_PRERELEASE_WEBHOOK_URL:
        print("Discord webhook url for prerelease is not set.")
        return
    webhook_id, webhook_token = get_webhook_id_token_from_url(settings.DISCORD_NSFW_PRERELEASE_WEBHOOK_URL if chapter.series.is_nsfw else settings.DISCORD_PRERELEASE_WEBHOOK_URL)
    webhook = Webhook.partial(webhook_id, webhook_token, adapter=RequestsWebhookAdapter())

    root = f"{uri_scheme}://{settings.CANONICAL_ROOT_DOMAIN}"
    url = f"{root}{chapter.get_absolute_url()}" if chapter.is_public else f"{root}{chapter.get_private_absolute_url()}"
    series_url = f"{root}{chapter.series.get_absolute_url()}"
    author_url = f"{root}{chapter.series.author.get_absolute_url()}"
    artist_url = f"{root}{chapter.series.artist.get_absolute_url()}"
    chapter_1st_image = f"{root}{chapter.first_page_absolute_url()}"
    site_log_url = f"{root}/static/logo-mt-squared-small.png"
    version_label = f"(v{chapter.version})" if chapter.version else "(v1)"

    em = Embed(
        color=0x000000,
        title=f"Ch. {chapter.clean_chapter_number()} {version_label} of {chapter.series.name} -  Please PR this new release!",
        description=f"{url}\n\n"
                    f"[Read other chapters]({series_url})\n"
                    f"[Read other series by this author]({author_url})\n\n"
                    f"{settings.DISCORD_PRERELEASE_MESSAGE}",
        url=url,
        timestamp=datetime.utcnow(),
    )
    em.set_author(name=f"{chapter.series.author.name}", url=author_url)

    em.add_field(name='Author', value=f"[{chapter.series.author.name}]({author_url})", inline=True)
    em.add_field(name='Artist', value=f"[{chapter.series.artist.name}]({artist_url})", inline=True)

    em.set_image(url=chapter_1st_image)

    # Only ping if it is the first version of the chapter
    ping_role = settings.DISCORD_PING_NSFW_QC_ROLE if chapter.series.is_nsfw else settings.DISCORD_PING_QC_ROLE
    ping_str = None if chapter.version else ping_role
    webhook.send(content=ping_str, embed=em, username=settings.DISCORD_USERNAME, avatar_url=site_log_url)


def post_release_to_discord(uri_scheme: str, chapter: Chapter, tumblr_post_url: Optional[str]):
    webhook_url = settings.DISCORD_NSFW_RELEASE_WEBHOOK_URL if chapter.series.is_nsfw else settings.DISCORD_RELEASE_WEBHOOK_URL
    if not webhook_url:
        print("Discord webhook url for release is not set.")
        return
    webhook_id, webhook_token = get_webhook_id_token_from_url(webhook_url)
    webhook = Webhook.partial(webhook_id, webhook_token, adapter=RequestsWebhookAdapter())

    root = f"{uri_scheme}://{settings.CANONICAL_ROOT_DOMAIN}"
    url = f"{root}{chapter.get_absolute_url()}"
    series_url = f"{root}{chapter.series.get_absolute_url()}"
    author_url = f"{root}{chapter.series.author.get_absolute_url()}"
    artist_url = f"{root}{chapter.series.artist.get_absolute_url()}"
    chapter_1st_image = f"{root}{chapter.first_page_absolute_url()}"
    site_log_url = f"{root}/static/logo-mt-squared-small.png"

    links = f"{url}\n"
    if chapter.scraper_hash:
        links += f"https://mangadex.org/chapter/{chapter.scraper_hash}\n" 
    if tumblr_post_url:
        links += f"{tumblr_post_url}\n" 

    
    title =  f"{chapter.series.name} - Oneshot" if chapter.chapter_number == 0 and chapter.series.is_oneshot else f"{chapter.series.name} - {chapter.clean_title()}"
    em = Embed(
        color=0x000000,
        title=title,
        description=f"{links}\n"
                    f"[Read other chapters]({series_url})\n"
                    f"[Read other series by this author]({author_url})\n",
        url=url,
        timestamp=datetime.utcnow(),
    )
    em.set_author(name=f"{chapter.series.author.name}", url=author_url)

    em.add_field(name='Author', value=f"[{chapter.series.author.name}]({author_url})", inline=True)
    em.add_field(name='Artist', value=f"[{chapter.series.artist.name}]({artist_url})", inline=True)

    em.set_image(url=chapter_1st_image)

    ping_str = settings.DISCORD_PING_NEW_RELEASE
    if chapter.series.is_nsfw:
        ping_str += " " + settings.DISCORD_PING_NEW_NSFW_RELEASE
    if chapter.series.is_oneshot and settings.DISCORD_PING_ONESHOT:
        ping_str += " " + settings.DISCORD_PING_ONESHOT
    if chapter.series.discord_role_id:
        ping_str += f" <@&{chapter.series.discord_role_id}>"
    summary_str = f" {title} by {chapter.series.author.name}"
    webhook.send(content=ping_str + summary_str, embed=em, username=settings.DISCORD_USERNAME, avatar_url=site_log_url)


def upload_new_chapter(request, series_slug):
    if request.method == "POST" and request.user and request.user.is_staff:
        group = Group.objects.get(name=request.POST["scanGroup"])
        series = Series.objects.get(slug=series_slug)
        chapter_number = float(request.POST["chapterNumber"])
        volume = request.POST["volumeNumber"]
        title = request.POST["chapterTitle"]
        ch_obj, chapter_folder, group_folder, is_update = create_chapter_obj(
            chapter_number, group, series, volume, title
        )
        save_zip_file(request.FILES["chapterPages"], chapter_folder, group_folder)
        chapter_post_process(ch_obj, is_update=is_update)
        if "notifyOnDiscord" in request.POST and request.POST["notifyOnDiscord"]:
            post_prerelease_to_discord(request.scheme, ch_obj)
        return HttpResponse(
            json.dumps({"response": "success"}), content_type="application/json"
        )
    else:
        return HttpResponse(
            json.dumps({"response": "failure"}), content_type="application/json"
        )


def publish_chapter(request, series_slug, chapter):
    if request.method == "POST" and request.user and request.user.is_staff:
        series = Series.objects.get(slug=series_slug)
        chapter = Chapter.objects.get(chapter_number=chapter, series=series)
        chapter.is_public = True
        chapter.save()
        
        tumblr_post_url = None
        if not series.is_nsfw:
            tumblr_post_url = tumblr.publish_post(request.scheme, chapter)
        post_release_to_discord(request.scheme, chapter, tumblr_post_url)
        return HttpResponse(
            json.dumps({"response": "success"}), content_type="application/json"
        )
    
    return HttpResponse(
        json.dumps({"response": "failure"}), content_type="application/json"
    )


def upload_new_oneshot(request):
    if request.method == "POST" and request.user and request.user.is_staff:
        author_name = request.POST["author"]
        author = Person.objects.filter(name=author_name).all()[0]
        slug = request.POST["seriesSlug"]
        is_oneshot = request.POST['isOneshot'] == "oneshot"

        series = Series.objects.create(
            name=request.POST["seriesTitle"],
            slug=slug,
            author=author,
            artist=author,
            synopsis=request.POST["synopsis"],
            alternative_titles=request.POST["alternativeTitles"],
            scraping_enabled=False,
            is_oneshot=(request.POST['isOneshot'] == "oneshot")
        )
        if is_oneshot:
            request.POST["chapterTitle"] = "oneshot"

        if "seriesCover" in request.FILES:
            Volume.objects.create(volume_number=request.POST["volumeNumber"], series=series, volume_cover=request.FILES["seriesCover"])

        return upload_new_chapter(request, slug)
    else:
        return HttpResponse(
            json.dumps({"response": "failure"}), content_type="application/json"
        )


@csrf_exempt
@cache_control(public=True, max_age=3600, s_maxage=3600)
def get_volume_covers(request, series_slug):
    if request.method == "POST":
        covers = cache.get(f"vol_covers_{series_slug}")
        if not covers:
            series = Series.objects.get(slug=series_slug)
            volume_covers = (
                Volume.objects.filter(series=series)
                .order_by("volume_number")
                .values_list("volume_number", "volume_cover")
            )
            covers = {
                "covers": [
                    [
                        cover[0],
                        f"/media/{str(cover[1])}",
                        f"/media/{str(cover[1]).rsplit('.', 1)[0]}.webp",
                    ]
                    for cover in volume_covers
                    if cover[1]
                ]
            }
            cache.set(f"vol_covers_{series_slug}", covers)
        return HttpResponse(json.dumps(covers), content_type="application/json")
    else:
        return HttpResponse(json.dumps({}), content_type="application/json")


@csrf_exempt
def search_index(request, series_slug):
    if request.method == "POST":
        series = Series.objects.get(slug=series_slug)
        search_query = request.POST["searchQuery"]
        search_results = {}
        for word in set(search_query.split()[:20]):
            word_query = ChapterIndex.objects.filter(
                word__startswith=word.upper(), series=series
            )
            search_results[word] = {}
            for word_obj in word_query:
                chapter_and_pages = json.loads(word_obj.chapter_and_pages)
                search_results[word][word_obj.word] = chapter_and_pages
        return HttpResponse(json.dumps(search_results), content_type="application/json")
    else:
        return HttpResponse(json.dumps({}), content_type="application/json")


@csrf_exempt
def clear_cache(request):
    if request.method == "POST" and request.user and request.user.is_staff:
        if request.POST["clear_type"] == "all":
            clear_pages_cache()
            response = "Cleared all cache"
        elif request.POST["clear_type"] == "chapter":
            for series_slug in Series.objects.all().values_list("slug"):
                clear_series_cache(series_slug)
            response = "Cleared series cache"
        else:
            response = "Not a valid option"
        return HttpResponse(
            json.dumps({"response": response}), content_type="application/json"
        )
    else:
        return HttpResponse(json.dumps({}), content_type="application/json")


@csrf_exempt
def black_hole_mail(request):
    if request.method == "POST":
        text = request.POST["text"]
        user_ip = get_user_ip(request)
        user_sent_count = cache.get(f"mail_user_ip_{user_ip}")
        if not user_sent_count:
            cache.set(f"mail_user_ip_{user_ip}", 1, 30)
        else:
            user_sent_count += 1
            if user_sent_count > 4:
                return HttpResponse(
                    json.dumps({"error": "Error: sending mail too frequently."}),
                    content_type="application/json",
                )
            else:
                cache.set(f"mail_user_ip_{user_ip}", user_sent_count, 30)
        if len(text) > 2000:
            return HttpResponse(
                json.dumps(
                    {"error": "Error: message too long. can only send 2000 characters."}
                ),
                content_type="application/json",
            )
        try:
            webhook = Webhook.partial(
                settings.MAIL_DISCORD_WEBHOOK_ID,
                settings.MAIL_DISCORD_WEBHOOK_TOKEN,
                adapter=RequestsWebhookAdapter(),
            )
            em = Embed(
                color=0x000000,
                title="Black Hole",
                description=f"⚫ You've got guyamail! 📬\n\n{text}",
                timestamp=datetime.utcnow(),
            )
            em.set_footer(
                text=f"IP hash: {hashlib.md5(user_ip.encode()).hexdigest()[:32]}"
            )
            webhook.send(content=None, embed=em, username="Guya.moe")
        except (AttributeError, NameError):
            feedback_folder = os.path.join(settings.MEDIA_ROOT, "feedback")
            os.makedirs(feedback_folder, exist_ok=True)
            feedback_file = str(int(datetime.utcnow().timestamp()))
            with open(os.path.join(feedback_folder, f"{feedback_file}.txt"), "w") as f:
                f.write(text)
        return HttpResponse(
            json.dumps({"success": "Mail successfully crossed the event horizon"}),
            content_type="application/json",
        )
