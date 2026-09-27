#!/usr/bin/env python3
"""qoiref.py: a reference QOI codec in Python, and the writer of the
differential and corpus suites from it.

The codec follows the QOI specification (qoiformat.org, version 1.0)
the way the reference implementation qoi.h does: channel differences
wrap at 256, the running array is written for every decoded pixel, and
the encoder writes it only when a pixel is not already in it.

Run from the package root:

    python3 tools/qoiref.py check <dir>       # the official test images
    python3 tools/qoiref.py corpus <dir>      # copy the small ones, write tests/corpus_tests.nv
    python3 tools/qoiref.py differential      # write tests/differential_tests.nv

`check` decodes each `.png` of the official set with a small PNG reader
built on zlib, and asserts that this codec decodes the matching `.qoi`
to the same pixels and encodes those pixels to the same bytes.
"""
import os
import random
import shutil
import struct
import subprocess
import sys
import zlib


def canonical(path):
    """Puts a written suite in the style `novo fmt` prints, as the
    package's other sources are."""
    subprocess.run([os.environ.get('NOVO', 'novo'), 'fmt', path], check=True,
                   stdout=subprocess.DEVNULL)

MAGIC = b'qoif'
END = b'\x00' * 7 + b'\x01'


def qhash(r, g, b, a):
    return (r * 3 + g * 5 + b * 7 + a * 11) % 64


def wrap(d):
    return ((d + 128) % 256) - 128


def encode(width, height, channels, space, pixels):
    """pixels: bytes, `channels` per pixel.  Returns the file."""
    out = bytearray(MAGIC + struct.pack('>II', width, height) + bytes([channels, space]))
    index = [(0, 0, 0, 0)] * 64
    prev = (0, 0, 0, 255)
    run = 0
    total = width * height
    for p in range(total):
        o = p * channels
        px = (pixels[o], pixels[o + 1], pixels[o + 2], pixels[o + 3] if channels == 4 else 255)
        if px == prev:
            run += 1
            if run == 62 or p == total - 1:
                out.append(0xC0 | (run - 1))
                run = 0
            continue
        if run > 0:
            out.append(0xC0 | (run - 1))
            run = 0
        h = qhash(*px)
        if index[h] == px:
            out.append(h)
        else:
            index[h] = px
            if px[3] == prev[3]:
                dr, dg, db = wrap(px[0] - prev[0]), wrap(px[1] - prev[1]), wrap(px[2] - prev[2])
                rg, bg = dr - dg, db - dg
                if -2 <= dr <= 1 and -2 <= dg <= 1 and -2 <= db <= 1:
                    out.append(0x40 | (dr + 2) << 4 | (dg + 2) << 2 | (db + 2))
                elif -32 <= dg <= 31 and -8 <= rg <= 7 and -8 <= bg <= 7:
                    out.append(0x80 | (dg + 32))
                    out.append((rg + 8) << 4 | (bg + 8))
                else:
                    out += bytes([0xFE, px[0], px[1], px[2]])
            else:
                out += bytes([0xFF, px[0], px[1], px[2], px[3]])
        prev = px
    out += END
    return bytes(out)


def decode(data, channels=None):
    """Returns (width, height, channels, space, pixels)."""
    assert data[:4] == MAGIC
    width, height = struct.unpack('>II', data[4:12])
    ch, space = data[12], data[13]
    channels = channels or ch
    index = [(0, 0, 0, 0)] * 64
    px = (0, 0, 0, 255)
    out = bytearray()
    p = 14
    run = 0
    for _ in range(width * height):
        if run > 0:
            run -= 1
        else:
            b1 = data[p]
            p += 1
            if b1 == 0xFE:
                px = (data[p], data[p + 1], data[p + 2], px[3])
                p += 3
            elif b1 == 0xFF:
                px = tuple(data[p:p + 4])
                p += 4
            elif b1 >> 6 == 0:
                px = index[b1]
            elif b1 >> 6 == 1:
                px = ((px[0] + (b1 >> 4 & 3) - 2) % 256, (px[1] + (b1 >> 2 & 3) - 2) % 256,
                      (px[2] + (b1 & 3) - 2) % 256, px[3])
            elif b1 >> 6 == 2:
                b2 = data[p]
                p += 1
                dg = (b1 & 63) - 32
                px = ((px[0] + dg + (b2 >> 4) - 8) % 256, (px[1] + dg) % 256,
                      (px[2] + dg + (b2 & 15) - 8) % 256, px[3])
            else:
                run = b1 & 63
            index[qhash(*px)] = px
        out += bytes(px[:channels])
    assert data[p:] == END, 'end marker'
    return width, height, ch, space, bytes(out)


