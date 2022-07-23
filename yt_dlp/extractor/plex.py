import urllib.parse

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    int_or_none,
    parse_age_limit,
    traverse_obj,
)


class PlexWatchBaseIE(InfoExtractor):
    _NETRC_MACHINE = 'plex'
    # provider url is in https://plex.tv/media/providers?X-Plex-Token=<plex_token>
    # nb: need Accept: application/json, otherwise return xml
    _CDN_ENDPOINT = {
        'vod': 'https://vod.provider.plex.tv',
        'live': 'https://epg.provider.plex.tv',
        # from api ( identifier : baseUrl)
        'tv.plex.provider.epg': 'https://epg.provider.plex.tv',
        'tv.plex.provider.vod': 'https://vod.provider.plex.tv',
        'tv.plex.provider.music': 'https://music.provider.plex.tv',
        # not used yet, but will be supported
        'tv.plex.provider.discover': 'https://discover.provider.plex.tv',
        'tv.plex.provider.metadata': 'https://metadata.provider.plex.tv',

    }

    _TOKEN = None
    _CLIENT_IDENTIFIER = None

    def _initialize_pre_login(self):
        # TO DO: find better way to get cookie
        # request to random page in plex.tv to get clientIdentifier in cookie
        if self._TOKEN is None:
            client_id = self._request_webpage(  # noqa: F841
                'https://watch.plex.tv/', 'client_id', note='Downloading html page to get clientIdentifier')
            self.write_debug('trying to get clientIdentifier')

            # get cookie from cookiejar
            cookie_ = {cookie.name: cookie.value for cookie in self.cookiejar}
            self._CLIENT_IDENTIFIER = cookie_.get('clientIdentifier')

    def _perform_login(self, username, password):
        self.write_debug('Trying to login')
        try:
            resp_api = self._download_json(
                'https://plex.tv/api/v2/users/signin', 'Auth', query={'X-Plex-Client-Identifier': self._CLIENT_IDENTIFIER},
                data=f'login={username}&password={password}&rememberMe=true'.encode(),
                headers={'Accept': 'application/json'}, expected_status=429,
                note='Downloading JSON Auth Info')
            self.write_debug('login successfully')
            self._TOKEN = resp_api.get('authToken')

        except ExtractorError as e:
            # Default to non-login error when there's any problem in login
            error = self._parse_json(e.cause.read(), 'login error')
            self.write_debug(f'There\'s error on login : {error["errors"][0]["message"]}, caused by {e.cause} '
                             f'trying to use non-login method')

    def _real_initialize(self):
        if not self._TOKEN:
            try:
                # WARNING: This API request is rate-limited
                self.write_debug('using non-login method (login as anonymous)')
                resp_api = self._download_json(
                    'https://plex.tv/api/v2/users/anonymous', 'Auth', data=b'',
                    headers={
                        'X-Plex-Provider-Version': '6.2.0',
                        'Accept': 'application/json',
                        'X-Plex-Product': 'Plex Mediaverse',
                        'X-Plex-Client-Identifier': self._CLIENT_IDENTIFIER.encode()
                    },
                    note='Downloading JSON Auth Info (as anonymous)')
            except ExtractorError as e:
                error = self._parse_json(e.cause.read(), 'login error')
                raise ExtractorError(error['errors'][0]['message'], cause=e.cause)

            self._TOKEN = resp_api['authToken']

    def _get_formats_and_subtitles(self, selected_media, display_id, sites_type='vod', metadata_field={}, format_field={}):
        formats, subtitles = [], {}
        fmts, subs = [], {}
        if isinstance(selected_media, str):
            selected_media = [selected_media]
        for media in selected_media or []:
            if determine_ext(media) == 'm3u8' or media.endswith('hls'):
                fmt, subs = self._extract_m3u8_formats_and_subtitles(
                    f'{self._CDN_ENDPOINT[sites_type]}{media}',
                    display_id, query={'X-PLEX-TOKEN': self._TOKEN})
                for fmt_ in fmt:
                    fmt_.update(**format_field)
                    fmts.append(fmt_)

            elif determine_ext(media) == 'mpd':

                fmt, subs = self._extract_mpd_formats_and_subtitles(
                    f'{self._CDN_ENDPOINT[sites_type]}{media}',
                    display_id, query={'X-PLEX-TOKEN': self._TOKEN})
                for fmt_ in fmt:
                    fmt_.update(**format_field)
                    fmts.append(fmt_)
            else:
                formats.append({
                    'url': f'{self._CDN_ENDPOINT[sites_type]}{media}?X-Plex-Token={self._TOKEN}',
                    'ext': 'mp4',
                    **metadata_field
                })

            formats.extend(fmts)
            self._merge_subtitles(subs, target=subtitles)
        return formats, subtitles

    def _get_clips(self, nextjs_json, display_id):
        self.write_debug('Trying to download Extras/trailer')

        media_json_list = []
        for _media in traverse_obj(nextjs_json, ('Extras', 'Metadata', ..., 'key')):
            media_json_list.append(self._download_json(
                'https://play.provider.plex.tv/playQueues', display_id,
                query={'uri': f'provider://tv.plex.provider.vod{_media}'}, data=b'',
                headers={'X-PLEX-TOKEN': self._TOKEN, 'Accept': 'application/json'}))

        for media in traverse_obj(media_json_list, (..., 'MediaContainer', 'Metadata', ...)) or []:
            for media_ in traverse_obj(media, ('Media', ..., 'Part', ..., 'key')):
                fmt, sub = self._get_formats_and_subtitles(media_, display_id, format_field={'format_note': 'Extras video'})
                yield {
                    'id': media['ratingKey'],
                    'title': media['title'],
                    'formats': fmt,
                    'subtitles': sub,
                }

    def _extract_movie(self, nextjs_json, display_id, sites_type, **kwargs):
        media_json = self._download_json(
            'https://play.provider.plex.tv/playQueues', display_id,
            query={'uri': nextjs_json['playableKey']}, data=b'',
            headers={'X-PLEX-TOKEN': self._TOKEN, 'Accept': 'application/json'})

        selected_media = []
        for media in media_json['MediaContainer']['Metadata']:
            if media.get('slug') == display_id or sites_type == 'show':
                selected_media = traverse_obj(media, ('Media', ..., 'Part', ..., 'key'))
                break

        formats, subtitles = self._get_formats_and_subtitles(selected_media, display_id)
        self._sort_formats(formats)

        return {
            'id': nextjs_json.get('playableID') or nextjs_json['ratingKey'],
            'display_id': display_id,
            'formats': formats,
            'subtitles': subtitles,
            'title': nextjs_json.get('title'),
            'alt_title': nextjs_json.get('originalTitle'),
            'description': nextjs_json.get('summary'),
            'thumbnail': nextjs_json.get('thumb'),
            'duration': int_or_none(nextjs_json.get('duration'), 1000),
            'cast': traverse_obj(nextjs_json, ('Role', ..., 'tag')),
            'rating': parse_age_limit(nextjs_json.get('contentRating')),
            'categories': traverse_obj(nextjs_json, ('Genre', ..., 'tag')),
            **kwargs,
        }

    def _extract_data(self, url, **kwargs):
        sites_type, display_id = self._match_valid_url(url).group('sites_type', 'id')

        nextjs_json = self._search_nextjs_data(
            self._download_webpage(url, display_id), display_id)['props']['pageProps']['metadataItem']

        movie_entry = [self._extract_movie(nextjs_json, display_id, sites_type, **kwargs)] if nextjs_json.get('playableKey') else []

        if self._yes_playlist(nextjs_json['ratingKey'], 'Movie'):
            trailer_entry = list(self._get_clips(nextjs_json, display_id)) if nextjs_json.get('Extras') else []
            movie_entry.extend(trailer_entry)
            return self.playlist_result(movie_entry, nextjs_json['ratingKey'], nextjs_json.get('title'))
        else:
            if len(movie_entry) == 0:
                raise ExtractorError('No movie/episode video found')
            else:
                return movie_entry[0]


