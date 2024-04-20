import argparse, os, shlex, sys
from pathlib import Path

from xklb import media_printer, usage
from xklb.createdb import tube_backend
from xklb.fsdb import big_dirs
from xklb.mediadb import db_history, db_media
from xklb.playback import media_player
from xklb.tablefiles import mcda
from xklb.utils import arggroups, consts, db_utils, devices, file_utils, iterables, nums, objects, processes, sql_utils
from xklb.utils.arg_utils import parse_args_limit, parse_args_sort
from xklb.utils.consts import SC
from xklb.utils.log_utils import Timer, log


def parse_args(action, default_chromecast=None) -> argparse.Namespace:
    DEFAULT_PLAYER_ARGS_SUB = ["--speed=1"]
    DEFAULT_PLAYER_ARGS_NO_SUB = ["--speed=1.46"]

    parser = argparse.ArgumentParser(prog="library " + action, usage=usage.play(action))
    arggroups.sql_fs(parser)
    arggroups.sql_media(parser)
    arggroups.playback(parser)
    arggroups.multiple_playback(parser)
    arggroups.capability_clobber(parser)
    arggroups.post_actions(parser)

    parser.add_argument("--big-dirs", "--bigdirs", "-B", action="count", default=0, help=argparse.SUPPRESS)
    arggroups.operation_group_folders(parser)
    arggroups.operation_cluster(parser)
    arggroups.operation_related(parser)
    parser.add_argument("--play-in-order", "-O", nargs="?", const="natural_ps", help=argparse.SUPPRESS)

    parser.add_argument(
        "--chromecast-device",
        "--cast-to",
        "-t",
        default=default_chromecast or "",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--chromecast", "--cast", "-c", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cast-with-local", "-wl", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--interdimensional-cable", "-4dtv", type=int, help=argparse.SUPPRESS)

    parser.add_argument(
        "--partial",
        "-P",
        "--previous",
        "--recent",
        default=False,
        const="n",
        nargs="?",
        help=argparse.SUPPRESS,
    )

    parser.add_argument("--watch-later-directory", default=consts.DEFAULT_MPV_WATCH_LATER, help=argparse.SUPPRESS)
    parser.add_argument("--subtitle-mix", default=consts.DEFAULT_SUBTITLE_MIX, help=argparse.SUPPRESS)

    parser.add_argument("--player-args-sub", "-player-sub", nargs="*", default=DEFAULT_PLAYER_ARGS_SUB)
    parser.add_argument("--player-args-no-sub", "-player-no-sub", nargs="*", default=DEFAULT_PLAYER_ARGS_NO_SUB)
    parser.add_argument("--transcode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--transcode-audio", action="store_true", help=argparse.SUPPRESS)

    for i in range(0, 255):
        parser.add_argument(f"--cmd{i}", help=argparse.SUPPRESS)
    parser.add_argument("--shallow-organize", default="/mnt/d/", help=argparse.SUPPRESS)

    parser.add_argument("--safe", action="store_true", help="Skip generic URLs")
    parser.add_argument("--refresh", "--rescan", action="store_true")

    parser.add_argument("--fetch-siblings")
    parser.add_argument("--sibling", "--episode", "--episodes", "--episodic", action="store_true")
    parser.add_argument("--solo", action="store_true")

    parser.add_argument("--prefetch", type=int, default=3)
    parser.add_argument("--prefix", default="", help=argparse.SUPPRESS)

    parser.add_argument("--timeout", "-T", help="Quit after x minutes")
    parser.add_argument("--delete-unplayable", action="store_true")
    arggroups.debug(parser)

    arggroups.database(parser)
    parser.add_argument("search", nargs="*")
    args = parser.parse_intermixed_args()
    args.action = action
    args.defaults = []

    args.include += args.search
    if len(args.include) == 1:
        if args.include == ["."]:
            args.include = [str(Path().cwd().resolve())]
        elif os.sep in args.include[0]:
            args.include = [file_utils.resolve_absolute_path(args.include[0])]

    args.db = db_utils.connect(args)

    if args.mpv_socket is None:
        if args.action in (SC.listen,):
            args.mpv_socket = consts.DEFAULT_MPV_LISTEN_SOCKET
        else:
            args.mpv_socket = consts.DEFAULT_MPV_WATCH_SOCKET

    if args.big_dirs:
        args.local_media_only = True

    parse_args_limit(args)
    parse_args_sort(args)

    if args.cols:
        args.cols = list(iterables.flatten([s.split(",") for s in args.cols]))

    if args.duration:
        args.duration = sql_utils.parse_human_to_sql(nums.human_to_seconds, "duration", args.duration)

    if args.size:
        args.size = sql_utils.parse_human_to_sql(nums.human_to_bytes, "size", args.size)

    if args.duration_from_size:
        args.duration_from_size = sql_utils.parse_human_to_sql(nums.human_to_bytes, "size", args.duration_from_size)

    if args.chromecast:
        from catt.api import CattDevice

        args.cc = CattDevice(args.chromecast_device, lazy=True)
        args.cc_ip = devices.get_ip_of_chromecast(args.chromecast_device)

    if args.override_player:
        args.override_player = shlex.split(args.override_player)

    if args.multiple_playback > 1:
        args.gui = True

    if args.keep_dir:
        args.keep_dir = Path(args.keep_dir).expanduser().resolve()

    if args.solo:
        args.upper = 1
    if args.sibling:
        args.lower = 2

    if args.post_action:
        args.post_action = args.post_action.replace("-", "_")

    log.info(objects.dict_filter_bool(args.__dict__))

    processes.timeout(args.timeout)

    args.sock = None
    return args


def construct_query(args) -> tuple[str, dict]:
    m_columns = db_utils.columns(args, "media")

    args.filter_sql = []
    args.aggregate_filter_sql = []
    args.filter_bindings = {}

    if args.duration:
        args.filter_sql.append(" and duration IS NOT NULL " + args.duration)
    if args.size:
        args.filter_sql.append(" and size IS NOT NULL " + args.size)
    if args.duration_from_size:
        args.filter_sql.append(
            " and size IS NOT NULL and duration in (select distinct duration from media where 1=1 "
            + args.duration_from_size
            + ")",
        )

    if args.no_video:
        args.filter_sql.append(" and video_count=0 ")
    if args.no_audio:
        args.filter_sql.append(" and audio_count=0 ")
    if args.subtitles:
        args.filter_sql.append(" and subtitle_count>0 ")
    if args.no_subtitles:
        args.filter_sql.append(" and subtitle_count=0 ")

    if args.created_within:
        args.aggregate_filter_sql.append(
            f"and time_created >= cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.created_within)}')) as int)",
        )
    if args.created_before:
        args.aggregate_filter_sql.append(
            f"and time_created < cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.created_before)}')) as int)",
        )
    if args.changed_within:
        args.aggregate_filter_sql.append(
            f"and time_modified >= cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.changed_within)}')) as int)",
        )
    if args.changed_before:
        args.aggregate_filter_sql.append(
            f"and time_modified < cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.changed_before)}')) as int)",
        )
    if args.played_within:
        args.aggregate_filter_sql.append(
            f"and time_last_played >= cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.played_within)}')) as int)",
        )
    if args.played_before:
        args.aggregate_filter_sql.append(
            f"and time_last_played < cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.played_before)}')) as int)",
        )
    if args.deleted_within:
        args.aggregate_filter_sql.append(
            f"and time_deleted >= cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.deleted_within)}')) as int)",
        )
    if args.deleted_before:
        args.aggregate_filter_sql.append(
            f"and time_deleted < cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.deleted_before)}')) as int)",
        )
    if args.downloaded_within:
        args.aggregate_filter_sql.append(
            f"and time_downloaded >= cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.downloaded_within)}')) as int)",
        )
    if args.downloaded_before:
        args.aggregate_filter_sql.append(
            f"and time_downloaded < cast(STRFTIME('%s', datetime( 'now', '-{nums.sql_human_time(args.downloaded_before)}')) as int)",
        )

    args.table = "media"
    if args.db["media"].detect_fts() and not args.no_fts:
        if args.include:
            args.table, search_bindings = db_utils.fts_search_sql(
                "media",
                fts_table=args.db["media"].detect_fts(),
                include=args.include,
                exclude=args.exclude,
                flexible=args.flexible_search,
            )
            args.filter_bindings = {**args.filter_bindings, **search_bindings}
            m_columns = {**m_columns, "rank": int}
        elif args.exclude:
            db_utils.construct_search_bindings(
                args,
                [f"m.{k}" for k in m_columns if k in db_utils.config["media"]["search_columns"]],
            )
    else:
        db_utils.construct_search_bindings(
            args,
            [f"m.{k}" for k in m_columns if k in db_utils.config["media"]["search_columns"]],
        )

    if args.table == "media" and args.random and not any([args.print, args.limit not in args.defaults]):
        limit = 16 * (args.limit or consts.DEFAULT_PLAY_QUEUE)
        where_not_deleted = (
            "where COALESCE(time_deleted,0) = 0"
            if "time_deleted" in m_columns
            and "deleted" not in args.sort_groups_by
            and "time_deleted" not in " ".join(args.where)
            else ""
        )
        args.filter_sql.append(
            f"and m.id in (select id from media {where_not_deleted} order by random() limit {limit})",
        )

    aggregate_filter_columns = ["time_first_played", "time_last_played", "play_count", "playhead"]

    cols = args.cols or ["path", "title", "duration", "size", "subtitle_count", "is_dir", "rank"]
    if "deleted" in " ".join(sys.argv):
        cols.append("time_deleted")
    if "played" in " ".join(sys.argv):
        cols.append("time_last_played")
    args.select = [c for c in cols if c in m_columns or c in ["*"]] + getattr(args, "select", [])
    if args.action == SC.read and "tags" in m_columns:
        args.select += ["cast(length(tags) / 4.2 / 220 * 60 as INT) + 10 duration"]

    select_sql = "\n        , ".join(args.select)
    limit_sql = "LIMIT " + str(args.limit) if args.limit else ""
    offset_sql = f"OFFSET {args.offset}" if args.offset and args.limit else ""
    query = f"""WITH m as (
            SELECT
                m.id
                , SUM(CASE WHEN h.done = 1 THEN 1 ELSE 0 END) play_count
                , MIN(h.time_played) time_first_played
                , MAX(h.time_played) time_last_played
                , FIRST_VALUE(h.playhead) OVER (PARTITION BY h.media_id ORDER BY h.time_played DESC) playhead
                , *
            FROM {args.table} m
            LEFT JOIN history h on h.media_id = m.id
            WHERE 1=1
                {db_media.filter_args_sql(args, m_columns)}
                {" ".join(args.filter_sql)}
                {" ".join([f" and path like '%.{ext}'" for ext in args.ext])}
                {" ".join([" and " + w for w in args.where if not any(a in w for a in aggregate_filter_columns)])}
            GROUP BY m.id, m.path
        )
        SELECT
            {select_sql}
            , play_count
            , time_first_played
            , time_last_played
            , playhead
        FROM m
        WHERE 1=1
            {" ".join(args.aggregate_filter_sql)}
            {" ".join([" and " + w for w in args.where if any(a in w for a in aggregate_filter_columns)])}
        ORDER BY 1=1
            , {args.sort}
        {limit_sql} {offset_sql}
    """

    args.filter_sql = [s for s in args.filter_sql if "id" not in s]  # only use random id constraint in first query

    return query, args.filter_bindings


def filter_episodic(args, media: list[dict]) -> list[dict]:
    parent_dict = {}
    for m in media:
        path = Path(m["path"])
        parent_path = path.parent
        parent_dict.setdefault(parent_path, 0)
        parent_dict[parent_path] += 1

    filtered_media = []
    for m in media:
        path = Path(m["path"])
        parent_path = path.parent

        siblings = parent_dict[parent_path]

        if args.lower is not None and siblings < args.lower:
            continue
        elif args.upper is not None and siblings > args.upper:
            continue
        else:
            filtered_media.append(m)

    return filtered_media


def history_sort(args, media) -> list[dict]:
    if "s" in args.partial:  # skip; only play unseen
        previously_watched_paths = [m["path"] for m in media if m["time_first_played"]]
        return [m for m in media if m["path"] not in previously_watched_paths]

    def mpv_progress(m):
        playhead = m.get("playhead")
        duration = m.get("duration")
        if not playhead:
            return float("-inf")
        if not duration:
            return float("-inf")

        if "p" in args.partial and "t" in args.partial:
            return (duration / playhead) * -(duration - playhead)  # weighted remaining
        elif "t" in args.partial:
            return -(duration - playhead)  # time remaining
        else:
            return playhead / duration  # percent remaining

    def sorting_hat():
        if "f" in args.partial:  # first-viewed
            return lambda m: m.get("time_first_played") or 0
        elif "p" in args.partial or "t" in args.partial:  # sort by remaining duration
            return mpv_progress

        return lambda m: m.get("time_last_played") or m.get("time_first_played") or 0

    reverse_chronology = True
    if "o" in args.partial:  # oldest first
        reverse_chronology = False

    key = sorting_hat()
    if args.print:
        reverse_chronology = not reverse_chronology

    media = sorted(
        media,
        key=key,
        reverse=reverse_chronology,
    )

    if args.offset:
        media = media[int(args.offset) :]

    return media


def process_playqueue(args) -> None:
    db_history.create(args)

    query, bindings = construct_query(args)

    if args.print and not any(
        [
            args.partial,
            args.lower,
            args.upper,
            args.safe,
            args.play_in_order,
            args.big_dirs,
            args.fetch_siblings,
            args.related,
            args.cluster_sort,
            args.folder,
            args.folder_glob,
        ],
    ):
        media_printer.printer(args, query, bindings)
        return

    t = Timer()
    media = list(args.db.query(query, bindings))
    log.debug("query: %s", t.elapsed())

    if args.fetch_siblings:
        media = db_media.get_sibling_media(args, media)

    if args.partial:
        media = history_sort(args, media)
        log.debug("utils.history_sort: %s", t.elapsed())

    if args.lower is not None or args.upper is not None:
        media = filter_episodic(args, media)
        log.debug("utils.filter_episodic: %s", t.elapsed())

    if not media:
        if args.include:
            p = Path(" ".join(args.include)).resolve()
            if p.is_file():
                media = [{"path": str(p)}]
            elif p.is_dir():
                if args.folder_glob:
                    media = [{"path": s} for s in file_utils.fast_glob(p)]
                elif args.action in SC.watch:
                    media = [{"path": s} for s in file_utils.rglob(str(p), consts.VIDEO_EXTENSIONS)[0]]
                elif args.action == SC.listen:
                    media = [{"path": s} for s in file_utils.rglob(str(p), consts.AUDIO_ONLY_EXTENSIONS)[0]]
                elif args.action in SC.view:
                    media = [{"path": s} for s in file_utils.rglob(str(p), consts.IMAGE_EXTENSIONS)[0]]
                elif args.action in SC.read:
                    media = [{"path": s} for s in file_utils.rglob(str(p), consts.TEXTRACT_EXTENSIONS)[0]]
                else:
                    media = [{"path": s} for s in file_utils.rglob(str(p))[0]]
            else:
                processes.no_media_found()
        else:
            processes.no_media_found()

    if args.safe:
        media = [d for d in media if tube_backend.is_supported(d["path"]) or Path(d["path"]).exists()]
        log.debug("tube_backend.is_supported: %s", t.elapsed())

    if args.related >= consts.RELATED:
        media = db_media.get_related_media(args, media[0])
        log.debug("player.get_related_media: %s", t.elapsed())

    if args.big_dirs:
        media_keyed = {d["path"]: d for d in media}
        folders = big_dirs.group_files_by_folder(args, media)
        dirs = big_dirs.process_big_dirs(args, folders)
        dirs = mcda.group_sort_by(args, dirs)
        log.debug("process_bigdirs: %s", t.elapsed())
        dirs = list(reversed([d["path"] for d in dirs]))
        if "limit" in args.defaults:
            media = db_media.get_dir_media(args, dirs)
            log.debug("get_dir_media: %s", t.elapsed())
        else:
            media = []
            media_set = set()
            for dir in dirs:
                if len(dir) == 1:
                    continue

                for key in media_keyed:
                    if key in media_set:
                        continue

                    if os.sep not in key.replace(dir, "") and key.startswith(dir):
                        media_set.add(key)
                        media.append(media_keyed[key])
            log.debug("double for loop compare_block_strings: %s", t.elapsed())

    if args.play_in_order:
        media = db_media.natsort_media(args, media)

    if args.cluster_sort:
        from xklb.text.cluster_sort import cluster_dicts

        media = cluster_dicts(args, media)
        log.debug("cluster-sort: %s", t.elapsed())

    if getattr(args, "refresh", False):
        marked = db_media.mark_media_deleted(args, [d["path"] for d in media if not Path(d["path"]).exists()])
        log.warning(f"Marked {marked} metadata records as deleted")
        args.refresh = False
        return process_playqueue(args)

    if args.folder:
        media = ({**m, "path": str(Path(m["path"]).parent)} for m in media)
    elif args.folder_glob:
        media = ({"path": s} for m in media for s in file_utils.fast_glob(Path(m["path"]).parent, args.folder_glob))

    if any(
        [
            args.print,
            args.delete_files,
            args.delete_rows,
            args.mark_deleted,
            args.mark_watched,
        ]
    ):
        media_printer.media_printer(args, media)
    else:
        media_player.play_list(args, media)


def watch() -> None:
    args = parse_args(SC.watch, default_chromecast="Living Room TV")
    process_playqueue(args)


def listen() -> None:
    args = parse_args(SC.listen, default_chromecast="Xylo and Orchestra")
    process_playqueue(args)


def filesystem() -> None:
    args = parse_args(SC.filesystem)
    process_playqueue(args)


def read() -> None:
    args = parse_args(SC.read)
    process_playqueue(args)


def view() -> None:
    args = parse_args(SC.view)
    process_playqueue(args)