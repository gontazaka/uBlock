#!/usr/bin/env python3
"""
Submit or poll self-hosted Firefox add-on signing on AMO, replace the raw XPI on
GitHub Releases with the signed XPI, and generate dist/firefox/updates.json.

Modes:
  1. Legacy positional invocation (backward compatible with main.yml):
       publish-signed-beta.py <version> [xpi_url]
     Equivalent to: --mode submit --version <version> --wait-minutes 5
  2. Explicit submit mode (Phase 1, run on tag creation):
       publish-signed-beta.py --mode submit --version <version> [--wait-minutes 5]
  3. Poll mode (Phase 2, run on schedule / workflow_dispatch):
       publish-signed-beta.py --mode poll [--version <version>]
"""

import argparse
import datetime
import functools
import json
import os
import re
import sys
import tempfile
import time
import zipfile

import jwt
import requests

print = functools.partial(print, flush=True)

EXTENSION_ID = 'ublock@gontazaka'
GITHUB_OWNER = 'gontazaka'
GITHUB_REPO = 'uBlock'
AMO_BASE_URL = 'https://addons.mozilla.org/api/v5'
GITHUB_API_BASE = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}'
UPDATE_URL = f'https://{GITHUB_OWNER}.github.io/{GITHUB_REPO}/firefox/updates.json'
VERSION_RE = re.compile(r'^(\d+\.\d+\.\d+)(\.\d+)?$')
RAW_XPI_RE = re.compile(r'^uBlock[^_]*_(\d+\.\d+\.\d+(?:\.\d+)?)\.firefox\.xpi$')
SIGNED_XPI_RE = re.compile(r'^uBlock[^_]*_(\d+\.\d+\.\d+(?:\.\d+)?)\.firefox\.signed\.xpi$')


def find_projdir():
    projdir = os.path.split(os.path.abspath(__file__))[0]
    while not os.path.isdir(os.path.join(projdir, '.git')):
        parent = os.path.normpath(os.path.join(projdir, '..'))
        if parent == projdir:
            break
        projdir = parent
    return projdir


def parse_version_tuple(v_str):
    if not v_str:
        return ()
    m = VERSION_RE.match(v_str.strip())
    if not m:
        return ()
    return tuple(int(x) for x in v_str.strip().split('.'))


def raw_xpi_name(version):
    return f'uBlock._{version}.firefox.xpi'


def signed_xpi_name(version):
    return f'uBlock._{version}.firefox.signed.xpi'


def set_github_output(key, value):
    out_file = os.environ.get('GITHUB_OUTPUT')
    if out_file:
        with open(out_file, 'a', encoding='utf-8') as f:
            f.write(f'{key}={value}\n')


class SecretManager:
    def __init__(self):
        self._cache = {}

    def get(self, label, env_name):
        key = env_name.upper()
        if key not in self._cache:
            val = os.environ.get(key, '').strip()
            if not val:
                print(f'Token error: {env_name}')
                sys.exit(1)
            print(f' ✔ {label}')
            self._cache[key] = val
        return self._cache[key]

    def github_headers(self, accept=None):
        token = self.get('Github token', 'github_token')
        headers = {'Authorization': f'token {token}'}
        if accept:
            headers['Accept'] = accept
        return headers

    def amo_headers(self):
        api_key = self.get('AMO API key', 'amo_api_key')
        secret = self.get('AMO API secret', 'amo_secret')
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            'iss': api_key,
            'jti': os.urandom(8).hex(),
            'iat': now,
            'exp': now + datetime.timedelta(seconds=30),
        }
        encoded = jwt.encode(payload, secret)
        if not isinstance(encoded, str):
            encoded = encoded.decode('utf-8')
        return {'Authorization': f'JWT {encoded}'}


def get_release_by_tag(secrets, tag_version):
    print(f'Downloading release info for {tag_version} from GitHub...')
    url = f'{GITHUB_API_BASE}/releases/tags/{tag_version}'
    r = requests.get(url, headers=secrets.github_headers(), timeout=30)
    if r.status_code != 200:
        print(f'Error: Release {tag_version} not found: {r.status_code}')
        sys.exit(1)
    return r.json()


def list_recent_releases(secrets, per_page=15):
    url = f'{GITHUB_API_BASE}/releases?per_page={per_page}'
    r = requests.get(url, headers=secrets.github_headers(), timeout=30)
    if r.status_code != 200:
        print(f'Error: Failed to list releases: {r.status_code}')
        sys.exit(1)
    return r.json()