class PlexWatchMovieIE(PlexWatchBaseIE):
    _VALID_URL = r'https?://watch\.plex\.tv/(?:\w+/)?(?:country/\w+/)?(?P<sites_type>movie)/(?P<id>[\w-]+)'
    _TESTS = [{
        # movie only
        'url': 'https://watch.plex.tv/movie/bowery-at-midnight',
        'info_dict': {
            'id': '627585f7408eb57249d905d5',
            'display_id': 'bowery-at-midnight',
            'ext': 'mp4',
            'title': 'Bowery at Midnight',
            'description': 'md5:7ebaa1b530d98f042295e18d6f4f8c21',
            'duration': 3660,
            'thumbnail': 'https://image.tmdb.org/t/p/original/lDWHvIotQkogG77wHVuMT8mF8P.jpg',
            'cast': 'count:22',
            'categories': ['Horror', 'Action', 'Comedy', 'Crime', 'Thriller'],
        }
    }, {
        # trailer only
        'url': 'https://watch.plex.tv/movie/the-sea-beast-2',
        'info_dict': {
            'id': '5d77709a6afb3d002061df55',
            'title': 'The Sea Beast'
        },
        'playlist_count': 4,
    }, {
        # movie and trailer
        'url': 'https://watch.plex.tv/movie/wheels-on-meals',
        'info_dict': {
            'id': '5d776d10594b2b001e700571',
            'title': 'Wheels on Meals',
        },
        'playlist_count': 2,
    }]

    def _real_extract(self, url):
        return self._extract_data(url)


