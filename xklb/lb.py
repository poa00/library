import argparse, sys

from xklb import __version__
from xklb.dl_extract import dl_download
from xklb.fs_extract import fs_add, fs_update
from xklb.gdl_extract import gallery_add, gallery_update
from xklb.hn_extract import hacker_news_add
from xklb.media.dedupe import dedupe_media
from xklb.play_actions import filesystem, listen, read, view, watch
from xklb.reddit_extract import reddit_add, reddit_update
from xklb.scripts.bigdirs import bigdirs
from xklb.scripts.block import block
from xklb.scripts.christen import christen
from xklb.scripts.cluster_sort import cluster_sort
from xklb.scripts.copy_play_counts import copy_play_counts
from xklb.scripts.dedupe_czkawka import czkawka_dedupe
from xklb.scripts.dedupe_db import dedupe_db
from xklb.scripts.disk_usage import disk_usage
from xklb.scripts.download_status import download_status
from xklb.scripts.eda import eda
from xklb.scripts.export_text import export_text
from xklb.scripts.history import history
from xklb.scripts.incremental_diff import incremental_diff
from xklb.scripts.mcda import mcda
from xklb.scripts.merge_dbs import merge_dbs
from xklb.scripts.merge_online_local import merge_online_local
from xklb.scripts.mining.extract_links import extract_links
from xklb.scripts.mining.markdown_links import markdown_links
from xklb.scripts.mining.mpv_watchlater import mpv_watchlater
from xklb.scripts.mining.nouns import nouns
from xklb.scripts.mining.pushshift import pushshift_extract
from xklb.scripts.mining.reddit_selftext import reddit_selftext
from xklb.scripts.mining.substack import substack
from xklb.scripts.mining.tildes import tildes
from xklb.scripts.move_list import move_list
from xklb.scripts.optimize_db import optimize_db
from xklb.scripts.places_import import places_import
from xklb.scripts.playback_control import playback_next, playback_now, playback_pause, playback_stop
from xklb.scripts.playlists import playlists
from xklb.scripts.process_audio import process_audio
from xklb.scripts.redownload import redownload
from xklb.scripts.relmv import relmv
from xklb.scripts.scatter import scatter
from xklb.scripts.search_db import search_db
from xklb.scripts.streaming_tab_loader import streaming_tab_loader
from xklb.search import search
from xklb.site_extract import site_add
from xklb.tabs_actions import tabs
from xklb.tabs_extract import tabs_add
from xklb.tube_extract import tube_add, tube_update
from xklb.utils import devices, iterables
from xklb.utils.consts import SC
from xklb.utils.log_utils import log