def inspect_release_assets(release_info, tag_version):
    raw_asset = None
    signed_asset = None
    expected_raw = raw_xpi_name(tag_version)
    expected_signed = signed_xpi_name(tag_version)
    for asset in release_info.get('assets', []):
        name = asset.get('name', '')
        if name == expected_raw or RAW_XPI_RE.match(name):
            raw_asset = asset
        elif name == expected_signed or SIGNED_XPI_RE.match(name):
            signed_asset = asset
    return raw_asset, signed_asset


def select_pending_releases(releases, max_age_days=30):
    """Return releases (oldest first) that still have a raw .firefox.xpi, are
    newer than the highest version already signed, and were created within
    max_age_days."""
    highest_signed = ()
    for rel in releases:
        if rel.get('draft'):
            continue
        tag = (rel.get('tag_name') or '').strip()
        v_tuple = parse_version_tuple(tag)
        if not v_tuple:
            continue
        _, signed_asset = inspect_release_assets(rel, tag)
        if signed_asset and v_tuple > highest_signed:
            highest_signed = v_tuple

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=max_age_days)
    pending = []
    for rel in releases:
        if rel.get('draft'):
            continue
        tag = (rel.get('tag_name') or '').strip()
        v_tuple = parse_version_tuple(tag)
        if not v_tuple:
            continue
        if highest_signed and v_tuple <= highest_signed:
            continue
        created_str = rel.get('created_at')
        if created_str:
            try:
                created_dt = datetime.datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                if created_dt < cutoff:
                    continue
            except ValueError:
                pass
        raw_asset, signed_asset = inspect_release_assets(rel, tag)
        if raw_asset and not signed_asset:
            pending.append((v_tuple, rel))

    pending.sort(key=lambda item: item[0])
    return [rel for _, rel in pending]


def download_raw_and_inject_update_url(secrets, raw_asset, tmpdir):
    raw_path = os.path.join(tmpdir, raw_asset['name'])
    unsigned_path = os.path.join(tmpdir, 'uBlock..firefox.unsigned.xpi')
    print(f"Downloading raw xpi package ({raw_asset['name']}) from GitHub...")
    r = requests.get(
        raw_asset['url'],
        headers=secrets.github_headers(accept='application/octet-stream'),
        timeout=(30.0, 300.0),
    )
    if r.status_code != 200:
        print(f'Error: Downloading raw package failed -- server error {r.status_code}')
        sys.exit(1)
    with open(raw_path, 'wb') as f:
        f.write(r.content)

    print('Converting raw xpi package into self-hosted xpi package...')
    with zipfile.ZipFile(raw_path, 'r') as zipin:
        with zipfile.ZipFile(unsigned_path, 'w') as zipout:
            for item in zipin.infolist():
                data = zipin.read(item.filename)
                if item.filename == 'manifest.json':
                    manifest = json.loads(data.decode('utf-8'))
                    manifest['browser_specific_settings']['gecko']['update_url'] = UPDATE_URL
                    data = json.dumps(manifest, indent=2, separators=(',', ': '), sort_keys=True).encode('utf-8')
                zipout.writestr(item, data, compresslevel=9)
    return unsigned_path


