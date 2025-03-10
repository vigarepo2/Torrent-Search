# app.py
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
import concurrent.futures
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Common trackers for magnet links
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
TRACKERS = '&'.join(urlencode({'tr': tracker}) for tracker in TRACKERS_LIST)

# Base class for all torrent site APIs
class TorrentAPI:
    name = "Base API"
    url = ""
    
    def search(self, query, category='all'):
        """Search for torrents and return results"""
        raise NotImplementedError("Subclasses must implement search method")
    
    def format_size(self, size_bytes):
        """Format bytes to human readable size"""
        if isinstance(size_bytes, str):
            try:
                size_bytes = float(size_bytes)
            except ValueError:
                return size_bytes
                
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
            
    def get_category_name(self, category_id):
        """Get category name from ID"""
        category_map = {
            '0': 'All',
            '100': 'Music',
            '200': 'Movies',
            '300': 'Software',
            '400': 'Games',
        }
        return category_map.get(category_id, 'Other')
    
    def retrieve_url(self, url, headers=None):
        """Retrieve URL content with error handling"""
        if headers is None:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'}
        
        request = urllib.request.Request(url, None, headers)
        
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error for {url}: {e.code} {e.reason}")
            return ""
        except urllib.error.URLError as e:
            logger.error(f"URL Error for {url}: {e.reason}")
            return ""
        except Exception as e:
            logger.error(f"Error retrieving {url}: {str(e)}")
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
        dataStr = dataStr.replace('&quot;', '\\"')
        dataStr = html.unescape(dataStr)
        
        return dataStr

class PirateBayAPI(TorrentAPI):
    name = "The Pirate Bay"
    url = 'https://thepiratebay.org'
    api_url = "https://apibay.org"
    supported_categories = {
        'all': '0',
        'music': '100',
        'movies': '200',
        'games': '400',
        'software': '300'
    }
    
    def search(self, query, category='all'):
        base_url = f"{self.api_url}/q.php?%s"
        
        # Get response json
        query = unquote(query)
        category_id = self.supported_categories.get(category, '0')
        params = {'q': query}
        if category_id != '0':
            params['cat'] = category_id
            
        data = self.retrieve_url(base_url % urlencode(params))
        if not data:
            return []
            
        try:
            response_json = json.loads(data)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON response from {self.name}")
            return []
            
        # Check empty response
        if len(response_json) == 0 or (len(response_json) == 1 and 'error' in response_json[0]):
            return []
            
        # Parse results
        results = []
        for result in response_json:
            if result.get('info_hash') == '0000000000000000000000000000000000000000':
                continue
                
            try:
                size = int(result.get('size', 0))
                formatted_size = self.format_size(size)
            except (ValueError, TypeError):
                size = 0
                formatted_size = "Unknown"
                
            res = {
                'link': self.create_magnet(result),
                'name': result.get('name', 'Unknown'),
                'size': formatted_size,
                'raw_size': size,
                'seeds': int(result.get('seeders', 0)),
                'leech': int(result.get('leechers', 0)),
                'source': self.name,
                'category': self.get_category_name(result.get('category', '0')),
                'desc_link': f"{self.url}/description.php?id={result.get('id', '')}",
                'pub_date': int(result.get('added', 0)),
            }
            results.append(res)
            
        return results
        
    def create_magnet(self, result):
        """Create a magnet link from result data"""
        return f"magnet:?xt=urn:btih:{result['info_hash']}&{urlencode({'dn': result['name']})}&{TRACKERS}"

class LimeTorrentsAPI(TorrentAPI):
    name = "LimeTorrents"
    url = "https://www.limetorrents.lol"
    supported_categories = {
        'all': 'all',
        'anime': 'anime',
        'software': 'applications',
        'games': 'games',
        'movies': 'movies',
        'music': 'music',
        'tv': 'tv'
    }
    
    def search(self, query, category='all'):
        query = query.replace(" ", "-")
        category = self.supported_categories.get(category, 'all')
        
        results = []
        
        # Only check first page for now
        page_url = f"{self.url}/search/{category}/{query}/seeds/1/"
        html = self.retrieve_url(page_url)
        
        if not html:
            return results
            
        # Parse results using regex
        pattern = r'<div class="tt-name"><a href="([^"]+)"[^>]*>([^<]+)</a></div>.*?<td class="tdnormal">([^<]+)</td>.*?<td class="tdseed">([^<]+)</td>.*?<td class="tdleech">([^<]+)</td>'
        matches = re.finditer(pattern, html, re.DOTALL)
        
        for match in matches:
            link = match.group(1)
            name = match.group(2).strip()
            size = match.group(3).strip()
            seeds = match.group(4).strip()
            leech = match.group(5).strip()
            
            # Extract info hash for magnet link - simplified for demo
            # In real implementation, we'd need to fetch the torrent page
            magnet_link = f"magnet:?xt=urn:btih:&{urlencode({'dn': name})}&{TRACKERS}"
            
            result = {
                'link': magnet_link,
                'name': name,
                'size': size,
                'raw_size': self.parse_size_to_bytes(size),
                'seeds': int(seeds.replace(',', '')),
                'leech': int(leech.replace(',', '')),
                'source': self.name,
                'category': category,
                'desc_link': self.url + link if not link.startswith('http') else link,
                'pub_date': int(time.time()),  # Placeholder as we don't extract the date
            }
            results.append(result)
            
        return results
        
    def parse_size_to_bytes(self, size_str):
        """Convert size string to bytes"""
        size_str = size_str.lower().replace(',', '')
        if not size_str or size_str == 'unknown':
            return 0
            
        multipliers = {
            'b': 1,
            'kb': 1024,
            'mb': 1024**2,
            'gb': 1024**3,
            'tb': 1024**4
        }
        
        try:
            for suffix, multiplier in multipliers.items():
                if size_str.endswith(suffix):
                    size_value = float(size_str.rstrip(suffix).strip())
                    return int(size_value * multiplier)
        except ValueError:
            pass
            
        return 0

