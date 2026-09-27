# qoi-nv

QOI, the Quite OK Image format, is a lossless image format whose
[specification](https://qoiformat.org/qoi-specification.pdf) is one page. This
package implements all of it in novo-lang: the fourteen-byte header, all six
opcodes, the sixty-four-entry running array, a decoder, and an encoder. The
pixel type comes from [color-nv](https://novo-lang.org/packages/color-nv),
which is the only dependency.

## What it is

A QOI file is a fourteen-byte header followed by a sequence of **opcodes** and
then an eight-byte end marker. Each opcode produces one or more pixels from
two things: the pixel before it, and a table of sixty-four recently seen
pixels. There is no entropy coding, no sliding window, no dictionary and no
other state. That is the whole of QOI's compression.

The table is called the **running array**. It is addressed by a hash of the
pixel's four channels rather than by recency, so it is not a cache with an
eviction policy. A pixel is written to its hash position every time it is
seen, and two colours that hash to the same position displace each other.

There are six opcodes. Four carry their payload in the low six bits of a
single byte, tagged by the top two bits. The other two are tagged by all eight
bits and carry literal channel values after them.

| Opcode | Tag | Payload | Bytes |
| --- | --- | --- | --- |
| `QoiOpIndex` | `00` | a position in the running array | 1 |
| `QoiOpDiff` | `01` | each channel's difference, −2 to 1, biased by 2 | 1 |
| `QoiOpLuma` | `10` | the green difference, −32 to 31, then two more | 2 |
| `QoiOpRun` | `11` | one less than the number of repeats, 1 to 62 | 1 |
| `QoiOpRgb` | `11111110` | three literal channel bytes | 4 |
| `QoiOpRgba` | `11111111` | four literal channel bytes | 5 |

The header is fourteen bytes.

| Offset | Field | Size |
| --- | --- | --- |
| 0 | the magic, the four ASCII bytes `qoif` | 4 bytes |
| 4 | width in pixels, unsigned, big-endian | 4 bytes |
| 8 | height in pixels, unsigned, big-endian | 4 bytes |
| 12 | channels, 3 or 4 | 1 byte |
| 13 | colour space, 0 or 1 | 1 byte |

| Quantity | Value |
| --- | --- |
| Entries in the running array | 64 |
| Longest run one opcode can code | 62 pixels |
| End marker | 8 bytes: seven zeroes then a one |
| Largest a file of *n* pixels can be | 5*n* + 22 bytes |
| Byte values that are not a valid opcode | none |

This package performs no input and no output. A QOI file is exactly the thing
a caller has in a file, so the two are reconciled by a **feed-and-drain state
machine**: the caller holds the stream, hands over whatever bytes have
arrived, and gets back the pixels those bytes produced along with a decoder to
hand the next chunk to. The state a decoder carries between chunks is the
sixty-four-entry table, one previous pixel and six integers.

## Install

```
novo pkg add qoi-nv
```

## Example

```novo
use std.bytes
use qoi
use qoidec
use qoienc
use qoierror

fn main() [io]
    // The bytes of a QOI file. This package performs no input of its own,
    // so the caller reads the file and hands over the buffer.
    let file: Bytes = bytes.zeros(0)

    match qoidec.decode(file)
        Ok((head, pixels)) =>
            // How many pixels the header describes.
            println("${qoi.pixel_count(head)}")

            // Encode the same pixels again. The format fixes every choice
            // an encoder could make, so this is the file that came in.
            match qoienc.encode(head, pixels)
                Ok(again) => println("${bytes.len(again)}")
                Err(e)    => println("${qoierror.offset_of(e)}")
        Err(e) => println("${qoierror.offset_of(e)}")
```

## What the package contains

| Module | Contents |
| --- | --- |
| `qoi` | The header as a value, the two enumerated bytes in it, the magic and the end marker, and the size arithmetic a caller needs before allocating anything. |
| `qoiop` | The six opcodes, the running array, the index hash, and the two functions that turn an opcode into a pixel and a pixel into the shortest opcode. |
| `qoidec` | The decoder, in two shapes: a feed-and-drain state machine, and one call over a whole buffer. |
| `qoienc` | The encoder, in two shapes: start, push and finish into a buffer the caller supplies, and one call that allocates its own. |
| `qoierror` | Every way a QOI file can refuse to be read or written, each carrying the byte offset it happened at. |

## How to choose an entry point

**`qoidec.decode` reads a whole file held in memory.** It answers the header
and the pixels together. Use it when the file fits and the image fits.

**`qoidec.decoder`, `feed` and `finish` read a stream.** `feed` takes whatever
bytes have arrived and answers the pixels they produced plus the decoder to
feed next. A chunk may split anything, including the header between its width
and its height, and whatever a chunk could not finish is carried into the next
one. Use this when the file arrives in pieces, and write the pixels somewhere
as they come.

**`qoienc.encode` writes a whole image and allocates the buffer.** Use it when
one call is what you want.

**`qoienc.encoder`, `start`, `push` and `finish` write into a buffer you
own.** The buffer is passed as a `var` name and written in place.
`qoi.max_encoded_size` says how large it must be, so a caller encoding a
hundred frames allocates once, and a caller writing into the middle of a
larger buffer needs no copy afterwards. `push_samples` takes a whole row of
packed samples rather than one pixel.

**`qoiop` on its own is the format's arithmetic with no stream around it.**
`read_op`, `apply`, `remember` and `choose` are what an inspector, a converter
or a device driver reaches for.

## The rules a user needs

1. **A run of 63 and a run of 64 do not exist.** `11111110` and `11111111` are
   the two literal tags, so `QoiOpRun` stops at 62. An encoder that emitted a
   longer run writes a file whose next pixel is read as a literal.
2. **The running array is addressed by a hash, not by recency.** The position
   is `(r * 3 + g * 5 + b * 7 + a * 11) % 64`. Nothing about those multipliers
   is optimal, and changing one produces a format nothing else can read.
3. **The two initial states disagree, on purpose.** The running array starts
   as sixty-four fully transparent pixels. The previous-pixel register starts
   as opaque black. An implementation that seeds both the same way decodes
   almost every image correctly and a black one wrongly.
4. **The dimensions in the header are big-endian.** QOI is a
   twenty-first-century format designed on little-endian machines, and a
   reader who assumes native order gets dimensions in the billions.
5. **The colour space byte changes nothing.** The specification says it is
   purely informative. It selects no transfer function and alters no opcode.
   It is carried so that a round trip preserves it.
6. **`feed` hands back pixels it has not verified.** QOI has no checksum
   anywhere. Its only integrity checks are the pixel count and the end marker,
   and both are at the end of the file. Only a successful `finish` says the
   file was whole.
7. **A corrupt QOI file usually decodes to a plausible image rather than to an
   error.** All 256 byte values are valid opcodes. A caller who needs to know
   a file is intact needs a checksum of their own.
8. **`feed` does not answer a `Result`, and a failure is sticky.** A corrupt
   file at pixel 40 000 does not throw away the 39 999 before it.
   `qoidec.error` is what asks, and once it is set every later `feed` produces
   nothing. `qoierror.image_is_complete` says whether the pixels so far are
   usable.
9. **`push` often writes nothing, and `finish` is not optional.** A run spans
   pixels, so `push` holds a run open until it reaches 62, a different pixel
   arrives, or the image's last pixel does. `finish` writes the end marker,
   and refuses an image that is missing pixels.
10. **An encoder has nothing to choose.** The specification fixes the
    preference order: index, then diff, then luma, then a literal. There is no
    compression level, no strategy and no window size, so two conforming
    encoders produce byte-identical files from the same pixels.
11. **A decoder or an encoder is never changed by a call; each call answers a
    new one.** A decoder can be kept, or fed from two places. The one thing a
    call writes into is the encoder's output buffer, which is the caller's
    own.
12. **The channels byte and the colour space byte are refused at undefined
    values.** Both are informative and a lenient reader would still conform.
    This one is strict: a file that disagrees with the specification in a
    field nothing reads was not written by a QOI encoder.
13. **A width or a height of zero is refused.** The format permits the header.
    There is no body it could have.
14. **`qoidec.with_channels` drains a fixed channel count rather than the
    header's.** The reference implementation has the same parameter. Nothing
    in the format requires it.
15. **An image of 400,000,000 pixels or more is refused.** That is the
    `QOI_PIXELS_MAX` of the reference implementation, `qoi.h`. Below it every
    size this package computes fits in an `Int`.
16. **A three-channel image is opaque.** The encoder takes a pixel pushed into
    a three-channel image as opaque whatever its alpha, so the file never
    changes alpha and stays within `qoi.max_encoded_size`.
17. **Channel differences wrap at 256.** A red channel going from 255 to 0 is a
    difference of 1 and codes as `QoiOpDiff`, as it does in `qoi.h`.
18. **Every error carries a byte offset counted from the first byte of the
    file.** A QOI file is not a thing a person edited, so a line number would
    mean nothing. The offset is across every chunk, because a caller feeding
    64 KiB at a time does not know where a chunk started either.

## What is not included

- **A `read_all` that pumps a stream for you.** A QOI file expands to width
  times height times channels bytes, so a caller who cannot hold the whole
  input cannot hold the whole output either. `decode` takes both whole, and
  `feed` is for a caller who can hold neither.
- **A device build.** The pixel type is color-nv's `Srgba8`, a plain struct,
  and a build for a microcontroller with no heap refuses to construct one.
  So no module here claims to run on a device.
- **A checksum.** The format has none. See rule 7.
- **Any part of the format.** The specification is one page and this package
  covers all of it. Anything it cannot do is a defect to report.

## Related packages

- [color-nv](https://novo-lang.org/packages/color-nv) owns the pixel type. A
  QOI pixel is a colour with an alpha beside it, the running array is indexed
  by a hash of its four channels, and the opcodes are differences between
  colours, so the type is taken from there rather than declared twice.
- [png-nv](https://novo-lang.org/packages/png-nv) is the PNG codec. PNG
  compresses far harder, carries metadata and supports interlacing. QOI does
  none of that and decodes in a fraction of the state.
- [image-io-nv](https://novo-lang.org/packages/image-io-nv) reads and writes
  image files by looking at what they are. It calls this package for a QOI
  file and png-nv for a PNG.

## Tests

```bash
novo test tests/corpus_tests.nv    # one suite; the table below lists them all
bash tests/coverage.sh             # every suite, and the line coverage of src/
```

| Suite | What it asserts |
| --- | --- |
| `qoi_tests.nv`, `qoiop_tests.nv`, `qoicodec_tests.nv` | The header, the opcodes, the running array, and the contract of the decoder and the encoder |
| `corpus_tests.nv` | Four images of the official test set, decoded to the pixels of their PNG twins and encoded back to the same bytes |
| `differential_tests.nv` | 17 images built to reach each opcode, runs of 61 to 125 pixels, and differences that wrap, against the Python codec in `tools/qoiref.py` |
| `stream_tests.nv` | Decoding in chunks of every size, every refusal at its offset, and every opcode written, read and applied |

The reference implementation is `qoi.h`, Dominic Szablewski's single-file C
codec. The oracle is the [QOI test images](https://qoiformat.org/qoi_test_images.zip)
published beside it. `tests/images/` holds the four smallest: `edgecase.qoi`,
`qoi_logo.qoi`, `testcard.qoi` and `testcard_rgba.qoi`. `edgecase.qoi` uses
opcodes an encoder would not choose, so it is checked by decoding only.

`tools/qoiref.py` is a second codec, written in Python from the specification
the way `qoi.h` behaves, with a PNG reader built on `zlib`.
`python3 tools/qoiref.py check <dir>` checks it against every image of the
official set, the large ones included. `corpus` and `differential` write the
two suites that compare this package with it.

Because the format leaves an encoder nothing to choose, the correctness
condition is byte equality with the reference encoder rather than a round
trip.

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
