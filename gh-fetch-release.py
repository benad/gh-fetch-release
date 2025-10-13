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
        prog="gh-fetch-release",
        description=("Fetch and extract binary files from the latest "
                     "GitHub release of the given repository."),
        add_help=True,
        allow_abbrev=True,
        exit_on_error=True)
    parser.add_argument("--repo", type=str, required=True,
                        help="GitHub repository in the form owner/repo")
    parser.add_argument("--pattern", type=str, required=True,
                        help="Regex pattern to match the asset filename")
    parser.add_argument("--outdir", type=str, required=True,
                        help="Output directory to install the binary files.")
    parser.add_argument("--binfiles", type=str, required=True,
                        help=("Glob pattern to match the binary files to install "
                              "from the extracted files"))
    parser.add_argument("--downloaddir", type=str, required=False, default=None,
                        help=("Temporary download directory. If not given, a "
                              "temporary directory will be created and deleted."))
    parser.add_argument("--setexec", action="store_true", required=False, default=False,
                        help="Set executable permission on the installed binary files")
    parser.add_argument("--rename", type=str, required=False, default=None,
                        help=("Set the name of the installed binary file. "
                              "Only used if a single file is matched by --binfiles."))
    parser.add_argument("--token", type=str, required=False,
                        default=os.environ.get("GITHUB_TOKEN", None),
                        help=("GitHub token to use for authentication. "
                              "Can also be set via the GITHUB_TOKEN environment variable."))
    args = parser.parse_args()
    return vars(args)

def get_download_url(options) -> str | None:
    owner, repo = options['repo'].split('/')

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    token_headers = {}
    if options.get("token", None) is not None:
        print("Using GitHub token")
        # Validate token: GitHub tokens are usually alphanumeric with some dashes/underscores
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', options['token']):
            raise ValueError("Invalid GitHub token format.")
        token_headers["Authorization"] = f"Bearer {options['token']}"
    try:
        request = urllib.request.Request(
            api_url,
            headers={"User-Agent": "python", **token_headers}
        )
        with urllib.request.urlopen(request) as response:
            if response.status != 200:
                raise RuntimeError(("GitHub API request failed with status code:"
                                   f" {response.status} {response.reason}"))
            response_data = response.read().decode(encoding='utf-8')
    except urllib.error.URLError as e:
        print(f"Error fetching release info: {e}")
        return None
    response = json.loads(response_data)
    if 'assets' not in response:
        print("No assets found in the latest release.")
        return None
    for asset in response['assets']:
        if not ( 'name' in asset and 'browser_download_url' in asset ):
            continue
        print(f"Checking asset: {asset['name']} against pattern {options['pattern']}")
        if re.search(options['pattern'], asset['name']) is not None:
            return asset['browser_download_url']
    print('No matching asset found.')
    return None

def download_file(url: str, path: str) -> int:
    try:
        urllib.request.urlretrieve(url, path)
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Error downloading file: {e}")
        return 1

def extract_binfiles(download_filename: str, download_path: str, downloaddir: str) -> int:
    class Archive:
        def __init__(self, path: str):
            self.path = path
        @staticmethod
        def extension() -> str:
            return ''
        def extract(self, _outdir: str) -> int:
            return 1 # Not implemented

    # pylint: disable=possibly-unused-variable
    class ArchiveTarGz(Archive):
        @staticmethod
        def extension() -> str:
            return '.tar.gz'
        def extract(self, outdir: str) -> int:
            return subprocess.call(["tar", "-xzf", self.path, "-C", outdir])

    class ArchiveBz2(Archive):
        class TempChdir:
            def __init__(self, path):
                self.new_path = path
                self.old_path = os.getcwd()
            def __enter__(self):
                os.chdir(self.new_path)
            def __exit__(self, _exc_type, _exc_val, _exc_tb):
                os.chdir(self.old_path)
        @staticmethod
        def extension() -> str:
            return '.bz2'
        def extract(self, outdir: str) -> int:
            with self.TempChdir(outdir):
                return subprocess.call(["bzip2", "-d", self.path])

    class ArchiveTarBz2(Archive):
        @staticmethod
        def extension() -> str:
            return '.tar.bz2'
        def extract(self, outdir: str) -> int:
            return subprocess.call(["tar", "-xjf", self.path, "-C", outdir])

    class ArchiveZip(Archive):
        @staticmethod
        def extension() -> str:
            return '.zip'
        def extract(self, outdir: str) -> int:
            return subprocess.call(["unzip", "-o", self.path, "-d", outdir])

    class ArchiveTarZst(Archive):
        @staticmethod
        def extension() -> str:
            return '.tar.zst'
        def extract(self, outdir: str) -> int:
            return subprocess.call([
                "tar", "--use-compress-program=unzstd", "-xf", self.path,
                "-C", outdir
            ])
    # pylint: enable=possibly-unused-variable

    archive_classes = [
        obj for obj in locals().values()
        if isinstance(obj, type) and issubclass(obj, Archive) and obj is not Archive
    ]
    archive_classes.sort(key=lambda cls: -len(cls.extension()))

    archive_obj = None
    for cls in archive_classes:
        if download_filename.endswith(cls.extension()):
            archive_obj = cls(download_path)
            break

    if archive_obj is None:
        raise ValueError(f"Unsupported archive format: {download_filename}")

    return archive_obj.extract(downloaddir)

def run(options: dict) -> None:
    url = get_download_url(options)
    if url is None:
        raise RuntimeError("No matching asset found in the latest release.")

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
        res = download_file(url, download_path)

        if res != 0:
            raise RuntimeError(f"Failed to download {url}")

        print("Extracting to", downloaddir)
        res = extract_binfiles(download_filename, download_path, downloaddir)
        if res != 0:
            raise RuntimeError(f"Failed to extract {download_path} to {downloaddir}")

        matching_files = glob.glob(os.path.join(downloaddir, options['binfiles']))
        if len(matching_files) == 0:
            raise RuntimeError(
                f"Binary file {options['binfiles']} not found in the extracted files."
            )

        outdir = options["outdir"]
        if not os.path.exists(outdir):
            os.makedirs(outdir)

        for file in matching_files:
            outfilepath = os.path.join(outdir, os.path.basename(file))
            if len(matching_files) == 1 and options.get("rename", None) is not None:
                outfilepath = os.path.join(outdir, options["rename"])
            shutil.copyfile(file, outfilepath)
            if options.get("setexec", False):
                os.chmod(outfilepath, 0o755)
            print(f"Installed {file} as {outfilepath}")
    finally:
        if temporary_dir is not None:
            temporary_dir.cleanup()

if __name__ == "__main__":
    cli_options = get_cli_options()
    run(cli_options)
