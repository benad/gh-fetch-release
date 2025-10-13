# gh-fetch-release

## Usage

```
python3 gh-fetch-release.py [-h] --repo REPO --pattern PATTERN --outdir OUTDIR --binfiles BINFILES
                            [--downloaddir DOWNLOADDIR] [--setexec] [--rename RENAME]

Fetch and extract binary files from the latest GitHub release of the given repository.

options:
  -h, --help            show this help message and exit
  --repo REPO           GitHub repository in the form owner/repo
  --pattern PATTERN     Regex pattern to match the asset filename
  --outdir OUTDIR       Output directory to install the binary files.
  --binfiles BINFILES   Glob pattern to match the binary files to install from the extracted files
  --downloaddir DOWNLOADDIR
                        Temporary download directory (if not given, a temporary directory will be created and deleted)
  --setexec             Set executable permission on the installed binary files
  --rename RENAME       Set the name of the installed binary file (only if a single file is matched by --binfiles)
  --token TOKEN         GitHub token to use for authentication. Can also be set via the GITHUB_TOKEN environment variable.
  ```

Requirements:

- Python 3
- `tar`
- `unzip` (optional)
- `unzstd` (from the `zstd` package, optional)

Examples:

```sh
python gh-fetch-release.py \
  --repo microsoft/edit \
  --pattern 'x86_64-linux-gnu\.tar\.zst$' \
  --outdir ~/bin \
  --binfiles 'edit' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo jarun/nnn \
  --pattern 'musl-static-.*\.x86_64\.tar\.gz$' \
  --outdir ~/bin \
  --binfiles 'nnn-musl-static' \
  --setexec \
  --rename 'nnn'
```

```sh
python gh-fetch-release.py \
  --repo rclone/rclone \
  --pattern 'linux-amd64\.zip$' \
  --outdir ~/bin \
  --binfiles 'rclone-*/rclone' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo sharkdp/bat \
  --pattern 'x86_64-unknown-linux-musl.tar.gz$' \
  --outdir ~/bin \
  --binfiles 'bat*/bat' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo aristocratos/btop \
  --pattern 'x86_64-linux-musl.tbz$' \
  --outdir ~/bin \
  --binfiles 'btop/bin/btop' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo junegunn/fzf \
  --pattern 'linux_amd64.tar.gz$' \
  --outdir ~/bin \
  --binfiles 'fzf' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo dandavison/delta \
  --pattern 'x86_64-unknown-linux-musl\.tar\.gz$' \
  --outdir ~/bin \
  --binfiles 'delta-*/delta' \
  --setexec
```

```sh
python gh-fetch-release.py \
  --repo restic/restic \
  --pattern 'linux_amd64\.bz2$' \
  --outdir ~/bin \
  --binfiles 'restic*' \
  --setexec \
  --rename restic
```

## GitHub Token (Optional)

Use: https://github.com/settings/personal-access-tokens/new

Repository access: Public repositories. No need to add any permission
under the section "Permissions".

## Background

I have a bunch of Linux tools that I install in `~/bin` because either
they are not available's in the system's package manager, or if it's
there it is quite outdated. Those tools' binaries are often from GitHub.

My initial version of this tool looked like this:

```
curl -s https://api.github.com/repos/dandavison/delta/releases/latest | \
jq -r '.assets[] | select(.name | test("delta-.*-x86_64-unknown-linux-musl\\.tar\\.gz$")) | .browser_download_url' | \
xargs -I {} curl -sL {} -o - | \
tar -C /tmp -xzvf - && \
cp /tmp/delta-*-unknown-linux-musl/delta ~/bin && \
rm -rf /tmp/delta-*-unknown-linux-musl
```

Sure, it's a clever one-liner, but then it requires installing [`jq`](https://jqlang.org/),
and tweaking it for each different tool is a mess.

I looked at a few alternatives, like [binup](https://github.com/KonishchevDmitry/binup),
[eget](https://github.com/zyedidia/eget), [hubapp](https://github.com/warrensbox/hubapp) and
[getghrel](https://github.com/kavishgr/getghrel) (to name a few), and they were not to my
liking for the following reasons:

- Limited control on how to identify the binary from the extracted package, and where to
  place them, possibly after renaming them and adding the executable bit.
- They are all binaries themselves, which doesn't help if they don't support your CPU
  architecture (for example arm64).
- Some require interactive use or maintaining configuration files.

So I went with a simpler approach. I assume the Linux system has at least
Python 3, `curl`, `tar` and maybe `unzip` and `unzstd`. This seems reasonable.
(Newer versions remove the `curl` requirement.)
And then, copy over a single-file Python script with no additional dependencies
and run it. The script is samll enough that it could be copied over an SSH shell
(`cat > gh-fetch-release.py`, paste, control-d).