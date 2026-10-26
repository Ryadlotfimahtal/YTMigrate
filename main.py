import functools
import os
import json
from typing import Tuple
from datetime import datetime

import ytmusicapi
from ytmusicapi import YTMusic

version = "1.1"
# Browser headers of each account (OAuth is rejected by YouTube Music since late 2024)
source_auth_filename = "source_browser.json"
dest_auth_filename = "dest_browser.json"
# Number of songs sent per add_playlist_items request
add_batch_size = 100


def prompt_yes_no(message: str, default_yes: bool = True) -> bool:
    while True:
        sel = input(message + (" [Y/n] " if default_yes else " [y/N] "))
        if not sel:
            return default_yes
        elif sel in "yY":
            return True
        elif sel in "nN":
            return False


def write_backup(data: list | dict, type: str) -> bool:
    try:
        backup_date = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        with open(f"{type}_backup_{backup_date}.json", "w") as backup_file:
            json.dump(data, backup_file)
    except Exception as e:
        print(f"Failed to save backup, {str(e)}!")
        return False
    else:
        print("Backup saved succesfully!")
        return True


def copy_likes(ytm: Tuple[YTMusic, YTMusic]):
    print("Loading liked songs from source account...", end="", flush=True)
    liked_source = ytm[0].get_playlist("LM", limit=None)
    liked_source_ids = track_video_ids(liked_source["tracks"])

    print("\rLoading liked songs from destination account...", end="", flush=True)
    liked_dest = ytm[1].get_playlist("LM", limit=None)
    liked_dest_ids = set(track_video_ids(liked_dest["tracks"]))

    print("\r" + " " * 50 + "\r", end="", flush=True)

    # Liked songs are listed newest first: like the oldest first to keep the order
    songs_to_like = [
        song for song in reversed(liked_source_ids) if song not in liked_dest_ids
    ]

    if len(songs_to_like) < len(liked_source_ids):
        print(
            f"Skipping {len(liked_source_ids) - len(songs_to_like)} out of "
            f"{len(liked_source_ids)} songs liked!"
        )

    if len(songs_to_like) == 0:
        print("No songs left to like!")
        return

    if not prompt_yes_no(f"Add {len(songs_to_like)} songs to likes?"):
        print("Operation cancelled!")
        return

    failed = []
    for index, song in enumerate(songs_to_like):
        print(
            f"\rAdding songs to likes... {index + 1}/{len(songs_to_like)}",
            end="",
            flush=True,
        )
        try:
            ytm[1].rate_song(song, "LIKE")
        except Exception as e:
            failed.append(song)
            print(f"\nFailed to like song {song},", e)

    if failed:
        print(
            f"\n{len(failed)} out of {len(songs_to_like)} songs could not be liked, "
            "run 'Copy likes' again to retry them."
        )
    else:
        print("\nTransferred all liked songs successfully!")


def track_video_ids(tracks: list) -> list:
    # Unavailable (removed / region-blocked) tracks have no videoId
    return [track["videoId"] for track in tracks if track.get("videoId")]


def add_songs(ytm: YTMusic, playlist_id: str, song_ids: list) -> list:
    """Adds songs in batches, retrying a failed batch one song at a time.
    Returns the ids of the songs that could not be added."""

    def add(ids: list) -> bool:
        try:
            result = ytm.add_playlist_items(playlist_id, ids, duplicates=True)
        except Exception:
            return False
        return isinstance(result, dict) and "SUCCEEDED" in result.get("status", "")

    failed = []
    for start in range(0, len(song_ids), add_batch_size):
        batch = song_ids[start : start + add_batch_size]
        print(
            f"\rAdding songs... {start + len(batch)}/{len(song_ids)}",
            end="",
            flush=True,
        )
        if not add(batch):
            failed += [song for song in batch if not add([song])]
    print()
    return failed