class TorrentCSVAPI(TorrentAPI):
    name = "Torrents-CSV"
    url = 'https://torrents-csv.com'
    supported_categories = {'all': ''}
    
    def search(self, query, category='all'):
        search_url = f"{self.url}/service/search?size=100&q={query}"
        
        results = []
        
        # Get response json
        response = self.retrieve_url(search_url)
        if not response:
            return results
            
        try:
            response_json = json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON response from {self.name}")
            return results
            
        # Parse results
        for result in response_json.get("torrents", []):
            formatted_size = self.format_size(int(result.get('size_bytes', 0)))
            
            res = {
                'link': self.create_magnet(result),
                'name': result.get('name', 'Unknown'),
                'size': formatted_size,
                'raw_size': int(result.get('size_bytes', 0)),
                'seeds': int(result.get('seeders', 0)),
                'leech': int(result.get('leechers', 0)),
                'source': self.name,
                'category': result.get('category', 'Unknown'),
                'desc_link': f"{self.url}/#/search/torrent/{query}/1",
                'pub_date': int(result.get('created_unix', 0)),
            }
            results.append(res)
            
        return results
        
    def create_magnet(self, result):
        """Create a magnet link from result data"""
        return f"magnet:?xt=urn:btih:{result['infohash']}&{urlencode({'dn': result['name']})}&{TRACKERS}"

class NyaaAPI(TorrentAPI):
    name = "Nyaa.si"
    url = 'https://nyaa.si'
    supported_categories = {
        'all': '0_0',
        'anime': '1_0',
        'books': '3_0',
        'music': '2_0',
        'pictures': '5_0',
        'software': '6_0',
        'tv': '4_0',
        'movies': '4_0'
    }
    
    def search(self, query, category='all'):
        category_id = self.supported_categories.get(category, '0_0')
        search_url = f"{self.url}/?f=0&s=seeders&o=desc&c={category_id}&q={query}"
        
        results = []
        
        html = self.retrieve_url(search_url)
        if not html:
            return results
            
        # Parse results using regex
        pattern = r'<tr class="default">.*?<a href="([^"]+)".*?title="([^"]+)".*?<td class="text-center">([^<]+)</td>.*?<td class="text-center">(\d+)</td>.*?<td class="text-center">(\d+)</td>'
        matches = re.finditer(pattern, html, re.DOTALL)
        
        for match in matches:
            link_path = match.group(1)
            name = match.group(2)
            size = match.group(3)
            seeds = match.group(4)
            leech = match.group(5)
            
            # Extract torrent ID and build magnet link
            torrent_id = link_path.split('/download/')[1].split('.torrent')[0] if '/download/' in link_path else ''
            magnet_link = f"magnet:?xt=urn:btih:{torrent_id}&{urlencode({'dn': name})}&{TRACKERS}"
            
            result = {
                'link': magnet_link,
                'name': name,
                'size': size,
                'raw_size': self.parse_size_to_bytes(size),
                'seeds': int(seeds),
                'leech': int(leech),
                'source': self.name,
                'category': category,
                'desc_link': self.url + link_path,
                'pub_date': int(time.time()),  # Placeholder
            }
            results.append(result)
            
        return results
        
    def parse_size_to_bytes(self, size_str):
        """Convert size string to bytes"""
        size_str = size_str.lower().replace(',', '')
        if not size_str or size_str == 'unknown':
            return 0
            
        multipliers = {
            'bytes': 1,
            'b': 1,
            'kib': 1024,
            'mib': 1024**2,
            'gib': 1024**3,
            'tib': 1024**4
        }
        
        try:
            parts = size_str.split()
            if len(parts) == 2:
                size_value = float(parts[0])
                unit = parts[1].lower()
                for suffix, multiplier in multipliers.items():
                    if unit == suffix:
                        return int(size_value * multiplier)
        except ValueError:
            pass
            
        return 0

# Add more API implementations as needed

# API Factory
def get_apis():
    """Return a list of available torrent APIs"""
    return [
        PirateBayAPI(),
        LimeTorrentsAPI(),
        TorrentCSVAPI(),
        NyaaAPI(),
        # Add more APIs as implemented
    ]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def search():
    """Multi-source torrent search API endpoint"""
    query = request.args.get('q', '')
    category = request.args.get('category', 'all')
    sources = request.args.getlist('source')  # Allow filtering by specific sources
    
    if not query:
        return jsonify([])
    
    apis = get_apis()
    
    # Filter APIs by source if requested
    if sources:
        apis = [api for api in apis if api.name in sources]
    
    # Use concurrent.futures to search multiple sources in parallel
    all_results = []
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(apis)) as executor:
            # Start the API search tasks
            future_to_api = {
                executor.submit(api.search, query, category): api 
                for api in apis
            }
            
            # Process results as they come in
            for future in concurrent.futures.as_completed(future_to_api):
                api = future_to_api[future]
                try:
                    results = future.result()
                    logger.info(f"Got {len(results)} results from {api.name}")
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Error with {api.name}: {str(e)}")
    except Exception as e:
        logger.error(f"Error during multi-search: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
    # Sort by seeds (descending)
    all_results.sort(key=lambda x: x.get('seeds', 0), reverse=True)
    
    return jsonify(all_results)

@app.route('/api/sources')
def get_sources():
    """Return a list of available sources"""
    return jsonify([api.name for api in get_apis()])

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
