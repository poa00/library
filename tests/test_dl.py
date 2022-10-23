import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from xklb import consts, utils
from xklb.db import connect
from xklb.dl_extract import dl_block, dl_download
from xklb.tube_backend import yt
from xklb.tube_extract import tube_add, tube_update

PLAYLIST_URL = "https://youtube.com/playlist?list=PLVoczRgDnXDLWV1UJ_tO70VT_ON0tuEdm"
PLAYLIST_VIDEO_URL = "https://www.youtube.com/watch?v=QoXubRvB6tQ"
STORAGE_PREFIX = str(Path("tests/data/").resolve())

dl_db = "--db", str(Path("tests/data/dl.db").resolve())
tube_add([*dl_db, "-c=Self", PLAYLIST_URL])

tube_db = "--db", str(Path("tests/data/tube_dl.db").resolve())
tube_add([*tube_db, PLAYLIST_URL])


class TestTube(unittest.TestCase):
    def test_yt(self):
        tube_add([*dl_db, "-c=Self", PLAYLIST_URL])

        args = Namespace(
            database=dl_db[1],
            profile="video",
            dl_config={},
            prefix=STORAGE_PREFIX,
            ext=None,
            ignore_errors=False,
            small=False,
            verbose=0,
        )
        args.db = connect(args)
        yt(args, dict(path=PLAYLIST_VIDEO_URL, dl_config="{}", category="Self"))

    @mock.patch("xklb.tube_backend.yt")
    @mock.patch("xklb.tube_backend.process_playlist")
    def test_tube_dl_conversion(self, process_playlist, mocked_yt):
        tube_add([*tube_db, "-c=Self", PLAYLIST_URL])
        out = process_playlist.call_args[0][1]
        assert out == PLAYLIST_URL

        dl_download([*tube_db, "--prefix", STORAGE_PREFIX, "--video"])
        out = mocked_yt.call_args[0]
        assert out[1]["path"] == PLAYLIST_VIDEO_URL

    @mock.patch("xklb.tube_backend.yt")
    def test_download(self, mocked_yt):
        with utils.file_temp_copy(dl_db[1]) as dbo:
            dl_download(["--db", dbo.name, "--prefix", STORAGE_PREFIX, "--audio"])
            out = mocked_yt.call_args[0]
            assert out[1]["path"] == PLAYLIST_VIDEO_URL

    @mock.patch("xklb.tube_backend.update_playlists")
    def test_dlupdate(self, update_playlists):
        with utils.file_temp_copy(dl_db[1]) as dbo:
            tube_update(["--db", dbo.name])
            out = update_playlists.call_args[0]
            assert out[1][0]["path"] == PLAYLIST_URL

    @mock.patch("xklb.tube_backend.update_playlists")
    def test_dlupdate_subset_category(self, update_playlists):
        with utils.file_temp_copy(dl_db[1]) as dbo:
            tube_update(["--db", dbo.name, "-c=Self"])
            out = update_playlists.call_args[0]
            assert out[1][0]["path"] == PLAYLIST_URL

    def test_block_existing(self):
        with utils.file_temp_copy(dl_db[1]) as dbo:
            dl_block([dbo.name, PLAYLIST_URL])
            db = connect(Namespace(database=dbo.name, verbose=2))
            playlists = list(db["playlists"].rows)
            assert playlists[0]["time_deleted"] != 0
            assert playlists[0]["category"] == consts.BLOCK_THE_CHANNEL
