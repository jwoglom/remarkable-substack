"""Thin wrapper around the rmapi-js CLI.

https://github.com/jwoglom/rmapi-js

This replaces the older pairing of the rmapy Python library (used for auth) with
the Go rmapi binary (used for everything else). rmapi-js does both, so there is
no longer a shared ~/.rmapi file that two implementations have to agree on.

This file is intentionally identical across remarkable-newspaper-daily,
remarkable-mirror and remarkable-substack. Keep it that way: if you change it
here, copy it to the other two rather than letting them drift.
"""

import json
import os
import subprocess

# rmapi-js installs both `rmapi` and `rmapi-js`. Default to `rmapi-js` because
# the Go clients (ddvk/rmapi, juruen/rmapi) also install a binary called
# `rmapi`, and a machine or image part-way through this migration may have both
# on PATH. Picking the wrong one fails in confusing ways: the flags differ
# (`-ni` is gone) and `stat` returns a different shape.
BIN = os.environ.get('RMAPI_BIN', 'rmapi-js')

# The registration URL changed: rmapy pointed at /device/desktop/connect.
REGISTER_URL = 'https://my.remarkable.com/device/browser/connect'

# Guard against an older rmapi-js, or against `rmapi` resolving to a Go client.
MIN_MAJOR_VERSION = 12

# Exit codes, from src/cli/main.ts.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 3
EXIT_AUTH = 4
EXIT_VALIDATION = 5
EXIT_STALE = 6


class RemarkableError(RuntimeError):
    """An rmapi-js invocation failed."""


class RemarkableAuthError(RemarkableError):
    """Not authenticated, or the device token was rejected (exit 4).

    Callers generally want to trigger a relogin notification on this.
    """


class RemarkableAmbiguousError(RemarkableError):
    """A target matched more than one item (exit 3).

    reMarkable allows duplicate visibleNames in a folder, so addressing by path
    is ambiguous. Address by id to avoid this.
    """


def escape_segment(name):
    """Escape a single path component for use in a target path.

    Forward slashes in a visibleName are written as \\/ so they aren't read as
    a path separator.
    """
    return name.replace('\\', '\\\\').replace('/', '\\/')


def join_path(*segments):
    """Build a target path out of individual visibleNames."""
    return '/'.join(escape_segment(s) for s in segments if s)


def target_for(entry):
    """Return an unambiguous `id:` target for an entry dict (or a raw id)."""
    if isinstance(entry, dict):
        entry = entry['id']
    if entry.startswith(('id:', 'path:', 'hash:')):
        return entry
    return 'id:' + entry