class PlexWatchEpisodeIE(PlexWatchBaseIE):
    _VALID_URL = r'https?://watch\.plex\.tv/(?:\w+/)?(?:country/\w+/)?(?P<sites_type>show)/(?P<id>[\w-]+)/season/(?P<season_num>\d+)/episode/(?P<episode_num>\d+)'
    _TESTS = [{
        'url': 'https://watch.plex.tv/show/popeye-the-sailor/season/1/episode/1',
        'info_dict': {
            'id': '5ebdfbd4808e8b0040551a4c',
            'ext': 'mp4',
            'display_id': 'popeye-the-sailor',
            'description': 'md5:d3fcad5bd678b43428f93944b66c2752',
            'thumbnail': 'https://image.tmdb.org/t/p/original/r3SwiK3IANuAAvb1a0oShu8HKcV.jpg',
            'title': 'Barbecue for Two',
            'episode_number': 1,
            'episode': 'Episode 1',
            'season': 'Season 1',
            'season_number': 1,
        }
    }, {
        'url': 'https://watch.plex.tv/show/a-cooks-tour-2/season/1/episode/3',
        'info_dict': {
            'id': '624c6c71d8d423a47b4fa7a7',
            'ext': 'mp4',
            'description': 'md5:54aec1794285c7e977e87d726439b01f',
            'display_id': 'a-cooks-tour-2',
            'title': 'Cobra Heart, Food That Makes You Manly',
            'thumbnail': 'https://metadata-static.plex.tv/b/gracenote/b4452f949f600db816b3e6a51ce0674a.jpg',
            'episode': 'Episode 3',
            'episode_number': 3,
            'season_number': 1,
            'season': 'Season 1',
        }
    }]

    def _real_extract(self, url):
        return self._extract_data(
            url, episode_number=int_or_none(self._match_valid_url(url).group('episode_num')),
            season_number=int_or_none(self._match_valid_url(url).group('season_num')))


