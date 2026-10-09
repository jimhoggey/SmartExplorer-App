import subprocess

import pytest

import drive


@pytest.mark.parametrize("path", [
    r"G:\My Drive\Sunday Media",
    r"C:\Users\booth\My Drive\Sunday Media",
    r"G:\Shared drives\Media Team\Sunday Media",
    "/Users/fynn/Library/CloudStorage/GoogleDrive-me@example.com/My Drive/Sunday Media",
    "/Users/fynn/Google Drive/Sunday Media",
])
def test_drive_folders_are_recognised(path):
    assert drive.is_drive_folder(path)


@pytest.mark.parametrize("path", [r"C:\Media\Sunday", "/Users/fynn/Desktop/Slides", "", "/tmp/My Driveway"])
def test_other_folders_are_not(path):
    assert not drive.is_drive_folder(path)


def done(code, out=b""):
    return lambda argv, **kw: subprocess.CompletedProcess(argv, code, out, b"")


def test_running_on_windows_reads_the_task_list():
    yes = done(0, b'"GoogleDriveFS.exe","4321","Console","1","180,000 K"\r\n')
    no = done(0, b"INFO: No tasks are running which match the specified criteria.\r\n")
    assert drive.running(run=yes, system="win32") is True
    assert drive.running(run=no, system="win32") is False


def test_running_on_a_mac_asks_pgrep():
    seen = []

    def run(argv, **kw):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"812\n", b"")

    assert drive.running(run=run, system="darwin") is True and seen[0][:2] == ["pgrep", "-x"]
    assert drive.running(run=done(1), system="darwin") is False


def test_running_is_unknown_when_it_cannot_tell():
    def boom(argv, **kw):
        raise OSError("no tasklist")

    assert drive.running(run=boom, system="win32") is None
    assert drive.running(run=done(3), system="darwin") is None  # pgrep's own error
    assert drive.running(run=done(0), system="linux") is None
