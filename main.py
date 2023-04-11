#!/usr/bin/env python3
import argparse
import re
import tempfile
import os
import json
import pypdf
import time

from remarkable import Remarkable
from sstack import Substack

from datetime import datetime

def parse_args():
    a = argparse.ArgumentParser(description="Writes recent Substack articles to reMarkable cloud")
    a.add_argument('--max-save-count', type=int, default=20, help='Maximum number of articles to save on device')
    a.add_argument('--max-fetch-count', type=int, default=40, help='Maximum number of articles to fetch from Substack')
    a.add_argument('--delete-already-read', action='store_true', help='Delete articles in reMarkable cloud which are already read')
    a.add_argument('--folder', default='Substack', help='Folder title to write to')
    a.add_argument('--remarkable-auth-token', help='For initial authentication with reMarkable: device token')
    a.add_argument('--substack-login-url', help='For initial authentication with reMarkable: device token')
    a.add_argument('--config-folder', help='Configuration folder for remarkable-substack')
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
    
    print(f'Existing files in {args.folder}: {ls}')
    
    db_file = os.path.join(args.config_folder, 'db_file.json')
    article_data = {}
    if os.path.exists(db_file):
        article_data = json.loads(open(db_file, 'r').read())

    existing_ids = set()
    files_to_delete = set()
    for file in ls:
        id = parse_filename(file)
        if id:
            existing_ids.add(id)
            if args.delete_already_read and id in article_data:
                num_pages = article_data.get(id)['num_pages']
                stat = rm.stat(f'{args.folder}/{file}')
                print(f"Check: {file} is on page {1+stat['CurrentPage']} of {num_pages} total")
                if 1 + stat['CurrentPage'] == num_pages:
                    print(f"Will delete {file} since already read")
                    files_to_delete.add(f'{args.folder}/{file}')
    
    print(f'{existing_ids=}')
    if args.delete_already_read:
        print(f'{files_to_delete=}')


    cookie_file = os.path.join(args.config_folder, '.substack-cookie')
    ss = Substack(cookie_file=cookie_file, login_url=args.substack_login_url)
    subs = ss.get_subscriptions()
    publications = {}
    for pub in subs['publications']:
        publications[pub['id']] = pub['name']

    def to_filename(post):
        pub_name = publications[post['publication_id']]
        title = post['title']
        return f"{pub_name} - {title} [{id}].pdf"


    new_ids = set()
    fetched_ids = set()
    all_posts = []
    after = None
    while len(new_ids) + len(existing_ids) < args.max_save_count and len(fetched_ids) < args.max_fetch_count:
        print(f'get_posts(after={after})')
        posts = ss.get_posts(limit=20, after=None)

        for post in posts['posts']:
            id = str(post['id'])
            fetched_ids.add(id)
            if id not in existing_ids:
                if len(new_ids) + len(existing_ids) < args.max_save_count:
                    print(f'Found new article: {id}: {to_filename(post)}')
                    new_ids.add(id)
            else:
                print(f'Already read article: {id}: {to_filename(post)}')
            after = post['post_date']
            all_posts.append(post)

        if not posts['more']:
            print('No more posts to return -- stopping')
            break
    
    print(f'{fetched_ids=}')
    print(f'{new_ids=}')

    dir = tempfile.gettempdir()
    to_upload = []
    for post in all_posts:
        id = str(post['id'])
        if id in new_ids:
            output_file = os.path.join(dir, to_filename(post))
            print(f"Downloading {post['canonical_url']} to pdf {output_file}")
            ss.download_pdf(post['canonical_url'], output_file)
            num_pages = get_num_pages(output_file)
            article_data[id] = {
                'id': id,
                'num_pages': num_pages,
                'canonical_url': post['canonical_url'],
                'added': time.time()
            }
            to_upload.append(output_file)
    
    print(f'Uploading: {to_upload}')
    for f in to_upload:
        print(f'Uploading {f} to {args.folder}')
        rm.put(f, args.folder)

    print('Upload complete')

    with open(db_file, 'w') as f:
        f.write(json.dumps(article_data))

    if args.delete_already_read and len(files_to_delete) > 0:
        print('Deleting old files')
        for path in files_to_delete:
            print(f'Deleting {path}')
            assert path.startswith(f'{args.folder}/')
            assert '../' not in path
            assert '/..' not in path
            assert len(path) > 2 + len(args.folder)
            rm.rm(path)

def get_num_pages(path):
    with open(path, 'rb') as f:
        r = pypdf.PdfReader(f)
        return len(r.pages)

if __name__ == '__main__':
    args = parse_args()
    main(args)