def copy_playlist(
    ytm: Tuple[YTMusic, YTMusic],
    playlist_id: str,
    playlist_name: str = "",
    dest_titles: set | None = None,
):
    print(f"\nLoading playlist: {playlist_name} - [{playlist_id}]...")
    playlist_data = ytm[0].get_playlist(playlist_id, limit=None)
    if not playlist_data:
        print("Failed to load playlist!")
        return

    song_ids = track_video_ids(playlist_data["tracks"])
    unavailable = len(playlist_data["tracks"]) - len(song_ids)
    if unavailable:
        print(f"Skipping {unavailable} unavailable songs!")

    if dest_titles and playlist_data["title"] in dest_titles:
        if not prompt_yes_no(
            "A playlist with this name already exists in the destination account, "
            "copy it anyway?",
            default_yes=False,
        ):
            print("Playlist skipped!")
            return

    print("Creating playlist... ", end="", flush=True)
    try:
        dest_playlist_id = ytm[1].create_playlist(
            playlist_data["title"],
            playlist_data.get("description") or "",
            playlist_data.get("privacy") or "PRIVATE",
        )
    except Exception as e:
        print("\nFailed to create new playlist,", e)
        return
    if type(dest_playlist_id) != str:
        print("\nFailed to create new playlist!")
        return
    print(
        f"\rPlaylist created! URL: https://music.youtube.com/playlist?list={dest_playlist_id}"
    )

    failed = add_songs(ytm[1], dest_playlist_id, song_ids)
    if failed:
        print(
            f"Copied {len(song_ids) - len(failed)} out of {len(song_ids)} songs, "
            f"failed: {' '.join(failed)}"
        )
    else:
        print(f"Copied all {len(song_ids)} songs successfully!")


def parse_number_ids(selection: str):
    result = []
    id_tokens = selection.split()

    for token in id_tokens:
        try:
            if "-" in token:
                start, end = map(int, token.split("-"))
                result.extend(range(start, end + 1))
            else:
                result.append(int(token))
        except ValueError:
            print(
                f"Error: Invalid format for token '{token}'. Please use a valid format."
            )
            return None
    return result


def menu_copy_playlists(ytm: Tuple[YTMusic, YTMusic]):
    print("Loading playlists from source account...", end="", flush=True)
    source_playlists = ytm[0].get_library_playlists(limit=None)
    print("\rLoading playlists from destination account...", end="", flush=True)
    dest_titles = {p["title"] for p in ytm[1].get_library_playlists(limit=None)}
    print("\rSelect playlists:" + " " * 30)

    all_playlists = []
    count = 0

    for playlist in source_playlists:
        # Exclude "Episodes for later" and "Liked songs" playlists
        if playlist["playlistId"] not in ("LM", "SE"):
            all_playlists += [playlist]
            count += 1
            print(
                f"{count}: {playlist['title']}"
                + (f" - {playlist['count']} songs" if "count" in playlist else "")
                + f" - [{playlist['playlistId']}]"
            )

    print("A: All playlists")
    print("C: Cancel")

    while True:
        sel = input(
            "Selection (enter playlist numbers, 'A' for all, or 'C' to cancel): "
        )
        sel_playlists = []

        if sel.lower() == "c":
            print("Operation cancelled!")
            return
        elif sel.lower() == "a":
            sel_playlists = all_playlists
        else:
            sel_ids = parse_number_ids(sel)
            if not sel_ids or not all(1 <= i <= count for i in sel_ids):
                print("Invalid selection. Please enter valid playlist numbers.")
                continue
            for i in sel_ids:
                sel_playlists += [all_playlists[i - 1]]

        for p in sel_playlists:
            try:
                copy_playlist(ytm, p["playlistId"], p["title"], dest_titles)
            except Exception as e:
                print(f"Error copying playlist '{p['title']}': {e}")
                # Handle the error appropriately, e.g., log it or prompt the user
        return


