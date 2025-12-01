import requests
import pickle
import os
import urllib.parse
import json
import time
import subprocess

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

login_failures = 0
login_successes = 0
class Substack:
    def __init__(self, context, cookie_file=None, login_url=None):
        self.context = context
        self.page = None

        self.s = requests.Session()
        self.cookies = None
        self.cookie_file = cookie_file
        if login_url:
            print('Using Substack login_url')
            try:
                self.login(login_url)
            except Exception as e:
                print('login failed, trying to read existing cookies', e)
                self.read_cookies()
        else:
            print(f'Using existing substack cookie file {cookie_file=}')
            self.read_cookies()
            self.launch_homepage_and_save_cookies()
    
    def _new_page(self):
        p = self.context.new_page()
        def _refresh_if_429(response):
            if response.status == 429 and not ('api/v1' in response.url):
                print('429, waiting', response.url)
                time.sleep(5)
                p.reload()
                p.wait_for_load_state()
        p.on('response', _refresh_if_429)
        return p

    def login(self, login_url, headless=True):
        #r = self.s.get(login_url, allow_redirects=True)
        print('[login] Opening playwright:', login_url)
        if not self.page:
            self.page = self._new_page()
        page = self.page
        page.goto(login_url)
        page.wait_for_load_state()
        page.wait_for_timeout(5000)
        try:
            page.evaluate('location.reload()')
        except:
            print('location.reload() failed')
        page.goto(login_url)
        page.wait_for_load_state()
        try:
            page.evaluate('location.reload()')
        except:
            print('location.reload() failed')
        page.goto('https://substack.com/home')
        page.wait_for_load_state()
        c = self.context.cookies()
        print('[login] got cookies: %s' % c)
        self.write_cookies(c)
    
    def launch_homepage_and_save_cookies(self):
        print('[launch] Opening playwright: https://substack.com/home')
        if self.cookies:
            print(f'adding {len(self.cookies)} cookies')
            self.context.add_cookies(self.cookies)
        if not self.page:
            self.page = self._new_page()
        page = self.page
        page.goto('https://substack.com/home')
        page.wait_for_load_state()
        try:
            page.evaluate('location.reload()')
        except:
            print('location.reload() failed')
        page.goto('https://substack.com/home')
        page.wait_for_load_state()
        c = self.context.cookies()
        print('[launch] got cookies: %s' % c)
        self.write_cookies(c)
    
    def write_cookies(self, playwright_cookies):
        def _to_json(c):
            return {
                'name': c.get('name'),
                'value': c.get('value'),
                'domain': c.get('domain'),
                'path': c.get('path'),
                'expires': c.get('expires'),
                'httpOnly': c.get('httpOnly'),
                'secure': c.get('secure'),
                'sameSite': c.get('sameSite'),
            }

        if not self.cookie_file:
            return
        with open(self.cookie_file, 'w') as f:
            j = [_to_json(c) for c in playwright_cookies]
            f.write(json.dumps(j, indent=4))
            self.cookies = j
    
    def read_cookies(self):
        if not self.cookie_file:
            return
        if not os.path.exists(self.cookie_file):
            return
        with open(self.cookie_file, 'r') as f:
            self.cookies = json.load(f)
            for c in self.cookies:
                self.s.cookies.set(c['name'], c['value'], domain=c['domain'])



    
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
        if r.status_code == 429:
            print('429, waiting')
            time.sleep(5)
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    def get_full_archive(self, domain):
        out = []
        offset = None
        c = 0
        while True:
            try:
                ret = self.get_archive(domain, limit=12, offset=offset)
            except RuntimeError as e:
                if '429:' in str(e):
                    time.sleep(15)
                    continue
                else:
                    raise e
            print(f'get_archive({offset=})')
            if not ret:
                print(f'get_full_archive done {len(out)}')
                return out
            c += 1
            out += ret
            if offset:
                offset += 12
            else:
                offset = 12
            if c % 5 == 0:
                time.sleep(5)
            time.sleep(1)

    def get_subscriptions(self):
        r = self.s.get(f'https://substack.com/api/v1/subscriptions')
        if r.status_code//100 != 2:
            raise RuntimeError(f'{r.status_code}: {r.text}')
        return r.json()

    # def playwright_cookies(self):
    #     return [{'name': k.name, 'value': k.value, 'port': k.port, 'domain': k.domain, 'path': k.path, 'secure': k.secure, 'expires': k.expires} for k in self.s.cookies]


    relogin_command_run = False
    def download_pdf(self, *args, **kwargs):
        global login_successes
        global login_failures
        for i in range(3):
            try:
                ret = self._download_pdf(*args, retry=i, **kwargs)
                if ret:
                    login_successes += 1
                    print(f'STATUS {login_failures=} {login_successes=}')
                    return ret
            except Exception as e:
                print('download_pdf call', i+1, 'swallowed exception', e)
            print('Retrying download_pdf()')
        ret = self._download_pdf(*args, retry=3, **kwargs)
        if not ret:
            login_failures += 1
            if kwargs.get('relogin_command') and not self.relogin_command_run and login_successes == 0:
                print(f'STATUS {login_failures=} {login_successes=}')
                subprocess.run(['/bin/bash', '-c', kwargs.get('relogin_command')])
                self.relogin_command_run = True
        else:
            login_successes += 1
            print(f'STATUS {login_failures=} {login_successes=}')
        return ret

    def _download_pdf(self, url, output_file, headless=True, slow_mo=0, relogin_command=None, retry=0):
        print('Opening playwright:', url)

        _logged_in_locator = 'svg.lucide-bell, a[href*=sign-out]'
        
        if self.cookies:
            print(f'adding {len(self.cookies)} cookies')
            self.context.add_cookies(self.cookies)
        if not self.page:
            self.page = self._new_page()
        page = self.page

        print('Opening https://substack.com/home')
        page.goto('https://substack.com/home')
        page.wait_for_load_state()
        page.wait_for_timeout(5000)
        print('Opened https://substack.com/home')
        try:
            page.locator(_logged_in_locator).wait_for(timeout=1000)
        except Exception as e:
            print('Unable to ensure logged-in on substack homepage (no icon), you need to relogin', e)
            return None
        print('Found logged-in session on substack.com')

        page.goto(url)
        try:
            page.wait_for_load_state(timeout=5000)
        except:
            print('load state ignored')
        print('Ensuring logged-in session carries to article details')
        try:
            page.locator(_logged_in_locator).wait_for(timeout=2000)
        except Exception as e:
            print('try 1: unable to ensure logged-in to', url, '\n - error:', e)
            try:
                page.locator('a[href*="sign-in"]').first.click()
            except:
                print('no href=sign-in')
            try:
                si = page.locator('[data-href*="sign-in"]').first
                si_url = si.get_attribute('data-href')
                si.click()

                page.wait_for_load_state(timeout=2000)
                page.goto(si_url)
                page.wait_for_load_state(timeout=2000)
            except:
                print('no data-href=sign-in')
            try:
                page.wait_for_load_state(timeout=5000)
            except:
                print('load state ignored')
            page.wait_for_timeout(1000)
            print('Opening https://substack.com/home again')
            page.goto('https://substack.com/home')
            try:
                page.wait_for_load_state(timeout=5000)
            except:
                print('load state ignored')
            page.wait_for_timeout(2000)
            print("Reloading page after signin carryover")
            page.goto(url)
            try:
                page.wait_for_load_state(timeout=5000)
            except:
                print('load state ignored')
            page.wait_for_timeout(1000)
            print("Looking for login session")
            try:
                page.locator(_logged_in_locator).wait_for(timeout=2000)
                print("Logged in!")
            except Exception as e:
                print('try 2: unable to ensure logged-in to', url, '\n - error:', e)
                try:
                    page.locator('a[href*="sign-in"]').first.click()
                except:
                    print('no href=sign-in')
                try:
                    page.locator('[data-href*="sign-in"]').first.click()
                except:
                    print('no data-href=sign-in')
                try:
                    page.evaluate('location.reload()')
                except:
                    print('location.reload() failed')
                try:
                    page.wait_for_load_state(timeout=5000)
                except:
                    print('load state ignored')
                page.wait_for_timeout(2000)
                print('Opening https://substack.com/home again')
                page.goto('https://substack.com/home')
                try:
                    page.wait_for_load_state(timeout=5000)
                except:
                    print('load state ignored')
                page.wait_for_timeout(2000)
                print("Reloading original page after signin carryover")
                page.goto(url)
                try:
                    page.wait_for_load_state(timeout=2000)
                except:
                    print('load state ignored')
                try:
                    page.evaluate('location.reload()')
                except:
                    print('location.reload() failed')
                try:
                    page.wait_for_load_state(timeout=5000)
                except:
                    print('load state ignored')
                page.wait_for_timeout(2000)
                print("Looking for login session")
                try:
                    page.locator(_logged_in_locator).wait_for(timeout=3000)
                    print("Logged in!")
                except Exception as e2:
                    pass
                bell = page.evaluate('document.querySelector("svg.lucide-bell")')
                if not bell:
                    print('TIMED OUT: unable to ensure logged-in to', url, '\n - error:', e2)
                    return None
                else:
                    print('FOUND!')
        page.wait_for_timeout(1000)
        page.emulate_media(media="print")
        page.wait_for_timeout(1000)
        page.add_style_tag(content='''                           
@page {
    size: A4;
    margin: 20mm !important;
}
@media all {
    @page {
        size: A4;
        margin: 20mm !important;
    }

    article {
        margin: 0 20mm !important;
    }

    div#discussion, .publication-footer, .footer {
        display: none !important;
    }

    html, body {
        width: 250mm;
    }
}
        ''')
        page.wait_for_timeout(1000)
        print("Starting scroll...")
        lastScrollY = -1000
        curScrollY = page.evaluate('(document.scrollingElement || document.body).scrollTop')
        scrolled = 0
        while curScrollY > lastScrollY:
            N = 250
            page.mouse.wheel(0, N)
            scrolled += N
            page.wait_for_timeout(50)
            lastScrollY = curScrollY
            curScrollY = page.evaluate('(document.scrollingElement || document.body).scrollTop')

        print("Resetting to top")
        page.mouse.wheel(0, -1 * scrolled)
        page.wait_for_timeout(1000)
        print("Done scrolling")
        page.pdf(path=output_file, prefer_css_page_size=True)
        return True

