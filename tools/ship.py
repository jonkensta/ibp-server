import os
import json
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


dazzle_template = jinja2.Template(u"""\
<DAZzle
    Start="PRINTING"
    Prompt="NO"
    AbortOnError="YES"
    SkipUnverified="NO"
    Autoclose="YES"
    OutputFile='{{ outfilename }}'
    Test={{ "YES" if test else "NO" }}>

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
</DAZzle>\
""")

try:
    PROGRAM_FILES = os.environ['ProgramW6432']
except KeyError:
    pass
else:
    DAZZLE_DIR = os.path.join(PROGRAM_FILES, 'Envelope Manager', 'DAZzle')
    DAZZLE = os.path.join(DAZZLE_DIR, 'DAZZLE.EXE')


class PostageError(Exception):
    pass


def purchase_and_print_postage(from_, to, weight, test=False):

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
                outfilename=outfilename, test=bool(test)
            )
            infile.write(xml)

        cmd = [DAZZLE, infile.name]
        subprocess.check_call(cmd)

        with open(outfilename) as outfile:
            e = ElementTree.parse(outfile).getroot()
            p = e.find('Package')

            status = p.find('status')
            status = status and status.text or 'Failure'

            if not test and status != 'Success':
                raise PostageError("failed to purchase postage")

            pic = p.find('PIC')
            pic = pic and str(pic.text) or None

            amt = p.find('FinalPostage')
            amt = amt and float(amt.text) or None

            wt = p.find('WeightOz')
            wt = wt and float(wt.text) or None

            result = dict(tracking_code=pic, amount=amt, weight=wt)

        return result


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

    def unit_autoids(self):
        return self._post('unit_autoids')

    def return_address(self):
        return self._post('return_address')

    def unit_address(self, unit_id):
        return self._post('unit_address/{}'.format(unit_id))

    def request_address(self, request_id):
        return self._post('request_address/{}'.format(request_id))

    def ship_request(self, request_id, weight, tracking, postage):
        path = 'ship_request/{}'.format(request_id)
        self._post(path, weight=weight, tracking=tracking, postage=postage)


def generate_request_ids():
    while True:
        msg = "Place request on the scale and scan ID: "
        request_id = raw_input(msg)  # noqa
        try:
            request_id = int(request_id)
        except ValueError:
            print("Invalid request ID")
            continue
        else:
            yield request_id


def main():
    """IBP shipping application"""
    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument('--apikey')
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--test', action='store_true', default=False)

    args = parser.parse_args()
    server = Server(args.url, args.apikey)
    from_ = server.return_address()

    with MockScale() as scale:
        for request_id in generate_request_ids():
            weight = scale.sample()
            to = server.request_address(request_id)
            e = purchase_and_print_postage(from_, to, weight, test=args.test)
            print(e)


if __name__ == '__main__':
    main()
