from .common import InfoExtractor
from .turner import TurnerBaseIE
from ..utils import parse_qs, traverse_obj, url_basename


class CNNIE(TurnerBaseIE):
    _VALID_URL = r'''(?x)https?://(?:(?P<sub_domain>edition|www|money)\.)?cnn\.com/(?:video/(?:data/.+?|\?)/)?videos?/
        (?P<path>.+?/(?P<title>[^/]+?)(?:\.(?:[a-z\-]+)|(?=&)))'''

    _TESTS = [{
        'url': 'http://edition.cnn.com/video/?/video/sports/2013/06/09/nadal-1-on-1.cnn',
        'md5': '3e6121ea48df7e2259fe73a0628605c4',
        'info_dict': {
            'id': 'sports/2013/06/09/nadal-1-on-1.cnn',
            'ext': 'mp4',
            'title': 'Nadal wins 8th French Open title',
            'description': 'World Sport\'s Amanda Davies chats with 2013 French Open champion Rafael Nadal.',
            'duration': 135,
            'upload_date': '20130609',
        },
        'expected_warnings': ['Failed to download m3u8 information'],
    }, {
        'url': 'http://edition.cnn.com/video/?/video/us/2013/08/21/sot-student-gives-epic-speech.georgia-institute-of-technology&utm_source=feedburner&utm_medium=feed&utm_campaign=Feed%3A+rss%2Fcnn_topstories+%28RSS%3A+Top+Stories%29',
        'md5': 'b5cc60c60a3477d185af8f19a2a26f4e',
        'info_dict': {
            'id': 'us/2013/08/21/sot-student-gives-epic-speech.georgia-institute-of-technology',
            'ext': 'mp4',
            'title': "Student's epic speech stuns new freshmen",
            'description': "A Georgia Tech student welcomes the incoming freshmen with an epic speech backed by music from \"2001: A Space Odyssey.\"",
            'upload_date': '20130821',
        },
        'expected_warnings': ['Failed to download m3u8 information'],
    }, {
        'url': 'http://www.cnn.com/video/data/2.0/video/living/2014/12/22/growing-america-nashville-salemtown-board-episode-1.hln.html',
        'md5': 'f14d02ebd264df951feb2400e2c25a1b',
        'info_dict': {
            'id': 'living/2014/12/22/growing-america-nashville-salemtown-board-episode-1.hln',
            'ext': 'mp4',
            'title': 'Nashville Ep. 1: Hand crafted skateboards',
            'description': 'md5:e7223a503315c9f150acac52e76de086',
            'upload_date': '20141222',
        },
        'expected_warnings': ['Failed to download m3u8 information'],
    }, {
        'url': 'http://money.cnn.com/video/news/2016/08/19/netflix-stunning-stats.cnnmoney/index.html',
        'md5': '52a515dc1b0f001cd82e4ceda32be9d1',
        'info_dict': {
            'id': '/video/news/2016/08/19/netflix-stunning-stats.cnnmoney',
            'ext': 'mp4',
            'title': '5 stunning stats about Netflix',
            'description': 'Did you know that Netflix has more than 80 million members? Here are five facts about the online video distributor that you probably didn\'t know.',
            'upload_date': '20160819',
        },
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }, {
        'url': 'http://cnn.com/video/?/video/politics/2015/03/27/pkg-arizona-senator-church-attendance-mandatory.ktvk',
        'only_matching': True,
    }, {
        'url': 'http://cnn.com/video/?/video/us/2015/04/06/dnt-baker-refuses-anti-gay-order.wkmg',
        'only_matching': True,
    }, {
        'url': 'http://edition.cnn.com/videos/arts/2016/04/21/olympic-games-cultural-a-z-brazil.cnn',
        'only_matching': True,
    }]

    _CONFIG = {
        # http://edition.cnn.com/.element/apps/cvp/3.0/cfg/spider/cnn/expansion/config.xml
        'edition': {
            'data_src': 'http://edition.cnn.com/video/data/3.0/video/%s/index.xml',
            'media_src': 'http://pmd.cdn.turner.com/cnn/big',
        },
        # http://money.cnn.com/.element/apps/cvp2/cfg/config.xml
        'money': {
            'data_src': 'http://money.cnn.com/video/data/4.0/video/%s.xml',
            'media_src': 'http://ht3.cdn.turner.com/money/big',
        },
    }

    def _extract_timestamp(self, video_data):
        # TODO: fix timestamp extraction
        return None

    def _real_extract(self, url):
        sub_domain, path, page_title = self._match_valid_url(url).groups()
        if sub_domain not in ('money', 'edition'):
            sub_domain = 'edition'
        config = self._CONFIG[sub_domain]
        return self._extract_cvp_info(
            config['data_src'] % path, page_title, {
                'default': {
                    'media_src': config['media_src'],
                },
                'f4m': {
                    'host': 'cnn-vh.akamaihd.net',
                },
            })


