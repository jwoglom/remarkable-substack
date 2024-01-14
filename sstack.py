import requests
import pickle
import os
import urllib.parse
import json

from playwright.sync_api import sync_playwright

class Substack:
    def __init__(self, cookie_file=None, login_url=None):
        self.s = requests.Session()
        self.cookie_file = cookie_file
        if login_url:
            self.login(login_url)
        else:
            self.read_cookies()
    
    def write_cookies(self):
        if not self.cookie_file:
            return
        with open(self.cookie_file, 'wb') as f:
            pickle.dump(self.s.cookies, f)
    
    def read_cookies(self):
        if not self.cookie_file:
            return
        if not os.path.exists(self.cookie_file):
            return
        with open(self.cookie_file, 'rb') as f:
            self.s.cookies.update(pickle.load(f))

    
    def login(self, login_url):
        r = self.s.get(login_url)
        print(r.status_code, r)
        self.write_cookies()
    
    def get_posts(self, inbox_type='inbox', limit=12, after=None): # max limit enforced by substack: 20
        url = f'https://substack.com/api/v1/reader/posts?inboxType={inbox_type}&limit={limit}'
        if after:
            url += f'&after={after}'
        r = self.s.get(url)
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    def get_archive(self, domain, limit=12, offset=None): # max limit enforced by substack: 20
        url = f'https://{domain}/api/v1/archive?sort=new&search=&limit={limit}'
        if offset:
            url += f'&offset={offset}'
        r = self.s.get(url)
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    def get_full_archive(self, domain):
        out = []
        offset = None
        while True:
            ret = self.get_archive(domain, limit=12, offset=offset)
            print(f'get_archive({offset=})')
            if not ret:
                return out
            out += ret
            if offset:
                offset += 12
            else:
                offset = 12

    def get_subscriptions(self):
        r = self.s.get(f'https://substack.com/api/v1/subscriptions')
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    def playwright_cookies(self):
        return [{'name': k.name, 'value': k.value, 'port': k.port, 'domain': k.domain, 'path': k.path, 'secure': k.secure, 'expires': k.expires} for k in self.s.cookies]


    def download_pdf(self, *args, **kwargs):
        for i in range(2):
            try:
                ret = self._download_pdf(*args, **kwargs)
                if ret:
                    return ret
            except Exception as e:
                print('download_pdf call', i+1, 'swallowed exception', e)
            print('Retrying download_pdf()')
        return self._download_pdf(*args, **kwargs)

    def _download_pdf(self, url, output_file, headless=True):
        print('Opening playwright:', url)
        parsed_url = urllib.parse.urlparse(url)
        with sync_playwright() as p:
            chromium = p.chromium
            browser = chromium.launch(headless=headless)
            context = browser.new_context()
            context.add_cookies(self.playwright_cookies())
            page = context.new_page()
            if not parsed_url.netloc.endswith('.substack.com'):
                page.goto('https://substack.com')
                page.wait_for_load_state()
                page.wait_for_timeout(5000)
            page.goto(url)
            page.wait_for_load_state()
            try:
                page.locator('.signed-in').wait_for(timeout=20000)
            except Exception as e:
                print('try 1: unable to ensure logged-in to', url, ' - error:', e)
                page.locator('.sign-in-link').click()
                page.wait_for_load_state()
                page.wait_for_timeout(5000)
                page.goto(url)
                page.wait_for_load_state()
                try:
                    page.locator('.signed-in').wait_for(timeout=20000)
                except Exception as e:
                    print('TIMED OUT: unable to ensure logged-in to', url, ' - error:', e)
                    return None

            page.emulate_media(media="print")
            page.pdf(path=output_file)
            browser.close()
        return True

if __name__ == '__main__':
    import argparse

    a = argparse.ArgumentParser(description="Writes recent Substack articles to reMarkable cloud")
    a.add_argument('--download-url', help='URL to download PDF for')
    a.add_argument('--download-domain', help='Substack domain to download all PDFs for')
    a.add_argument('--config-folder', help='Configuration folder for remarkable-substack', default='')
    a.add_argument('--substack-login-url', help='For initial authentication with Substack: the URL from the email received from Substack when entering your email on the login page')
    a.add_argument('--non-headless', help='Debug by not having headless browser', action='store_true')
    args = a.parse_args()

    if not args.config_folder:
        args.config_folder = os.path.join(os.path.expanduser('~'), '.config', 'remarkable-substack')
        if not os.path.exists(args.config_folder):
            os.makedirs(args.config_folder)
        print(f'Set --config-folder to {args.config_folder}')
    cookie_file = os.path.join(args.config_folder, '.substack-cookie')
    ss = Substack(cookie_file=cookie_file, login_url=args.substack_login_url)
    if args.download_url:
        ss.download_pdf(args.download_url, '/tmp/test.pdf', headless=not args.non_headless)

    if args.download_domain:
        if not os.path.exists(f'out/{args.download_domain}.json'):
            archive = ss.get_full_archive(args.download_domain)
            with open(f'out/{args.download_domain}.json','w') as f:
                f.write(json.dumps(archive, indent=4))
        else:
            with open(f'out/{args.download_domain}.json','r') as f:
                archive = json.loads(f.read())

        print(f'{len(archive)=}')
        root = f'out/{args.download_domain}'
        if not os.path.exists(root):
            os.makedirs(root, exist_ok=True)

        for item in archive:
            date = item['post_date'].split('T')[0]
            title = item['title']
            path = os.path.join(root, f'{date} - {title}.pdf')
            if os.path.exists(path):
                print(f'File {path=} already exists, skipping')
                continue
            print(f'Downloading {date=} {title=} {path=}')
            ss.download_pdf(item['canonical_url'], path, headless=not args.non_headless)

