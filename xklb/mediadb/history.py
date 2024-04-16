import argparse

from xklb import media_printer, usage
from xklb.history import create
from xklb.utils import arggroups, consts, db_utils, objects, sql_utils, strings
from xklb.utils.log_utils import log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        "library history",
        usage=usage.history,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    arggroups.sql_fs(parser)
    arggroups.sql_media(parser)

    arggroups.frequency(parser)
    parser.add_argument(
        "facet",
        metavar="facet",
        type=str.lower,
        default="watched",
        const="watched",
        nargs="?",
        help=f"One of: {', '.join(consts.time_facets)}",
    )
    parser.add_argument("--hide-deleted", action="store_true")
    parser.add_argument("--played", "--opened", action="store_true")

    arggroups.debug(parser)

    arggroups.database(parser)
    args = parser.parse_intermixed_args()

    args.facet = strings.partial_startswith(args.facet, consts.time_facets)
    args.frequency = strings.partial_startswith(args.frequency, consts.frequency)

    args.db = db_utils.connect(args)

    args.action = consts.SC.history
    log.info(objects.dict_filter_bool(args.__dict__))

    args.filter_bindings = {}

    return args


def process_search(args, m_columns):
    args.table = "media"
    if args.db["media"].detect_fts():
        if args.include:
            args.table, search_bindings = db_utils.fts_search_sql(
                "media",
                fts_table=args.db["media"].detect_fts(),
                include=args.include,
                exclude=args.exclude,
            )
            args.filter_bindings = search_bindings
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


def recent_media(args, time_column):
    m_columns = db_utils.columns(args, "media")
    process_search(args, m_columns)
    query = f"""
    SELECT
        path
        {', title' if 'title' in m_columns else ''}
        {', duration' if 'duration' in m_columns else ''}
        {', subtitle_count' if 'subtitle_count' in m_columns else ''}
        , {time_column}
    FROM {args.table} m
    {'JOIN history h on h.media_id = m.id' if args.played else ''}
    WHERE 1=1
      AND coalesce({time_column}, 0)>0
    {'AND COALESCE(time_deleted, 0)=0' if args.hide_deleted else ""}
    ORDER BY {time_column} desc
    LIMIT {args.limit or 5}
    """
    return list(args.db.query(query, args.filter_bindings))


def remove_duplicate_data(tbl):
    for d in tbl:
        if d["play_count"] == 1:
            del d["time_first_played"]


def history() -> None:
    args = parse_args()
    m_columns = args.db["media"].columns_dict
    create(args)

    WATCHED = ["watched", "listened", "seen", "heard"]
    WATCHING = ["watching", "listening"]
    if args.facet in WATCHED + WATCHING:
        args.played = True

    history_fn = sql_utils.historical_usage_items
    if args.played:
        history_fn = sql_utils.historical_usage

    if args.facet in WATCHING:
        print(args.facet.title() + ":")
        tbl = history_fn(
            args, args.frequency, "time_played", hide_deleted=args.hide_deleted, where="and coalesce(play_count, 0)=0"
        )
        media_printer.media_printer(args, tbl)

        process_search(args, m_columns)
        query = f"""WITH m as (
                SELECT
                    SUM(CASE WHEN h.done = 1 THEN 1 ELSE 0 END) play_count
                    , MIN(h.time_played) time_first_played
                    , MAX(h.time_played) time_last_played
                    , FIRST_VALUE(h.playhead) OVER (PARTITION BY h.media_id ORDER BY h.time_played DESC) playhead
                    , path
                    {', title' if 'title' in m_columns else ''}
                    {', duration' if 'duration' in m_columns else ''}
                    {', subtitle_count' if 'subtitle_count' in m_columns else ''}
                FROM {args.table} m
                JOIN history h on h.media_id = m.id
                WHERE 1=1
                {'AND COALESCE(time_deleted, 0)=0' if args.hide_deleted else ""}
                GROUP BY m.id, m.path
            )
            SELECT *
            FROM m
            WHERE 1=1
                and playhead > 60
                and coalesce(play_count, 0) = 0
            ORDER BY time_last_played desc, playhead desc
            LIMIT {args.limit or 5}
        """
        tbl = list(args.db.query(query, args.filter_bindings))
        remove_duplicate_data(tbl)
        media_printer.media_printer(args, tbl)

    elif args.facet in WATCHED:
        print(args.facet.title() + ":")
        tbl = history_fn(
            args, args.frequency, "time_played", hide_deleted=args.hide_deleted, where="and coalesce(play_count, 0)>0"
        )
        media_printer.media_printer(args, tbl)

        process_search(args, m_columns)
        query = f"""WITH m as (
                SELECT
                    SUM(CASE WHEN h.done = 1 THEN 1 ELSE 0 END) play_count
                    , MIN(h.time_played) time_first_played
                    , MAX(h.time_played) time_last_played
                    , FIRST_VALUE(h.playhead) OVER (PARTITION BY h.media_id ORDER BY h.time_played DESC) playhead
                    , path
                    {', title' if 'title' in m_columns else ''}
                    {', duration' if 'duration' in m_columns else ''}
                    {', subtitle_count' if 'subtitle_count' in m_columns else ''}
                FROM {args.table} m
                JOIN history h on h.media_id = m.id
                WHERE 1=1
                {'AND COALESCE(time_deleted, 0)=0' if args.hide_deleted else ""}
                GROUP BY m.id, m.path
            )
            SELECT *
            FROM m
            WHERE play_count > 0
            ORDER BY time_last_played desc, path
            LIMIT {args.limit or 5}
        """
        tbl = list(args.db.query(query, args.filter_bindings))
        remove_duplicate_data(tbl)
        media_printer.media_printer(args, tbl)

    else:
        print(f"{args.facet.title()} media:")
        tbl = history_fn(args, args.frequency, f"time_{args.facet}", args.hide_deleted)
        media_printer.media_printer(args, tbl)
        tbl = recent_media(args, f"time_{args.facet}")
        remove_duplicate_data(tbl)
        media_printer.media_printer(args, tbl)


if __name__ == "__main__":
    history()