def amo_lookup_version(secrets, ext_version):
    """Look up an existing AMO version object for ext_version.
    Returns the version dict if found, or None if not found (404)."""
    # 1. Direct version detail lookup (prefix with 'v' per AMO docs)
    for ver_key in (f'v{ext_version}', ext_version):
        detail_url = f'{AMO_BASE_URL}/addons/addon/{EXTENSION_ID}/versions/{ver_key}/'
        r = requests.get(detail_url, headers=secrets.amo_headers(), timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get('version') == ext_version:
                return data
        elif r.status_code not in (404,):
            print(f'Warning: AMO version detail ({ver_key}) returned {r.status_code}')

    # 2. Fallback: versions list with filter=all_with_unlisted
    list_url = f'{AMO_BASE_URL}/addons/addon/{EXTENSION_ID}/versions/?filter=all_with_unlisted&page_size=25'
    r = requests.get(list_url, headers=secrets.amo_headers(), timeout=30)
    if r.status_code == 200:
        for item in r.json().get('results', []):
            if item.get('version') == ext_version:
                return item

    # 3. Fallback: addon detail latest_unlisted_version
    addon_url = f'{AMO_BASE_URL}/addons/addon/{EXTENSION_ID}/'
    r = requests.get(addon_url, headers=secrets.amo_headers(), timeout=30)
    if r.status_code == 200:
        latest = r.json().get('latest_unlisted_version') or {}
        if latest.get('version') == ext_version:
            return latest

    return None


def amo_submit_new_version(secrets, unsigned_xpi_filepath, ext_version, validation_timeout_sec=600, poll_interval=15):
    """Upload unsigned XPI to AMO, wait for validation, and create the version."""
    print('Submitting package to AMO to be validated...')
    upload_create_url = f'{AMO_BASE_URL}/addons/upload/'
    with open(unsigned_xpi_filepath, 'rb') as f:
        r = requests.post(
            upload_create_url,
            headers=secrets.amo_headers(),
            data={'channel': 'unlisted'},
            files={'upload': f},
            timeout=(30.0, 600.0),
        )
    if r.status_code != 201:
        print(f'Error: Uploading package failed -- server error {r.status_code}')
        print(r.text)
        sys.exit(1)
    upload_uuid = r.json()['uuid']
    print(f'Upload created (uuid={upload_uuid}). Waiting for AMO validation...')

    upload_detail_url = f'{AMO_BASE_URL}/addons/upload/{upload_uuid}/'
    deadline = time.time() + validation_timeout_sec
    while True:
        time.sleep(poll_interval)
        print('🦊', end='', flush=True)
        r = requests.get(upload_detail_url, headers=secrets.amo_headers(), timeout=30)
        if r.status_code != 200:
            print(f'\nError: AMO validation check failed -- server error {r.status_code}')
            print(r.text)
            sys.exit(1)
        detail = r.json()
        if not detail.get('processed'):
            if time.time() >= deadline:
                print('\nError: AMO validation timed out')
                sys.exit(1)
            continue
        if not detail.get('valid'):
            print('\nError: AMO validation failed')
            print(json.dumps(detail.get('validation'), indent=2))
            sys.exit(1)
        print('\nPackage successfully validated.')
        break

    print(f'Creating new unlisted version {ext_version} on AMO...')
    version_create_url = f'{AMO_BASE_URL}/addons/addon/{EXTENSION_ID}/versions/'
    r = requests.post(
        version_create_url,
        headers=secrets.amo_headers(),
        json={'upload': upload_uuid},
        timeout=(30.0, 600.0),
    )
    if r.status_code == 201:
        print('New version successfully created on AMO.')
        return r.json()
    if r.status_code == 409 or 'already exists' in r.text.lower():
        print(f'Version {ext_version} already exists on AMO; reusing existing submission.')
        existing = amo_lookup_version(secrets, ext_version)
        if existing:
            return existing
    print(f'Error: Creating new version failed -- server error {r.status_code}')
    print(r.text)
    sys.exit(1)


def inspect_amo_version_status(version_obj):
    """Return (status, download_url) where status is 'public', 'disabled', or 'unreviewed'."""
    if not version_obj:
        return ('missing', None)
    file_info = version_obj.get('file') or {}
    status = file_info.get('status') or 'unreviewed'
    download_url = file_info.get('url')
    if version_obj.get('is_disabled') or status == 'disabled':
        return ('disabled', download_url)
    if status == 'public':
        return ('public', download_url)
    return ('unreviewed', download_url)


def verify_signed_xpi(signed_xpi_filepath, expected_version):
    """Verify the downloaded signed XPI is a valid zip containing Mozilla's
    signature and the expected self-hosted manifest metadata."""
    try:
        with zipfile.ZipFile(signed_xpi_filepath, 'r') as zf:
            names = set(zf.namelist())
            if 'META-INF/mozilla.rsa' not in names:
                print('Error: Downloaded XPI does not contain META-INF/mozilla.rsa')
                sys.exit(1)
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    except Exception as e:
        print(f'Error: Downloaded XPI is not a valid signed archive: {e}')
        sys.exit(1)

    gecko = manifest.get('browser_specific_settings', {}).get('gecko', {})
    if gecko.get('id') != EXTENSION_ID:
        print(f"Error: Signed XPI gecko.id mismatch: {gecko.get('id')}")
        sys.exit(1)
    if manifest.get('version') != expected_version:
        print(f"Error: Signed XPI version mismatch: {manifest.get('version')} != {expected_version}")
        sys.exit(1)
    if gecko.get('update_url') != UPDATE_URL:
        print(f"Error: Signed XPI update_url mismatch: {gecko.get('update_url')}")
        sys.exit(1)
    strict_min = gecko.get('strict_min_version') or '115.0'
    return strict_min


def should_write_updates_json(tag_version, current_updates_json_path):
    if not current_updates_json_path or not os.path.isfile(current_updates_json_path):
        return True
    try:
        with open(current_updates_json_path, encoding='utf-8') as f:
            cur_data = json.load(f)
        cur_ver = (
            cur_data.get('addons', {})
            .get(EXTENSION_ID, {})
            .get('updates', [{}])[0]
            .get('version', '')
        )
        cur_tuple = parse_version_tuple(cur_ver)
        new_tuple = parse_version_tuple(tag_version)
        if cur_tuple and new_tuple and new_tuple < cur_tuple:
            print(
                f'Skipping updates.json overwrite: signed version {tag_version} '
                f'is older than current {cur_ver}'
            )
            return False
    except Exception as e:
        print(f'Warning: Could not read {current_updates_json_path}: {e}')
    return True


def write_updates_json(projdir, tag_version, browser_download_url, strict_min_version, current_updates_json_path=None):
    updates_json_filepath = os.path.join(projdir, 'dist', 'firefox', 'updates.json')
    template_filepath = os.path.join(projdir, 'dist', 'firefox', 'updates.template.json')
    with open(template_filepath, encoding='utf-8') as f:
        updates_json = json.load(f)
    update_entry = updates_json['addons'][EXTENSION_ID]['updates'][0]
    update_entry['version'] = tag_version
    update_entry['update_link'] = browser_download_url
    update_entry.setdefault('browser_specific_settings', {}).setdefault('gecko', {})[
        'strict_min_version'
    ] = strict_min_version
    serialized = json.dumps(updates_json, indent=2, separators=(',', ': '), sort_keys=True) + '\n'
    with open(updates_json_filepath, 'w', encoding='utf-8') as f:
        f.write(serialized)
    if current_updates_json_path:
        parent_dir = os.path.dirname(os.path.abspath(current_updates_json_path))
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(current_updates_json_path, 'w', encoding='utf-8') as f:
            f.write(serialized)
    print(f'Updated {updates_json_filepath} for version {tag_version}.')


def backfill_updates_json_from_signed_release(secrets, releases, projdir, current_updates_json_path):
    """If current_updates_json_path is missing (e.g. wiped by a prior orphan deploy),
    restore updates.json from the highest release that already has a signed XPI."""
    best = None
    for rel in releases:
        if rel.get('draft'):
            continue
        tag = (rel.get('tag_name') or '').strip()
        v_tuple = parse_version_tuple(tag)
        if not v_tuple:
            continue
        _, signed_asset = inspect_release_assets(rel, tag)
        if signed_asset and (best is None or v_tuple > best[0]):
            best = (v_tuple, tag, signed_asset)
    if not best:
        return False

    _, tag_version, signed_asset = best
    print(f'Restoring missing updates.json from latest signed release {tag_version}...')
    with tempfile.TemporaryDirectory() as tmpdir:
        signed_filepath = os.path.join(tmpdir, signed_asset['name'])
        r = requests.get(
            signed_asset['url'],
            headers=secrets.github_headers(accept='application/octet-stream'),
            timeout=(30.0, 300.0),
        )
        if r.status_code != 200:
            print(f'Warning: Failed to download {signed_asset["name"]} for backfill ({r.status_code})')
            return False
        with open(signed_filepath, 'wb') as f:
            f.write(r.content)
        strict_min_version = verify_signed_xpi(signed_filepath, tag_version)
    write_updates_json(
        projdir=projdir,
        tag_version=tag_version,
        browser_download_url=signed_asset['browser_download_url'],
        strict_min_version=strict_min_version,
        current_updates_json_path=current_updates_json_path,
    )
    return True


def download_and_publish_signed_xpi(
    secrets,
    download_url,
    release_info,
    raw_asset,
    signed_asset,
    tag_version,
    tmpdir,
    projdir,
    current_updates_json_path=None,
):
    signed_filename = signed_xpi_name(tag_version)
    signed_filepath = os.path.join(tmpdir, signed_filename)

    print('Downloading signed self-hosted xpi package from AMO...')
    r = requests.get(download_url, headers=secrets.amo_headers(), timeout=(30.0, 300.0))
    if r.status_code != 200:
        print(f'Error: Download signed package failed -- server error {r.status_code}')
        print(r.text)
        sys.exit(1)
    with open(signed_filepath, 'wb') as f:
        f.write(r.content)
    strict_min_version = verify_signed_xpi(signed_filepath, tag_version)
    print(f'Signed self-hosted xpi package verified (strict_min_version={strict_min_version}).')

    # Upload signed package to GitHub Release BEFORE deleting raw package
    if signed_asset:
        print(f'Signed asset {signed_filename} already exists on release; reusing.')
        browser_download_url = signed_asset['browser_download_url']
    else:
        print(f'Uploading {signed_filename} to GitHub release {tag_version}...')
        upload_url = release_info['upload_url'].replace('{?name,label}', f'?name={signed_filename}')
        headers = secrets.github_headers()
        headers['Content-Type'] = 'application/zip'
        with open(signed_filepath, 'rb') as f:
            r = requests.post(upload_url, headers=headers, data=f.read(), timeout=(30.0, 300.0))
        if r.status_code != 201:
            print(f'Error: Upload signed package failed -- server error: {r.status_code}')
            print(r.text)
            sys.exit(1)
        browser_download_url = r.json()['browser_download_url']
        print(f'Uploaded signed package: {browser_download_url}')

    # Remove raw unsigned package from GitHub Release now that signed asset is safe
    if raw_asset:
        print(f"Removing raw xpi package ({raw_asset['name']}) from GitHub release...")
        r = requests.delete(raw_asset['url'], headers=secrets.github_headers(), timeout=30)
        if r.status_code != 204:
            print(f'Warning: Deletion of raw package returned status {r.status_code}')

    # Update dist/firefox/updates.json only if tag_version >= current updates.json version
    should_write_updates = should_write_updates_json(tag_version, current_updates_json_path)
    if should_write_updates:
        write_updates_json(
            projdir=projdir,
            tag_version=tag_version,
            browser_download_url=browser_download_url,
            strict_min_version=strict_min_version,
            current_updates_json_path=current_updates_json_path,
        )

    return should_write_updates


def process_single_release(
    secrets,
    release_info,
    projdir,
    wait_minutes=5,
    poll_interval=30,
    current_updates_json_path=None,
):
    """Process one release: submit to AMO if needed, poll up to wait_minutes,
    and if signed, replace release asset and update updates.json.
    Returns True if updates.json was updated."""
    tag_version = (release_info.get('tag_name') or '').strip()
    if not parse_version_tuple(tag_version):
        print(f'Error: Invalid version string: {tag_version}')
        sys.exit(1)

    raw_asset, signed_asset = inspect_release_assets(release_info, tag_version)
    if signed_asset and not raw_asset:
        print(f'Release {tag_version} already has signed package {signed_asset["name"]}.')
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        version_obj = amo_lookup_version(secrets, tag_version)
        if version_obj is None:
            if not raw_asset:
                print(f'Error: Release {tag_version} has neither AMO submission nor raw XPI asset.')
                sys.exit(1)
            unsigned_path = download_raw_and_inject_update_url(secrets, raw_asset, tmpdir)
            version_obj = amo_submit_new_version(secrets, unsigned_path, tag_version)
        else:
            print(f'Found existing AMO submission for version {tag_version}.')

        status, download_url = inspect_amo_version_status(version_obj)
        deadline = time.time() + max(0, wait_minutes) * 60
        while status == 'unreviewed' and time.time() < deadline:
            time.sleep(poll_interval)
            print('🦊', end='', flush=True)
            version_id = version_obj.get('id')
            if version_id:
                detail_url = f'{AMO_BASE_URL}/addons/addon/{EXTENSION_ID}/versions/{version_id}/'
                r = requests.get(detail_url, headers=secrets.amo_headers(), timeout=30)
                if r.status_code == 200:
                    version_obj = r.json()
                else:
                    version_obj = amo_lookup_version(secrets, tag_version) or version_obj
            else:
                version_obj = amo_lookup_version(secrets, tag_version) or version_obj
            status, download_url = inspect_amo_version_status(version_obj)

        if status == 'disabled':
            print(f'\nError: AMO version {tag_version} is disabled or rejected.')
            print(json.dumps(version_obj, indent=2))
            sys.exit(1)

        if status != 'public':
            print(
                f'\nAMO signing for {tag_version} is still pending review (status={status}). '
                'Will complete asynchronously on a subsequent poll run.'
            )
            return False

        if not download_url:
            print(f'\nError: AMO version {tag_version} is public but has no download URL.')
            print(json.dumps(version_obj, indent=2))
            sys.exit(1)

        print(f'\nSelf-hosted xpi package for {tag_version} is signed on AMO.')
        return download_and_publish_signed_xpi(
            secrets=secrets,
            download_url=download_url,
            release_info=release_info,
            raw_asset=raw_asset,
            signed_asset=signed_asset,
            tag_version=tag_version,
            tmpdir=tmpdir,
            projdir=projdir,
            current_updates_json_path=current_updates_json_path,
        )


def parse_args(argv, projdir):
    # Support legacy positional call: publish-signed-beta.py <version> [xpi_url]
    if argv and not argv[0].startswith('-'):
        ap = argparse.ArgumentParser()
        ap.add_argument('version')
        ap.add_argument('xpi_url', nargs='?', default='')
        ns = ap.parse_args(argv)
        return argparse.Namespace(
            mode='submit',
            version=ns.version.strip(),
            wait_minutes=5,
            poll_interval=30,
            max_age_days=30,
            current_updates_json=None,
        )

    ap = argparse.ArgumentParser(description='Submit or poll AMO signing for uBlock 🦆.')
    ap.add_argument('--mode', choices=('submit', 'poll'), default='submit')
    ap.add_argument('--version', default='', help='Target release tag version (e.g. 1.76.2.0)')
    ap.add_argument('--wait-minutes', type=float, default=None)
    ap.add_argument('--poll-interval', type=int, default=30)
    ap.add_argument('--max-age-days', type=int, default=30)
    ap.add_argument('--current-updates-json', default=None)
    ns = ap.parse_args(argv)

    if ns.wait_minutes is None:
        ns.wait_minutes = 5 if ns.mode == 'submit' else 0
    if ns.mode == 'submit' and not ns.version:
        version_filepath = os.path.join(projdir, 'dist', 'versiongz')
        if os.path.isfile(version_filepath):
            with open(version_filepath, encoding='utf-8') as f:
                ns.version = f.read().strip()
    ns.version = ns.version.strip()
    return ns


def main(argv=None):
    projdir = find_projdir()
    args = parse_args(sys.argv[1:] if argv is None else argv, projdir)
    secrets = SecretManager()

    updated_any = False
    if args.mode == 'submit':
        if not parse_version_tuple(args.version):
            print(f'Error: Invalid version string: {args.version}')
            sys.exit(1)
        rel = get_release_by_tag(secrets, args.version)
        updated_any = process_single_release(
            secrets=secrets,
            release_info=rel,
            projdir=projdir,
            wait_minutes=args.wait_minutes,
            poll_interval=args.poll_interval,
            current_updates_json_path=args.current_updates_json,
        )
    else:
        releases = None
        if args.version:
            pending = [get_release_by_tag(secrets, args.version)]
        else:
            releases = list_recent_releases(secrets, per_page=15)
            pending = select_pending_releases(releases, max_age_days=args.max_age_days)
        if not pending:
            print('No pending unsigned Firefox releases found.')
        for rel in pending:
            tag = rel.get('tag_name', '')
            print(f'Checking pending Firefox release {tag}...')
            if process_single_release(
                secrets=secrets,
                release_info=rel,
                projdir=projdir,
                wait_minutes=args.wait_minutes,
                poll_interval=args.poll_interval,
                current_updates_json_path=args.current_updates_json,
            ):
                updated_any = True

        # If meta/firefox/updates.json is missing (e.g. wiped by an earlier release run),
        # restore it from the latest already-signed release while waiting for pending AMO review.
        if (
            not updated_any
            and args.current_updates_json
            and not os.path.isfile(args.current_updates_json)
        ):
            if releases is None:
                releases = list_recent_releases(secrets, per_page=15)
            if backfill_updates_json_from_signed_release(
                secrets=secrets,
                releases=releases,
                projdir=projdir,
                current_updates_json_path=args.current_updates_json,
            ):
                updated_any = True

    set_github_output('updated', 'true' if updated_any else 'false')
    if updated_any:
        print('🤘 All done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

