# Danke.moe
Website for the [Danke Für Lesen](https://danke.moe) scanlation group.
Generalized manga reading framework for scanlation groups. This is a fork of [Guya.moe](https://github.com/appu1232/guyamoe), a website focus on Kaguya-sama manga. Most of the nginx configs are from [mahoushoujobu.com](https://github.com/milleniumbug/guyamoe)'s fork.

Difference from the original:
 - You should only need to update `about.html`, `layout.html`, `base.py`, `prod.py` and of course the logos to have a functional website for you scanlation group.
 - Remove hardcoded reference to Kaguya-sama in source code. The website will work even if there is no manga in the database.
 - Add a homepage where the series are shown as a gallery.
 - Add a page to see the list of chapters from all series.
 - In embbedded link to chapters a preview of the first page is shown, instead of the site's logo.
 - Sitemap.xml works even if you don't have pages.


⚠ **Note:** The install instructions below will not result in a general purpose CMS due to the amount of hardcoded assets.

⚠ **Important:** Please don't use this framework to run ads.

Limitations:
 - This is not a a generalized CMS!
 - Only one unique numbered chapter per scanlation group per series.
 - No multilingual support, so you cannot have the same chapter in different languages.
 - Only one group assigned to each chapter. One work around for collaborations is to create a group with the name of both groups.
 - No tagging system. The only tag currently is `is_oneshot`.

## Prerequisites 
- git
- python 3.6.5+
- pip
- virtualenv

For Debian:
```
sudo apt-get install libpq-dev build-essential python3-dev python3-pip
```

## Install
1. Create a venv for Guyamoe in your home directory.
```
virtualenv -p python3 ~/env_guyamoe
```

2. Clone Guyamoe's source code into the venv.
```
git clone https://github.com/kafkaien42/guyamoe ~/guyamoe
```

3. Activate the venv.
```
cd ~/guyamoe && source ~/env_guyamoe/bin/activate
```

4. Install Guyamoe's dependencies.
```
pip3 install -r requirements.txt
```

At this point you may get an error that pg_config is missing. [Install development version of PostgreSQL.](https://stackoverflow.com/questions/11618898/pg-config-executable-not-found)

5. Change the value of the `SECRET_KEY` variable to a randomly generated string.
```
sed -i "s|\"o kawaii koto\"|\"$(openssl rand -base64 32)\"|" guyamoe/settings/base.py
```

6. Upstream repo don't have migrations set up because something. It's possible it will be fixed later, in the meantime do this.
```
mkdir misc/migrations && touch misc/migrations/__init__.py
```

7. Create an admin user for Guyamoe.
```
python3 manage.py createsuperuser
```

8. Collect static files. Otherwise the admin static files won't be accessible.
```
python3 manage.py collectstatic
```

Before starting the server, create a `media` folder in the base directory. Add manga with the corresponding chapters and page images. Structure it like so:
```
media
└───manga
    └───<series-slug-name>
        └───chapters
        	└───001
            	├───001.jpg
            	├───002.jpg
           		└───...
```
E.g. `Kaguya-Wants-To-Be-Confessed-To` for `<series-slug-name>`. 

**Note:** Zero pad chapter folder numbers like so: `001` for the Kaguya series (this is how the fixtures data for the series has it). It doesn't matter for pages though nor does it have to be .jpg. Only thing required for pages is that the ordering can be known from a simple numerical/alphabetical sort on the directory.

## Start the server
-  `python3 manage.py runserver` - keep this console active

Now the site should be accessible on localhost:8000

Django docs say this: [DO NOT USE THIS SERVER IN A PRODUCTION SETTING. It has not gone through security audits or performance tests.](https://docs.djangoproject.com/en/3.1/ref/django-admin/). Below is the section on my attempt on making it work good enough for production, on Debian.

## How to Use

Pretty much everything is done throught `/admin`.  To upload a new chapter or update a chapter you need to go to the series page's (`/reader/series/<series_slug_name>`) and add `/admin` to the url to get `/reader/series/<series_slug_name>/admin`, a upload button should appear. While you don't necessary need to create a volume to each chapter, some part of the website will ignore chapters without an assigned volume. 

Relevant URLs (as of now): 

- `/` - home page
- `/about` - about page
- `/admin` - admin view (login with created user above)
- `/admin_home` - admin endpoint for clearing the site's cache
- `/reader/series/<series_slug_name>` - series info and all chapter links
- `/reader/series/<series_slug_name>/<chapter_number>/<page_number>` - url scheme for reader opened on specfied page of chapter of series.
- `/api/series/<series_slug_name>` - all series data requested by reader frontend
- `/media/manga/<series_slug_name>/<chapter_number>/<page_file_name>` - url scheme to used by reader to actual page as an image.

# Debian setup

The `nginx` directory contains systemd module, the script and nginx config. Nginx is a web server that will communicate with guyamoe Django app through uWSGI.
These instructions make a lot of assumptions. Adjust these instructions and configuration to your own needs.

Install uWSGI

```
pip3 install uwsgi
```

Add the user that will be running the app to www-data

```
sudo usermod -a -G www-data ubuntu
```

Copy the config to appropriate places

```
sudo cp nginx/guyamoe.service /etc/systemd/system
sudo cp nginx/guya-site-nginx /etc/nginx/sites-available/guyamoe
sudo ln -s /etc/nginx/sites-available/guyamoe /etc/nginx/sites-enabled/guyamoe
```

To start the server and make start at boot time:
```
systemctl start guyamoe.service
systemctl enable guyamoe.service
```

Use [certbot](https://certbot.eff.org/) to set up TLS certificate for your own domain.

# Tool
To check if the paths of every chapter and volume are valid:
```
python3 manage.py chapter_sanity_check
```
