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


def parse_date(date):
    return datetime.strptime(date, "%Y-%m-%d").date()


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
    return list(connection.execute(sql).fetchone().values())[0]


def generate_units(connection):
    sql = """
        SELECT autoid, name, jurisdiction, url, shipping_method,
               street1, street2, city, zipcode, state
        FROM units
    """
    for unit in connection.execute(sql):
        unit["id"] = unit.pop("autoid")
        yield ibp.models.Unit(**unit)


def generate_comments(connection, inmate_autoid):
    sql = f"""
        SELECT * FROM comments
        WHERE inmate_id = {inmate_autoid}
        ORDER BY datetime ASC
    """
    comments = connection.execute(sql)
    for index, comment in enumerate(comments):
        comment.pop("inmate_id")
        comment.pop("autoid")
        comment["index"] = index
        comment["datetime"] = parse_datetime(comment["datetime"])
        yield ibp.models.Comment(**comment)


def shipments_length(connection):
    sql = "SELECT COUNT(*) FROM shipments"
    return list(connection.execute(sql).fetchone().values())[0]


def generate_shipments(connection):
    shipments = connection.execute("SELECT * FROM shipments")
    for shipment in shipments:
        shipment["id"] = shipment.pop("autoid")
        shipment["date_shipped"] = parse_date(shipment["date_shipped"])
        yield ibp.models.Shipment(**shipment)


def generate_requests(connection, inmate_autoid):
    sql = f"""
        SELECT * FROM requests
        WHERE inmate_autoid = {inmate_autoid}
        ORDER BY date_postmarked ASC
    """

    requests = connection.execute(sql)

    for index, request in enumerate(requests):
        request.pop("inmate_autoid")
        request.pop("autoid")
        request["index"] = index

        request["date_processed"] = parse_date(request["date_processed"])
        request["date_postmarked"] = parse_date(request["date_postmarked"])
        request["shipment_id"] = request.pop("shipment_autoid")

        yield ibp.models.Request(**request)


def inmates_length(connection):
    sql = "SELECT COUNT(*) FROM inmates"
    return list(connection.execute(sql).fetchone().values())[0]


def generate_inmates(connection):
    inmates_sql = "SELECT autoid, id, jurisdiction FROM inmates"
    for inmate in connection.execute(inmates_sql):
        autoid = inmate.pop("autoid")
        inmate = ibp.models.Inmate(**inmate)
        inmate.comments = list(generate_comments(connection, autoid))
        inmate.requests = list(generate_requests(connection, autoid))
        yield inmate


def main():
    """Import data from IBP database"""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("filepath", help="database filepath")
    args = parser.parse_args()

    ibp.db.create_all()

    with closing(sqlite3.connect(args.filepath)) as connection:
        connection.row_factory = dict_factory

        with ibp.app.app_context():
            print("Adding units")
            units = generate_units(connection)
            progress = ProgressBar(max_value=units_length(connection))
            units = progress(units)
            ibp.db.session.add_all(units)
            ibp.db.session.commit()

            print("Adding shipments")
            shipments = generate_shipments(connection)
            progress = ProgressBar(max_value=shipments_length(connection))
            shipments = progress(shipments)
            ibp.db.session.add_all(shipments)
            ibp.db.session.commit()

            print("Adding inmates")
            inmates = generate_inmates(connection)
            progress = ProgressBar(max_value=inmates_length(connection))
            inmates = progress(inmates)
            ibp.db.session.add_all(inmates)
            ibp.db.session.commit()


if __name__ == "__main__":
    main()
