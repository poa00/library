import os
import subprocess
from pathlib import Path
from shutil import which
from time import sleep

from rich import inspect

from .db import sqlite_con
from .utils import cmd, conditional_filter, get_ordinal_media, log, parse_args, remove_media, stop


def play_mpv(args, audio_path):
    if which("mpv") is not None:
        player = ["mpv", "--input-ipc-server=/tmp/mpv_socket", "--no-video", "--keep-open=no", "--term-osd-bar"]
    else:
        player = ["xdg-open"]

    try:
        print(cmd("ffprobe", "-hide_banner", "-loglevel", "info", audio_path, quiet=True).stderr)
    except:
        print(audio_path)

    if args.chromecast:
        Path("/tmp/mpcatt_playing").write_text(audio_path)

        cmd("touch /tmp/sub.srt")
        if not args.with_local:
            cmd("catt", "-d", args.chromecast_device, "cast", "-s", "/tmp/sub.srt", audio_path)
        else:
            cast_process = subprocess.Popen(
                ["catt", "-d", args.chromecast_device, "cast", "-s", "/tmp/sub.srt", audio_path], preexec_fn=os.setpgrp
            )
            sleep(0.974)  # imperfect lazy sync; I use keyboard shortcuts to send `set speed` commands to mpv for resync
            cmd(*player, "--", audio_path)
            cast_process.communicate()  # wait for chromecast to stop (you can tell any chromecast to pause)
            sleep(3.0)  # give chromecast some time to breathe
    else:
        cmd(*player, "--", audio_path, quiet=True)


def listen(args):
    con = sqlite_con(args.db)

    bindings = {}
    if args.search:
        bindings["search"] = "%" + args.search.replace(" ", "%").replace("%%", " ") + "%"
    if args.exclude:
        bindings["exclude"] = "%" + args.exclude.replace(" ", "%").replace("%%", " ") + "%"

    sql_filter = conditional_filter(args)

    search_string = """and (
        filename like :search
        OR mood like :search
        OR genre like :search
        OR year like :search
        OR bpm like :search
        OR key like :search
        OR time like :search
        OR decade like :search
        OR categories like :search
        OR city like :search
        OR country like :search
        OR description like :search
        OR album like :search
        OR title like :search
        OR artist like :search
    )"""

    exclude_string = """and (
        filename not like :exclude
        OR mood not like :exclude
        OR genre not like :exclude
        OR year not like :exclude
        OR bpm not like :exclude
        OR key not like :exclude
        OR time not like :exclude
        OR decade not like :exclude
        OR categories not like :exclude
        OR city not like :exclude
        OR country not like :exclude
        OR description not like :exclude
        OR album not like :exclude
        OR title not like :exclude
        OR artist not like :exclude
    )"""

    query = f"""
    SELECT filename, duration / size AS seconds_per_byte, size
    FROM media
    WHERE 1=1
    {search_string if args.search else ''}
    {exclude_string if args.exclude else ''}
    {"" if args.search else 'and listen_count = 0'}
    {sql_filter}
    ORDER BY
        listen_count asc nulls first,
        {args.sort + ',' if args.sort else ''}
        {'filename,' if args.search and (args.play_in_order > 0) else ''}
        seconds_per_byte ASC
    limit 1 OFFSET {args.skip if args.skip else 0}
    """

    if args.print and "q" in args.print:
        print(query)
        stop()

    next_audio = con.execute(query, bindings).fetchone()
    if next_audio is None:
        print('No media found')
        stop()

    next_audio = Path(dict(next_audio)["filename"])

    # limit to audiobook since normal music does not get deleted so only the first track would ever be played
    if "audiobook" in str(next_audio):
        next_audio = Path(get_ordinal_media(con, args, next_audio, sql_filter))

    if args.print:
        print(next_audio)
        stop()

    if not next_audio.exists():
        print("Removing orphaned metadata", next_audio)
        remove_media(con, next_audio)
    else:
        if args.move:
            keep_path = str(Path(args.move))
            cmd("mv", next_audio, keep_path)
        else:
            play_mpv(args, next_audio)
            if args.action == "delete" or "audiobook" in str(next_audio).lower():
                cmd("trash-put", next_audio, strict=False)
                remove_media(con, next_audio)

    con.execute("update media set listen_count = listen_count +1 where filename = ?", (str(next_audio),))
    con.commit()


def main():
    args = parse_args(default_chromecast="Xylo and Orchestra")

    try:
        listen(args)
    finally:
        if args.chromecast:
            cmd("rm /tmp/mpcatt_playing", strict=False)


if __name__ == "__main__":
    main()
