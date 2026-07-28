# remarkable-substack

Syncs unread Substack posts onto your ReMarkable tablet.

## How to run

You can run either via Docker or locally with Python + pipenv.

### Docker
With `docker run`, use an invocation such as the following. Update the version number to the latest release.

```bash
docker run -v ~/.config/rmapi-js:/home/appuser/.config/rmapi-js -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.3.9
```

Note the volume-mounted `.config/rmapi-js` directory from your home directory, which stores the long-lived remarkable device token and the hash cache, and the `.config/remarkable-substack` folder which stores the substack session token.

### Pipenv
```bash
git clone https://github.com/jwoglom/remarkable-substack
cd remarkable-substack
pipenv install
pipenv run python main.py
```

Running locally also needs the [rmapi-js](https://github.com/jwoglom/rmapi-js) CLI (v12+) on `PATH`, which requires Node 22 or newer:

```bash
npm install -g https://github.com/jwoglom/rmapi-js/releases/download/v12.0.0/jwoglom-rmapi-js-12.0.0.tgz
rmapi-js --version
```

This project invokes `rmapi-js` rather than `rmapi`, because the Go clients (`ddvk/rmapi`, `juruen/rmapi`) also install a binary named `rmapi` and the two are not flag-compatible. Set `RMAPI_BIN` to override the binary name.


## First-time setup
The first time you run remarkable-substack, you need to authenticate with both the ReMarkable Cloud and Substack.

### Authenticating with ReMarkable

Go to https://my.remarkable.com/device/browser/connect and log in with your existing account.
You will be provided an 8-letter verification code on this page.
Run the application with the additional argument `--remarkable-auth-token=XXXXXXXX`, substituting the code from this page.

That code is exchanged once for a device token, which does not expire and is stored mode 0600 in the config directory (`$RMAPI_CONFIG_DIR`, else `~/.config/rmapi-js`). A session token is cached alongside it and refreshed automatically, so `--remarkable-auth-token` is only needed once.

To run headless, supply an existing device token instead of registering: `export RMAPI_DEVICE_TOKEN="<token>"` (from `rmapi-js auth token --print-token`). It is a long-lived credential — keep it in a secret store or an environment variable, never committed and never baked into an image. The config directory still has to be writable, since the session token and hash cache are written there.

For the examples above, this would look like either:
```
docker run -v ~/.config/rmapi-js:/home/appuser/.config/rmapi-js -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.3.9 --remarkable-auth-token=XXXXXXXX
pipenv run python main.py --remarkable-auth-token=XXXXXXXX
```

### Authenticating with Substack

After authenticating with ReMarkable, you'll need to log in to substack. Open an incognito window in your browser and log in to substack.com. Request a login link via email, and then provide that URL as `--substack-login-url=https://XXXXX`


For the examples above, this would look like either:
```
docker run -v ~/.config/rmapi-js:/home/appuser/.config/rmapi-js -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.3.9 --substack-login-url=https://XXXXX
pipenv run python main.py --substack-login-url=https://XXXXX
```

## Configuration
You can tweak these additional parameters:

```
usage: main.py [-h] [--max-save-count MAX_SAVE_COUNT] [--max-fetch-count MAX_FETCH_COUNT] [--delete-already-read] [--delete-unread-after-hours DELETE_UNREAD_AFTER_HOURS] [--folder FOLDER] [--remarkable-auth-token REMARKABLE_AUTH_TOKEN]
               [--substack-login-url SUBSTACK_LOGIN_URL] [--config-folder CONFIG_FOLDER] [--tmp-folder TMP_FOLDER]

Writes recent Substack articles to reMarkable cloud

options:
  -h, --help            show this help message and exit
  --max-save-count MAX_SAVE_COUNT
                        Maximum number of articles to save on device
  --max-fetch-count MAX_FETCH_COUNT
                        Maximum number of articles to fetch from Substack
  --delete-already-read
                        Delete articles in reMarkable cloud which are already read
  --delete-unread-after-hours DELETE_UNREAD_AFTER_HOURS
                        If an article has not been opened for this many hours on the device and there are new articles to add, will delete. Set to -1 to disable, or 0 to always replace old articles.
  --delete-unread-always
                        Delete unread articles once they pass --delete-unread-after-hours, rather than only when a new article needs the space
  --wipe-folder         One-time cleanup: delete every document in --folder before syncing, then refill with the latest articles
  --folder FOLDER       Folder title to write to
  --remarkable-auth-token REMARKABLE_AUTH_TOKEN
                        For initial authentication with reMarkable: the 8-letter code from
                        https://my.remarkable.com/device/browser/connect
  --substack-login-url SUBSTACK_LOGIN_URL
                        For initial authentication with Substack: the URL from the email
                        received from Substack when entering your email on the login page
  --config-folder CONFIG_FOLDER
                        Configuration folder for remarkable-substack
  --tmp-folder TMP_FOLDER
                        Temporary storage folder for remarkable-substack
```

## Notes

* `--delete-already-read` decides what to delete from the document's last-read page (`lastOpenedPage`). That field has not yet been verified end-to-end against rmapi-js on a real device — confirm it tracks your reading position before relying on it. Note the deployed nomad job passes this flag.
* Unlike the Go client, which reported page 0 both for "never opened" and for "opened to the first page", rmapi-js omits the field entirely when a document has never been opened. `--delete-already-read` will not delete a document with no recorded page.
* Deletion moves documents to the reMarkable **trash**, which has to be emptied from a device or from my.remarkable.com.
* Documents are deleted by id, resolved from a listing of `--folder`, so nothing outside that folder is reachable.
* Without `--delete-unread-always`, an unread article past `--delete-unread-after-hours` is only a candidate: it is dropped when a newly fetched article needs its slot, and otherwise stays. With the flag, it is deleted on the first run after it expires whether or not there is anything to replace it.
* Age is measured from when this tool downloaded the article, which is tracked in `db_file.json` in `--config-folder`. An article the db has no record of is never expired, so losing that file leaves existing documents on the device to be cleaned up by hand.
* `--wipe-folder` empties `--folder` and clears `db_file.json`, so the same run re-downloads the newest `--max-save-count` articles from scratch. It is meant to be passed once, by hand, not left in a scheduled job.
