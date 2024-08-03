#!/usr/bin/env python3
import argparse
import re
import tempfile
import os
import json
import pypdf
import time
import subprocess

from remarkable import Remarkable
from sstack import Substack

from datetime import datetime

def parse_args():
    a = argparse.ArgumentParser(description="Writes recent Substack articles to reMarkable cloud")
    a.add_argument('--max-save-count', type=int, default=20, help='Maximum number of articles to save on device')
    a.add_argument('--max-fetch-count', type=int, default=20, help='Maximum number of articles to fetch from Substack')
    a.add_argument('--delete-already-read', action='store_true', help='Delete articles in reMarkable cloud which are already read')
    a.add_argument('--delete-unread-after-hours', type=int, default=48, help='If an article has not been opened for this many hours on the device and there are new articles to add, will delete. Set to -1 to disable, or 0 to always replace old articles.')
    a.add_argument('--folder', default='Substack', help='Folder title to write to')
    a.add_argument('--remarkable-auth-token', help='For initial authentication with reMarkable: device token')
    a.add_argument('--substack-login-url', help='For initial authentication with Substack: the URL from the email received from Substack when entering your email on the login page')
    a.add_argument('--config-folder', help='Configuration folder for remarkable-substack')
    a.add_argument('--tmp-folder', help='Temporary storage folder for remarkable-substack')
    a.add_argument('--relogin-command', help='Command to run when relogin is required to substack (e.g. send a notification)', default=None)
    a.add_argument('--remarkable-relogin-command', help='Command to run when relogin is required to remarkable (e.g. send a notification)', default=None)
    return a.parse_args()

def parse_filename(fn):
    # Find ID in final brackets
    pattern = r"\[([^\[\]]*)\][^\[\]]*$"
    match = re.search(pattern, fn)
    if match:
        return match.group(1)
    return None


