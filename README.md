# qoi-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`. Installing this package works;
calling it panics with `not implemented`.

## What this is

The Quite OK Image format, whole. The fourteen-byte header, all six
opcodes, the sixty-four-entry running array that is the entirety of
QOI's compression, and both directions over it: a feed-and-drain
decoder the host pumps, a whole-buffer decode for the common case, an
encoder that writes into a buffer the caller supplies at a size this
package can state exactly, and a whole-buffer encode for the caller who
would rather not.

**This interface is complete rather than a subset**, which is unusual
enough on this grid to be the first thing worth saying. QOI's
specification is one page: six opcodes, one header, one end marker, no
compression level, no filter choice, no interlacing, no ancillary
chunks, no extensibility. So anything an implementation of this cannot
do is a defect and not a scope decision — and that is why qoi-nv is the
package that proves the codec shape before png-nv pays for it.

```
novo pkg add qoi-nv
novo pkg build
novo test
```

## The one example that will work

```novo
use qoi
use qoidec
use qoienc

fn recompress(file: Bytes) -> Result<Bytes, QoiError>
    let (head, pixels) = qoidec.decode(file)!
    qoienc.encode(head, pixels)
```

For QOI — and for nothing else on this grid — that round trip is
**byte-identical to its input**. The specification fixes the encoder's
preference order, so there is no level, no strategy and no heuristic to
diverge on, and any two conforming encoders produce the same file from
the same pixels.

## The layer, and why

`core` — no effects at all, on a package whose subject is a file.

That is not a contradiction, it is the design. Decoding QOI is
arithmetic over bytes the caller already holds, and the state a decoder
carries between chunks is a sixty-four-entry table, one previous pixel
and six integers. No window, no Huffman tables, no row history. That is
what makes a QOI decoder affordable in a way almost nothing else on
this grid is, and it is why `core` is an honest layer here rather than
a claim.

The host does the reading. `qoidec.feed` takes whatever bytes have
arrived and hands back the pixels they produced plus the decoder to
feed next; `qoidec.finish` says whether the file was whole.

**There is deliberately no `read_all`.** flate-nv and png-nv both offer
the effect-polymorphic `read_all<S: Read[e]>` that writes the pump once
inside the package and is charged what the caller's stream costs. QOI
does not, because it would be a convenience that defeats its own
purpose: a QOI file expands to `w × h × channels` bytes with no
compression state at all, so a caller who cannot hold the whole input
certainly cannot hold the whole output, and `read_all` would build
exactly that. png-nv's arithmetic is different — a compressed PNG can
be a hundredth of its image — and that package has the function.

**The device claim is real, and the audit cannot check it.**
`tests/embedded_probe.nv` is firmware that runs the decoder's inner
loop — apply an opcode, hash the pixel, write it back to the table —
and it links for `--target=nrf52-qemu` when it is built by hand. The
audit's `core-embedded` row builds a probe from the package's OWN `src/`
only, so `use srgb` — a module of color-nv, the dependency the pixel
type comes from — resolves to nothing and the row goes red with two
type errors that look like the probe's fault. The row stays red and
this paragraph is the reason, because deleting the probe would make the
row pass by withdrawing a claim that is true. It is filed against the
audit under `tooling`.

What the probe deliberately does not touch is `Bytes`, `Str` and
`Result`, none of which exist at `@tier(embedded)` today. So the honest
statement is that QOI's *arithmetic* runs on a device and QOI's *I/O
surface* does not yet — which is the same sentence as "`bytes.zeros` is
`not embedded`", written where a reader will meet it.

## The load-bearing interface

```novo
pub fn decoder() -> QoiDecoder
pub fn feed(d: QoiDecoder, chunk: Bytes) -> (QoiDecoder, Bytes)
pub fn finish(d: QoiDecoder) -> Result<Unit, QoiError>
```

