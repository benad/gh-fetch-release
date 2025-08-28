#!/usr/bin/env python3

# MIT License
# Copyright (c) 2025 Benoit Nadeau
# See LICENSE file for details.

# Fetch and extract binary files from the latest GitHub
# release of the given repository.

import argparse
import glob
import json
import os
import os.path
import re
import shutil
import tempfile
import subprocess

def get_cli_options() -> dict:
    parser = argparse.ArgumentParser(
                            prog='gh-fetch-release',
                            description='''Fetch and extract binary files from the latest GitHub
                            release of the given repository.''',
                            add_help=True,
                            allow_abbrev=True,
                            exit_on_error=True)
    parser.add_argument('--repo', type=str, required=True,
                        help='GitHub repository in the form owner/repo')
    parser.add_argument('--pattern', type=str, required=True,
                        help='Regex pattern to match the asset filename')
    parser.add_argument('--outdir', type=str, required=True,
                        help='Output directory to install the binary files.')
    parser.add_argument('--binfiles', type=str, required=True,
                        help='Glob pattern to match the binary files to install from the extracted files')
    parser.add_argument('--downloaddir', type=str, required=False, default=None,
                        help='''Temporary download directory (if not given, a temporary
                                directory will be created and deleted)''')
    parser.add_argument('--setexec', action='store_true', required=False, default=False,
                        help='Set executable permission on the installed binary files')
    parser.add_argument('--rename', type=str, required=False, default=None,
                        help='''Set the name of the installed binary file (only if a single file is
                                matched by --binfiles)''')
    args = parser.parse_args()
    return vars(args)

def get_download_url(options) -> str | None:
    owner, repo = options['repo'].split('/')

    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        response_data = subprocess.check_output(
            ["curl", "-sL", "-H", "User-Agent: python", api_url],
            text=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error fetching release info: {e}")
        return None
    response = json.loads(response_data)
    if 'assets' not in response:
        raise Exception("No assets found in the latest release.")
    for asset in response['assets']:
        if not ( 'name' in asset and 'browser_download_url' in asset ):
            continue
        print(f"Checking asset: {asset['name']} against pattern {options['pattern']}")
        if re.search(options['pattern'], asset['name']) is not None:
            return asset['browser_download_url']

def download_file(url: str, path: str) -> int:
    try:
        res = subprocess.call(["curl", "-L", "-o", path, url])
    except Exception as e:
        print(f"Error downloading file: {e}")
        res = 1
    return res

def extract_binfiles(download_filename: str, download_path: str, downloaddir: str) -> int:
    class Archive:
        def __init__(self, path: str):
            self.path = path

        def extract(self, outdir: str) -> int:
            return 1 # Not implemented

    class ArchiveTarGz(Archive):
        def extract(self, outdir: str) -> int:
            return os.system(f"tar -xzf {self.path} -C {outdir}")
    
    class ArchiveTarBz2(Archive):
        def extract(self, outdir: str) -> int:
            return os.system(f"tar -xjf {self.path} -C {outdir}")

    class ArchiveZip(Archive):
        def extract(self, outdir: str) -> int:
            return os.system(f"unzip -o {self.path} -d {outdir}")

    class ArchiveTarZst(Archive):
        def extract(self, outdir: str) -> int:
            return os.system(f"tar --use-compress-program=unzstd -xf {self.path} -C {outdir}")

    archive_classes = {
        '.tar.gz': ArchiveTarGz,
        '.tgz': ArchiveTarGz,
        '.tar.bz2': ArchiveTarBz2,
        '.tbz': ArchiveTarBz2,
        '.zip': ArchiveZip,
        '.tar.zst': ArchiveTarZst
    }

    archive_obj = None
    for ext, cls in archive_classes.items():
        if download_filename.endswith(ext):
            archive_obj = cls(download_path)
            break

    if archive_obj is None:
        raise Exception(f"Unsupported archive format: {download_filename}")

    return archive_obj.extract(downloaddir)

def run(options: dict) -> None:
    url = get_download_url(options)
    if url is None:
        raise Exception("No matching asset found in the latest release.")

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
            raise Exception(f"Failed to download {url}")

        print("Extracting to", downloaddir)
        res = extract_binfiles(download_filename, download_path, downloaddir)
        if res != 0:
            raise Exception(f"Failed to extract {download_path} to {downloaddir}")

        matching_files = glob.glob(os.path.join(downloaddir, options['binfiles']))
        if len(matching_files) == 0:
            raise Exception(f"Binary file {options['binfiles']} not found in the extracted files.")

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
    options = get_cli_options()
    run(options)