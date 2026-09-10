# Changelog

## 0.0.1

- The interface, covering the whole format: the fourteen-byte header,
  all six opcodes, the sixty-four-entry running array, a feed-and-drain
  decoder and a whole-buffer one, and an encoder that writes into a
  caller-supplied buffer or allocates its own.
- Every body is `todo()`. Nothing is implemented.
