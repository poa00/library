import argparse, html
from urllib.parse import urlparse

from xklb import db, utils
from xklb.utils import log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="library reddit-selftext",
        usage="""library reddit-selftext DATABASE

    Extract URLs from reddit selftext from the reddit_posts table to the media table
""",
    )
    parser.add_argument("database")
    parser.add_argument("--verbose", "-v", action="count", default=0)
    args = parser.parse_args()

    args.db = db.connect(args)
    log.info(utils.dict_filter_bool(args.__dict__))
    return args


def get_page_links(path, text):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html.unescape(text), "lxml")
    internal_links = set()
    external_links = set()

    for a in soup.findAll("a", attrs={"href": True}):
        href = a["href"].strip()
        if all([len(href) > 1, href[0] != "#", "javascript:" not in href, "mailto:" not in href, "tel:" not in href]):
            if "http" in href or "https" in href:
                if urlparse(path).netloc.lower() in urlparse(href).netloc.lower():
                    internal_links.add(a["href"])
                else:
                    external_links.add(a["href"])
            else:
                utils.log.debug(a["href"])

    return internal_links, external_links


def reddit_selftext() -> None:
    from markdown import markdown

    args = parse_args()
    m_columns = args.db["media"].columns_dict

    reddit_posts = list(
        args.db.query(
            f"""
            select path, selftext
            from reddit_posts
            where 1=1
                {'AND path not in (select distinct webpage from media where webpage is not null)' if 'webpage' in m_columns else ''}
            """,
        ),
    )

    for d in reddit_posts:
        html_data = markdown(d["selftext"])
        internal_links, external_links = get_page_links(d["path"], html_data)
        if internal_links:
            for i_link in internal_links:
                log.info(i_link)

        for e_link in external_links:
            args.db["media"].upsert({**d, "path": e_link, "webpage": d["path"]}, pk="path", alter=True)


if __name__ == "__main__":
    reddit_selftext()