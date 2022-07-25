import re
import json
import urllib.parse
import base64

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    determine_ext,
    float_or_none,
    get_element_text_and_html_by_tag,
    join_nonempty,
    traverse_obj,
    url_or_none,
)


class DailyWireBaseIE(InfoExtractor):
    _NETRC_MACHINE = 'dailywire'
    _JSON_PATH = {
        'episode': ('props', 'pageProps', 'episodeData', 'episode'),
        'videos': ('props', 'pageProps', 'videoData', 'video'),
        'podcasts': ('props', 'pageProps', 'episode'),
    }
    _HEADER = {
        'content-type': 'application/json',
    }
    _QUERY = {}
    
    def _perform_login(self, username, password):
        # The login function still in work
        self.write_debug('Trying to login')
        '''
        The url requests to https://authorize.dailywire.com/authorize 
        and require 'response_type(=code)' and 'client_id'. This url should
        redirect and the give us _csrf cookie
        '''
        webpage_instance = self._request_webpage(
            'https://authorize.dailywire.com/authorize', 'authorize webpage',
            query={'response_type': 'code', 'client_id': 'hDgwLR0K67GTe9IuVKATlbohhsAbD37H'})
        
        next_url = webpage_instance.geturl()
        
        required_query = urllib.parse.parse_qs(next_url)
        
        
        authorize_webpage = self._download_webpage(
            next_url, 'auth_webpage')
        #print(get_element_text_and_html_by_tag('script', authorize_webpage))
        # extra parameter can be found in <script> var config = JSON.parse(<config>),
        # the <config> is base64 decoded
        config_json = re.search(
            r'\bwindow\.atob\("(?P<data>[\w=]+)"[\)]+', authorize_webpage).group('data')
        config_json = self._parse_json(
            base64.b64decode(config_json), 'config')
        
        print(config_json)
        
        try :
            real_login_webpage = self._download_webpage(
                'https://authorize.dailywire.com/usernamepassword/login', 'login url',
                data=json.dumps({
                    'connection': 'Username-Password-Authentication',
                    'client_id': config_json.get('clientID'),
                    'tenant': 'dailywire',
                    'sso': True,
                    'popup_option': [],
                    'audience': 'https://api.dailywire.com/',
                    'redirect_uri': config_json.get('callbackURL'),
                    'username': f'{username}', 
                    'password': f'{password}',
                    **config_json.get('extraParams')}).encode(),
                headers={
                    'Content-Type': 'application/json',
                    'Auth0-Client': 'eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMTkuMyIsImVudiI6eyJsb2NrLmpzLXVscCI6IjExLjE1LjAiLCJhdXRoMC1qcy11bHAiOiI5LjEwLjIifX0=',
                    })
            
        except ExtractorError as e:
            if not isinstance(e.cause, urllib.error.HTTPError):
                raise
            error = self._parse_json(e.cause.read(), 'error')
            raise ExtractorError(traverse_obj(error, ('description')))
        
        callback_request_data = self._hidden_inputs(real_login_webpage)
        print(callback_request_data)
        
        # code below return error 404 at final redirect
        callback_request = self._request_webpage(
            'https://authorize.dailywire.com/login/callback', 'callback_url',
            data=f'wa={callback_request_data.get("wa")}&wresult={callback_request_data.get("wresult")}&wctx={callback_request_data.get("wctx")}&rememberMe=true'.encode(),
            fatal=False)
        print(callback_request.geturl)
        '''
         The url get token from 'https://authorize.dailywire.com/oauth/token' (POST), with request body contain
         {
            'client_id': <client_id>,
            'code': <code>,
            'code_verifier': <code_verifier>,
            'grant_type': 'authorization_code',
            'redirect_url': https://www.dailywire.com/callback
         }
         From this url, we can get the token in json['access_token']
        '''
        raise ExtractorError
    def _get_json(self, url):
        sites_type, slug = self._match_valid_url(url).group('sites_type', 'id')
        json_data = self._search_nextjs_data(self._download_webpage(url, slug), slug)
        
        # another api call, can be used to get access_token and fallback json
        nextdata_api_json = self._download_json(
            f'https://www.dailywire.com/_next/data/{json_data.get("buildId")}/{sites_type}/{slug}.json',
            slug, headers=self._HEADER)
        
        # this is not a proper solution to get cookie though,
        # actually we can the access_token from https://authorize.dailywire.com/oauth/token,
        # but this requires full login support (-u, -p, --netrc)
        
        # access_token = self._get_cookies(f'https://www.dailywire.com/_next/data/{json_data.get("buildId")}/episode/{slug}.json').get('access_token')
        
        # set access_token from cookie to headers
        # assuming the access_token token is always Bearer
        
        # self._HEADER['Authorization'] = f'Bearer {access_token}'

        # using graphql api
        query = {
            'query': self._QUERY,
            'variables': {'slug': f'{slug}'}
        }
        # this url call below expected to get Authorization Header if login
        json_page = self._download_json(
            'https://v2server.dailywire.com/app/graphql',
            slug, data=json.dumps(query).encode(), headers=self._HEADER, fatal=False,
            note='Downloading graphql json')

        return slug, traverse_obj(json_page, ('data', 'episode')) or traverse_obj(json_data or nextdata_api_json, self._JSON_PATH[sites_type])


