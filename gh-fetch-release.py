#!/usr/bin/python3

# MIT License
# Copyright (c) 2025 Benoit Nadeau
# See LICENSE file for details.

# Fetch and extract binary files from the latest GitHub
# release of the given repository.

# pylint: disable=missing-class-docstring,missing-function-docstring,missing-module-docstring,invalid-name

import argparse
import glob
import json
import os
import os.path
import re
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error

def get_cli_options() -> dict:
    parser = argparse.ArgumentParser(
        prog='gh-fetch-release',
        description='Fetch and extract binary files from the latest GitHub release of the given repository.')
    parser.add_argument('--repo', type=str, required=True,
                        help='GitHub repository in the form owner/repo')
    parser.add_argument('--pattern', type=str, required=True,
                        help='Regex pattern to match the asset filename')
    parser.add_argument('--outdir', type=str, required=True,
                        help='Output directory to install the binary files.')
    parser.add_argument('--binfiles', type=str, required=True,
                        help='Glob pattern to match the binary files to install from the extracted files')
    parser.add_argument('--downloaddir', type=str, default=None,
                        help='Temporary download directory (if not given, a temporary directory will be created and deleted)')
    parser.add_argument('--setexec', action='store_true',
                        help='Set executable permission on the installed binary files')
    parser.add_argument('--rename', type=str, default=None,
                        help='Set the name of the installed binary file (only if a single file is matched by --binfiles)')
    parser.add_argument('--token', type=str, default=os.environ.get('GITHUB_TOKEN'),
                        help='GitHub token to use for authentication. Can also be set via the GITHUB_TOKEN environment variable.')
    parser.add_argument('--state-file', type=str, default=None,
                        help='JSON file to track installed versions and skip if they did not change')
    return vars(parser.parse_args())

def get_download_url(options) -> tuple[str | None, str | None]:
    owner, repo = options['repo'].split('/')
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {"User-Agent": "python"}
    if options.get("token"):
        print("Using GitHub token")
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', options['token']):
            raise ValueError("Invalid GitHub token format.")
        headers["Authorization"] = f"Bearer {options['token']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(api_url, headers=headers)) as response:
            if response.status != 200:
                raise RuntimeError("GitHub API request failed with status code:" +
                                   f" {response.status} {response.reason}")
            data = json.loads(response.read().decode())
    except urllib.error.URLError as e:
        print(f"Error fetching release info: {e}")
        return None, None
    tag_name = data.get('tag_name')
    for asset in data.get('assets', []):
        if 'name' not in asset or 'browser_download_url' not in asset:
            continue
        print(f"Checking asset: {asset['name']} against pattern {options['pattern']}")
        if re.search(options['pattern'], asset['name']):
            return asset['browser_download_url'], tag_name
    print('No matching asset found.')
    return None, tag_name

def download_file(url: str, path: str) -> int:
    try:
        urllib.request.urlretrieve(url, path)
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Error downloading file: {e}")
        return 1

def extract_binfiles(download_filename: str, download_path: str, downloaddir: str) -> int:
    extractors = [
        ('.tar.gz',  lambda p, d: subprocess.call(["tar", "-xzf", p, "-C", d])),
        ('.tar.bz2', lambda p, d: subprocess.call(["tar", "-xjf", p, "-C", d])),
        ('.tar.zst', lambda p, d: subprocess.call(["tar", "--use-compress-program=unzstd", "-xf", p, "-C", d])),
        ('.tbz',     lambda p, d: subprocess.call(["tar", "-xjf", p, "-C", d])),
        ('.zip',     lambda p, d: subprocess.call(["unzip", "-o", p, "-d", d])),
        ('.bz2',     lambda p, d: subprocess.call(["bzip2", "-d", p])),
    ]
    for ext, extractor in extractors:
        if download_filename.endswith(ext):
            return extractor(download_path, downloaddir)
    raise ValueError(f"Unsupported archive format: {download_filename}")

def run(options: dict) -> None:
    url, tag_name = get_download_url(options)
    if url is None:
        raise RuntimeError("No matching asset found in the latest release.")

    state_file = options.get("state_file")
    state = {}
    if state_file:
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
            except Exception as e:
                print(f"Warning: failed to read state file: {e}")
        if state.get(options['repo']) == tag_name:
            print(f"Version {tag_name} is already installed. Skipping.")
            return

    downloaddir = options.get("downloaddir", None)
    temporary_dir = None
    if downloaddir is None:
        temporary_dir = tempfile.TemporaryDirectory(delete=False)
        downloaddir = temporary_dir.name
    else:
        os.makedirs(downloaddir, exist_ok=True)

    print(f"Downloading {url} to {downloaddir}")

    try:
        download_filename = os.path.basename(url)
        download_path = os.path.join(downloaddir, download_filename)
        if download_file(url, download_path) != 0:
            raise RuntimeError(f"Failed to download {url}")

        print("Extracting to", downloaddir)
        if extract_binfiles(download_filename, download_path, downloaddir) != 0:
            raise RuntimeError(f"Failed to extract {download_path} to {downloaddir}")

        matching_files = glob.glob(os.path.join(downloaddir, options['binfiles']))
        if not matching_files:
            raise RuntimeError(
                f"Binary file {options['binfiles']} not found in the extracted files."
            )

        outdir = options["outdir"]
        os.makedirs(outdir, exist_ok=True)

        for file in matching_files:
            outname = options["rename"] if len(matching_files) == 1 and options.get("rename") else os.path.basename(file)
            outfilepath = os.path.join(outdir, outname)
            shutil.copyfile(file, outfilepath)
            if options.get("setexec"):
                os.chmod(outfilepath, 0o755)
            print(f"Installed {file} as {outfilepath}")

        if state_file:
            state[options['repo']] = tag_name
            try:
                with open(state_file, 'w') as f:
                    json.dump(state, f)
            except Exception as e:
                print(f"Warning: failed to write state file: {e}")
    finally:
        if temporary_dir is not None:
            temporary_dir.cleanup()

if __name__ == "__main__":
    run(get_cli_options())
