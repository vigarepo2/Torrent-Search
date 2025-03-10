from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import gzip
import html
import io
import urllib.error
import urllib.request
from urllib.parse import urlencode, unquote

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

class PirateBayAPI:
    url = 'https://thepiratebay.org'
    name = 'The Pirate Bay'
    supported_categories = {
        'all': '0',
        'music': '100',
        'movies': '200',
        'games': '400',
        'software': '300'
    }

    # initialize trackers for magnet links
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
    trackers = '&'.join(urlencode({'tr': tracker}) for tracker in trackers_list)

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
        response_json = json.loads(data)

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
            }
            results.append(res)
        
        return results

    def download_link(self, result):
        return "magnet:?xt=urn:btih:{}&{}&{}".format(
            result['info_hash'], urlencode({'dn': result['name']}), self.trackers)

    def retrieve_url(self, url):
        # Request data from API
        request = urllib.request.Request(
            url, 
            None, 
            {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'}
        )

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
        dataStr = dataStr.replace('&quot;', '\\"')  # Manually escape &quot; before
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
    
    def get_category_name(self, category_id):
        category_map = {
            '0': 'All',
            '100': 'Music',
            '200': 'Movies',
            '300': 'Software',
            '400': 'Games',
        }
        return category_map.get(category_id, 'Other')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', 'all')
    
    if not query:
        return jsonify([])
    
    try:
        api = PirateBayAPI()
        results = api.search(query, category)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=80)
