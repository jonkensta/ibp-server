#!/usr/bin/env python

from __future__ import print_function, division

import os
import json
import difflib
import tempfile
import urlparse
import argparse
import traceback
import contextlib
import subprocess
from xml.etree import ElementTree

import jinja2
import requests

###################
# Dazzle Bullshit #
###################

dazzle_template = jinja2.Template(u"""\
<DAZzle
    Start="PRINTING"
    Prompt="NO"
    AbortOnError="YES"
    SkipUnverified="NO"
    Autoclose="YES"
    OutputFile="{{ outfilename }}"
    Test="{{ "YES" if test else "NO" }}">

    <Package>
        <MailClass>LIBRARYMAIL</MailClass>
        <DateAdvance>2</DateAdvance>
        <PackageType>NONRECTPARCEL</PackageType>
        <OversizeRate>FALSE</OversizeRate>
        <WeightOz>{{ weight }}</WeightOz>
        <Value>0.0</Value>
        <Description>Free Books</Description>

        <ToName>{{ to.name }}</ToName>
        <ToAddress1>{{ to.street1 }}</ToAddress1>
        {% if to.street2 -%}<ToAddress2>{{ to.street2 }}</ToAddress2>{% endif %}
        <ToCity>{{ to.city }}</ToCity>
        <ToState>{{ to.state }}</ToState>
        <ToPostalCode>{{ to.zipcode }}</ToPostalCode>

        <ReturnAddress1>{{ return_.addressee }}</ReturnAddress1>
        <ReturnAddress2>{{ return_.street1 }}</ReturnAddress2>
        {% if return_.street2 -%}
        <ReturnAddress3>{{ return_.street2 }}</ReturnAddress3>
        {%- else -%}
        {% endif -%}
        <ReturnAddress4>{{ return_.city }}, {{ return_.state }} {{ return_.zipcode }}</ReturnAddress4>
    </Package>
</DAZzle>\
""")  # noqa

try:
    PROGRAM_FILES = os.environ['ProgramW6432']
except KeyError:
    DAZZLE = None
else:
    DAZZLE_DIR = os.path.join(PROGRAM_FILES, 'Envelope Manager', 'DAZzle')
    DAZZLE = os.path.join(DAZZLE_DIR, 'DAZZLE.EXE')


class PostageError(Exception):
    pass


def print_postage(from_, to, weight, test=False):
    test = bool(test)

    @contextlib.contextmanager
    def xml_tmpfile():
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp:
            pass  # just use tempfile to create the file
        try:
            yield tmp.name
        finally:
            os.remove(tmp.name)

    with xml_tmpfile() as infilename, xml_tmpfile() as outfilename:

        with open(infilename, 'w') as infile:
            xml = dazzle_template.render(
                to=to, return_=from_, weight=weight,
                outfilename=outfilename, test=test
            )
            infile.write(xml)

        if DAZZLE or not test:
            cmd = [DAZZLE, infile.name]
            subprocess.check_call(cmd)

        else:
            with open(outfilename, 'w') as outfile:
                outfile.write(xml)

        with open(outfilename) as outfile:
            e = ElementTree.parse(outfile).getroot()
            p = e.find('Package')

            if test:
                pic = '9400100000000000000000'
                return dict(tracking_code=pic, postage=0, weight=0)

            state = p.find('Status')
            state = state.text if state is not None else "Unknown State"

            if state != 'Success':
                raise PostageError("failed to purchase postage: " + str(state))

            pic = p.find('PIC')
            if pic is not None:
                pic = pic.text

            amt = p.find('FinalPostage')
            if amt is not None:
                amt = int(round(100 * float(amt.text)))

            wt = p.find('WeightOz')
            if wt is not None:
                wt = int(round(float(wt.text)))

            result = dict(tracking_code=pic, postage=amt, weight=wt)

        return result


#######################
# Convenience classes #
#######################