def copy_albums(ytm: Tuple[YTMusic, YTMusic]):
    print("Loading saved albums from source account...", end="", flush=True)
    albums_source = ytm[0].get_library_albums(limit=5000)
    # List of playlistId of all albums from library
    albums_source_ids = functools.reduce(
        lambda l, i: l + [i["playlistId"]], albums_source, []
    )

    print("\rLoading saved albums from destination account...", end="", flush=True)
    albums_dest = ytm[1].get_library_albums(limit=5000)
    # List of playlistId of all albums from library
    albums_dest_ids = functools.reduce(
        lambda l, i: l + [i["playlistId"]], albums_dest, []
    )

    print("\r" + " " * 50 + "\r", end="", flush=True)

    albums_to_save = list(set(albums_source_ids) - set(albums_dest_ids))

    if len(albums_to_save) < len(albums_source_ids):
        print(
            f"Skipping {len(albums_source_ids) - len(albums_to_save)} out of "
            f"{len(albums_source_ids)} albums saved!"
        )

    if len(albums_to_save) == 0:
        print("No albums left to transfer over!")
        return

    if not prompt_yes_no(
        f"Add {len(albums_to_save)} albums to destination account's library?"
    ):
        print("Operation cancelled!")
        return

    try:
        for index, album_playlist_id in enumerate(albums_to_save):
            print(
                f"\rAdding albums to likes... {index + 1}/{len(albums_to_save)}",
                end="",
                flush=True,
            )
            ytm[1].rate_playlist(album_playlist_id, "LIKE")
    except Exception as e:
        print("\nFailed to add albums,", e)
    else:
        print("\nTransferred all saved albums successfully!")


def remove_albums(ytm: YTMusic):
    print("\rLoading saved albums from selected account...", end="", flush=True)
    albums_data = ytm.get_library_albums(limit=5000)
    # List of playlistId and browseId of all albums from library
    albums_ids = functools.reduce(
        lambda l, i: l + [{"playlistId": i["playlistId"], "browseId": i["browseId"]}],
        albums_data,
        [],
    )

    print("\r" + " " * 50 + "\r", end="", flush=True)

    if len(albums_ids) == 0:
        print("No albums left to remove!")
        return

    print("Removed album IDs will be saved to a JSON file for safety.")
    if not prompt_yes_no(
        f"Remove {len(albums_ids)} albums from the selected account's library?"
    ):
        print("Operation cancelled!")
        return

    if not write_backup(albums_ids, "removed_albums"):
        print("Aborting operation!")
        return

    try:
        for index, album in enumerate(albums_ids):
            print(
                f"\rRemoving albums from library... {index + 1}/{len(albums_ids)}",
                end="",
                flush=True,
            )
            ytm.rate_playlist(album["playlistId"], "INDIFFERENT")
    except Exception as e:
        print("\nFailed to remove albums,", e)
    else:
        print("\nRemoved all saved albums successfully!")


def remove_likes(ytm: YTMusic):
    print("Loading liked songs from selected account...", end="", flush=True)
    liked_data = ytm.get_playlist("LM", limit=5000)
    liked_ids = functools.reduce(
        lambda l, i: l + [{"videoId": i["videoId"]}], liked_data["tracks"], []
    )

    print("\r" + " " * 50 + "\r", end="", flush=True)

    if len(liked_ids) == 0:
        print("No liked songs left to remove!")
        return

    print("Removed liked song IDs will be saved to a JSON file for safety.")
    if not prompt_yes_no(
        f"Remove {len(liked_ids)} songs from the selected account's likes?"
    ):
        print("Operation cancelled!")
        return

    if not write_backup(liked_ids, "removed_likes"):
        print("Aborting operation!")
        return

    try:
        for index, song in enumerate(liked_ids):
            print(
                f"\rRemoving songs from likes... {index + 1}/{len(liked_ids)}",
                end="",
                flush=True,
            )
            ytm.rate_song(song["videoId"], "INDIFFERENT")
    except Exception as e:
        print("\nFailed to remove songs from likes,", e)
    else:
        print("\nRemoved all liked songs successfully!")