class Remarkable:
    def __init__(self, check_version=True):
        if check_version:
            self.check_rmapi_binary()

    def _run(self, *args, **kwargs):
        """Run rmapi-js and return its parsed --json output.

        Raises a typed exception based on the exit code. Errors are reported by
        the CLI on stderr as {"error": ..., "code": ...} when --json is passed.
        """
        json_out = kwargs.pop('json_out', True)
        retry_stale = kwargs.pop('retry_stale', True)
        if kwargs:
            raise TypeError('unexpected kwargs: %s' % list(kwargs))

        cmd = [BIN] + [str(a) for a in args]
        if json_out:
            cmd.append('--json')

        env = dict(os.environ)
        env['NO_COLOR'] = '1'

        try:
            out = subprocess.run(cmd, capture_output=True, env=env)
        except FileNotFoundError:
            raise RemarkableError(
                "Couldn't find the '%s' binary. Install it with: "
                'npm install -g https://github.com/jwoglom/rmapi-js/releases/'
                'download/v12.0.0/jwoglom-rmapi-js-12.0.0.tgz' % BIN)

        if out.returncode == EXIT_OK:
            if not json_out:
                return out.stdout.decode().strip()
            body = out.stdout.decode().strip()
            return json.loads(body) if body else None

        message = self._error_message(out)

        # The root generation moved under us, i.e. something else wrote to the
        # account while we were working. Retrying with a fresh root hash is the
        # documented fix.
        if out.returncode == EXIT_STALE and retry_stale:
            return self._run(*args, '--refresh', json_out=json_out,
                             retry_stale=False)

        if out.returncode == EXIT_AUTH:
            raise RemarkableAuthError(message)
        if out.returncode == EXIT_NOT_FOUND:
            # Exit 3 covers both "not found" and "matched N entries".
            if 'entries on reMarkable' in message:
                raise RemarkableAmbiguousError(message)
            raise FileNotFoundError(message)
        raise RemarkableError('%s (exit %d)' % (message, out.returncode))

    def _error_message(self, out):
        stderr = out.stderr.decode().strip()
        try:
            return str(json.loads(stderr)['error'])
        except Exception:
            return stderr or out.stdout.decode().strip() or 'unknown error'

    def check_rmapi_binary(self):
        """Verify the binary exists and is a new enough rmapi-js."""
        info = self._run('--version')
        version = str((info or {}).get('version', ''))
        try:
            major = int(version.split('.')[0])
        except ValueError:
            raise RemarkableError(
                "'%s' reported an unrecognized version %r -- is it rmapi-js?"
                % (BIN, version))
        if major < MIN_MAJOR_VERSION:
            raise RemarkableError(
                "'%s' is version %s, but >=%d.0.0 is required"
                % (BIN, version, MIN_MAJOR_VERSION))
        return version

    def auth_if_needed(self, code):
        """Register with a one-time code if there is no device token yet."""
        if self.is_auth():
            return True

        print('Not authenticated')
        if code:
            # Deliberately not logged: this is a credential.
            print('Registering with the supplied code')
            self.register_device(code)
            if self.is_auth():
                print('Success!')
                return True
            print('Error -- still not authenticated')
            exit(1)

        print('Please authenticate by passing a registration code')
        print('Receive an 8-letter code at %s' % REGISTER_URL)
        print('Alternatively, set RMAPI_DEVICE_TOKEN to an existing token')
        exit(1)

    def is_auth(self):
        """True if a device token is available.

        Note this does not contact the server: it reports whether a token
        exists, not whether it still works. Use verify_auth() for that, or
        treat RemarkableAuthError from any later call as "relogin needed".
        """
        return bool(self._run('auth', 'status')['registered'])

    def auth_source(self):
        """Where the device token came from: 'env' or 'config'."""
        return self._run('auth', 'status').get('source')

    def verify_auth(self):
        """Confirm the token actually works, with a cheap authenticated read."""
        self._run('ls', '/', '--refresh')
        return True

    def register_device(self, code):
        return self._run('auth', 'register', code)

    def ls(self, folder='/', ftype=None):
        """List a folder. Returns entry dicts.

        Each entry has: id, hash, visibleName, lastModified, parent, pinned,
        type ('DocumentType' or 'CollectionType'), plus lastOpened on documents.
        Raises FileNotFoundError if the folder doesn't exist.
        """
        entries = self._run('ls', folder) or []
        if ftype:
            entries = [e for e in entries if e['type'] == ftype]
        return entries

    def documents(self, folder='/'):
        """List only the documents in a folder (not subfolders)."""
        return self.ls(folder, ftype='DocumentType')

    def document_names(self, folder='/'):
        """Visible names of the documents in a folder.

        Note these have no file extension: an uploaded `foo.pdf` is named `foo`.
        """
        return [e['visibleName'] for e in self.documents(folder)]

    def mkdir(self, folder, parents=True):
        """Create a folder. Idempotent when parents=True."""
        args = ['mkdir', folder]
        if parents:
            args.append('--parents')
        return self._run(*args)

    def put(self, local_path, folder=None, parent_id=None):
        """Upload a PDF or EPUB.

        The resulting visibleName is the basename without its extension.
        """
        args = ['put', local_path]
        if parent_id:
            args += ['--parent', parent_id]
        elif folder:
            args.append(folder)
        return self._run(*args)

    def stat(self, target):
        """Return {entry, metadata, content} for an item."""
        return self._run('stat', target_for(target))

    def current_page(self, target):
        """0-based last read page, or None if the item was never opened.

        Accepts a target or an already-fetched stat() result. lastOpenedPage
        lives on metadata in practice; content is checked as a fallback. It is
        absent (not 0) on a document that has never been opened, so None and 0
        are distinguishable here -- unlike the Go client's CurrentPage, which
        reported 0 for both.
        """
        stat = target if isinstance(target, dict) and 'metadata' in target \
            else self.stat(target)
        for section in ('metadata', 'content'):
            page = stat.get(section, {}).get('lastOpenedPage')
            if page is not None:
                return int(page)
        return None

    def rm(self, target):
        """Move an item to the reMarkable trash.

        Note this is not a permanent delete -- the trash has to be emptied from
        a device or from my.remarkable.com.
        """
        return self._run('rm', target_for(target))