def png_pixels(path):
    """RGB or RGBA pixels of an 8-bit, non-interlaced PNG, as RGBA."""
    data = open(path, 'rb').read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    p = 8
    idat = b''
    while p < len(data):
        n, kind = struct.unpack('>I4s', data[p:p + 8])
        body = data[p + 8:p + 8 + n]
        if kind == b'IHDR':
            w, h, depth, ctype, _, _, lace = struct.unpack('>IIBBBBB', body)
            assert depth == 8 and ctype in (2, 6) and lace == 0
        elif kind == b'IDAT':
            idat += body
        p += 12 + n
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows = []
    prior = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prior[x]
            c = prior[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 255
        rows.append(bytes(line))
        prior = line
    flat = b''.join(rows)
    if bpp == 4:
        return w, h, flat
    out = bytearray()
    for i in range(0, len(flat), 3):
        out += flat[i:i + 3] + b'\xff'
    return w, h, bytes(out)


SMALL = ['edgecase', 'qoi_logo', 'testcard', 'testcard_rgba']


# edgecase.qoi is written by hand to reach corners a decoder must
# handle, with opcodes an encoder would not choose, so it is checked by
# decoding only.
DECODE_ONLY = ['edgecase']


def check(folder, names):
    for name in names:
        qoi = open(os.path.join(folder, name + '.qoi'), 'rb').read()
        w, h, ch, space, pixels = decode(qoi, 4)
        pw, ph, png = png_pixels(os.path.join(folder, name + '.png'))
        assert (w, h) == (pw, ph) and pixels == png, name + ': decode differs from the PNG'
        native = decode(qoi)[4]
        if name not in DECODE_ONLY:
            assert encode(w, h, ch, space, native) == qoi, name + ': encode differs from the file'
        print('%s: %dx%d, agrees with the reference files' % (name, w, h))


def novo_str(s):
    return '"' + s + '"'


def corpus(folder):
    check(folder, SMALL)
    os.makedirs('tests/images', exist_ok=True)
    lines = []
    for name in SMALL:
        src = os.path.join(folder, name + '.qoi')
        shutil.copyfile(src, os.path.join('tests/images', name + '.qoi'))
        qoi = open(src, 'rb').read()
        w, h, ch, space, rgba = decode(qoi, 4)
        _, _, _, _, native = decode(qoi)
        lines.append((name, w, h, ch, space, zlib.crc32(rgba), zlib.crc32(native), len(qoi),
                      zlib.crc32(qoi), name not in DECODE_ONLY))
    out = open('tests/corpus_tests.nv', 'w')
    out.write('''// corpus_tests.nv — the small images of the official QOI test set.
//
// Written by `python3 tools/qoiref.py corpus <dir>`, where <dir> holds
// the unpacked https://qoiformat.org/qoi_test_images.zip.  The tool
// checks each file against its PNG twin with a PNG reader of its own
// and a Python QOI codec, then records here what the pixels and the
// file hash to.  Each case decodes the file and compares the pixels'
// CRC-32 with the PNG's.  Each file an encoder could have written is
// encoded back from those pixels byte for byte; edgecase.qoi uses
// opcodes an encoder would not choose, and is encoded and decoded back
// to the same pixels instead.

use std.test
use std.fs
use std.codec
use qoi
use qoidec
use qoienc

fn read(name: Str) -> Bytes [fs]
    fs.read_bytes("tests/images/" + name + ".qoi") ?? bytes.zeros(0)

// Whether a file decodes to pixels with the recorded CRC-32 in four
// channels and in its own, and encodes back to itself.
fn agrees(name: Str, w: Int, h: Int, ch: Int, space: Int, rgba_crc: Int, native_crc: Int,
          size: Int, file_crc: Int, canonical: Bool) -> Bool [fs]
    let file = read(name)
    if bytes.len(file) != size or codec.crc32(file) != file_crc
        return false
    let (d, rgba) = qoidec.feed(qoidec.with_channels(qoidec.decoder(), 4), file)
    let whole = qoidec.finish(d)
    match qoidec.decode(file)
        Ok((head, pixels)) =>
            let shape = head.width == w and head.height == h
                and qoi.channel_count(head.channels) == ch and qoi.space_byte(head.space) == space
            shape and whole == Ok() and codec.crc32(rgba) == rgba_crc
                and codec.crc32(pixels) == native_crc and encodes_back(head, pixels, file, canonical)
        Err(_)             => false

// Whether the pixels encode to the file itself, or, for a file an
// encoder would not have written, to a file that decodes to them.
fn encodes_back(head: QoiHeader, pixels: Bytes, file: Bytes, canonical: Bool) -> Bool
    match qoienc.encode(head, pixels)
        Ok(again) =>
            if canonical
                return again == file
            match qoidec.decode(again)
                Ok((_, back)) => back == pixels
                Err(_)        => false
        Err(_)    => false

@test
fn test_the_official_images_decode_and_encode_byte_for_byte() [io, fs]
''')
    for (name, w, h, ch, space, rc, nc, size, fc, canon) in lines:
        out.write('    test.case("%s, %d by %d, %d channels")\n' % (name, w, h, ch))
        out.write('    test.assert(agrees("%s", %d, %d, %d, %d, %d, %d, %d, %d, %s))\n'
                  % (name, w, h, ch, space, rc, nc, size, fc, 'true' if canon else 'false'))
    out.close()
    canonical('tests/corpus_tests.nv')
    print('wrote tests/corpus_tests.nv and tests/images/')


def image(rng, w, h, channels, style):
    """A small test image whose pixels exercise one part of the format."""
    px = []
    prev = [rng.randrange(256) for _ in range(4)]
    for i in range(w * h):
        if style == 'noise':
            p = [rng.randrange(256) for _ in range(4)]
        elif style == 'steps':
            p = [(prev[k] + rng.choice([-2, -1, 0, 1])) % 256 for k in range(3)] + [prev[3]]
        elif style == 'gradient':
            dg = rng.randrange(-32, 32)
            p = [(prev[0] + dg + rng.randrange(-8, 8)) % 256, (prev[1] + dg) % 256,
                 (prev[2] + dg + rng.randrange(-8, 8)) % 256, prev[3]]
        elif style == 'runs':
            p = prev if rng.random() < 0.9 else [rng.randrange(256) for _ in range(3)] + [255]
        elif style == 'palette':
            pal = [[0, 0, 0, 255], [255, 255, 255, 255], [255, 0, 0, 128], [0, 0, 0, 0],
                   [10, 200, 30, 255], [250, 1, 3, 255]]
            p = list(rng.choice(pal))
        else:
            p = [rng.choice([0, 1, 254, 255]) for _ in range(3)] + [rng.choice([0, 255])]
        if channels == 3:
            p[3] = 255
        px.append(p)
        prev = p
    return bytes(v for p in px for v in p[:channels])


def differential():
    rng = random.Random(20260927)
    cases = []
    for style in ['noise', 'steps', 'gradient', 'runs', 'palette', 'wrap']:
        for channels in (3, 4):
            w, h = rng.randrange(1, 24), rng.randrange(1, 12)
            pixels = image(rng, w, h, channels, style)
            qoi = encode(w, h, channels, channels - 3, pixels)
            assert decode(qoi)[4] == pixels
            cases.append((style, w, h, channels, pixels, qoi))
    # A run of exactly 62 and of 63 pixels, and a run that ends the image.
    for n in (61, 62, 63, 124, 125):
        pixels = b'\x00\x00\x00\xff' * n + b'\x05\x06\x07\xff'
        cases.append(('run of %d' % n, n + 1, 1, 4, pixels, encode(n + 1, 1, 4, 0, pixels)))
    out = open('tests/differential_tests.nv', 'w')
    out.write('''// differential_tests.nv — this codec against the Python reference
// codec in tools/qoiref.py.
//
// Written by `python3 tools/qoiref.py differential`.  Each case is a
// small image, generated from a fixed seed to exercise one part of the
// format (noise, steps a diff codes, gradients a luma codes, runs, a
// small palette the index reuses, and differences that wrap at 256),
// and the file the Python encoder wrote for it.  This encoder has to
// write the same bytes, and this decoder has to read them back to the
// same pixels.

use std.test
use qoidec
use qoienc

fn agrees(w: Int, h: Int, channels: Int, pixels_hex: Str, qoi_hex: Str) -> Bool
    let pixels = bytes.from_hex(pixels_hex) ?? bytes.zeros(0)
    let file = bytes.from_hex(qoi_hex) ?? bytes.zeros(0)
    let chans = if channels == 3 then QoiRgb else QoiRgba
    let space = if channels == 3 then QoiSrgbLinearAlpha else QoiAllLinear
    let h1 = QoiHeader { width: w, height: h, channels: chans, space: space }
    match qoidec.decode(file)
        Ok((head, back)) =>
            head.width == w and head.height == h and back == pixels
                and qoienc.encode(h1, pixels) == Ok(file)
        Err(_)           => false

@test
fn test_the_codec_agrees_with_the_python_reference() [io]
''')
    for (style, w, h, channels, pixels, qoi) in cases:
        out.write('    test.case("%s, %d by %d, %d channels")\n' % (style, w, h, channels))
        out.write('    test.assert(agrees(%d, %d, %d,\n' % (w, h, channels))
        out.write('                       "%s",\n' % pixels.hex())
        out.write('                       "%s"))\n' % qoi.hex())
    out.close()
    canonical('tests/differential_tests.nv')
    print('wrote tests/differential_tests.nv with %d cases' % len(cases))


if __name__ == '__main__':
    if sys.argv[1] == 'check':
        check(sys.argv[2], SMALL + [n for n in ['dice', 'kodim10', 'kodim23', 'wikipedia_008']
                                    if os.path.exists(os.path.join(sys.argv[2], n + '.qoi'))])
    elif sys.argv[1] == 'corpus':
        corpus(sys.argv[2])
    else:
        differential()