def removal_tools(ytm: Tuple[YTMusic, YTMusic]):
    selected_ytm = ytm[0]
    while True:
        sel = input("Select an account [0=source / 1=destination]: ")
        if sel == "0" or sel == "1":
            selected_ytm = ytm[int(sel)]
            break
        else:
            print("Invalid input!")

    while True:
        print("\nWARNING: These operations are permanent and cannot be undone.")
        print("Removal tools:")
        print("  1. Remove liked songs")
        print("  2. Remove saved albums")
        print("  0. Back")
        sel = input("Your selection: ")
        match sel:
            case "0":
                return
            case "1":
                remove_likes(selected_ytm)
            case "2":
                remove_albums(selected_ytm)
            case _:
                print("Invalid selection:", sel)


def menu_main(ytm: Tuple[YTMusic, YTMusic]):
    while True:
        print("\nMain menu:")
        print("Copy tools:")
        print("  1. Copy playlists")
        print("  2. Copy likes")
        print("  3. Copy albums")
        print("Other tools:")
        print("  4. Removal tools")
        print("  0. Exit")
        sel = input("Your selection: ")
        match sel:
            case "0":
                return
            case "1":
                menu_copy_playlists(ytm)
            case "2":
                copy_likes(ytm)
            case "3":
                copy_albums(ytm)
            case "4":
                removal_tools(ytm)
            case _:
                print("Invalid option:", sel)


def setup_account(label: str, filename: str) -> bool:
    print(f"\nLog in to the {label} account:")
    print(
        "  1. Open https://music.youtube.com in your browser, signed in with the "
        f"{label} account (switch account from the avatar menu if needed)\n"
        "  2. Open the developer tools > Network tab, filter on 'browse' "
        "and click on Library\n"
        "  3. Copy the request headers of a POST 'browse?...' request with status 200 "
        "(Firefox: right click > Copy Value > Copy Request Headers)\n"
        "  4. Paste them below, then press Enter and Ctrl-D"
    )
    try:
        ytmusicapi.setup(filepath=filename)
    except Exception as e:
        print("Failed to read headers:", e)
        return False
    return True


def load_account(label: str, filename: str) -> Tuple[YTMusic, str] | None:
    if not os.path.isfile(filename) and not setup_account(label, filename):
        return None
    try:
        with open(filename, "r") as auth_file:
            headers = {k.lower(): v for k, v in json.load(auth_file).items()}
        if "SAPISIDHASH" not in headers.get("authorization", ""):
            raise ValueError(
                "no 'authorization: SAPISIDHASH ...' header, copy the headers "
                "of a POST 'browse' request"
            )
        ytm = YTMusic(filename)
        info = ytm.get_account_info()
    except Exception as e:
        print(f"Authentication failed for the {label} account:", e)
        print(f"Delete {filename} and run the script again to log in again.")
        return None
    account = f"{info['accountName']} {info.get('channelHandle') or ''}".strip()
    print(f"{label.capitalize()} account: {account}")
    return ytm, account


def do_auth() -> Tuple[YTMusic, YTMusic] | None:
    source = load_account("source", source_auth_filename)
    if not source:
        return None
    dest = load_account("destination", dest_auth_filename)
    if not dest:
        return None

    if source[1] == dest[1]:
        print(
            "Source and destination are the same account! Delete "
            f"{dest_auth_filename} and log in again with the destination account."
        )
        return None
    if not prompt_yes_no(f"Copy from '{source[1]}' to '{dest[1]}'?"):
        print("Delete the JSON file of the wrong account and run the script again.")
        return None
    return source[0], dest[0]


def main():
    print(f"YTMigrate, version {version}\n")
    ytm = do_auth()
    if ytm:
        menu_main(ytm)


if __name__ == "__main__":
    main()
