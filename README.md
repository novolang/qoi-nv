# qoi-nv

QOI, the Quite OK Image format, is a lossless image format whose
[specification](https://qoiformat.org/qoi-specification.pdf) is one page. This
package implements all of it in novo-lang: the fourteen-byte header, all six
opcodes, the sixty-four-entry running array, a decoder, and an encoder. The
pixel type comes from [color-nv](https://novo-lang.org/packages/color-nv),
which is the only dependency.

**Status: NOT IMPLEMENTED — interface only.** Every function is declared with
its full signature, but every body is a `todo()` that panics when called. The
package is published so its design can be reviewed and depended on before it
is implemented. Version 0.1.0 will be the first working release.

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

Build and test with `novo pkg build` and `novo test`. Today `novo test` fails
on purpose: every test reaches a `not implemented: qoi-nv.<module>.<fn>`
panic. The tests are the specification the implementation will have to
satisfy.

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
own.** `qoi.max_encoded_size` says exactly how large that buffer must be, so a
caller encoding a hundred frames allocates once, and a caller writing into the
middle of a larger buffer needs no copy afterwards. `push_samples` takes a
whole row of packed samples rather than one pixel.

**`qoiop` on its own is the format's arithmetic with no stream around it.**
`read_op`, `apply`, `remember` and `choose` are what an inspector, a converter
or a device driver reaches for.

## The rules a user needs

1. **A run of 63 and a run of 64 do not exist.** `11111110` and `11111111` are
   the two literal tags, so `QoiOpRun` stops at 62. An encoder that emitted a
   longer run writes a file whose next pixel is read as a literal. This single
   interaction is the only subtle thing in the format.
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
9. **`push` usually writes nothing, and `finish` is not optional.** A run
   spans pixels, so `push` holds an open run rather than emitting it. A caller
   who stops without calling `finish` loses the tail of their image and the
   end marker.
10. **An encoder has nothing to choose.** The specification fixes the
    preference order: index, then diff, then luma, then a literal. There is no
    compression level, no strategy and no window size, so two conforming
    encoders produce byte-identical files from the same pixels.
11. **Every decoder and encoder function answers a new value rather than
    changing one.** `[mutate]` is a host effect and this package has none,
    which is also what makes a decoder safe to keep, fork or feed from two
    places.
12. **The channels byte and the colour space byte are refused at undefined
    values.** Both are informative and a lenient reader would still conform.
    This one is strict: a file that disagrees with the specification in a
    field nothing reads was not written by a QOI encoder.
13. **A width or a height of zero is refused.** The format permits the header.
    There is no body it could have.
14. **`qoidec.with_channels` drains a fixed channel count rather than the
    header's.** The reference implementation has the same parameter. Nothing
    in the format requires it.
15. **Every error carries a byte offset counted from the first byte of the
    file.** A QOI file is not a thing a person edited, so a line number would
    mean nothing. The offset is across every chunk, because a caller feeding
    64 KiB at a time does not know where a chunk started either.

## Running on a microcontroller

The claim in this package's manifest is that its opcode arithmetic runs on a
device with no heap allocator. **That claim rests on the code and is not yet
checked by a build.** `tests/embedded_probe.nv` is written as the firmware
that would check it, and today it does not compile:

```bash
novo build --target=nrf52-qemu tests/embedded_probe.nv
```

fails with two `cannot infer the type of this expression` errors, on the two
lines that name a type from color-nv. `novo build` given a file outside `src/`
loads the package's own modules and does not resolve its registry
dependencies, so `use srgb` finds nothing and every value of a color-nv type
becomes untyped. The probe is kept rather than deleted, because deleting it
would remove the claim's only description.

What the probe describes is the decoder's inner loop: apply an opcode, hash
the pixel, write it back to the table. QOI's state is a few hundred bytes, and
a decoder that streams into a display's framebuffer never holds an image, so a
microcontroller driving a small panel from a flash chip is the use this
arrangement is for.

The `Bytes`, `Str` and `Result` half of the package is outside the claim in
any case. None of the three is available on the device target today, so the
honest statement is that QOI's arithmetic runs on a device and QOI's buffer
surface does not.

## What is not included

- **A `read_all` that pumps a stream for you.** flate-nv and png-nv both have
  one. A QOI file expands to width times height times channels bytes with no
  compression state, so a caller who cannot hold the whole input certainly
  cannot hold the whole output. `decode` is honest about needing both, and
  `feed` is for a caller who can hold neither.
- **A checksum.** The format has none. See rule 7.
- **Any part of the format.** The specification is one page and this interface
  covers all of it. Anything the implementation cannot do is a defect to
  report, not a scope decision.

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
novo test tests/qoi_tests.nv        # the header and the size arithmetic
novo test tests/qoiop_tests.nv      # the six opcodes and the running array
novo test tests/qoicodec_tests.nv   # the decoder and the encoder
```

The reference implementation is `qoi.h`, Dominic Szablewski's single-file C
version, and the oracle is [the QOI test images](https://qoiformat.org/benchmark/).

These assertions are binding rather than illustrative. The specification fixes
the opcode sizes, the hash multipliers, both initial states and the maximum
run, so a body that disagrees with one of them is wrong rather than different.
The codec suite asserts the contract instead: that a fresh decoder knows
nothing, that an empty chunk is not an end of stream, that a failure is
sticky, that truncation and the end marker are checked in `finish`, and that
the encoder holds a run back until something ends it.

Because the format leaves an encoder nothing to choose, the correctness
condition here is byte equality with the reference encoder rather than a round
trip.

The tests compile today and fail at run, each on the
`not implemented: qoi-nv.<module>.<fn>` panic that is its body. That is the
expected state of an interface release. They turn green one at a time as
bodies land. `novo test --isolate tests/<file>` prints one verdict per test.

## Implementation status

| Item | Implemented |
| --- | --- |
| `qoi.QoiHeader`, `.QoiChannels`, `.QoiSpace` | the types are declared; nothing constructs one |
| `qoi.magic`, `.is_qoi`, `.end_marker`, `.header_size` | no |
| `qoi.channel_count`, `.space_byte`, `.pixel_count` | no |
| `qoi.decoded_size`, `.max_encoded_size`, `.write_header` | no |
| `qoiop.QoiOp`, `.QoiRunning` | the types are declared; nothing constructs one |
| `qoiop.op_name`, `.op_size`, `.op_pixels`, `.index_of` | no |
| `qoiop.running_new`, `.running_len`, `.remember`, `.recall` | no |
| `qoiop.apply`, `.choose`, `.read_op`, `.write_op` | no |
| `qoidec.QoiDecoder` | the type is declared; nothing constructs one |
| `qoidec.decoder`, `.with_channels`, `.feed`, `.finish` | no |
| `qoidec.header`, `.error`, `.total_in`, `.total_out`, `.is_done` | no |
| `qoidec.decode`, `.read_header` | no |
| `qoienc.QoiEncoder`, `.QoiWrite` | the types are declared; nothing constructs one |
| `qoienc.encoder`, `.start`, `.push`, `.push_samples`, `.finish` | no |
| `qoienc.error`, `.total_in`, `.total_out`, `.encode` | no |
| `qoierror.QoiError` | the type is declared; nothing constructs one |
| `qoierror.offset_of`, `.image_is_complete` | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
