import os
import json
import tempfile
import urlparse
import argparse
import subprocess
from xml.etree import ElementTree

import jinja2
import requests

import usb.core
import usb.util


dazzle_template = jinja2.Template(u"""
<DAZzle
    Start="PRINTING"
    Prompt="NO"
    AbortOnError="YES"
    SkipUnverified="NO"
    Autoclose="YES"
    OutputFile='{{ outfilename }}'
    Test="NO">

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
        {% if to.street2 %}
            <ToAddress2>{{ to.street2 }}</ToAddress2>
        {% endif %}
        <ToCity>{{ to.city }}</ToCity>
        <ToState>{{ to.state }}</ToState>
        <ToPostalCode>{{ to.zipcode }}</ToPostalCode>

        <ReturnAddress1>{{ return_['addressee'] }}</ReturnAddress1>
        <ReturnAddress2>{{ return_['street1'] }}</ReturnAddress2>
        {% if 'street2' in return_ %}
            <ReturnAddress3>{{ return_['street2'] }}</ReturnAddress3>
        {% endif %}
        <ReturnAddress4>
            {{ return_['city'] }},
            {{ return_['state'] }}
            {{ return_['zipcode'] }}
        </ReturnAddress4>
    </Package>
</DAZzle>
""")

try:
    PROGRAM_FILES = os.environ['ProgramW6432']
except KeyError:
    DAZZLE = None
else:
    DAZZLE = os.path.join(PROGRAM_FILES, 'DAZzle', 'DAZZLE.EXE')


def purchase_and_print_postage(from_, to, weight):
    File = tempfile.NamedTemporaryFile(suffix='.xml')
    with File() as infile, File() as outfile:
        xml = dazzle_template.render(
            to=to, return_=from_, weight=weight, outfilename=outfile.name
        )
        infile.write(xml)
        infile.flush()

        cmd = [DAZZLE, infile.name]
        subprocess.check_call(cmd)

        e = ElementTree.parse(outfile.name).getroot()
        return e


class DymoScale(object):

    def __init__(self, num_attempts=10, vendor_id=0x0922, product_id=0x8003):

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

    def request_addresses(self, request_id):
        path = 'request_addresses/{}'.format(request_id)
        addresses = self._post(path)
        from_ = addresses['from_address']
        to = addresses['to_address']
        return from_, to

    def ship_request(self, request_id, weight, tracking_code):
        path = 'ship_request/{}'.format(request_id)
        self._post(path, weight=weight, tracking_code=tracking_code)


def generate_request_ids():
    while True:
        request_id = raw_input("Place request on the scale and scan ID: ")  # noqa
        try:
            request_id = int(request_id)
        except ValueError:
            print("Invalid request ID")
            continue
        else:
            yield request_id


def main():
    desc = "IBP shipping application"
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--apikey')

    args = parser.parse_args()
    server = Server(args.url, args.apikey)

    with MockScale() as scale:
        for request_id in generate_request_ids():
            from_, to = server.request_addresses(request_id)
            weight = scale.sample()
            e = purchase_and_print_postage(from_, to, weight)
            print(e)


if __name__ == '__main__':
    main()
