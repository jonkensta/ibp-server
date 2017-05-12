#!/usr/bin/env python2

import os
from os.path import abspath, join, dirname, pardir
import subprocess
from datetime import datetime

LOCAL_DIR = abspath(join(dirname(abspath(__file__)), pardir))

DB_FPATH = os.path.join(LOCAL_DIR, 'data.db')
CONFIG_FILE = os.path.join(LOCAL_DIR, 'conf', 'dropbox_uploader')
DROPBOX_COMMAND = os.path.join(LOCAL_DIR, 'tools', 'dropbox_uploader.sh')
BUFFER_SIZE = 100


def call_dropbox(*args):
    command = [DROPBOX_COMMAND, '-q', '-f', CONFIG_FILE] + list(args)
    return subprocess.check_output(command)


def list_files():
    output = call_dropbox('list')
    lines = output.split('\n')
    lines = filter(None, lines)
    files = []
    for line in lines:
        tokens = line.split(None, 2)
        if tokens[0] == '[F]':
            files.append(tokens[-1])
    return files


def upload(src, dst):
    return call_dropbox('upload', src, dst)


def delete(dst):
    return call_dropbox('delete', dst)


def main():
    src = DB_FPATH
    dst = 'data-' + str(datetime.now()) + '.db'
    upload(src, dst)

    files = sorted(list_files(), reverse=True)
    to_delete = files[BUFFER_SIZE:]

    for file_ in to_delete:
        delete(file_)


if __name__ == '__main__':
    main()
