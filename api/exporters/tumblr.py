from typing import Optional, Tuple
import pytumblr
import os
from django.conf import settings
from reader.models import Chapter, ChapterIndex, Group, Series, Volume

MAX_NUMBER_IMAGE_PER_POST = 10

def get_tumblr_credentials() -> Optional[Tuple[str, str, str, str, str]]:
    if not settings.TUMBLR_CREDENTIALS:
        return
    variables = settings.TUMBLR_CREDENTIALS.split(':')
    if len(variables) != 5:
        return
    consumer_key, consumer_secret, token, secret = variables[:4]
    # The blog name could have ":" in the url, so they need to be add back
    blog_name = ":".join(variables[4:])
    return consumer_key, consumer_secret, token, secret, blog_name


def is_tumblr_supported() -> bool:
    return True if get_tumblr_credentials() else False


def publish_post(uri_scheme: str, chapter: Chapter) -> Optional[str]:
    if not is_tumblr_supported():
        return
    consumer_key, consumer_secret, token, secret, blog_name = get_tumblr_credentials()
    client = pytumblr.TumblrRestClient(consumer_key, consumer_secret, token, secret)

    print(client.info())

    title =  f"{chapter.series.name} - Oneshot" if chapter.chapter_number == 0 and chapter.series.is_oneshot else f"{chapter.series.name} - {chapter.clean_title()}"
    root = f"{uri_scheme}://{settings.CANONICAL_ROOT_DOMAIN}"
    caption = f"###Artist: {chapter.series.author.name}"
    if not chapter.series.is_oneshot:
        caption += f"\n[Other chapters]({root}{chapter.series.get_absolute_url()})"
    if chapter.scraper_hash:
        caption += f"\n[Read on MangaDex](https://mangadex.org/chapter/{chapter.scraper_hash})\n"
    caption += f"\n[Read on Danke.moe]({root}{chapter.get_absolute_url()})"

    if chapter.series.uploadable_to_tumblr:
        image_paths = chapter.image_paths()
        res = client.create_photo(blog_name, state="published", tags=["manga", "scanlation"], format="markdown",
                        data=image_paths[:MAX_NUMBER_IMAGE_PER_POST],
                        caption=f"##{title}\n" + caption)
    else:
        res = client.create_link(blog_name, state="published", tags=["manga", "scanlation"], format="markdown",
                                 title=title, url=f"{root}{chapter.get_absolute_url()}",
                                 description=caption)
    print(res)
    if 'id' not in res or ('meta' in res and res['meta'].get('status', 200) != 200):
        print(f"Error failed to submit post: {res}")
        return
    post_url = f"{uri_scheme}://{blog_name}/{res['id']}"
    return post_url
