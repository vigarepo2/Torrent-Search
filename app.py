from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import gzip
import html
import io
import urllib.error
import urllib.request
from urllib.parse import urlencode, unquote
import re
import time
from datetime import datetime

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Common trackers list for magnet links
trackers_list = [
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

# Base Torrent API class
class BaseTorrentAPI:
    def retrieve_url(self, url, request_data=None):
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
    
    def get_trackers_string(self):
        return '&'.join(urlencode({'tr': tracker}) for tracker in trackers_list)
    
    def parse_size(self, size_str):
        """Convert human-readable size to bytes"""
        if not size_str or size_str == "Unknown":
            return 0
            
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

class PirateBayAPI(BaseTorrentAPI):
    url = 'https://thepiratebay.org'
    name = 'The Pirate Bay'
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
            result['info_hash'], urlencode({'dn': result['name']}), self.get_trackers_string())

    def get_category_name(self, category_id):
        category_map = {
            '0': 'All',
            '100': 'Music',
            '200': 'Movies',
            '300': 'Software',
            '400': 'Games',
        }
        return category_map.get(category_id, 'Other')

class LimeTorrentsAPI(BaseTorrentAPI):
    url = 'https://www.limetorrents.lol'
    name = 'LimeTorrents'
    supported_categories = {
        'all': 'all',
        'movies': 'movies',
        'tv': 'tv',
        'music': 'music',
        'games': 'games',
        'software': 'applications'
    }

    def search(self, what, cat='all'):
        results = []
        what = what.replace("%20", "-")
        category = self.supported_categories[cat]
        
        for page in range(1, 3):  # Check first 2 pages
            if category != 'all':
                search_url = f"{self.url}/search/{category}/{what}/seeds/{page}/"
            else:
                search_url = f"{self.url}/search/{what}/seeds/{page}/"
                
            html = self.retrieve_url(search_url)
            
            # Extract torrents using regex
            pattern = r'<div class="tt-name"><a href="([^"]+)"[^>]*>(.*?)</a>.*?<div class="tt-size"><span>(.*?)</span></div>.*?<div class="ttseed">(.*?)</div>.*?<div class="ttleech">(.*?)</div>'
            matches = re.findall(pattern, html, re.DOTALL)
            
            if not matches:
                break
                
            for match in matches:
                link, name, size, seeds, leechers = match
                
                # Get the torrent details page to extract the hash for magnet link
                details_url = self.url + link
                details_html = self.retrieve_url(details_url)
                
                hash_match = re.search(r'([A-F0-9]{40})', details_html, re.IGNORECASE)
                if not hash_match:
                    continue
                    
                torrent_hash = hash_match.group(1)
                magnet_link = f"magnet:?xt=urn:btih:{torrent_hash}&{urlencode({'dn': name})}&{self.get_trackers_string()}"
                
                result = {
                    'link': magnet_link,
                    'name': name.strip(),
                    'size': size.strip(),
                    'raw_size': self.parse_size(size.strip()),
                    'seeds': int(seeds.strip()) if seeds.strip().isdigit() else 0,
                    'leech': int(leechers.strip()) if leechers.strip().isdigit() else 0,
                    'engine_url': self.url,
                    'desc_link': details_url,
                    'pub_date': int(time.time()),  # Use current time as fallback
                    'category': category.capitalize(),
                    'source': self.name
                }
                
                results.append(result)
                
            if len(matches) < 20:  # If less than 20 results, don't check next page
                break
                
        return results

class TorLockAPI(BaseTorrentAPI):
    url = 'https://www.torlock.com'
    name = 'TorLock'
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
        results = []
        what = what.replace("%20", "-")
        category = self.supported_categories[cat]
        
        for page in range(1, 3):  # Check first 2 pages
            search_url = f"{self.url}/{category}/torrents/{what}.html?sort=seeds&page={page}"
            html = self.retrieve_url(search_url)
            
            # Extract torrents using regex
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
                    magnet_link = f"magnet:?xt=urn:btih:{torrent_id}&{self.get_trackers_string()}&{urlencode({'dn': name})}"
                    
                    result = {
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds) if seeds.isdigit() else 0,
                        'leech': int(leech) if leech.isdigit() else 0,
                        'engine_url': self.url,
                        'desc_link': desc_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': category.capitalize(),
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing TorLock result: {e}")
                    continue
                    
        return results

class TorrentsCSVAPI(BaseTorrentAPI):
    url = 'https://torrents-csv.com'
    name = 'Torrents CSV'
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
            result['infohash'], urlencode({'dn': result['name']}), self.get_trackers_string())

