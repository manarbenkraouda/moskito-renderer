import io
import sys

import PIL


class PrinterData():
    ''' The image data to be used by `PrinterDriver`.
        Optionally give an io `file` to read PBM image data from it.
        To read the bitmap data, simply do `io` operation with attribute `data`
    '''

    buffer = 4 * 1024 * 1024

    width: int
    'Constant width'
    _data_width: int
    'Amount of data bytes per line'
    height: int
    'Total height of bitmap data'
    data: bytearray
    'Monochrome bitmap data `io`, of size `width * height // 8`'
    pages: list
    'Height of every page in a `list`'
    max_size: int
    'Max size of `data`'
    full: bool
    'Whether the data is full (i.e. have reached max size)'

    def __init__(self, width, file: io.BufferedIOBase = None, max_size=64 * 1024 * 1024):
        self.width = width
        self._data_width = width // 8
        self.height = 0
        self.max_size = max_size
        self.max_height = max_size // self._data_width
        self.full = False
        self.data = io.BytesIO()
        self.pages = []
        if file is not None:
            self.from_pbm(file)

    def write(self, data: bytearray):
        ''' Directly write bitmap data to `data` directly. For memory safety,
            will overwrite earliest data if going to reach `max_size`.
            returns the io position after writing.
        '''
        data_len = len(data)
        if self.data.tell() + data_len > self.max_size:
            self.full = True
            self.data.seek(0)
        self.data.write(data)
        position = self.data.tell()
        if not self.full:
            self.height = position // self._data_width
        return position

    def read(self, length=-1):
        ''' Read the bitmap data entirely, in chunks.
            `yield` the resulting data.
            Will finally put seek point to `0`
        '''
        self.data.seek(0)
        while chunk := self.data.read(length):
            yield chunk
        self.data.seek(0)

    def from_pbm(self, file: io.BufferedIOBase):
        ''' Read from buffer `file` that have PBM image data.
            Concatenating multiple files *is* allowed.
            Calling multiple times is also possible,
            before or after yielding `read`, not between.
            Will put seek point to last byte written.
        '''
        while signature := file.readline():
            if signature != b'P4\n':
                return -1
            while True:
                # There can be comments. Skip them
                line = file.readline()[0:-1]
                if line[0:1] != b'#':
                    break
            width, height = map(int, line.split(b' '))
            if width != self.width:
                return -1
            self.pages.append(height)
            self.height += height
            total_size = 0
            expected_size = self._data_width * height
            while raw_data := file.read(
                    min(self.buffer, expected_size - total_size)):
                total_size += len(raw_data)
                self.write(raw_data)
                if self.full:
                    self.pages.pop(0)
            if total_size != expected_size:
                return -1
        if file is not sys.stdin.buffer:
            file.close()

    def to_pbm(self, *, merge_pages=False):
        ''' `yield` the pages as PBM image data,
            optionally just merge to one page.
            Will restore the previous seek point.
        '''
        pointer = self.data.tell()
        self.data.seek(0)
        if merge_pages:
            yield bytearray(
                b'P4\n%i %i\n' % (self.width, self.height)
            ) + self.data.read()
        else:
            for i in self.pages:
                yield bytearray(
                    b'P4\n%i %i\n' % (self.width, i)
                ) + self.data.read(self._data_width * i)
        self.data.seek(pointer)

    def __del__(self):
        self.data.truncate(0)
        self.data.close()
        del self.data
