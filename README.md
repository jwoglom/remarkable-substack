# remarkable-substack

Syncs unread Substack posts onto your ReMarkable tablet.

## How to run

You can run either via Docker or locally with Python + pipenv.

### Docker
With `docker run`, use an invocation such as the following. Update the version number to the latest release.

```bash
docker run -v ~/.rmapi:/home/appuser/.rmapi -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.2.3
```

Note the volume-mounted `.rmapi` folder from your home directory which is used to store the long-running remarkable session token, and the `.config/remarkable-substack` folder which stores the substack session token.

### Pipenv
```bash
git clone https://github.com/jwoglom/remarkable-substack
cd remarkable-substack
pipenv install
pipenv run python3.py
```


## First-time setup
The first time you run remarkable-substack, you need to authenticate with both the ReMarkable Cloud and Substack.

### Authenticating with ReMarkable

Go to https://my.remarkable.com/device/desktop/connect and log in with your existing account.
You will be provided a verification code on this page.
Run the application with the additional argument `--remarkable-login-token=XXXXX`, substituting the token from this page.

For the examples above, this would look like either:
```
docker run -v ~/.rmapi:/home/appuser/.rmapi -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.2.3 --remarkable-login-token=XXXXX
pipenv run python3.py --remarkable-login-token=XXXXX
```

### Authenticating with Substack

After authenticating with ReMarkable, you'll need to log in to substack. Open an incognito window in your browser and log in to substack.com. Request a login link via email, and then provide that URL as `--substack-login-url=https://XXXXX`


For the examples above, this would look like either:
```
docker run -v ~/.rmapi:/home/appuser/.rmapi -v ~/.config/remarkable-substack:/home/appuser/.config/remarkable-substack  --rm -it ghcr.io/jwoglom/remarkable-substack/remarkable-substack:v0.2.3 --substack-login-url=https://XXXXX
pipenv run python3.py --substack-login-url=https://XXXXX
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
  --folder FOLDER       Folder title to write to
  --remarkable-auth-token REMARKABLE_AUTH_TOKEN
                        For initial authentication with reMarkable: device token
  --substack-login-url SUBSTACK_LOGIN_URL
                        For initial authentication with reMarkable: device token
  --config-folder CONFIG_FOLDER
                        Configuration folder for remarkable-substack
  --tmp-folder TMP_FOLDER
                        Temporary storage folder for remarkable-substack
```
