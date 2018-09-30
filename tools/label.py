#!/usr/bin/env python

import json
import time
import argparse
import tempfile
import threading
import http.server
from queue import Queue
from urllib.parse import parse_qs

import cups
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def code39(s, size):
    writer = ImageWriter()
    options = dict(write_text=False, writer=writer, dpi=300, quiet_zone=0)

    def px2mm(px):
        return 25.4*px / options['dpi']

    code = barcode.Code39(str(s), writer=writer, add_checksum=False)

    raw = code.build()
    modules_per_line = len(raw[0])
    w = px2mm(size[0]) / modules_per_line
    options['module_width'] = w

    h = px2mm(size[1]) - 2  # barcode adds this for some reason
    options['module_height'] = h

    return code.render(options)


def box_size(box):
    (y0, x0), (y1, x1) = box
    return y1 - y0, x1 - x0


def fit_font(size, text):
    size_h, size_w = size

    min_, max_ = 1, 100
    while abs(max_ - min_) > 1:
        font_size = int(round((max_ - min_) / 2)) + min_

        font = fit_font.fonts[font_size]
        text_h, text_w = font.getsize(text)

        if text_h < size_h and text_w < size_w:
            min_ = font_size
        else:
            max_ = font_size

    font = fit_font.fonts[min_]
    return font


fit_font.fonts = {
    font_size: ImageFont.truetype('DejaVuSansMono.ttf', font_size)
    for font_size in range(1, 100)
}


def round_box(box):
    (w0, h0), (w1, h1) = box
    w0, h0, w1, h1 = map(round, (w0, h0, w1, h1))
    w0, h0, w1, h1 = map(int, (w0, h0, w1, h1))
    return (w0, h0), (w1, h1)


def fit_text(draw, box, text):
    text = str(text)
    lhs, _ = round_box(box)
    size = box_size(box)

    font = fit_font(size, text)
    text_size = font.getsize(text)

    x = lhs[0] + round((size[0] - text_size[0]) / 2)
    y = lhs[1] + round((size[1] - text_size[1]) / 2)

    draw.text((x, y), text, font=font)


def add_barcode(image, label, box):
    lhs, rhs = round_box(box)
    size = rhs[0] - lhs[0], rhs[1] - lhs[1]
    barcode = code39(label, size)
    image.paste(barcode, lhs)


def render(label):
    size = w, h = 1300, 500
    image = Image.new('L', size, color=(255,))
    draw = ImageDraw.Draw(image)

    # package ID barcode
    box = (0.68*w, 0.00*h), (1.00*w, 0.10*h)
    fit_text(draw, box, 'package ID')

    box = (0.68*w, 0.10*h), (1.00*w, 0.50*h)
    add_barcode(image, label['package_id'], box)

    box = (0.68*w, 0.50*h), (1.00*w, 0.60*h)
    fit_text(draw, box, label['package_id'])

    # inmate ID barcode
    box = (0.02*w, 0.00*h), (0.65*w, 0.10*h)
    fit_text(draw, box, 'inmate ID')

    box = (0.02*w, 0.10*h), (0.65*w, 0.50*h)
    add_barcode(image, label['inmate_id'], box)

    box = (0.02*w, 0.50*h), (0.65*w, 0.60*h)
    fit_text(draw, box, label['inmate_id'])

    # inmate name
    box = (0.00*w, 0.60*h), (1.00*w, 0.90*h)
    fit_text(draw, box, label['inmate_name'])

    # other info at bottom
    box = (0.00*w, 0.90*h), (0.33*w, 1.00*h)
    fit_text(draw, box, label['inmate_jurisdiction'])

    box = (0.33*w, 0.90*h), (0.67*w, 1.00*h)
    fit_text(draw, box, label['unit_name'])

    box = (0.67*w, 0.90*h), (1.00*w, 1.00*h)
    fit_text(draw, box, label['unit_shipping_method'])

    return image


class PrintFailed(Exception):
    pass


class Printer(object):

    _job_states = {
        3: 'pending',
        4: 'pending-held',
        5: 'processing',
        6: 'processing-stopped',
        7: 'canceled',
        8: 'aborted',
        9: 'completed',
    }

    def __init__(self):
        self._conn = cups.Connection()
        self._last_printer = None

    @property
    def _printers(self):
        if self._last_printer is not None:
            yield self._last_printer

        attributes = self._conn.getPrinters()
        printers = attributes.keys()

        def is_label_printer(printer):
            printer_type = attributes[printer]['printer-make-and-model']
            return printer_type.startswith('DYMO LabelWriter 450')

        printers = filter(is_label_printer, printers)

        def is_not_last_printer(printer):
            return self._last_printer is None or printer != self._last_printer

        printers = filter(is_not_last_printer, printers)

        for printer in printers:
            yield printer

    def _try_print_file_on_printer(self, name, printer, poll_period=0.25):
        try:
            job_id = self._conn.printFile(printer, name, name, dict())
        except cups.IPPError:
            raise PrintFailed

        def get_job_state(id_):
            job_state_enum = self._conn.getJobAttributes(id_)['job-state']
            return Printer._jobs_states[job_state_enum]

        def job_is_pending(id_):
            return (get_job_state(id_) in {'pending', 'processing'})

        def job_succeeded(id_):
            return (get_job_state(id_) == 'completed')

        while job_is_pending(job_id):
            time.sleep(float(poll_period))

        if not job_succeeded(job_id):
            raise PrintFailed

    def _print_file(self, name):
        for printer in self._printers:
            try:
                self._try_print_file_on_printer(name, printer)
            except PrintFailed:
                continue
            else:
                self._last_printer = printer
                break

    def print_label(self, label):
        rendered = render(label)
        with tempfile.NamedTemporaryFile(suffix='.png') as fp:
            rendered.save(fp)
            fp.flush()
            self._print_file(fp.name)


class Generator(object):

    def __init__(self, address):
        self._address = address
        queue = Queue()

        class Handler(http.server.BaseHTTPRequestHandler):

            def do_OPTIONS(self):
                self.send_response(200, 'ok')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

            def _get_post_data(self):
                content_length = int(self.headers['Content-Length'])
                return self.rfile.read(content_length).decode('utf-8')

            def do_POST(self):
                query = parse_qs(self._get_post_data(), keep_blank_values=1)

                try:
                    data = json.loads(query['data'][0])
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
                else:
                    queue.put(data)

                self.send_response(200)
                self.send_header("Content-type", "text/xml")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

        self._queue = queue
        self._httpd = http.server.HTTPServer(address, Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever)

    def __call__(self):
        self._thread.start()
        while True:
            yield self._queue.get()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()


def main():
    """Run label-printer application server"""

    parser = argparse.ArgumentParser(description=main.__doc__)
    subparsers = parser.add_subparsers(title='commands')

    print_parser = subparsers.add_parser('print')
    print_parser.add_argument('infilepath')

    def print_label(args):
        with open(args.infilepath) as infile:
            label = json.loads(infile.read())

        printer = Printer()
        printer.print_label(label)

    print_parser.set_defaults(func=print_label)

    print_parser = subparsers.add_parser('server')
    print_parser.add_argument('--port', type=int, default=40121)

    def run_server(args):
        printer = Printer()
        with Generator(('', args.port)) as generate_labels:
            for label in generate_labels():
                printer.print_label(label)

    print_parser.set_defaults(func=run_server)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