class CNNBlogsIE(InfoExtractor):
    _VALID_URL = r'https?://[^\.]+\.blogs\.cnn\.com/.+'
    _TEST = {
        'url': 'http://reliablesources.blogs.cnn.com/2014/02/09/criminalizing-journalism/',
        'md5': '3e56f97b0b6ffb4b79f4ea0749551084',
        'info_dict': {
            'id': 'bestoftv/2014/02/09/criminalizing-journalism.cnn',
            'ext': 'mp4',
            'title': 'Criminalizing journalism?',
            'description': 'Glenn Greenwald responds to comments made this week on Capitol Hill that journalists could be criminal accessories.',
            'upload_date': '20140209',
        },
        'expected_warnings': ['Failed to download m3u8 information'],
        'add_ie': ['CNN'],
    }

    def _real_extract(self, url):
        webpage = self._download_webpage(url, url_basename(url))
        cnn_url = self._html_search_regex(r'data-url="(.+?)"', webpage, 'cnn url')
        return self.url_result(cnn_url, CNNIE.ie_key())


class CNNArticleIE(InfoExtractor):
    _VALID_URL = r'https?://(?:(?:edition|www)\.)?cnn\.com/(?!videos?/)'
    _TESTS = [{
        # videoId in json+ld embedUrl or ContentUrl or in data-video-id
        'url': 'http://www.cnn.com/2014/12/21/politics/obama-north-koreas-hack-not-war-but-cyber-vandalism/',
        'md5': '689034c2a3d9c6dc4aa72d65a81efd01',
        'info_dict': {
            'id': 'bestoftv/2014/12/21/ip-north-korea-obama.cnn',
            'ext': 'mp4',
            'title': 'Obama: Cyberattack not an act of war',
            'description': 'md5:0a802a40d2376f60e6b04c8d5bcebc4b',
            'upload_date': '20141221',
        },
        'expected_warnings': ['Failed to download m3u8 information'],
        'add_ie': ['CNN'],
    }, {
        # url in window.__INITIAL_STATE__
        'url': 'https://www.cnn.com/travel/article/parrot-steals-gopro-scli-intl',
        'info_dict': {
            'id': 'world/2022/02/04/parrot-steals-gopro-new-zealand-lon-orig-na.cnn',
            'ext': 'mp4',
            'title': 'Watch parrot steal family\'s GoPro and film flight',
            'upload_date': '20220204',
            'duration': 48.0,
            'thumbnail': 'https://cdn.cnn.com/cnnnext/dam/assets/220204170742-parrot-gopro-lon-orig-na-full-169.jpg',
            'description': 'md5:5540608be9d61b46019bea7acdcc7a8f',
        }
    }]

    def _call_api(self, video_id, display_id, edition='domestic', **custom_query):
        json_api_data = self._download_json(
            'https://fave.api.cnn.io/v1/video', display_id,
            query={'id': video_id, 'customer': 'cnn', 'edition': edition, 'env': 'prod', **custom_query})
        return json_api_data

    def _real_extract(self, url):
        display_id = url_basename(url)
        webpage = self._download_webpage(url, display_id)

        initial_state_json = self._search_json(
            r'window\.__INITIAL_STATE__\s*=\s*', webpage, 'window.__INITIAL_STATE__', display_id, fatal=False)

        if initial_state_json:
            # root query
            root_query_json = initial_state_json.get('ROOT_QUERY')
            root_query_key = [key for key in root_query_json if key.startswith('PAL')][0]
            root_query_id = root_query_json[root_query_key]['id']

            main_data = initial_state_json.get(root_query_id)
            regions_id = traverse_obj(main_data, ('regions', 'id'))

            # region json
            region_data_json = [initial_state_json.get(key) for key in initial_state_json if key.startswith(regions_id)]
            element_data_json = [
                traverse_obj(region_data, ('elementContents', 'json', 'videoElement', 'elementContents'), get_all=False)
                for region_data in region_data_json if region_data.get('type') == 'element'][0]

            return self.url_result(f'https://edition.cnn.com{element_data_json.get("videoUrl")}', CNNIE.ie_key())
        else:
            json_ld_data = self._yield_json_ld(webpage, display_id)
            json_ld_video_data = [json_ld.get('embedUrl') for json_ld in json_ld_data if json_ld.get('@type') == 'VideoObject'][0]
            api_query = parse_qs(json_ld_video_data)
            video_id = api_query.get('video')
            api_query.pop('video')
            json_data = self._call_api(video_id, display_id, **api_query)
            print(json_data)
        # cnn_url = self._html_search_regex(r"video:\s*'([^']+)'", webpage, 'cnn url')
        # return self.url_result('http://cnn.com/video/?/video/' + cnn_url, CNNIE.ie_key())