class EZTVAPI(BaseTorrentAPI):
    url = 'https://eztvx.to'
    name = 'EZTV'
    supported_categories = {'all': 'all', 'tv': 'tv'}

    def search(self, what, cat='all'):
        what = what.replace('%20', '-')
        search_url = f"{self.url}/search/{what}"
        html = self.retrieve_url(search_url, b"layout=def_wlinks")
        
        results = []
        
        # Extract results using regex
        rows = re.findall(r'<tr class=\'gac_bb\'>(.*?)</tr>', html, re.DOTALL)
        
        for row in rows:
            try:
                name_match = re.search(r'class="epinfo"[^>]*title="([^"]+)"', row)
                link_match = re.search(r'class="magnet"[^>]*href="([^"]+)"', row)
                size_match = re.search(r'(\d+\.\d+\s+[KMG]B)', row)
                seeds_match = re.search(r'<td class="[^"]*">(\d+)</td>', row)
                
                if not (name_match and link_match):
                    continue
                    
                name = name_match.group(1).split(' (')[0]
                link = link_match.group(1)
                size = size_match.group(1) if size_match else "Unknown"
                seeds = seeds_match.group(1) if seeds_match else "0"
                
                # Parse date
                date_match = re.search(r'(\d+)h\s+(\d+)m', row)
                pub_date = int(time.time())
                if date_match:
                    hours, minutes = int(date_match.group(1)), int(date_match.group(2))
                    pub_date = int(time.time()) - (hours * 3600 + minutes * 60)
                
                result = {
                    'link': link,
                    'name': name,
                    'size': size,
                    'raw_size': self.parse_size(size),
                    'seeds': int(seeds) if seeds.isdigit() else 0,
                    'leech': 0,  # EZTV doesn't show leechers
                    'engine_url': self.url,
                    'desc_link': f"{self.url}/ep/{name.replace(' ', '-')}",
                    'pub_date': pub_date,
                    'category': 'TV Shows',
                    'source': self.name
                }
                
                results.append(result)
            except Exception as e:
                print(f"Error parsing EZTV result: {e}")
                continue
                
        return results