def main(args):
    try:
        rm = Remarkable()
        rm.auth_if_needed(args.remarkable_auth_token)
    except Exception as e:
        if args.remarkable_relogin_command:
            subprocess.run(['/bin/bash', '-c', args.remarkable_relogin_command])
        raise e

    if not rm.is_auth():
        if args.remarkable_relogin_command:
            subprocess.run(['/bin/bash', '-c', args.remarkable_relogin_command])

    ls = []
    try:
        ls = rm.ls(args.folder)
    except FileNotFoundError:
        rm.mkdir(args.folder)
        ls = []
    
    if not args.config_folder:
        args.config_folder = os.path.join(os.path.expanduser('~'), '.config', 'remarkable-substack')
        if not os.path.exists(args.config_folder):
            os.makedirs(args.config_folder)
        print(f'Set --config-folder to {args.config_folder}')
    
    print(f'Existing files in {args.folder}: {ls}')
    
    db_file = os.path.join(args.config_folder, 'db_file.json')
    already_downloaded_ids = set()
    article_data = {}
    if os.path.exists(db_file):
        article_data = json.loads(open(db_file, 'r').read())
    
    already_downloaded_ids = list(article_data.keys())

    existing_ids = set()
    files_to_delete = set()
    delete_if_needed = {}
    now_ts = time.time()
    for file in ls:
        id = parse_filename(file)
        if id:
            existing_ids.add(id)
            if id in article_data:
                added_ts = article_data.get(id)['added']
                num_pages = article_data.get(id)['num_pages']
                stat = rm.stat(f'{args.folder}/{file}')
                print(f"Check: {file} is on page {1+stat['CurrentPage']} of {num_pages} total")
                if args.delete_already_read:
                    if 1 + stat['CurrentPage'] == num_pages:
                        print(f"Will delete {file} since already read")
                        files_to_delete.add(f'{args.folder}/{file}')
                if stat['CurrentPage'] == 0:
                    unread_hrs = (now_ts - added_ts) / 60 / 60
                    if args.delete_unread_after_hours >= 0 and unread_hrs >= args.delete_unread_after_hours:
                        print(f"Article not opened after {unread_hrs} hrs, will delete if needed: {file}")
                        delete_if_needed[id] = f'{args.folder}/{file}'
    
    print(f'{existing_ids=}')
    print(f'{delete_if_needed.keys()=}')
    if args.delete_already_read:
        print(f'{files_to_delete=}')


    cookie_file = os.path.join(args.config_folder, '.substack-cookie')
    try:
        ss = Substack(cookie_file=cookie_file, login_url=args.substack_login_url)
        subs = ss.get_subscriptions()
    except Exception as e:
        if args.relogin_command:
            subprocess.run(['/bin/bash', '-c', args.relogin_command])
        raise e
    publications = {}
    for pub in subs['publications']:
        publications[pub['id']] = pub['name']

    def to_filename(post):
        pub_name = publications[post['publication_id']]
        title = post['title']
        return f"{pub_name} - {title} [{id}].pdf"


    new_ids = set()
    fetched_ids = set()
    fetched_old_ids = set()
    all_posts = []
    after = None
    while len(fetched_ids) < args.max_fetch_count:
        print(f'get_posts(after={after})')
        posts = ss.get_posts(limit=20, after=after)

        for post in posts['posts']:
            id = str(post['id'])
            fetched_ids.add(id)
            if id not in existing_ids:
                if id not in already_downloaded_ids:
                    if len(new_ids) + len(existing_ids) < args.max_save_count:
                        print(f'Found new article: {id}: {to_filename(post)}')
                        new_ids.add(id)
                    elif len(delete_if_needed) > 0 and args.delete_unread_after_hours >= 0:
                        delete_id = list(sorted(list(delete_if_needed.keys())))[0]
                        print(f'Article in delete_if_needed dropped: {delete_id} {delete_if_needed[delete_id]}')
                        files_to_delete.add(delete_if_needed[delete_id])
                        del delete_if_needed[delete_id]

                        print(f'Found new article: {id}: {to_filename(post)}')
                        new_ids.add(id)
                    else:
                        print(f'Found but not downloading new article (no space): {id}: {to_filename(post)}')
                else:
                    print(f'Article already read: {id}: {to_filename(post)}')
                
            else:
                fetched_old_ids.add(id)
                print(f'Article already on remarkable: {id}: {to_filename(post)}')
            after = post['post_date']
            all_posts.append(post)

        if not posts['more']:
            print('No more posts to return -- stopping')
            break
        
        time.sleep(5)
    
    print(f'{fetched_ids=}')
    print(f'{fetched_old_ids=}')
    print(f'{new_ids=}')

    dir = tempfile.gettempdir()
    if args.tmp_folder:
        dir = args.tmp_folder
    to_upload = []
    for post in all_posts:
        id = str(post['id'])
        if id in new_ids:
            output_file = os.path.join(dir, to_filename(post))
            print(f"Downloading {post['canonical_url']} to pdf {output_file}")
            ss.download_pdf(post['canonical_url'], output_file)
            if not os.path.exists(output_file):
                print(f"Unable to download {post['canonical_url']} to {output_file}. Skipping")
                time.sleep(5)
                continue
            num_pages = get_num_pages(output_file)
            article_data[id] = {
                'id': id,
                'num_pages': num_pages,
                'canonical_url': post['canonical_url'],
                'filename': to_filename(post),
                'added': now_ts
            }
            to_upload.append(output_file)
            print(f"Download complete: {article_data[id]}")
            time.sleep(5)

    
    print(f'Uploading: {to_upload}')
    for f in to_upload:
        print(f'Uploading {f} to {args.folder}')
        rm.put(f, args.folder)

    print('Upload complete')


    if args.delete_already_read and len(files_to_delete) > 0:
        print('Deleting old files')
        for path in files_to_delete:
            print(f'Deleting {path}')
            assert path.startswith(f'{args.folder}/')
            assert '../' not in path
            assert '/..' not in path
            assert len(path) > 2 + len(args.folder)
            rm.rm(path)

            id = parse_filename(path)
            if id and id in article_data:
                article_data[id]['deleted'] = now_ts
    
    with open(db_file, 'w') as f:
        f.write(json.dumps(article_data))

def get_num_pages(path):
    with open(path, 'rb') as f:
        r = pypdf.PdfReader(f)
        return len(r.pages)

if __name__ == '__main__':
    args = parse_args()
    main(args)