if __name__ == '__main__':
    import argparse

    a = argparse.ArgumentParser(description="Writes recent Substack articles to reMarkable cloud")
    a.add_argument('--download-url', help='URL to download PDF for')
    a.add_argument('--download-domain', help='Substack domain to download all PDFs for')
    a.add_argument('--config-folder', help='Configuration folder for remarkable-substack', default='')
    a.add_argument('--substack-login-url', help='For initial authentication with Substack: the URL from the email received from Substack when entering your email on the login page')
    a.add_argument('--non-headless', help='Debug by not having headless browser', action='store_true')
    a.add_argument('--output-folder', help='Output folder', default='out')
    a.add_argument('--relogin-command', help='Command to run when relogin is required (e.g. send a notification)', default=None)
    a.add_argument('--slow-mo', help='Slow down browser actions by this many milliseconds', default=0, type=int)
    args = a.parse_args()
    with Stealth().use_sync(sync_playwright()) as p:
        chromium = p.chromium
        browser = chromium.launch(headless=not args.non_headless, slow_mo=args.slow_mo)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )

        if not args.config_folder:
            args.config_folder = os.path.join(os.path.expanduser('~'), '.config', 'remarkable-substack')
            if not os.path.exists(args.config_folder):
                os.makedirs(args.config_folder)
            print(f'Set --config-folder to {args.config_folder}')

        cookie_file = os.path.join(args.config_folder, '.substack-cookie')
        ss = Substack(context, cookie_file=cookie_file, login_url=args.substack_login_url)
        if args.download_url:
            path = f'{args.output_folder}/article.pdf'
            print(f'Downloading {args.download_url=} {path=}')
            ret = ss.download_pdf(args.download_url, path, headless=not args.non_headless, slow_mo=args.slow_mo)
            print(f'Result: {ret}')

        if args.download_domain:
            archive = ss.get_full_archive(args.download_domain)
            with open(f'{args.output_folder}/{args.download_domain}.json','w') as f:
                f.write(json.dumps(archive, indent=4))

            print(f'{len(archive)=}')
            root = f'{args.output_folder}/{args.download_domain}'
            if not os.path.exists(root):
                os.makedirs(root, exist_ok=True)

            for item in archive:
                date = item['post_date'].split('T')[0]
                title = item['title'].replace('/','-')
                path = os.path.join(root, f'{date} - {title}.pdf')
                if os.path.exists(path):
                    print(f'File {path=} already exists, skipping')
                    continue
                print(f'Downloading {date=} {title=} {path=}')
                ret = ss.download_pdf(item['canonical_url'], path, headless=not args.non_headless, relogin_command=args.relogin_command, slow_mo=args.slow_mo)
                print(f'Result: {ret}')