class PlexWatchSeasonIE(PlexWatchBaseIE):
    _VALID_URL = r'https?://watch\.plex\.tv/show/(?P<season>[\w-]+)/season/(?P<season_num>\d+)/?(?:$|[#?])'
    _TESTS = [{
        'url': 'https://watch.plex.tv/show/a-cooks-tour-2/season/1',
        'info_dict': {
            'id': '624c6b291e79c48d83a2b04e',
            'title': 'A Cook\'s Tour',
            'season': 'A Cook\'s Tour',
            'season_number': '1',
        },
        'playlist_count': 22,
    }]

    def _get_episode_result(self, episode_list, season_name, season_index):
        for episode in episode_list:
            yield self.url_result(
                f'https://watch.plex.tv/show/{season_name}/season/{season_index}/episode/{episode}',
                ie=PlexWatchEpisodeIE)

    def _real_extract(self, url):
        season_name, season_num = self._match_valid_url(url).group('season', 'season_num')

        nextjs_json = self._search_nextjs_data(
            self._download_webpage(url, season_name), season_name)['props']['pageProps']

        return self.playlist_result(
            self._get_episode_result(
                traverse_obj(nextjs_json, ('episodes', ..., 'index')), season_name, season_num),
            traverse_obj(nextjs_json, ('metadataItem', 'playableID')),
            traverse_obj(nextjs_json, ('metadataItem', 'parentTitle')),
            traverse_obj(nextjs_json, ('metadataItem', 'summary')),
            season=traverse_obj(nextjs_json, ('metadataItem', 'parentTitle')), season_number=season_num)


class PlexWatchLiveIE(PlexWatchBaseIE):
    _VALID_URL = r'https?://watch\.plex\.tv/live-tv/channel/(?P<id>[\w-]+)'
    _TESTS = [{
        'url': 'https://watch.plex.tv/live-tv/channel/euronews',
        'info_dict': {
            'id': '5e20b730f2f8d5003d739db7-60089d90f682a3002c348299',
            'ext': 'mp4',
            'title': r're:[\w\s-]+[\d-]+\s*[\d+:]+',
            'display_id': 'euronews',
            'live_status': 'is_live',
        }
    }]

    def _real_extract(self, url):
        display_id = self._match_id(url)

        nextjs_json = self._search_nextjs_data(
            self._download_webpage(url, display_id), display_id)['props']['pageProps']['channel']
        media_json = self._download_json(
            f'https://epg.provider.plex.tv/channels/{nextjs_json["id"]}/tune',
            display_id, data=b'', headers={'X-PLEX-TOKEN': self._TOKEN, 'Accept': 'application/json'})

        formats, subtitles = self._get_formats_and_subtitles(
            traverse_obj(media_json, (
                'MediaContainer', 'MediaSubscription', ..., 'MediaGrabOperation', ..., 'Metadata', ..., 'Media', ..., 'Part', ..., 'key')),
            display_id, 'live')

        return {
            'id': nextjs_json['id'],
            'display_id': display_id,
            'title': traverse_obj(media_json, ('MediaContainer', 'MediaSubscription', 0, 'title')),
            'formats': formats,
            'subtitles': subtitles,
            'live_status': 'is_live',
        }


