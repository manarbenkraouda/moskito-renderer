import io
import subprocess
import sys
from bottle import route, run, request, auth_basic, HTTPResponse
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import os
from printer_data import PrinterData
from textwrap import wrap
from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image, IMAGE_TYPES
from text_print import TextCanvas

def reverse_bits(i: int):
    'Reverse the bits of this byte (as `int`)'
    i = ((i & 0b10101010) >> 1) | ((i & 0b01010101) << 1)
    i = ((i & 0b11001100) >> 2) | ((i & 0b00110011) << 2)
    return ((i & 0b11110000) >> 4) | ((i & 0b00001111) << 4)

def flip(buffer, width, height, horizontally=True, vertically=True, *, overwrite=False):
    'Flip the bitmap data'
    buffer.seek(0)
    if not horizontally and not vertically:
        return buffer
    data_width = width // 8
    result_0 = io.BytesIO()
    if horizontally:
        while data := buffer.read(data_width):
            data = bytearray(map(reverse_bits, data))
            data.reverse()
            result_0.write(data)
        result_0.seek(0)
    else:
        result_0 = buffer
    result_1 = io.BytesIO()
    if vertically:
        for i in range(height - 1, -1, -1):
            result_0.seek(i * data_width)
            data = result_0.read(data_width)
            result_1.write(data)
        result_1.seek(0)
    else:
        result_1 = result_0
    buffer.seek(0)
    if overwrite:
        while data := result_1.read(data_width):
            buffer.write(data)
        buffer.seek(0)
    return result_1

def print_bitmap(data: PrinterData):
    paper_width = 384
    flip(data.data, data.width, data.height, overwrite=True)
    bitmap = []
    for chunk in data.read(paper_width // 8):
        bitmap.append(list(map(reverse_bits, chunk)))
    return bitmap


def word_wrap(image, ctx, text, roi_width, roi_height):
    """Break long text to multiple lines, and reduce point size
    until all text fits within a bounding box."""
    mutable_message = text
    iteration_attempts = 100

    def eval_metrics(txt):
        """Quick helper function to calculate width/height of text."""
        metrics = ctx.get_font_metrics(image, txt, True)
        return (metrics.text_width, metrics.text_height)

    while ctx.font_size > 0 and iteration_attempts:
        iteration_attempts -= 1
        width, height = eval_metrics(mutable_message)
        if height > roi_height:
            ctx.font_size -= 0.75  # Reduce pointsize
            mutable_message = text  # Restore original text
        elif width > roi_width:
            columns = len(mutable_message)
            while columns > 0:
                columns -= 1
                mutable_message = '\n'.join(wrap(mutable_message, columns))
                wrapped_width, _ = eval_metrics(mutable_message)
                if wrapped_width <= roi_width:
                    break
            if columns < 1:
                ctx.font_size -= 0.75  # Reduce pointsize
                mutable_message = text  # Restore original text
        else:
            break
    if iteration_attempts < 1:
        raise RuntimeError("Unable to calculate word_wrap for " + text)
    return mutable_message

def is_authenticated_user(user, password):
    return user == 'moskito' and password == 'dafddd2e-c02e-4a0a-8157-b9fea1611549'

@route('/api/text2bitmap', method='POST')
@auth_basic(is_authenticated_user)
def index():
    text = request.forms.get('text')
    if (text is None):
        return HTTPResponse(status=400)
    
    ROI_SIDE = 384

    with Image(pseudo="canvas:white", width=384, height=384) as img:
        with Drawing() as ctx:
            # Set the font style
            ctx.fill_color = Color('BLACK')
            ctx.text_alignment = 'center'
            ctx.font_family = 'Arial'
            ctx.font_size = 40
            mutable_message = word_wrap(img,
                                        ctx,
                                        text,
                                        ROI_SIDE,
                                        ROI_SIDE)
            metrics = ctx.get_font_metrics(img, mutable_message, True)
            ctx.text(int((384 - metrics.text_width / 2)), int((384 - metrics.text_height) / 2), mutable_message)
            ctx.draw(img)
            img.black_threshold(Color("#808080"))
            img.format = 'pbm'
            pbm = io.BytesIO()
            img.save(pbm)
            img.convert('png')
            img.save(filename='../test.png')
            pbm.seek(0)
            printer_data = PrinterData(384, pbm)

            pixels = print_bitmap(printer_data)

            if (pixels == -1):
                return HTTPResponse(status=500)
            return {'pixels': list(pixels)}

run(host='0.0.0.0', port=8080)