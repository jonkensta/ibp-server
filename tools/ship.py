#!/usr/bin/env python

from __future__ import print_function, division

import os
import json
import difflib
import tempfile
import urlparse
import argparse
import contextlib
import subprocess
from xml.etree import ElementTree

import jinja2
import requests

import usb.core
import usb.util

try:
    import winsound
except ImportError:
    def beep_warning():
        pass
else:
    def beep_warning():
        frequencies = [2500, 3500, 2500]
        durations = [0.5, 0.5, 0.5]
        for frequency, duration in zip(frequencies, durations):
            winsound.Beep(frequency, duration)

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

            state = p.find('status')
            state = (test and 'Success') or (state and state.text) or 'Failed'

            if state != 'Success':
                raise PostageError("failed to purchase postage")

            pic = p.find('PIC')
            test_pic = "9400100000000000000000"
            pic = (test and test_pic) or (pic is not None and pic.text)

            amt = p.find('FinalPostage')
            test_amt = "0.0"
            amt = (test and test_amt) or (amt is not None and amt.text)

            wt = p.find('WeightOz')
            test_wt = "0.0"
            wt = (test and test_wt) or (wt is not None and wt.text)

            result = dict(tracking_code=pic, postage=amt, weight=wt)

        return result


#######################
# Convenience classes #
#######################

class DymoScale(object):

    # values shamelessly stolen from here:
    # http://steventsnyder.com/reading-a-dymo-usb-scale-using-python/
    VENDOR_ID = 0x0922
    PRODUCT_ID = 0x8003

    def __init__(self, num_attempts=10, vendor_id=VENDOR_ID, product_id=PRODUCT_ID):  # noqa

        self._device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if self._device is None:
            msg = "Dymo scale not turned on or plugged in?"
            raise ValueError(msg)

        self._num_attempts = int(num_attempts)

    @staticmethod
    def _grams_to_ounces(grams):
        FACTOR = 0.035274
        ounces = grams * FACTOR
        return round(ounces, ndigits=1)

    @staticmethod
    def _data_to_weight(data):
        GRAMS_MODE = 2
        OUNCES_MODE = 11

        raw_weight = data[4] + data[5] * 256

        if data[2] == OUNCES_MODE:
            ounces = raw_weight * 0.1
        elif data[2] == GRAMS_MODE:
            ounces = DymoScale._grams_to_ounces(raw_weight)
        else:
            ounces = None

        return ounces

    def _read(self):
        endpoint = self._device[0][(0, 0)][0]
        address = endpoint.bEndpointAddress
        size = endpoint.wMaxPacketSize

        last_exception = None
        for _ in range(self._num_attempts):
            try:
                data = self._device.read(address, size)
            except usb.core.USBError as e:
                last_exception = e
            else:
                return DymoScale._data_to_weight(data)

        raise last_exception

    def sample(self, stability_count=2):
        """Return instantaneous weight in ounces."""

        raw = None
        last_raw = None

        default_count = int(stability_count)
        count = default_count

        while count > 0:
            raw = self._read()
            if last_raw is None or raw != last_raw:  # precise to +/- 2g
                count = default_count
                last_raw = raw
            else:
                count -= 1

        return raw

    def configure(self):
        try:
            if self._device.is_kernel_driver_active(0):
                self._reattach = True
                self._device.detach_kernel_driver(0)
        except Exception:
            self._reattach = False

        self._device.set_configuration()

    def close(self):
        if self._reattach:
            try:
                self._device.attach_kernel_driver(0)
            except Exception:
                pass

        usb.util.dispose_resources(self._device)

    def __enter__(self):
        self.configure()
        return self

    def __exit__(self, *args):
        self.close()


class MockScale(object):

    def sample(self):
        return 32.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


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
        return self._post('ship_requests', request_ids=request_ids, **shipment)


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
        prompt = "Enter weight in format POUNDS.OUNCES: "
        weight = raw_input(prompt)  # noqa
        try:
            weight = float(weight)
        except ValueError:
            print("Invalid weight")
            continue

        pounds = int(weight)
        ounces = 100 * (weight % 1)
        if ounces >= 16:
            print("Invalid ounces")
            continue

        total_in_ounces = 16 * pounds + ounces

        def round_up(value):
            return int(value + 1)

        return round_up(total_in_ounces)


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
        try:
            unit = get_unit_from_input(units)
        except ConsoleInputError:
            continue

        request_ids = []
        prompt = "Scan request ID: "
        for id_ in generate_request_ids(prompt, stop_on_empty=True):
            try:
                request_unit = server.request_destination(id_)
            except requests.exceptions.RequestException:
                print("Could not find info for request '%d'" % id_)
                beep_warning()
                continue

            if request_unit != unit:
                msg = ("Request '{:d}' destined for unit '{}' not '{}'"
                       .format(id_, request_unit, unit))
                print(msg)
                beep_warning()
                continue

            else:
                request_ids.append(id_)

        if not request_ids:
            print("No requests were selected")
            continue

        weight = get_weight_from_input()
        yield (units[unit], weight, request_ids)


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

    with (DymoScale() if not args.test else MockScale()) as scale:
        prompt = "Place request on the scale and scan ID: "
        for request_id in generate_request_ids(prompt):
            weight = scale.sample()
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

    for bulk_shipment in generate_bulk_shipments(server, units):
        unit_autoid, weight, request_ids = bulk_shipment
        to = server.unit_address(unit_autoid)
        postage = print_postage(from_, to, weight, test=args.test)
        server.ship_requests(request_ids, **postage)


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
    args.ship(args)


if __name__ == '__main__':
    main()
