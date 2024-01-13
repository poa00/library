import argparse, json, sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from xklb import db_media, db_playlists, usage
from xklb.scripts import links_extract
from xklb.utils import arg_utils, db_utils, objects, web
from xklb.utils.log_utils import log


def parse_args(**kwargs):
    parser = argparse.ArgumentParser(**kwargs)
    parser.add_argument("--category", "-c", help=argparse.SUPPRESS)
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--fixed-pages", "--backfill", type=int)
    parser.add_argument("--stop-known", type=int, default=10)
    parser.add_argument("--stop-link")
    parser.add_argument("--page-step", "--step", "-S", type=int, default=1)
    parser.add_argument("--page-start", "--start", type=int)

    parser.add_argument(
        "--path-include",
        "--include-path",
        "--include",
        "-s",
        nargs="*",
        default=[],
        help="path substrings for inclusion (all must match to include)",
    )
    parser.add_argument(
        "--text-include",
        "--include-text",
        nargs="*",
        default=[],
        help="link text substrings for inclusion (all must match to include)",
    )
    parser.add_argument(
        "--after-include",
        "--include-after",
        nargs="*",
        default=[],
        help="plain text substrings after URL for inclusion (all must match to include)",
    )
    parser.add_argument(
        "--before-include",
        "--include-before",
        nargs="*",
        default=[],
        help="plain text substrings before URL for inclusion (all must match to include)",
    )
    parser.add_argument(
        "--path-exclude",
        "--exclude-path",
        "--exclude",
        "-E",
        nargs="*",
        default=["javascript:", "mailto:", "tel:"],
        help="path substrings for exclusion (any must match to exclude)",
    )
    parser.add_argument(
        "--text-exclude",
        "--exclude-text",
        nargs="*",
        default=[],
        help="link text substrings for exclusion (any must match to exclude)",
    )
    parser.add_argument(
        "--after-exclude",
        "--exclude-after",
        nargs="*",
        default=[],
        help="plain text substrings after URL for exclusion (any must match to exclude)",
    )
    parser.add_argument(
        "--before-exclude",
        "--exclude-before",
        nargs="*",
        default=[],
        help="plain text substrings before URL for exclusion (any must match to exclude)",
    )
    parser.add_argument("--strict-include", action="store_true", help="All include args must resolve true")
    parser.add_argument("--strict-exclude", action="store_true", help="All exclude args must resolve true")
    parser.add_argument("--case-sensitive", action="store_true", help="Filter with case sensitivity")

    parser.add_argument("--cookies", help="path to a Netscape formatted cookies file")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER[+KEYRING][:PROFILE][::CONTAINER]")

    parser.add_argument("--selenium", action="store_true")
    parser.add_argument("--manual", action="store_true", help="Confirm manually in shell before exiting the browser")
    parser.add_argument("--scroll", action="store_true", help="Scroll down the page; infinite scroll")
    parser.add_argument("--auto-pager", "--autopager", action="store_true")
    parser.add_argument("--poke", action="store_true")
    parser.add_argument("--chrome", action="store_true")

    parser.add_argument(
        "--extra-playlist-data",
        default={},
        nargs=1,
        action=arg_utils.ArgparseDict,
        metavar="KEY=VALUE",
    )

    parser.add_argument("--db", "-db", help=argparse.SUPPRESS)
    parser.add_argument("--verbose", "-v", action="count", default=0)

    parser.add_argument("--local-html", action="store_true", help="Treat paths as Local HTML files")
    parser.add_argument("--file", "-f", help="File with one URL per line")

    parser.add_argument("database", help=argparse.SUPPRESS)
    if "add" in kwargs["prog"]:
        parser.add_argument("paths", nargs="*", action=arg_utils.ArgparseArgsOrStdin, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.auto_pager:
        args.fixed_pages = 1

    if args.scroll:
        args.selenium = True

    if not args.case_sensitive:
        args.before_include = [s.lower() for s in args.before_include]
        args.path_include = [s.lower() for s in args.path_include]
        args.text_include = [s.lower() for s in args.text_include]
        args.after_include = [s.lower() for s in args.after_include]
        args.before_exclude = [s.lower() for s in args.before_exclude]
        args.path_exclude = [s.lower() for s in args.path_exclude]
        args.text_exclude = [s.lower() for s in args.text_exclude]
        args.after_exclude = [s.lower() for s in args.after_exclude]

    if args.db:
        args.database = args.db
    Path(args.database).touch()
    args.db = db_utils.connect(args)

    log.info(objects.dict_filter_bool(args.__dict__))
    return args


def add_playlist(args, path):
    info = {
        "extractor_config": {k: v for k, v in args.__dict__.items() if k not in ["db", "database", "verbose", "paths"]},
        "time_deleted": 0,
    }
    args.playlist_id = db_playlists.add(args, str(path), info)


def add_media(args, variadic):
    for a_ref_or_path in variadic:
        if isinstance(a_ref_or_path, str):
            path = a_ref_or_path
            d = objects.dict_filter_bool(db_media.consolidate_url(args, path))
        else:
            a_ref = a_ref_or_path
            d = objects.dict_filter_bool({**db_media.consolidate_url(args, a_ref.link), "title": a_ref.text.strip()})
        db_media.add(args, d)


def set_page_number(input_string, page_number):
    parsed_url = urlparse(input_string)
    query_params = parse_qs(parsed_url.query)
    query_params["page"] = [str(page_number)]
    updated_query = urlencode(query_params, doseq=True)
    modified_url = urlunparse(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, updated_query, parsed_url.fragment)
    )

    return modified_url


