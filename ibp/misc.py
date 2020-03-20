"""Miscellaneous utility functions."""

import io
import os
import typing
import itertools
import subprocess

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def get_next_available_index(indices: typing.Iterable[int]) -> int:
    """Get next available index from an iterable of indices."""
    used_indices = sorted(indices)
    enumerated = itertools.zip_longest(itertools.count(), used_indices)
    return next(
        index
        for index, used_index in enumerated
        if used_index is None or index != used_index
    )


def code39(text, size, dpi=300):
    writer = ImageWriter()
    options = dict(write_text=False, writer=writer, dpi=int(dpi), quiet_zone=0)

    def px2mm(px):
        """Convert pixels to millimeters for our given DPI."""
        return 25.4 * px / options["dpi"]

    code = barcode.Code39(str(text), writer=writer, add_checksum=False)

    raw = code.build()
    modules_per_line = len(raw[0])
    module_width = px2mm(size[0]) / modules_per_line
    options["module_width"] = module_width

    module_height = px2mm(size[1]) - 2  # barcode adds this for some reason
    options["module_height"] = module_height

    return code.render(options)


def build_font_fitter(min_font=1, max_font=100):

    fonts = {
        font_size: ImageFont.truetype("DejaVuSansMono.ttf", font_size)
        for font_size in range(min_font, max_font)
    }

    def fit_font(size, text):
        size_h, size_w = size

        min_, max_ = min_font, max_font
        while abs(max_ - min_) > 1:
            font_size = int(round((max_ - min_) / 2)) + min_

            font = fonts[font_size]
            text_h, text_w = font.getsize(text)

            if text_h < size_h and text_w < size_w:
                min_ = font_size
            else:
                max_ = font_size

        font = fonts[min_]
        return font

    return fit_font


fit_font = build_font_fitter()


class Box:
    def __init__(self, x0, y0, x1, y1):
        x0 = int(round(x0))
        y0 = int(round(y0))
        x1 = int(round(x1))
        y1 = int(round(y1))

        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)

        self._x0 = x0
        self._y0 = y0
        self._x1 = x1
        self._y1 = y1

    @property
    def x0(self):
        return self._x0

    @property
    def y0(self):
        return self._y0

    @property
    def x1(self):
        return self._x1

    @property
    def y1(self):
        return self._y1

    @property
    def width(self):
        return self._x1 - self._x0

    @property
    def height(self):
        return self._y1 - self._y0

    @property
    def size(self):
        return self.width, self.height


def fit_text(draw, box, text):
    text = str(text)

    font = fit_font(box.size, text)
    text_size = font.getsize(text)

    x0 = box.x0 + int((box.size[0] - text_size[0] + 1) / 2)
    y0 = box.y0 + int((box.size[1] - text_size[1] + 1) / 2)

    draw.text((x0, y0), text, font=font)


def add_barcode(image, label, box):
    image.paste(code39(label, box.size), (box.x0, box.y0))


def render_request_label(request, size=(1300, 500)):
    width, height = size
    image = Image.new("L", size, color=(255,))
    draw = ImageDraw.Draw(image)

    # package ID barcode
    box = Box(0.68 * width, 0.00 * height, 1.00 * width, 0.10 * height)
    fit_text(draw, box, "package ID")

    box = Box(0.68 * width, 0.10 * height, 1.00 * width, 0.50 * height)
    add_barcode(image, "1234", box)

    box = Box(0.68 * width, 0.50 * height, 1.00 * width, 0.60 * height)
    fit_text(draw, box, "1234")

    # inmate ID barcode
    box = Box(0.02 * width, 0.00 * height, 0.65 * width, 0.10 * height)
    fit_text(draw, box, "inmate ID")

    box = Box(0.02 * width, 0.10 * height, 0.65 * width, 0.50 * height)
    add_barcode(image, str(request.inmate.id), box)

    box = Box(0.02 * width, 0.50 * height, 0.65 * width, 0.60 * height)
    fit_text(draw, box, str(request.inmate.id))

    # inmate name
    box = Box(0.00 * width, 0.60 * height, 1.00 * width, 0.90 * height)
    fit_text(draw, box, str(request.inmate.first_name))

    # other info at bottom
    box = Box(0.00 * width, 0.90 * height, 0.33 * width, 1.00 * height)
    fit_text(draw, box, request.inmate.jurisdiction)

    box = Box(0.33 * width, 0.90 * height, 0.67 * width, 1.00 * height)
    fit_text(draw, box, request.inmate.unit.name)

    box = Box(0.67 * width, 0.90 * height, 1.00 * width, 1.00 * height)
    fit_text(draw, box, request.inmate.unit.shipping_method)

    return image