Three calls, and every other decoding function in the package is a
value they take, a value they return, or a convenience written in terms
of them. `feed` returns a NEW decoder rather than mutating one because
`[mutate]` is a host effect and this package has none — which is also
what makes a decoder safe to keep, fork or feed from two places.

A chunk may split anything: the header between its width and its
height, a `QoiOpLuma` between its two bytes, a run, the end marker.
Whatever a chunk could not finish is carried in the decoder and
completed by the next one.

**`feed` hands back pixels it has not verified**, and cannot do
otherwise: QOI has no checksum anywhere, and its only integrity checks
are the pixel count and the eight-byte end marker, both of which are at
the end. Only a successful `finish` says the file was whole. That is
worth stating twice, because it also means **a corrupt QOI file usually
decodes to a plausible image rather than to an error** — all 256 byte
values are valid opcodes. A caller who needs to know a file is intact
needs a checksum of their own.

The encoder is `start` / `push` / `finish` rather than `feed` /
`finish`, because a run spans pixels: `push` usually writes NOTHING —
it extends the run that is open — and a caller who stops without
calling `finish` loses the tail of their image.

## The reference implementation, and what is specification

`qoi.h` — Dominic Szablewski's single-file C reference — is the
implementation and the [qoi test images][corpus] are the oracle.

[corpus]: https://qoiformat.org/benchmark/

Unusually, the distinction the plan asks for is nearly empty here:
**almost everything about QOI is specification**, and this is the one
package on the grid whose correctness condition can be byte equality
rather than a round trip.

**Specification, and binding**

- The fourteen-byte header: the `qoif` magic, both dimensions as
  unsigned 32-bit BIG-endian, the channels byte (3 or 4) and the
  colorspace byte (0 or 1).
- All six opcodes and their tags, including the interaction that makes
  `QoiOpRun` stop at 62: `11111110` and `11111111` are the two literal
  tags, so runs of 63 and 64 do not exist.
- The index hash `(r*3 + g*5 + b*7 + a*11) % 64`. Nothing about those
  multipliers is optimal and a better hash is a different format.
- The two disagreeing initial states: the running array starts as
  sixty-four *fully transparent* pixels and the previous-pixel register
  starts as *opaque black*. An implementation that seeds both the same
  way decodes almost every image correctly and a black one wrongly.
- The encoder's preference order — index, diff, luma, literal — which
  is what makes byte equality a fair test.
- The eight-byte end marker: seven zeroes and a one.

**This package's own choices**

- That the colorspace byte and the channels byte are REFUSED at values
  the specification does not define, rather than clamped or ignored.
  Both are purely informative and change no opcode, so a lenient reader
  would be conforming; this one is strict, because a file that
  disagrees with the specification in a field nothing reads was not
  written by a QOI encoder.
- `qoidec.with_channels`, which drains a fixed channel count rather
  than the header's. The reference implementation has the same
  parameter; nothing in the format requires it.
- Refusing a width or height of zero. The format permits the header;
  there is no body it could have.

**Deliberately not ported:** nothing. If something in `qoi.h` has no
counterpart here it is an omission to file, not a decision.

## Status

Every function is `todo()`. `novo test` runs the API suite, and every
assertion in it reaches `not implemented: qoi-nv.<module>.<fn>` — which
is the expected result until the bodies land, and is what makes the
suite a description of the interface rather than of nothing.
`novo test --isolate tests/<file>` is the readable form: one verdict
per test, naming the function it stopped at.

The suite is more binding than most on this grid: QOI's specification
fixes the opcode sizes, the hash, both initial states and the maximum
run, so a body that disagrees with one of those assertions is wrong
rather than different.

| module | public types | functions | implemented |
| --- | --- | --- | --- |
| `qoi` | 3 | 10 | no |
| `qoiop` | 2 | 12 | no |
| `qoidec` | 1 | 11 | no |
| `qoienc` | 2 | 9 | no |
| `qoierror` | 1 | 2 | no |
| **total** | **9** | **44** | **no** |