class DailyWireIE(DailyWireBaseIE):
    _VALID_URL = r'https?://(?:www\.)dailywire(?:\.com)/(?P<sites_type>episode|videos)/(?P<id>[\w-]+)'
    _QUERY = '''
query getEpisodeBySlug($slug: String!) {
  episode(where: {slug: $slug}) {
    id
    title
    status
    slug
    isLive
    description
    createdAt
    scheduleAt
    updatedAt
    image
    allowedCountryNames
    allowedContinents
    rating
    show {
        id
        name
        slug
        belongsTo
    }
    segments {
        id
        image
        title
        liveChatAccess
        audio
        video
        duration
        watchTime
        description
        videoAccess
        muxAssetId
        muxPlaybackId
        captions {
            id
        }
    }
    createdBy {
        firstName
        lastName
    }
    discussionId
    }
}
'''
    _TESTS = [{
        'url': 'https://www.dailywire.com/episode/1-fauci',
        'info_dict': {
            'id': 'ckzsl50xnqpy30850in3v4bu7',
            'ext': 'mp4',
            'display_id': '1-fauci',
            'title': '1. Fauci',
            'description': 'md5:9df630347ef85081b7e97dd30bc22853',
            'thumbnail': 'https://daily-wire-production.imgix.net/episodes/ckzsl50xnqpy30850in3v4bu7/ckzsl50xnqpy30850in3v4bu7-1648237399554.jpg',
            'creator': 'Caroline Roberts',
            'series_id': 'ckzplm0a097fn0826r2vc3j7h',
            'series': 'China: The Enemy Within',
        }
    }, {
        'url': 'https://www.dailywire.com/episode/ep-124-bill-maher',
        'info_dict': {
            'id': 'cl0ngbaalplc80894sfdo9edf',
            'ext': 'mp3',
            'display_id': 'ep-124-bill-maher',
            'title': 'Ep. 124 - Bill Maher',
            'thumbnail': 'https://daily-wire-production.imgix.net/episodes/cl0ngbaalplc80894sfdo9edf/cl0ngbaalplc80894sfdo9edf-1647065568518.jpg',
            'creator': 'Caroline Roberts',
            'description': 'md5:adb0de584bcfa9c41374999d9e324e98',
            'series_id': 'cjzvep7270hp00786l9hwccob',
            'series': 'The Sunday Special',
        }
    }, {
        'url': 'https://www.dailywire.com/videos/the-hyperions',
        'only_matching': True,
    }, {
        'url': 'https://www.dailywire.com/episode/ep-1520-the-return-of-religious-freedom-bonus-hour-2',
        'info_dict': {
            'id': 'fixme',
            'ext': 'mp4',
        }
    }]

    def _real_extract(self, url):
        slug, episode_info = self._get_json(url)
        urls = traverse_obj(episode_info, (('segments', 'videoUrl'), ..., ('video', 'audio')), expected_type=url_or_none)
        formats, subtitles = [], {}
        
        # 'or []' intended to give better error message at the end of processing not as fallback
        for url in urls or []:
            if determine_ext(url) != 'm3u8':
                formats.append({'url': url})
                continue
            format_, subs_ = self._extract_m3u8_formats_and_subtitles(url, slug)
            formats.extend(format_)
            self._merge_subtitles(subs_, target=subtitles)
        self._sort_formats(formats)
        return {
            'id': episode_info['id'],
            'display_id': slug,
            'title': traverse_obj(episode_info, 'title', 'name'),
            'description': episode_info.get('description'),
            'creator': join_nonempty(('createdBy', 'firstName'), ('createdBy', 'lastName'), from_dict=episode_info, delim=' '),
            'duration': float_or_none(episode_info.get('duration')),
            'is_live': episode_info.get('isLive'),
            'thumbnail': traverse_obj(episode_info, 'thumbnail', 'image', expected_type=url_or_none),
            'formats': formats,
            'subtitles': subtitles,
            'series_id': traverse_obj(episode_info, ('show', 'id')),
            'series': traverse_obj(episode_info, ('show', 'name')),
        }


class DailyWirePodcastIE(DailyWireBaseIE):
    _VALID_URL = r'https?://(?:www\.)dailywire(?:\.com)/(?P<sites_type>podcasts)/(?P<podcaster>[\w-]+/(?P<id>[\w-]+))'
    _TESTS = [{
        'url': 'https://www.dailywire.com/podcasts/morning-wire/get-ready-for-recession-6-15-22',
        'info_dict': {
            'id': 'cl4f01d0w8pbe0a98ydd0cfn1',
            'ext': 'm4a',
            'display_id': 'get-ready-for-recession-6-15-22',
            'title': 'Get Ready for Recession | 6.15.22',
            'description': 'md5:c4afbadda4e1c38a4496f6d62be55634',
            'thumbnail': 'https://daily-wire-production.imgix.net/podcasts/ckx4otgd71jm508699tzb6hf4-1639506575562.jpg',
            'duration': 900.117667,
        }
    }]

    def _real_extract(self, url):
        slug, episode_info = self._get_json(url)
        audio_id = traverse_obj(episode_info, 'audioMuxPlaybackId')

        return {
            'id': episode_info['id'],
            'url': f'https://stream.media.dailywire.com/{audio_id}/audio.m4a',
            'display_id': slug,
            'title': episode_info.get('title'),
            'duration': float_or_none(episode_info.get('duration')),
            'thumbnail': episode_info.get('thumbnail'),
            'description': episode_info.get('description'),
        }