class Server(object):

    def __init__(self, url, apikey):
        self._url = url
        self._apikey = apikey

    def _post(self, path, **kwargs):
        url = urlparse.urljoin(self._url, path)
        kwargs['key'] = self._apikey
        r = requests.post(url, data=kwargs)
        r.raise_for_status()
        return json.loads(r.text)

    def unit_autoids(self):
        return self._post('unit_autoids')

    def return_address(self):
        return self._post('return_address')

    def unit_address(self, unit_id):
        return self._post('unit_address/{}'.format(unit_id))

    def request_destination(self, request_id):
        return self._post('request_destination/{}'.format(request_id))['name']

    def request_address(self, request_id):
        return self._post('request_address/{}'.format(request_id))

    def ship_requests(self, request_ids, **shipment):
        shipment = dict(shipment)
        ids = {"request_ids-%d" % k: v for k, v in enumerate(request_ids)}
        shipment.update(ids)
        return self._post('ship_requests', **shipment)


#################
# Input helpers #
#################

def query_yes_no(question, default="no"):
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        choice = raw_input(question + prompt).lower()  # noqa
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")


class ConsoleInputError(Exception):
    pass


def get_unit_from_input(units):
    unit = raw_input("Enter name of unit and press enter: ").upper()  # noqa
    num_matches, cutoff = 4, 0.0
    matches = difflib.get_close_matches(unit, units, num_matches, cutoff)

    for index, match in enumerate(matches, start=1):
        print("[%d]" % index, ':', match)

    msg = "Choose [1 - %d] corresponding to above: " % num_matches
    index = raw_input(msg)  # noqa

    try:
        return matches[int(index) - 1]
    except (ValueError, IndexError):
        raise ConsoleInputError


def get_weight_from_input():
    while True:
        prompt = "Enter weight in pounds: "
        pounds = raw_input(prompt)  # noqa
        try:
            pounds = int(pounds)
        except ValueError:
            print("Invalid weight")
            raise ConsoleInputError

        total_in_ounces = 16 * pounds
        return total_in_ounces


##############
# Generators #
##############

def generate_request_ids(prompt, stop_on_empty=False):
    prompt = str(prompt)
    stop_on_empty = bool(stop_on_empty)

    def query_done():
        return query_yes_no("Done with packages?")

    while True:
        request_id = raw_input(prompt)  # noqa

        if stop_on_empty and request_id == '' and query_done():
            raise StopIteration

        try:
            request_id = int(request_id)
        except ValueError:
            print("Invalid request ID")
            continue
        else:
            yield request_id


def generate_bulk_shipments(server, units):
    while True:
        while True:
            try:
                unit = get_unit_from_input(units)
            except ConsoleInputError:
                continue
            else:
                break

        while True:
            try:
                weight = get_weight_from_input()
            except ConsoleInputError:
                continue
            else:
                break

        yield (units[unit], weight)


############
# Commands #
############

def ship_individual(args):
    server = Server(args.url, args.apikey)

    try:
        from_ = server.return_address()
    except requests.RequestException:
        print("Could not connect to server")
        raise

    prompt = "Place request on the scale and scan ID: "
    for request_id in generate_request_ids(prompt):
        try:
            weight = get_weight_from_input()
        except ConsoleInputError:
            continue

        to = server.request_address(request_id)
        postage = print_postage(from_, to, weight, test=args.test)
        server.ship_requests([request_id], **postage)


def ship_bulk(args):
    server = Server(args.url, args.apikey)

    try:
        from_ = server.return_address()
        units = server.unit_autoids()
    except requests.RequestException:
        print("Could not connect to server")
        raise

    for unit_autoid, weight in generate_bulk_shipments(server, units):
        to = server.unit_address(unit_autoid)
        postage = print_postage(from_, to, weight, test=args.test)
        postage['unit_autoid'] = unit_autoid
        server.ship_requests([], **postage)


def main():
    """IBP shipping application"""
    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument('--apikey')
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--test', action='store_true', default=False)

    subparsers = parser.add_subparsers()

    parser_individual = subparsers.add_parser(
        'individual', help="ship individual packages"
    )
    parser_individual.set_defaults(ship=ship_individual)

    parser_bulk = subparsers.add_parser(
        'bulk', help="ship bulk packages"
    )
    parser_bulk.set_defaults(ship=ship_bulk)

    args = parser.parse_args()

    try:
        args.ship(args)
    except Exception as exc:
        print("Error: " + str(exc))
        traceback.print_exc()
        raw_input("Hit any key to close")  # noqa


if __name__ == '__main__':
    main()
