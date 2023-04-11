import requests
import pickle
import os

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

    def get_subscriptions(self):
        r = self.s.get(f'https://substack.com/api/v1/subscriptions')
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    def playwright_cookies(self):
        return [{'name': k.name, 'value': k.value, 'port': k.port, 'domain': k.domain, 'path': k.path, 'secure': k.secure, 'expires': k.expires} for k in self.s.cookies]

    def download_pdf(self, url, output_file):
        with sync_playwright() as p:
            chromium = p.chromium
            browser = chromium.launch()
            context = browser.new_context()
            context.add_cookies(self.playwright_cookies())
            page = context.new_page()
            page.emulate_media(media="print")
            page.goto(url)
            page.pdf(path=output_file)
            browser.close()
