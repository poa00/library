import os, shutil, sys, tempfile
from io import StringIO
from pathlib import Path

import pytest


class MockStdin:
    def __init__(self, input_text):
        self.input_text = input_text
        self.original_stdin = None

    def __enter__(self):
        self.original_stdin = sys.stdin
        sys.stdin = StringIO(self.input_text)

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdin = self.original_stdin


@pytest.fixture
def mock_stdin():
    def _mock_stdin(input_text):
        return MockStdin(input_text)

    return _mock_stdin


def create_file_tree(parent_dir, tree):
    for name, contents in tree.items():
        path = Path(parent_dir, name)
        if isinstance(contents, dict):
            os.makedirs(path)
            create_file_tree(path, contents)
        else:
            path.write_text(contents)


@pytest.fixture
def temp_file_tree(request):
    def _create_temp_file_tree(tree):
        temp_dir = tempfile.mkdtemp()
        create_file_tree(temp_dir, tree)
        request.addfinalizer(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    return _create_temp_file_tree


@pytest.fixture
def temp_db(request):
    def _create_temp_db():
        def remove_file(file_name):
            try:
                Path(file_name).unlink()
            except OSError:
                pass

        temp_db_name = tempfile.mktemp(".db")
        Path(temp_db_name).touch()
        request.addfinalizer(lambda: remove_file(temp_db_name))
        return temp_db_name

    return _create_temp_db


def generate_file_tree_dict(temp_dir, inodes=True):
    def _generate_tree_dict(directory):
        tree_dict = {}
        for item in directory.iterdir():
            if item.is_file():
                with item.open() as file:
                    tree_dict[item.name] = (item.stat().st_ino if inodes else 0, file.read())
            elif item.is_dir():
                tree_dict[item.name] = _generate_tree_dict(item)
        return tree_dict

    base_path = Path(temp_dir)
    return _generate_tree_dict(base_path)


def test_file_tree_creation(temp_file_tree):
    file_tree = {
        "folder1": {"file1.txt": "Content of file 1", "subfolder1": {"file2.txt": "Content of file 2"}},
        "folder2": {"file3.txt": "Content of file 3"},
        "file4.txt": "Content of file 4",
    }

    temp_dir = temp_file_tree(file_tree)

    assert Path(temp_dir).exists()
    assert Path(temp_dir, "file4.txt").read_text() == "Content of file 4"
    assert Path(temp_dir, "folder1", "subfolder1").is_dir()
    assert file_tree == generate_file_tree_dict(temp_dir)

    file_tree = {}
    temp_dir = temp_file_tree(file_tree)
    assert file_tree == generate_file_tree_dict(temp_dir)

    file_tree = {"folder1": {}}
    temp_dir = temp_file_tree(file_tree)
    assert file_tree == generate_file_tree_dict(temp_dir)

    file_tree = {"file4.txt": "Content of file 4"}
    temp_dir = temp_file_tree(file_tree)
    assert file_tree == generate_file_tree_dict(temp_dir)
