#!/usr/bin/env python3
import argparse
import re
import tempfile
import os
import time

from remarkable import Remarkable
from sstack import Substack

from datetime import datetime

def parse_args():
    a = argparse.ArgumentParser(description="Writes recent Substack articles to reMarkable cloud")
    a.add_argument('--max-count', type=int, default=20, help='Maximum number of articles')
    a.add_argument('--folder', default='Substack', help='Folder title to write to')
    a.add_argument('--remarkable-auth-token', help='For initial authentication with reMarkable: device token')
    a.add_argument('--substack-login-url', help='For initial authentication with reMarkable: device token')
    a.add_argument('--substack-cookie-file', help='File for writing and reading Substack login cookies')
    return a.parse_args()

def parse_filename(fn):
    # Find ID in final brackets
    pattern = r"\[([^\[\]]*)\][^\[\]]*$"
    match = re.search(pattern, fn)
    if match:
        return match.group(1)
    return None


def main(args):
    rm = Remarkable()
    rm.auth_if_needed(args.remarkable_auth_token)

    ls = []
    try:
        ls = rm.ls(args.folder)
    except FileNotFoundError:
        rm.mkdir(args.folder)
        ls = []
    
    existing_ids = set()
    for file in ls:
        id = parse_filename(file)
        if id:
            existing_ids.add(id)

    ss = Substack(cookie_file=args.substack_cookie_file, login_url=args.substack_login_url)
    subs = ss.get_subscriptions()
    publications = {}
    for pub in subs['publications']:
        publications[pub['id']] = pub['name']

    def to_filename(post):
        pub_name = publications[post['publication_id']]
        title = post['title']
        return f"{pub_name} - {title} [{id}].pdf"

    new_ids = set()
    after = None
    while len(new_ids) < args.max_count:
        posts = ss.get_posts(limit=min(args.max_count, 20), after=None)

        for post in posts['posts']:
            id = post['id']
            if id not in existing_ids and len(new_ids) < args.max_count:
                print(f'Found new article: {id}: {to_filename(post)}')
                new_ids.add(id)
            after = post['post_date']

        if not posts['more']:
            print('No more posts to return -- stopping')
            break

    dir = tempfile.gettempdir()
    to_upload = []
    for post in posts['posts']:
        id = post['id']
        if id in new_ids:
            output_file = os.path.join(dir, to_filename(post))
            print(f"Downloading {post['canonical_url']} to pdf {output_file}")
            ss.download_pdf(post['canonical_url'], output_file)
            to_upload.append(output_file)
    
    print(to_upload)


if __name__ == '__main__':
    args = parse_args()
    main(args)