def usage() -> str:
    return f"""xk media library subcommands (v{__version__})

    local media:
      lb fsadd                 Create a local media database; Add folders
      lb fsupdate              Refresh database: add new files, mark deleted

      lb listen                Listen to local and online media
      lb watch                 Watch local and online media
      lb search                Search text and subtitles

      lb read                  Read books
      lb view                  View images

      lb bigdirs               Discover folders which take much room
      lb dedupe                Deduplicate a media db's media files
      lb czkawka-dedupe        Split-screen czkawka results to decide which to delete
      lb relmv                 Move files/folders while preserving relative paths
      lb christen              Cleanse files by giving them a new name

      lb mv-list               Reach a target free space by moving data across mount points
      lb scatter               Scatter files across multiple mountpoints (mergerfs balance)

      lb search-db             Search a SQLITE file
      lb merge-dbs             Merge multiple SQLITE files
      lb dedupe-dbs            Deduplicate SQLITE tables
      lb copy-play-counts      Copy play counts from multiple SQLITE files

    online media:
      lb tubeadd               Create a tube database; Add playlists
      lb tubeupdate            Fetch new videos from saved playlists

      lb galleryadd            Create a gallery database; Add albums
      lb galleryupdate         Fetch new images from saved playlists

      lb redditadd             Create a reddit database; Add subreddits
      lb redditupdate          Fetch new posts from saved subreddits

      lb tildes                Backup tildes comments and topics
      lb substack              Backup substack articles

      lb merge-online-local    Merge local and online metadata

    downloads:
      lb download              Download media
      lb redownload            Redownload missing media
      lb block                 Prevent downloading specific media

    playback:
      lb now                   Print what is currently playing
      lb next                  Play next file
      lb stop                  Stop all playback
      lb pause                 Pause all playback

    statistics:
      lb history               Show some playback statistics
      lb playlists             List added playlists
      lb download-status       Show download status
      lb disk-usage            Print disk usage
      lb mount-stats           Print mount usage

    browser tabs:
      lb tabsadd               Create a tabs database; Add URLs
      lb tabs                  Open your tabs for the day
      lb siteadd               Create a sites database; Add URLs
      lb surf                  Load browser tabs in a streaming way (stdin)

    places:
      lb places-import         Load POIs from Google Maps Google Takeout

    mining:
      lb eda                   Exploratory Data Analysis on table-like files
      lb mcda                  Multi-criteria ranking on table-like files
      lb incremental-diff      Diff large table-like files in chunks

      lb reddit-selftext       db selftext external links -> db media table
      lb pushshift             Convert Pushshift jsonl.zstd -> reddit.db format (stdin)
      lb hnadd                 Create a hackernews database (this takes a few days)

      lb extract-links         Extract inner links from lists of web pages
      lb markdown-links        Extract titles from lists of web pages

      lb mpv-watchlater        Import timestamps from mpv watchlater to history table

      lb cluster-sort          Lines -> sorted by sentence similarity groups (stdin)
      lb nouns                 Unstructured text -> compound nouns (stdin)
    """


def print_help(parser) -> None:
    print(usage())
    print(parser.epilog)


known_subcommands = ["fs", "du", "tabs"]


def consecutive_prefixes(s):
    prefixes = [s[:j] for j in range(5, len(s)) if s[:j] and s[:j] not in known_subcommands]
    known_subcommands.extend(prefixes)
    return prefixes


def add_parser(subparsers, name, aliases=None):
    if aliases is None:
        aliases = []

    aliases += [
        s.replace("-", "") for s in [name] + aliases if "-" in s and s.replace("-", "") not in known_subcommands
    ]
    aliases += [
        s.replace("-", "_") for s in [name] + aliases if "-" in s and s.replace("-", "_") not in known_subcommands
    ]
    known_subcommands.extend([name, *aliases])

    aliases += consecutive_prefixes(name) + iterables.conform([consecutive_prefixes(a) for a in aliases])
    return subparsers.add_parser(name, aliases=aliases, add_help=False)