class TorrentProjectAPI(BaseTorrentAPI):
    url = 'https://torrentproject.cc'
    name = 'TorrentProject'
    supported_categories = {'all': '0'}

    def search(self, what, cat='all'):
        results = []
        
        for page in range(0, 3):  # Check first 3 pages
            url = f"{self.url}/browse?t={what}&p={page}"
            html = self.retrieve_url(url)
            
            # Parse search results
            rows = re.findall(r'<tr class=\'gac_bb\'>(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                try:
                    name_match = re.search(r'title="([^"]+)"', row)
                    desc_link_match = re.search(r'href="([^"]+)"', row)
                    size_match = re.search(r'<td>([^<]+)</td>', row)
                    seeds_match = re.search(r'style="color: green;">(\d+)</span>', row)
                    leech_match = re.search(r'style="color: red;">(\d+)</span>', row)
                    
                    if not (name_match and desc_link_match):
                        continue
                        
                    name = name_match.group(1)
                    desc_link = desc_link_match.group(1)
                    if not desc_link.startswith("http"):
                        desc_link = self.url + desc_link
                        
                    size = size_match.group(1).strip() if size_match else "Unknown"
                    seeds = seeds_match.group(1) if seeds_match else "0"
                    leech = leech_match.group(1) if leech_match else "0"
                    
                    # We need to visit the torrent page to get the magnet link
                    torrent_html = self.retrieve_url(desc_link)
                    magnet_match = re.search(r'href="(magnet:[^"]+)"', torrent_html)
                    
                    if not magnet_match:
                        continue
                        
                    magnet_link = magnet_match.group(1)
                    
                    result = {
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds),
                        'leech': int(leech),
                        'engine_url': self.url,
                        'desc_link': desc_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': 'Unknown',
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing TorrentProject result: {e}")
                    continue
                    
            if len(rows) < 20:  # If less than 20 results, don't check next page
                break
                
        return results

class NyaaAPI(BaseTorrentAPI):
    url = 'https://nyaa.si'
    name = 'Nyaa.si'
    supported_categories = {
        'all': '0_0',
        'anime': '1_0',
        'software': '6_0'
    }

    def search(self, what, cat='all'):
        results = []
        category = self.supported_categories[cat]
        
        for page in range(1, 3):  # Check first 2 pages
            search_url = f"{self.url}/?f=0&c={category}&q={what}&s=seeders&o=desc&p={page}"
            html = self.retrieve_url(search_url)
            
            # Extract results using regex
            rows = re.findall(r'<tr class="default">(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                try:
                    category_match = re.search(r'title="([^"]+)"', row)
                    name_match = re.search(r'title="([^"]+)">\s*<i class="fa fa-fw fa-[^"]+">\s*</i>\s*([^<]+)', row)
                    torrent_link_match = re.search(r'href="(/download/[^"]+)"', row)
                    magnet_link_match = re.search(r'href="(magnet:[^"]+)"', row)
                    size_match = re.search(r'<td class="text-center">([^<]+)</td>', row)
                    date_match = re.search(r'<td class="text-center">([^<]+)</td>\s*<td class="text-center"', row)
                    seeds_match = re.search(r'<td class="text-center" style="color: green;">(\d+)</td>', row)
                    leech_match = re.search(r'<td class="text-center" style="color: red;">(\d+)</td>', row)
                    
                    if not (name_match and magnet_link_match):
                        continue
                        
                    category = category_match.group(1) if category_match else "Unknown"
                    name = name_match.group(2).strip()
                    magnet_link = magnet_link_match.group(1)
                    size = size_match.group(1).strip() if size_match else "Unknown"
                    date_str = date_match.group(1).strip() if date_match else ""
                    seeds = seeds_match.group(1) if seeds_match else "0"
                    leech = leech_match.group(1) if leech_match else "0"
                    
                    # Convert date to timestamp
                    pub_date = int(time.time())
                    if date_str:
                        try:
                            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                            pub_date = int(dt.timestamp())
                        except:
                            pass
                    
                    result = {
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds),
                        'leech': int(leech),
                        'engine_url': self.url,
                        'desc_link': f"{self.url}/view{torrent_link_match.group(1).replace('/download', '')}",
                        'pub_date': pub_date,
                        'category': category,
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing Nyaa result: {e}")
                    continue
                    
            if len(rows) < 75:  # If less than 75 results, don't check next page
                break
                
        return results

class X1337API(BaseTorrentAPI):
    url = 'https://1337x.to'
    name = '1337x'
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
        results = []
        cat = cat.lower()

        # decide which type of search to perform based on category
        search_page = "search" if cat == 'all' else 'category-search'
        
        for page in range(1, 3):  # Check first 2 pages
            search_url = f"{self.url}/{search_page}/{what}/{page}/"
            
            # apply search category to url, if any.
            if cat != 'all':
                search_url = f"{self.url}/{search_page}/{what}/{self.supported_categories[cat]}/{page}/"
                
            html = self.retrieve_url(search_url)
            
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
                    torrent_link_match = re.search(r'href="(/torrent/\d+/[^/]+/)"', row)
                    desc_link = self.url + torrent_link_match.group(1)
                    
                    # Extract size, seeds, leechers
                    size_match = re.search(r'<td class="size">([^<]+)</td>', row)
                    seeds_match = re.search(r'<td class="seeds">(\d+)</td>', row)
                    leech_match = re.search(r'<td class="leeches">(\d+)</td>', row)
                    
                    size = size_match.group(1).strip() if size_match else "Unknown"
                    seeds = seeds_match.group(1) if seeds_match else "0"
                    leech = leech_match.group(1) if leech_match else "0"
                    
                    # We need to visit the torrent page to get the magnet link
                    torrent_html = self.retrieve_url(desc_link)
                    magnet_match = re.search(r'href="(magnet:[^"]+)"', torrent_html)
                    
                    if not magnet_match:
                        continue
                        
                    magnet_link = magnet_match.group(1)
                    
                    result = {
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds),
                        'leech': int(leech),
                        'engine_url': self.url,
                        'desc_link': desc_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': self.supported_categories.get(cat, 'Unknown'),
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing 1337x result: {e}")
                    continue
                    
            if len(rows) < 20:  # If less than 20 results, don't check next page
                break
                
        return results

class MagnetDLAPI(BaseTorrentAPI):
    url = 'http://www.magnetdl.com'
    name = 'MagnetDL'
    supported_categories = {'all': ''}

    def search(self, what, cat='all'):
        results = []
        what = what.lower().replace("%20", "-")
        
        # MagnetDL organizes by first letter
        first_letter = what[0] if what and what[0].isalpha() else '0'
        
        for page in range(1, 3):  # Check first 2 pages
            search_url = f"{self.url}/{first_letter}/{what}/{page}/"
            html = self.retrieve_url(search_url)
            
            # Parse search results
            rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                try:
                    # Check if this is actually a result row with magnet link
                    if 'magnet:?' not in row:
                        continue
                        
                    magnet_match = re.search(r'href="(magnet:\?[^"]+)"', row)
                    name_match = re.search(r'href="[^"]+">([^<]+)</a>', row)
                    size_match = re.search(r'<td class="s">([^<]+)</td>', row)
                    seeds_match = re.search(r'<td class="s">(\d+)</td>', row, re.DOTALL)
                    leech_match = re.search(r'<td class="l">(\d+)</td>', row)
                    
                    if not (magnet_match and name_match):
                        continue
                        
                    magnet_link = magnet_match.group(1)
                    name = name_match.group(1).strip()
                    size = size_match.group(1) if size_match else "Unknown"
                    seeds = seeds_match.group(1) if seeds_match else "0"
                    leech = leech_match.group(1) if leech_match else "0"
                    
                    result = {
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds) if seeds.isdigit() else 0,
                        'leech': int(leech) if leech.isdigit() else 0,
                        'engine_url': self.url,
                        'desc_link': self.url,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': 'Unknown',
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing MagnetDL result: {e}")
                    continue
                    
            if len(rows) < 20:  # If less than 20 results, don't check next page
                break
                
        return results

class GloTorrentsAPI(BaseTorrentAPI):
    url = 'https://glodls.to'
    name = 'GloTorrents'
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
        results = []
        category = self.supported_categories[cat]
        
        for page in range(1, 3):  # Check first 2 pages
            search_url = f"{self.url}/search_results.php?search={what}&cat={category}&order=seeders&by=DESC&page={page}"
            html = self.retrieve_url(search_url)
            
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
                        'link': magnet_link,
                        'name': name,
                        'size': size,
                        'raw_size': self.parse_size(size),
                        'seeds': int(seeds) if seeds.isdigit() else 0,
                        'leech': int(leech) if leech.isdigit() else 0,
                        'engine_url': self.url,
                        'desc_link': desc_link,
                        'pub_date': int(time.time()),  # Current time as fallback
                        'category': cat.capitalize(),
                        'source': self.name
                    }
                    
                    results.append(result)
                except Exception as e:
                    print(f"Error parsing GloTorrents result: {e}")
                    continue
                    
            if len(rows) < 20:  # If less than 20 results, don't check next page
                break
                
        return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', 'all')
    site = request.args.get('site', 'all')
    
    if not query:
        return jsonify([])
    
    results = []
    errors = []
    
    try:
        # Create instances of the torrent site APIs
        apis = {
            'piratebay': PirateBayAPI(),
            'limetorrents': LimeTorrentsAPI(),
            'torlock': TorLockAPI(),
            'torrentscsv': TorrentsCSVAPI(),
            'eztv': EZTVAPI(),
            'torrentproject': TorrentProjectAPI(),
            'nyaa': NyaaAPI(),
            '1337x': X1337API(),
            'magnetdl': MagnetDLAPI(),
            'glotorrents': GloTorrentsAPI()
        }
        
        # Search all sites or just the requested one
        if site == 'all':
            for api_name, api in apis.items():
                try:
                    site_results = api.search(query, category)
                    results.extend(site_results)
                except Exception as e:
                    errors.append(f"Error searching {api_name}: {str(e)}")
        elif site in apis:
            results = apis[site].search(query, category)
        
        # Sort results by seeders (descending)
        results = sorted(results, key=lambda x: int(x.get('seeds', 0)), reverse=True)
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e), "site_errors": errors}), 500

@app.route('/api/sites')
def get_sites():
    """Return available torrent sites"""
    sites = [
        {"id": "all", "name": "All Sites"},
        {"id": "piratebay", "name": "The Pirate Bay"},
        {"id": "limetorrents", "name": "LimeTorrents"},
        {"id": "torlock", "name": "TorLock"},
        {"id": "torrentscsv", "name": "Torrents CSV"},
        {"id": "eztv", "name": "EZTV"},
        {"id": "torrentproject", "name": "TorrentProject"},
        {"id": "nyaa", "name": "Nyaa.si"},
        {"id": "1337x", "name": "1337x"},
        {"id": "magnetdl", "name": "MagnetDL"},
        {"id": "glotorrents", "name": "GloTorrents"}
    ]
    return jsonify(sites)

@app.route('/api/categories')
def get_categories():
    """Return available categories"""
    categories = [
        {"id": "all", "name": "All Categories"},
        {"id": "movies", "name": "Movies"},
        {"id": "tv", "name": "TV Shows"},
        {"id": "music", "name": "Music"},
        {"id": "games", "name": "Games"},
        {"id": "software", "name": "Software"},
        {"id": "anime", "name": "Anime"},
        {"id": "books", "name": "Books"}
    ]
    return jsonify(categories)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