def count_pages(args):
    page_limit = args.fixed_pages or args.max_pages
    start_page = args.page_start or 1
    if page_limit:
        yield from range(start_page, start_page + (page_limit * args.page_step), args.page_step)
    else:
        page_num = start_page
        while True:
            yield page_num
            page_num += args.page_step


def extractor(args, playlist_path):
    known_media = set()
    end_of_playlist = False
    page_limit = args.fixed_pages or args.max_pages

    new_media = 0
    for page_num in count_pages(args):
        if end_of_playlist:
            break

        if page_limit == 1 and args.page_start is None:
            page_path = playlist_path
        else:
            page_path = set_page_number(playlist_path, page_num)

        log.info("Loading page #%s: %s", page_num, page_path)
        for a_ref in links_extract.get_inner_urls(args, page_path):
            if a_ref.link == args.stop_link or (len(known_media) > args.stop_known and not args.fixed_pages):
                end_of_playlist = True
                break

            if db_media.exists(args, a_ref.link):
                known_media.add(a_ref.link)
            else:
                add_media(args, [a_ref])
                new_media += 1

    return new_media


def links_add() -> None:
    args = parse_args(prog="library links-add", usage=usage.links_add)

    if args.no_extract:
        add_media(args, list(arg_utils.gen_urls(args)))
        sys.exit(0)

    if args.selenium:
        web.load_selenium(args)
    try:
        for playlist_path in arg_utils.gen_urls(args):
            add_playlist(args, playlist_path)
            extractor(args, playlist_path)

    finally:
        if args.selenium:
            web.quit_selenium(args)


def links_update() -> None:
    args = parse_args(prog="library links-update", usage=usage.links_update)

    link_playlists = db_playlists.get_all(
        args,
        order_by="""ROW_NUMBER() OVER ( PARTITION BY
            hostname
            , category
        ) -- prefer to spread hostname, category over time
        length(path)-length(REPLACE(path, '/', '')) desc
        , path
        """,
    )

    try:
        web.load_selenium(args)
    except Exception:
        pass

    try:
        for playlist in link_playlists:
            extractor_config = json.loads(playlist.get("extractor_config") or "{}")
            args_env = argparse.Namespace(**{**extractor_config, **args.__dict__})

            new_media = extractor(args_env, playlist["path"])

            if new_media > 0:
                db_playlists.decrease_update_delay(args, playlist["path"])
            else:
                db_playlists.increase_update_delay(args, playlist["path"])

    finally:
        try:
            web.quit_selenium(args)
        except Exception:
            pass


if __name__ == "__main__":
    links_add()