def create_subcommands_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lb",
        description="xk media library",
        epilog="Report bugs here: https://github.com/chapmanjacobd/library/issues/new/choose",
        add_help=False,
    )
    subparsers = parser.add_subparsers()
    subp_fsadd = add_parser(subparsers, "fs-add", ["x", "extract"])
    subp_fsadd.set_defaults(func=fs_add)
    subp_fsupdate = add_parser(subparsers, "fs-update", ["xu"])
    subp_fsupdate.set_defaults(func=fs_update)

    subp_watch = add_parser(subparsers, SC.watch, ["wt", "tubewatch", "tw", "entries"])
    subp_watch.set_defaults(func=watch)
    subp_listen = add_parser(subparsers, SC.listen, ["lt", "tubelisten", "tl"])
    subp_listen.set_defaults(func=listen)

    subp_search = add_parser(subparsers, "search-captions", ["sc", "search"])
    subp_search.set_defaults(func=search)

    subp_read = add_parser(subparsers, SC.read, ["text", "books", "docs"])
    subp_read.set_defaults(func=read)
    subp_view = add_parser(subparsers, SC.view, ["image", "see", "look"])
    subp_view.set_defaults(func=view)

    subp_filesystem = add_parser(subparsers, SC.filesystem, ["fs", "open"])
    subp_filesystem.set_defaults(func=filesystem)

    subp_bigdirs = add_parser(subparsers, "big-dirs", ["large-folders"])
    subp_bigdirs.set_defaults(func=bigdirs)
    subp_move_list = add_parser(subparsers, "mv-list", ["move-list"])
    subp_move_list.set_defaults(func=move_list)
    subp_relmv = add_parser(subparsers, "rel-mv", ["mv-rel"])
    subp_relmv.set_defaults(func=relmv)

    subp_scatter = add_parser(subparsers, "scatter")
    subp_scatter.set_defaults(func=scatter)
    subp_christen = add_parser(subparsers, "christen")
    subp_christen.set_defaults(func=christen)

    subp_search_db = add_parser(subparsers, "search-db", ["s", "sdb"])
    subp_search_db.set_defaults(func=search_db)
    subp_merge_db = add_parser(subparsers, "merge-dbs", ["merge-db"])
    subp_merge_db.set_defaults(func=merge_dbs)
    subp_dedupe_db = add_parser(subparsers, "dedupe-dbs", ["dedupe-db"])
    subp_dedupe_db.set_defaults(func=dedupe_db)
    subp_copy_play_counts = add_parser(subparsers, "copy-play-counts")
    subp_copy_play_counts.set_defaults(func=copy_play_counts)

    subp_dedupe = add_parser(subparsers, "dedupe-media")
    subp_dedupe.set_defaults(func=dedupe_media)
    subp_czkawka_dedupe = add_parser(subparsers, "czkawka-dedupe", ["dedupe-czkawka"])
    subp_czkawka_dedupe.set_defaults(func=czkawka_dedupe)
    subp_dedupe_local = add_parser(subparsers, "merge-online-local")
    subp_dedupe_local.set_defaults(func=merge_online_local)
    subp_optimize = add_parser(subparsers, "optimize", ["optimize-db"])
    subp_optimize.set_defaults(func=optimize_db)

    subp_site_add = add_parser(subparsers, "site-add", ["sa"])
    subp_site_add.set_defaults(func=site_add)
    # subp_site_update = add_parser(subparsers, "site-update", ["su"])
    # subp_site_update.set_defaults(func=site_update)
    # subp_site_sql = add_parser(subparsers, "site-sql", ["ss", "sql-site"])
    # subp_site_sql.set_defaults(func=site_sql)

    subp_tubeadd = add_parser(subparsers, "tube-add", ["ta", "dladd", "da"])
    subp_tubeadd.set_defaults(func=tube_add)
    subp_tubeupdate = add_parser(subparsers, "tube-update", ["dlupdate", "tu"])
    subp_tubeupdate.set_defaults(func=tube_update)

    subp_galleryadd = add_parser(subparsers, "gallery-add", ["gdl-add", "ga"])
    subp_galleryadd.set_defaults(func=gallery_add)
    subp_galleryupdate = add_parser(subparsers, "gallery-update", ["gdl-update", "gu"])
    subp_galleryupdate.set_defaults(func=gallery_update)

    subp_redditadd = add_parser(subparsers, "reddit-add", ["ra"])
    subp_redditadd.set_defaults(func=reddit_add)
    subp_redditupdate = add_parser(subparsers, "reddit-update", ["ru"])
    subp_redditupdate.set_defaults(func=reddit_update)
    subp_pushshift = add_parser(subparsers, "pushshift")
    subp_pushshift.set_defaults(func=pushshift_extract)

    subp_tildes = add_parser(subparsers, "tildes")
    subp_tildes.set_defaults(func=tildes)
    subp_substack = add_parser(subparsers, "substack")
    subp_substack.set_defaults(func=substack)

    subp_export_text = add_parser(subparsers, "export-text")
    subp_export_text.set_defaults(func=export_text)

    subp_hnadd = add_parser(subparsers, "hn-add")
    subp_hnadd.set_defaults(func=hacker_news_add)

    subp_download = add_parser(subparsers, "download", ["dl"])
    subp_download.set_defaults(func=dl_download)
    subp_block = add_parser(subparsers, "block")
    subp_block.set_defaults(func=block)
    subp_redownload = add_parser(subparsers, "re-download", ["re-dl"])
    subp_redownload.set_defaults(func=redownload)

    subp_playlist = add_parser(subparsers, "playlists", ["pl", "folders"])
    subp_playlist.set_defaults(func=playlists)
    subp_history = add_parser(subparsers, "history", ["hi", "log"])
    subp_history.set_defaults(func=history)
    subp_download_status = add_parser(subparsers, "download-status", ["ds", "dl-status"])
    subp_download_status.set_defaults(func=download_status)
    subp_disk_usage = add_parser(subparsers, "disk-usage", ["du", "usage"])
    subp_disk_usage.set_defaults(func=disk_usage)
    subp_mount_stats = add_parser(subparsers, "mount-stats", ["mu", "mount-usage"])
    subp_mount_stats.set_defaults(func=devices.mount_stats)

    subp_playback_now = add_parser(subparsers, "now")
    subp_playback_now.set_defaults(func=playback_now)
    subp_playback_next = add_parser(subparsers, "next")
    subp_playback_next.set_defaults(func=playback_next)
    subp_playback_stop = add_parser(subparsers, "stop")
    subp_playback_stop.set_defaults(func=playback_stop)
    subp_playback_pause = add_parser(subparsers, "pause", ["play"])
    subp_playback_pause.set_defaults(func=playback_pause)

    subp_tabsadd = add_parser(subparsers, "tabs-add")
    subp_tabsadd.set_defaults(func=tabs_add)
    subp_tabs = add_parser(subparsers, "tabs", ["tb"])
    subp_tabs.set_defaults(func=tabs)
    subp_surf = add_parser(subparsers, "surf")
    subp_surf.set_defaults(func=streaming_tab_loader)

    subp_nouns = add_parser(subparsers, "nouns")
    subp_nouns.set_defaults(func=nouns)
    subp_cluster_sort = add_parser(subparsers, "cluster-sort", ["cs"])
    subp_cluster_sort.set_defaults(func=cluster_sort)

    subp_eda = add_parser(subparsers, "eda", ["preview"])
    subp_eda.set_defaults(func=eda)
    subp_mcda = add_parser(subparsers, "mcda", ["mcdm", "rank"])
    subp_mcda.set_defaults(func=mcda)
    subp_incremental_diff = add_parser(subparsers, "incremental-diff")
    subp_incremental_diff.set_defaults(func=incremental_diff)

    subp_process_audio = add_parser(subparsers, "process-audio")
    subp_process_audio.set_defaults(func=process_audio)

    subp_places_import = add_parser(subparsers, "places-import")
    subp_places_import.set_defaults(func=places_import)

    subp_mpv_watchlater = add_parser(subparsers, "mpv-watchlater")
    subp_mpv_watchlater.set_defaults(func=mpv_watchlater)

    subp_reddit_selftext = add_parser(subparsers, "reddit-selftext")
    subp_reddit_selftext.set_defaults(func=reddit_selftext)
    subp_extract_links = add_parser(subparsers, "extract-links", ["links"])
    subp_extract_links.set_defaults(func=extract_links)
    subp_markdown_links = add_parser(subparsers, "markdown-links", ["markdown-urls"])
    subp_markdown_links.set_defaults(func=markdown_links)

    parser.add_argument("--version", "-V", action="store_true")
    return parser


def library(args=None) -> None:
    if args:
        sys.argv = ["lb", *args]

    parser = create_subcommands_parser()
    args, _unk = parser.parse_known_args(args)
    if args.version:
        return print(__version__)

    log.info("library v%s", __version__)
    log.info(sys.argv)
    original_argv = sys.argv
    if len(sys.argv) >= 2:
        del sys.argv[1]

    if hasattr(args, "func"):
        args.func()
        return None
    else:
        try:
            log.error("Subcommand %s not found", original_argv[1])
        except Exception:
            if len(original_argv) > 1:
                log.error("Invalid args. I see: %s", original_argv)

        print_help(parser)
        raise SystemExit(1)


if __name__ == "__main__":
    library()
