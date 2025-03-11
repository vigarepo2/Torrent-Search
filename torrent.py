# torrent.py - Consolidated torrent site APIs
import re
import json
import gzip
import html
import io
import urllib.error
import urllib.request
import urllib.parse
from urllib.parse import urlencode, unquote
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser

# Common trackers list for magnet links
TRACKERS_LIST = [
    'udp://tracker.internetwarriors.net:1337/announce',
    'udp://tracker.opentrackr.org:1337/announce',
    'udp://p4p.arenabg.ch:1337/announce',
    'udp://tracker.openbittorrent.com:6969/announce',
    'udp://www.torrent.eu.org:451/announce',
    'udp://tracker.torrent.eu.org:451/announce',
    'udp://retracker.lanta-net.ru:2710/announce',
    'udp://open.stealth.si:80/announce',
    'udp://exodus.desync.com:6969/announce',
    'udp://tracker.tiny-vps.com:6969/announce'
]


class BaseTorrentAPI:
    """Base class for all torrent site APIs"""
    name = "Base Torrent API"
    url = ""
    supported_categories = {'all': '0'}
    
    def __init__(self):
        # Initialize trackers for magnet links
        self.trackers = '&'.join(urlencode({'tr': tracker}) for tracker in TRACKERS_LIST)
    
    def retrieve_url(self, url, request_data=None):
        """General method to fetch data from URLs"""
        # Request data from API
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'}
        request = urllib.request.Request(url, request_data, headers)

        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError:
            return ""

        data = response.read()
        if data[:2] == b'\x1f\x8b':
            # Data is gzip encoded, decode it
            with io.BytesIO(data) as stream, gzip.GzipFile(fileobj=stream) as gzipper:
                data = gzipper.read()

        charset = 'utf-8'
        try:
            charset = response.getheader('Content-Type', '').split('charset=', 1)[1]
        except IndexError:
            pass

        dataStr = data.decode(charset, 'replace')
        dataStr = dataStr.replace('"', '\\"')  # Manually escape " before
        dataStr = html.unescape(dataStr)
        return dataStr
    
    def format_size(self, size_bytes):
        """Format bytes to human readable size"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.2f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes/1024**2:.2f} MB"
        elif size_bytes < 1024**4:
            return f"{size_bytes/1024**3:.2f} GB"
        else:
            return f"{size_bytes/1024**4:.2f} TB"
    
    def parse_size(self, size_str):
        """Convert human-readable size to bytes"""
        size_str = size_str.replace(',', '')
        parts = size_str.split()
        if len(parts) != 2:
            return 0
        
        try:
            size_num = float(parts[0])
            unit = parts[1].upper()
            
            if 'KB' in unit or 'KIB' in unit:
                return int(size_num * 1024)
            elif 'MB' in unit or 'MIB' in unit:
                return int(size_num * 1024**2)
            elif 'GB' in unit or 'GIB' in unit:
                return int(size_num * 1024**3)
            elif 'TB' in unit or 'TIB' in unit:
                return int(size_num * 1024**4)
            else:
                return int(size_num)
        except:
            return 0
    
    def search(self, what, cat='all'):
        """Default search method to be overridden"""
        return []


class PirateBayAPI(BaseTorrentAPI):
    """The Pirate Bay API implementation"""
    name = 'The Pirate Bay'
    url = 'https://thepiratebay.org'
    supported_categories = {
        'all': '0',
        'music': '100',
        'movies': '200',
        'games': '400',
        'software': '300'
    }

    def search(self, what, cat='all'):
        base_url = "https://apibay.org/q.php?%s"
        # get response json
        what = unquote(what)
        category = self.supported_categories[cat]
        params = {'q': what}
        if category != '0':
            params['cat'] = category

        # Calling custom `retrieve_url` function with adequate escaping
        data = self.retrieve_url(base_url % urlencode(params))
        try:
            response_json = json.loads(data)
        except:
            return []

        # check empty response
        if len(response_json) == 0:
            return []

        # parse results
        results = []
        for result in response_json:
            if result['info_hash'] == '0000000000000000000000000000000000000000':
                continue
            
            res = {
                'link': self.download_link(result),
                'name': result['name'],
                'size': self.format_size(int(result['size'])),
                'raw_size': result['size'],
                'seeds': result['seeders'],
                'leech': result['leechers'],
                'engine_url': self.url,
                'desc_link': self.url + '/description.php?id=' + result['id'],
                'pub_date': result['added'],
                'category': self.get_category_name(result.get('category', '0')),
                'source': self.name
            }
            results.append(res)
        return results

    def download_link(self, result):
        return "magnet:?xt=urn:btih:{}&{}&{}".format(
            result['info_hash'], urlencode({'dn': result['name']}), self.trackers)

    def get_category_name(self, category_id):
        category_map = {
            '0': 'All',
            '100': 'Music',
            '200': 'Movies',
            '300': 'Software',
            '400': 'Games',
        }
        return category_map.get(category_id, 'Other')


class YTSApi(BaseTorrentAPI):
    """YTS API for high-quality movies"""
    name = 'YTS'
    url = 'https://yts.mx'
    supported_categories = {
        'all': 'All',
        'movies': 'movie'
    }

    def search(self, what, cat='all'):
        base_url = "https://yts.mx/api/v2/list_movies.json"
        params = {
            'query_term': what,
            'limit': 50,
            'sort_by': 'seeds'
        }
        
        url = f"{base_url}?{urlencode(params)}"
        data = self.retrieve_url(url)
        
        try:
            response = json.loads(data)
            if response['status'] != 'ok' or response['data']['movie_count'] == 0:
                return []
            
            results = []
            movies = response['data']['movies']
            
            for movie in movies:
                for torrent in movie['torrents']:
                    result = {
                        'name': f"{movie['title']} ({movie['year']}) {torrent['quality']} {torrent['type']}",
                        'size': self.format_size(torrent['size_bytes']),
                        'raw_size': torrent['size_bytes'],
                        'seeds': torrent['seeds'],
                        'leech': torrent['peers'],
                        'engine_url': self.url,
                        'desc_link': movie['url'],
                        'link': self.create_magnet(torrent['hash'], movie['title']),
                        'pub_date': torrent['date_uploaded'],
                        'category': 'Movies',
                        'source': self.name
                    }
                    results.append(result)
            
            return results
        except Exception as e:
            print(f"Error parsing YTS results: {e}")
            return []

    def create_magnet(self, hash, name):
        return f"magnet:?xt=urn:btih:{hash}&{urlencode({'dn': name})}&{self.trackers}"


class EZTVAPI(BaseTorrentAPI):
    """EZTV API for TV shows"""
    name = 'EZTV'
    url = 'https://eztv.re'
    supported_categories = {
        'all': '0',
        'tv': '0'
    }

    def search(self, what, cat='all'):
        base_url = "https://eztv.re/api/get-torrents"
        params = {
            'limit': 50,
            'imdb_id': None
        }

        # First try to search by name
        search_url = f"{self.url}/search/{what}"
        search_data = self.retrieve_url(search_url)
        
        # Extract IMDB IDs from search results
        imdb_ids = re.findall(r'imdb_id=(\d+)', search_data)
        
        results = []
        if imdb_ids:
            params['imdb_id'] = imdb_ids[0]
            
            url = f"{base_url}?{urlencode(params)}"
            data = self.retrieve_url(url)
            
            try:
                response = json.loads(data)
                if response['torrents_count'] > 0:
                    for torrent in response['torrents']:
                        result = {
                            'name': torrent['title'],
                            'size': self.format_size(int(torrent['size_bytes'])),
                            'raw_size': torrent['size_bytes'],
                            'seeds': torrent['seeds'],
                            'leech': torrent.get('peers', 0),
                            'engine_url': self.url,
                            'desc_link': f"{self.url}/ep/{torrent['episode_url']}",
                            'link': torrent['magnet_url'],
                            'pub_date': torrent['date_released_unix'],
                            'category': 'TV Shows',
                            'source': self.name
                        }
                        results.append(result)
            except Exception as e:
                print(f"Error parsing EZTV results: {e}")
        
        return results


class NyaaAPI(BaseTorrentAPI):
    """Nyaa.si API for anime and Asian content"""
    name = 'Nyaa.si'
    url = 'https://nyaa.si'
    supported_categories = {
        'all': '0_0',
        'anime': '1_0',
        'software': '6_0'
    }

    def search(self, what, cat='all'):
        base_url = "https://nyaa.si/"
        params = {
            'f': '0',  # No filter
            'c': self.supported_categories[cat],
            'q': what,
            's': 'seeders',  # Sort by seeders
            'o': 'desc'  # Descending order
        }
        
        url = f"{base_url}?{urlencode(params)}"
        html_content = self.retrieve_url(url)
        
        results = []
        # Simple parsing using regex (a proper HTML parser would be better for production)
        rows = re.findall(r'<tr class="(default|success)">(.*?)</tr>', html_content, re.DOTALL)
        
        for _, row in rows:
            try:
                category = re.search(r'title="([^"]+)"', row).group(1)
                name = re.search(r'title="([^"]+)">\s*<i class="fa fa-fw fa-[^"]+">\s*</i>\s*([^<]+)', row).group(2).strip()
                torrent_link = re.search(r'href="(/download/[^"]+)"', row).group(1)
                magnet_link = re.search(r'href="(magnet:[^"]+)"', row).group(1)
                size = re.search(r'<td class="text-center">([^<]+)</td>', row).group(1).strip()
                date = re.search(r'<td class="text-center">([^<]+)</td>\s*<td class="text-center"', row).group(1).strip()
                seeders = re.search(r'<td class="text-center" style="color: green;">(\d+)</td>', row).group(1)
                leechers = re.search(r'<td class="text-center" style="color: red;">(\d+)</td>', row).group(1)
                
                # Convert size to bytes for raw_size
                size_bytes = self.parse_size(size)
                
                result = {
                    'name': name,
                    'size': size,
                    'raw_size': size_bytes,
                    'seeds': int(seeders),
                    'leech': int(leechers),
                    'engine_url': self.url,
                    'desc_link': f"{self.url}/view{torrent_link.replace('/download', '')}",
                    'link': magnet_link,
                    'pub_date': self.parse_date(date),
                    'category': category,
                    'source': self.name
                }
                
                results.append(result)
            except Exception as e:
                print(f"Error parsing Nyaa result: {e}")
                continue
                
        return results
    
    def parse_date(self, date_str):
        """Convert date string to unix timestamp"""
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            return int(time.mktime(dt.timetuple()))
        except:
            return int(time.time())


class LimeTorrentsAPI(BaseTorrentAPI):
    """LimeTorrents API"""
    name = 'LimeTorrents'
    url = 'https://www.limetorrents.pro'
    supported_categories = {
        'all': 'all',
        'movies': 'movies',
        'tv': 'tv',
        'music': 'music',
        'games': 'games',
        'software': 'applications'
    }

    def search(self, what, cat='all'):
        base_url = f"{self.url}/search/"
        category = self.supported_categories.get(cat, 'all')
        
        # LimeTorrents uses different URL structure based on category
        if category != 'all':
            search_url = f"{base_url}{what}/category/{category}/1/"
        else:
            search_url = f"{base_url}{what}/1/"
            
        html_content = self.retrieve_url(search_url)
        
        results = []
        # Extract torrent information using regex
        pattern = r'<div class="tt-name"><a href="([^"]+)"[^>]*>([^<]+)</a>.*?<div class="tt-size"><span>([^<]+)</span></div>.*?<div class="ttseed">([^<]+)</div>.*?<div class="ttleech">([^<]+)</div>'
        matches = re.findall(pattern, html_content, re.DOTALL)
        
        for link, name, size, seeders, leechers in matches:
            try:
                # Get the torrent details page to extract the hash
                torrent_page = self.retrieve_url(self.url + link)
                hash_match = re.search(r'([a-fA-F0-9]{40})', torrent_page)
                
                if hash_match:
                    torrent_hash = hash_match.group(1)
                    magnet_link = f"magnet:?xt=urn:btih:{torrent_hash}&{urlencode({'dn': name})}&{self.trackers}"
                    
                    # Parse size
                    size_bytes = self.parse_size(size)
                    
                    result = {
                        'name': name.strip(),
                        'size': size.strip(),
                        'raw_size': size_bytes,
                        'seeds': int(seeders.strip()) if seeders.strip().isdigit() else 0,
                        'leech': int(leechers.strip()) if leechers.strip().isdigit() else 0,
                        'engine_url': self.url,
                        'desc_link': self.url + link,
                        'link': magnet_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': category.capitalize(),
                        'source': self.name
                    }
                    
                    results.append(result)
            except Exception as e:
                print(f"Error parsing LimeTorrents result: {e}")
                continue
                
        return results


class TorrentProjectAPI(BaseTorrentAPI):
    """TorrentProject API"""
    name = 'TorrentProject'
    url = 'https://torrentproject.cc'
    supported_categories = {'all': '0'}

    def search(self, what, cat='all'):
        url = f"{self.url}/browse?t={what}"
        html = self.retrieve_url(url)
        
        results = []
        # Parse search results
        rows = re.findall(r'<tr class=\'gac_bb\'>(.*?)</tr>', html, re.DOTALL)
        
        for row in rows:
            try:
                name = re.search(r'title="([^"]+)"', row).group(1)
                desc_link = re.search(r'href="([^"]+)"', row).group(1)
                if not desc_link.startswith("http"):
                    desc_link = self.url + desc_link
                    
                # Extract size, seeds, leechers
                size = re.search(r'<td>([^<]+)</td>', row).group(1).strip()
                seeds = re.search(r'style="color: green;">(\d+)</span>', row).group(1)
                leech = re.search(r'style="color: red;">(\d+)</span>', row).group(1)
                
                # We need to visit the torrent page to get the magnet link
                torrent_html = self.retrieve_url(desc_link)
                magnet_match = re.search(r'href="(magnet:[^"]+)"', torrent_html)
                
                if magnet_match:
                    magnet_link = magnet_match.group(1)
                    
                    result = {
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds),
                        'leech': int(leech),
                        'engine_url': self.url,
                        'desc_link': desc_link,
                        'link': magnet_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': 'Unknown',
                        'source': self.name
                    }
                    
                    results.append(result)
            except Exception as e:
                print(f"Error parsing TorrentProject result: {e}")
                continue
                
        return results


class TorrentsCSVAPI(BaseTorrentAPI):
    """Torrents-CSV API"""
    name = 'Torrents CSV'
    url = 'https://torrents-csv.com'
    supported_categories = {'all': ''}

    def search(self, what, cat='all'):
        search_url = f"{self.url}/service/search?size=100&q={what}"
        desc_url = f"{self.url}/#/search/torrent/{what}/1"

        # get response json
        response = self.retrieve_url(search_url)
        try:
            response_json = json.loads(response)
        except:
            return []

        # parse results
        results = []
        for result in response_json.get("torrents", []):
            res = {
                'link': self.download_link(result),
                'name': result['name'],
                'size': self.format_size(int(result.get('size_bytes', 0))),
                'raw_size': result.get('size_bytes', 0),
                'seeds': result.get('seeders', 0),
                'leech': result.get('leechers', 0),
                'engine_url': self.url,
                'desc_link': desc_url,
                'pub_date': result.get('created_unix', int(time.time())),
                'category': 'Unknown',
                'source': self.name
            }
            results.append(res)
        return results

    def download_link(self, result):
        return "magnet:?xt=urn:btih:{}&{}&{}".format(
            result['infohash'], urlencode({'dn': result['name']}), self.trackers)


class X1337API(BaseTorrentAPI):
    """1337x API implementation"""
    name = '1337x'
    url = 'https://1337x.to'
    supported_categories = {
        'all': 'All',
        'movies': 'Movies',
        'tv': 'TV',
        'music': 'Music',
        'games': 'Games',
        'anime': 'Anime',
        'software': 'Apps'
    }

    def search(self, what, cat='all'):
        cat = cat.lower()

        # decide which type of search to perform based on category
        search_page = "search" if cat == 'all' else 'category-search'
        search_url = f"{self.url}/{search_page}/{what}/"

        # apply search category to url, if any.
        if cat != 'all':
            search_url += f"{self.supported_categories[cat]}/"

        results = []
        # Search multiple pages
        for page in range(1, 3):
            page_url = f"{search_url}{page}/"
            html = self.retrieve_url(page_url)
            
            # Parse search results
            rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                try:
                    # Check if this is actually a result row
                    if 'href="/torrent/' not in row:
                        continue
                        
                    name_match = re.search(r'href="/torrent/\d+/([^/]+)/">', row)
                    if not name_match:
                        continue
                        
                    name = name_match.group(1).replace('-', ' ')
                    torrent_link = re.search(r'href="(/torrent/\d+/[^/]+/)"', row).group(1)
                    desc_link = self.url + torrent_link
                    
                    # Extract size, seeds, leechers
                    size = re.search(r'<td class="size">([^<]+)</td>', row).group(1).strip()
                    seeds = re.search(r'<td class="seeds">(\d+)</td>', row).group(1)
                    leech = re.search(r'<td class="leeches">(\d+)</td>', row).group(1)
                    
                    # We need to visit the torrent page to get the magnet link
                    torrent_html = self.retrieve_url(desc_link)
                    magnet_match = re.search(r'href="(magnet:[^"]+)"', torrent_html)
                    
                    if magnet_match:
                        magnet_link = magnet_match.group(1)
                        
                        result = {
                            'name': name,
                            'size': size,
                            'raw_size': self.parse_size(size),
                            'seeds': int(seeds),
                            'leech': int(leech),
                            'engine_url': self.url,
                            'desc_link': desc_link,
                            'link': magnet_link,
                            'pub_date': int(time.time()),  # Current time as fallback
                            'category': self.supported_categories.get(cat, 'Unknown'),
                            'source': self.name
                        }
                        
                        results.append(result)
                except Exception as e:
                    print(f"Error parsing 1337x result: {e}")
                    continue
                    
        return results


class MagnetDLAPI(BaseTorrentAPI):
    """MagnetDL API implementation"""
    name = 'MagnetDL'
    url = 'https://www.magnetdl.com'
    supported_categories = {'all': ''}

    def search(self, what, cat='all'):
        what = what.lower().replace(" ", "-")
        # MagnetDL organizes by first letter
        first_letter = what[0] if what and what[0].isalpha() else '0'
        search_url = f"{self.url}/{first_letter}/{what}/"
        
        results = []
        for page in range(1, 3):  # Check first 2 pages
            page_url = f"{search_url}{page}/"
            html = self.retrieve_url(page_url)
            
            # Parse search results
            rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                try:
                    # Check if this is actually a result row with magnet link
                    if 'magnet:?' not in row:
                        continue
                        
                    magnet_link = re.search(r'href="(magnet:\?[^"]+)"', row).group(1)
                    name = re.search(r'href="[^"]+">([^<]+)</a>', row).group(1).strip()
                    
                    # Extract size, seeds, leechers
                    size_match = re.search(r'<td class="s">([^<]+)</td>', row)
                    seeds_match = re.search(r'<td class="s">(\d+)</td>', row, re.DOTALL)
                    leech_match = re.search(r'<td class="l">(\d+)</td>', row)
                    
                    size = size_match.group(1) if size_match else "Unknown"
                    seeds = seeds_match.group(1) if seeds_match else "0"
                    leech = leech_match.group(1) if leech_match else "0"
                    
                    result = {
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds) if seeds.isdigit() else 0,
                        'leech': int(leech) if leech.isdigit() else 0,
                        'engine_url': self.url,
                        'desc_link': self.url,
                        'link': magnet_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': 'Unknown',
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing MagnetDL result: {e}")
                    continue
                    
        return results


class TorLockAPI(BaseTorrentAPI):
    """TorLock API implementation"""
    name = 'TorLock'
    url = 'https://www.torlock.com'
    supported_categories = {
        'all': 'all',
        'anime': 'anime',
        'software': 'software',
        'games': 'game',
        'movies': 'movie',
        'music': 'music',
        'tv': 'television',
        'books': 'ebooks'
    }

    def search(self, what, cat='all'):
        category = self.supported_categories[cat]
        search_url = f"{self.url}/{category}/torrents/{what}.html?sort=seeds"
        
        html = self.retrieve_url(search_url)
        
        results = []
        # Use regex to find all torrent rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        
        for row in rows:
            try:
                # Skip rows that don't contain torrent data
                if '/torrent/' not in row:
                    continue
                    
                # Extract torrent info
                name_match = re.search(r'href="/torrent/(\d+)/([^"]+)"', row)
                if not name_match:
                    continue
                    
                torrent_id = name_match.group(1)
                name = name_match.group(2).replace('-', ' ')
                desc_link = f"{self.url}/torrent/{torrent_id}/{name}"
                
                # Extract size, seeds, leechers
                size_match = re.search(r'<td>([^<]+)</td>', row)
                seeds_match = re.search(r'<span class="seeds">(\d+)</span>', row)
                leech_match = re.search(r'<span class="leeches">(\d+)</span>', row)
                
                size = size_match.group(1).strip() if size_match else "Unknown"
                seeds = seeds_match.group(1) if seeds_match else "0"
                leech = leech_match.group(1) if leech_match else "0"
                
                # For TorLock, we need to construct the download link
                torrent_link = f"{self.url}/tor/{torrent_id}.torrent"
                
                # You might need to visit the desc page to get the magnet link
                magnet_link = f"magnet:?xt=urn:btih:{torrent_id}&{self.trackers}"
                
                result = {
                    'name': name,
                    'size': size,
                    'raw_size': self.parse_size(size),
                    'seeds': int(seeds) if seeds.isdigit() else 0,
                    'leech': int(leech) if leech.isdigit() else 0,
                    'engine_url': self.url,
                    'desc_link': desc_link,
                    'link': magnet_link,
                    'pub_date': int(time.time()),  # Current time as fallback
                    'category': category.capitalize(),
                    'source': self.name
                }
                
                results.append(result)
            except Exception as e:
                print(f"Error parsing TorLock result: {e}")
                continue
                
        return results


class GloTorrentsAPI(BaseTorrentAPI):
    """GloTorrents API implementation"""
    name = 'GloTorrents'
    url = 'https://glodls.to'
    supported_categories = {
        'all': '0', 
        'movies': '1', 
        'tv': '41', 
        'music': '22', 
        'games': '10', 
        'anime': '28',
        'software': '18'
    }

    def search(self, what, cat='all'):
        category = self.supported_categories[cat]
        search_url = f"{self.url}/search_results.php?search={what}&cat={category}&order=seeders&by=DESC"
        
        html = self.retrieve_url(search_url)
        
        results = []
        # Extract torrent rows
        rows = re.findall(r'<tr class=\'t-row\'>(.*?)</tr>', html, re.DOTALL)
        
        for row in rows:
            try:
                # Extract torrent info
                name_match = re.search(r'title="([^"]+)"', row)
                if not name_match:
                    continue
                    
                name = name_match.group(1)
                desc_link_match = re.search(r'href="(/.*?)"', row)
                desc_link = self.url + desc_link_match.group(1) if desc_link_match else self.url
                
                # Extract magnet link
                magnet_match = re.search(r'href="(magnet:[^"]+)"', row)
                if not magnet_match:
                    continue
                    
                magnet_link = magnet_match.group(1)
                
                # Extract size, seeds, leechers
                size_match = re.search(r'([0-9\.\,]+ (TB|GB|MB|KB))', row)
                seeds_match = re.search(r'<font color=\'green\'><b>(\d+)</b>', row)
                leech_match = re.search(r'<font color=\'#[0-9a-zA-Z]{6}\'><b>(\d+)</b>', row)
                
                size = size_match.group(1) if size_match else "Unknown"
                seeds = seeds_match.group(1) if seeds_match else "0"
                leech = leech_match.group(1) if leech_match else "0"
                
                result = {
                    'name': name,
                    'size': size,
                    'raw_size': self.parse_size(size),
                    'seeds': int(seeds) if seeds.isdigit() else 0,
                    'leech': int(leech) if leech.isdigit() else 0,
                    'engine_url': self.url,
                    'desc_link': desc_link,
                    'link': magnet_link,
                    'pub_date': int(time.time()),  # Current time as fallback
                    'category': cat.capitalize(),
                    'source': self.name
                }
                
                results.append(result)
            except Exception as e:
                print(f"Error parsing GloTorrents result: {e}")
                continue
                
        return results


# Create a dictionary of all available torrent site APIs
TORRENT_SITES = {
    'piratebay': PirateBayAPI,
    'yts': YTSApi,
    'eztv': EZTVAPI,
    'nyaa': NyaaAPI,
    'limetorrents': LimeTorrentsAPI,
    'torrentproject': TorrentProjectAPI,
    'torrentscsv': TorrentsCSVAPI,
    '1337x': X1337API,
    'magnetdl': MagnetDLAPI,
    'torlock': TorLockAPI,
    'glotorrents': GloTorrentsAPI
}


def get_all_sites():
    """Return a list of all available torrent sites"""
    return [
        {"id": site_id, "name": site_class().name} 
        for site_id, site_class in TORRENT_SITES.items()
    ]


def search_all_sites(query, category='all', limit=10):
    """Search all torrent sites and return the best results"""
    all_results = []
    
    for site_id, site_class in TORRENT_SITES.items():
        try:
            site = site_class()
            results = site.search(query, category)
            all_results.extend(results)
        except Exception as e:
            print(f"Error searching {site_id}: {e}")
    
    # Sort by seeders (descending)
    all_results = sorted(all_results, key=lambda x: int(x.get('seeds', 0)), reverse=True)
    
    # Return top results
    return all_results[:limit]
