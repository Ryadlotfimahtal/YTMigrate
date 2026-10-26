# YTMigrate

Tool to copy playlists, likes and saved albums from one YT Music account to another

## Installation

You need Python 3.10 or newer.

This tool makes use of [ytmusicapi](https://github.com/sigma67/ytmusicapi), which can be installed from PyPI: `pip install ytmusicapi`.

## Usage

Run the `main.py` script (or `uv run --with ytmusicapi main.py`). On first run it will ask for the browser request headers of the source account, then of the destination account, and save them to `source_browser.json` / `dest_browser.json` (they contain your session cookies: keep them private and delete them when done).

OAuth is no longer used: since late 2024 YouTube Music requires a Google Cloud client for OAuth and still rejects the requests (see [ytmusicapi#813](https://github.com/sigma67/ytmusicapi/issues/813)).

To get the headers of an account:

1. Open https://music.youtube.com signed in with that account (switch account from the avatar menu if both are signed in)
2. Open the developer tools > Network tab, filter on `browse` and click on Library
3. Copy the request headers of a POST `browse?...` request with status 200
   - Firefox: right click > Copy Value > Copy Request Headers
   - Chrome: click the request, in the Headers tab copy everything in "Request Headers"
4. Paste them in the terminal, then press Enter and Ctrl-D

Do not sign out of the accounts in the browser before the migration is done, signing out invalidates the copied cookies. If an account fails to authenticate, delete its JSON file and run the script again.

After you can use the menu to perform copy and remove operations.

```
Main menu:
Copy tools:
  1. Copy playlists
  2. Copy likes
  3. Copy albums
Other tools:
  4. Removal tools
  0. Exit
```
