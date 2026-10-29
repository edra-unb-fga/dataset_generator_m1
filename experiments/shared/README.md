# Shared study transport

`colab_transport.py` is a standard-library-only helper for SHA-256 checked chunk
transfer, atomic status JSON, and CLI output with proxy tokens redacted. Upload
this file itself when a remote study needs to reassemble a bundle without the
repository installed. The two older study `colab_chunking.py` files are local
compatibility entry points.

Allocation budgets, polling, watchdogs, archive retrieval, and shutdown remain in
each study's supervisor. Sharing transport does not change historical study
policies or authorize extra runtime allocations. New studies should reuse these
transport primitives while documenting their own resource and lifecycle policy.