class PlexAppIE(PlexWatchBaseIE):
    _VALID_URL = r'https://app\.plex\.tv/\w+/#!/provider/(?P<provider>(tv\.plex\.provider\.((?!music)\w+)))/details\?key\s*=\s*(?P<key>%2Flibrary%2Fmetadata%2F(?P<id>[a-f0-9]+))'
    _TESTS = [{
        # movie
        'url': 'https://app.plex.tv/desktop/#!/provider/tv.plex.provider.vod/details?key=%2Flibrary%2Fmetadata%2F5e0c0cda7440fc0020ab9ff5&context=library%3Ahub.movies.documentary~16~7',
        'info_dict': {
            'id': '5e0c0cda7440fc0020ab9ff5',
            'display_id': 'nazi-concentration-and-prison-camps',
            'ext': 'mp4',
            'title': 'Nazi Concentration and Prison Camps',
            'thumbnail': 'https://image.tmdb.org/t/p/original/uNxkPkR2GGG71JSyh2Lqptnwcwm.jpg',
            'cast': ['Dwight D. Eisenhower', 'Jack Taylor'],
            'duration': 3540,
            'description': 'md5:cc021d47035520acf2e027b8b4d244c2',
            'view_count': int,
            'categories': ['Documentary', 'History'],
        },
        'params': {
            'skip_download': True
        },
    }, {
        # episode
        'url': 'https://app.plex.tv/desktop/#!/provider/tv.plex.provider.vod/details?key=%2Flibrary%2Fmetadata%2F62b0fbd90776e5797e7d92fe&context=library%3Ahub.movies.reality-tv~8~9',
        'info_dict': {
            'id': '62b0fbd90776e5797e7d92fe',
            'ext': 'mp4',
            'duration': 1350,
            'description': 'Gorilla makes funny gestures and postures; horse makes funny faces; duck honking a horn.',
            'view_count': int,
            'title': 'If you\'re happy and you know it',
            'episode_number': 1,
            'season_number': 1,
            'episode': 'Episode 1',
            'display_id': 'funniest-pets-and-people',
            'thumbnail': 'https://cf-images.us-east-1.prod.boltdns.net/v1/jit/6058083015001/d958c52a-3e73-4902-8623-adfe2f36ea3f/main/1280x720/11m15s61ms/match/image.jpg',
            'season': 'Season 1',
        },
        'params': {
            'skip_download': True,
        }
    }, {
        # season
        'url': 'https://app.plex.tv/desktop/#!/provider/tv.plex.provider.vod/details?key=%2Flibrary%2Fmetadata%2F62a8b77b93fc109a6d020761&context=library%3Ahub.movies.reality-tv~8~9',
        'info_dict': {
            'id': '62a8b77b93fc109a6d020761',
            'title': 'Funniest Pets & People',
            'season': 'Funniest Pets & People',
            'season_number': '1',
            'thumbnail': 'https://image.tmdb.org/t/p/original/ngm14GVJ6jULL3zKK6puuVagRLH.jpg',
        },
        'playlist_count': 15,
    }, {
        # Extras
        'url': 'https://app.plex.tv/desktop/#!/provider/tv.plex.provider.metadata/details?key=%2Flibrary%2Fmetadata%2F5ef5ee0d1ce3fd004039976a&context=library%3Ahub.home.top_watchlisted~4~1',
        'info_dict': {
            'id': '5ef5ee0d1ce3fd004039976a',
            'title': 'Lightyear',
            'cast': 'count:34',
            'thumbnail': r're:https://image\.tmdb\.org/t/p/original/\w+\.jpg',
            'duration': 6000,
            'rating': 10,
        },
        'playlist_count': 22,
    }]

    def _real_extract(self, url):
        provider, key, display_id = self._match_valid_url(url).group('provider', 'key', 'id')
        key = urllib.parse.unquote(key)
        media_json = self._download_json(
            f'{self._CDN_ENDPOINT[provider]}{key}', display_id, query={'uri': f'provider://{provider}{key}', 'X-Plex-Token': self._TOKEN},
            headers={'Accept': 'application/json'})['MediaContainer']['Metadata'][0]

        # check if publicPagesURL, if exists redirect to PlexWatch*IE, else handle manually
        if media_json.get('publicPagesURL'):
            self.write_debug('got publicPagesURL, redirect to PlexWatch*IE')

            additional_info = {
                'view_count': int_or_none(media_json.get('viewCount')),
                'thumbnail': media_json.get('thumb'),
                'duration': int_or_none(media_json.get('duration'), 1000),
                'cast': traverse_obj(media_json, ('Role', ..., 'tag')),
                'rating': parse_age_limit(media_json.get('contentRating')),
            }

            return self.url_result(media_json.get('publicPagesURL'), url_transparent=True, **additional_info)

        else:
            if media_json.get('type') in ('episode', 'movie'):
                selected_media = traverse_obj(
                    media_json, ('Media', ..., 'Part', ..., 'key'))

                formats, subtitles = self._get_formats_and_subtitles(selected_media, display_id, provider)
                return {
                    'id': display_id,
                    'ext': 'mp4',
                    'title': media_json.get('title'),
                    'description': media_json.get('summary'),
                    'formats': formats,
                    'subtitles': subtitles,
                    'thumbnail': media_json.get('thumb'),
                    'duration': int_or_none(media_json.get('duration'), 1000),
                    'cast': traverse_obj(media_json, ('Role', ..., 'tag')),
                    'rating': parse_age_limit(media_json.get('contentRating')),
                    'view_count': media_json.get('viewCount')
                }