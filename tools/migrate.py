from __future__ import print_function

import os
import tempfile
import argparse
import itertools
import subprocess
from datetime import datetime
from contextlib import closing

import sqlite3
from progressbar import ProgressBar

local_dir = os.path.dirname(os.path.realpath(__file__))  # noqa
os.sys.path.append(os.path.join(local_dir, os.path.pardir))  # noqa

import ibp
from ibp.models import Unit, Request, Inmate, Comment


def parse_date(date):
    return datetime.strptime(date, '%Y-%m-%d').date()


def parse_date_or_None(date):
    return (date is not None) and parse_date(date) or None


def parse_datetime(dt):
    return datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")


def parse_datetime_or_None(dt):
    return (dt is not None) and parse_datetime(dt) or None


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def units_length(connection):
    sql = "SELECT COUNT(*) FROM units"
    return connection.execute(sql).fetchone().values()[0]


def generate_units(connection):
    sql = """
        SELECT
            id, name, jurisdiction, url, shipping_method,
            street1, street2, city, zipcode, state
        FROM units
    """
    for unit in connection.execute(sql):
        unit['autoid'] = unit.pop('id')
        yield Unit(**unit)


def requests_length(connection):
    sql = "SELECT COUNT(*) FROM packages"
    return connection.execute(sql).fetchone().values()[0]


def generate_requests(connection, session):
    sql = """
        SELECT
            id, date_postmarked, date_filled, action,
            inmate_id, inmate_jurisdiction
        FROM packages
    """

    action_map = {
        'Tossed': 'Tossed',
        'Cancelled': 'Tossed',
        'Filled': 'Filled',
        'Shipped': 'Filled',
    }

    for request in connection.execute(sql):
        request['autoid'] = request.pop('id')

        date_postmarked = request.pop('date_postmarked')
        request['date_postmarked'] = parse_date_or_None(date_postmarked)

        date_filled = request.pop('date_filled')
        if date_filled is not None:
            request['date_processed'] = parse_date_or_None(date_filled)
        else:
            request['date_processed'] = parse_date_or_None(date_postmarked)

        request['action'] = action_map.get(request['action'])

        inmate_id = request.pop('inmate_id')
        inmate_id = int(inmate_id.replace('-', ''))
        inmate_jurisdiction = request.pop('inmate_jurisdiction')
        inmate = Inmate.as_unique(inmate_jurisdiction, inmate_id)
        request['inmate'] = inmate

        yield Request(**request)


def comments_length(connection):
    sql = """
        SELECT COUNT(*)
        FROM comments
        WHERE body <> '' AND
              datetime <> "1990-01-01 01:01:01.000000"
    """
    return connection.execute(sql).fetchone().values()[0]


def generate_comments(connection, session):
    sql = """
        SELECT
            id, datetime, body, author,
            inmate_id, inmate_jurisdiction
        FROM comments
        WHERE body <> '' AND datetime <> "1990-01-01 01:01:01.000000"
    """
    for comment in connection.execute(sql):
        comment['author'] = comment['author'].strip().title()
        comment['autoid'] = comment.pop('id')
        comment['datetime'] = parse_datetime_or_None(comment['datetime'])

        inmate_id = comment.pop('inmate_id')
        inmate_id = int(inmate_id.replace('-', ''))
        inmate_jurisdiction = comment.pop('inmate_jurisdiction') or 'Texas'
        inmate = Inmate.as_unique(inmate_jurisdiction, inmate_id)
        comment['inmate_id'] = inmate.autoid

        yield Comment(**comment)


def edit_comment(comment):
    with tempfile.NamedTemporaryFile(suffix=".tmp") as tf:
        tf.write(comment.body)
        tf.flush()
        subprocess.check_call(['vim', tf.name])

        tf.seek(0)
        comment.body = tf.read()
        return comment if comment.body.strip() else None


def main():
    """Import data from IBP database"""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('filepath', help="Database filepath")
    parser.add_argument('--edit_comments', action='store_true', default=False)
    args = parser.parse_args()

    with closing(sqlite3.connect(args.filepath)) as connection:
        connection.row_factory = dict_factory

        with ibp.app.app_context():
            session = ibp.db.session

            print("Adding units")
            units = generate_units(connection)
            progress = ProgressBar(units_length(connection))
            units = progress(units)
            session.add_all(units)
            session.commit()

            print("Adding comments")
            comments = generate_comments(connection, session)
            progress = ProgressBar(comments_length(connection))
            comments = progress(comments)

            if args.edit_comments:
                comments = itertools.imap(edit_comment, comments)
                comments = itertools.ifilter(None, comments)

            session.add_all(comments)
            session.commit()

            print("Adding requests")
            requests = generate_requests(connection, session)
            progress = ProgressBar(requests_length(connection))
            requests = progress(requests)
            session.add_all(requests)
            session.commit()


if __name__ == '__main__':
    main()
