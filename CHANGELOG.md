# Changelog

## 0.1.0 — 2026-09-27

The first implementation of the interface published as 0.0.1: the
whole format, decoded and encoded.

### Added

- `qoidec` decodes in chunks of any size, checks the header field by
  field, refuses an image of 400,000,000 pixels or more as `qoi.h`
  does, and checks the end marker as soon as it arrives.
- `qoienc` writes the bytes the reference encoder writes, which the
  official test images and a differential against `tools/qoiref.py`
  confirm.
- `tools/qoiref.py`, a Python codec and PNG reader, and the corpus,
  differential and stream suites.

### Changed

These break code written against 0.0.x.

- `qoi.write_header`, `qoiop.write_op`, `qoienc.start`, `push`,
  `push_samples` and `finish` take their output buffer as a `var`
  parameter and write into it in place.  A caller passes a `var` name
  or a new buffer; `QoiWrite.buf` is a `var` field, so a `var` write
  result can be passed back in.
- `qoienc.push_samples` fails the encoder with `QoiBadChannels` for a
  channel count other than 3 or 4, where the interface said nothing.
- A run is written with the image's last pixel, so `qoienc.finish`
  writes only the end marker.
- A pixel pushed into a three-channel image is taken as opaque.
- The dependency is color-nv `^0.1.1`, and the toolchain floor is
  0.13.0.

### Removed

- `tests/embedded_probe.nv` and the README's section on running on a
  microcontroller.  The pixel type is color-nv's `Srgba8`, a plain
  struct, which an embedded build refuses to construct, so the claim
  could not be made good.

## 0.0.2 — 2026-09-15

- README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1

- The interface, covering the whole format: the fourteen-byte header,
  all six opcodes, the sixty-four-entry running array, a feed-and-drain
  decoder and a whole-buffer one, and an encoder that writes into a
  caller-supplied buffer or allocates its own.
- Every body is `todo()`. Nothing is implemented.
