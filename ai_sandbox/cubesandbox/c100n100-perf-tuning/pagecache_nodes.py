#!/usr/bin/env python3
"""Report (and optionally evict) the page-cache NUMA placement of files shared by sandbox VMs.

usage: pagecache_nodes.py [--evict] FILE...
Only resident pages are inspected (mincore); touching them is a minor fault, nothing is
read from disk. --evict calls posix_fadvise(DONTNEED) which drops clean cached pages only;
file content is untouched. Prints JSON lines per file.
"""
import collections
import ctypes
import json
import os
import sys

libc = ctypes.CDLL(None, use_errno=True)
libc.mmap.restype = ctypes.c_void_p
PAGE = 4096
SYS_MOVE_PAGES = 239  # arm64


def nodes(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        size = os.fstat(fd).st_size
        if size == 0:
            return {'file': path, 'size': 0}
        base = libc.mmap(None, ctypes.c_size_t(size), 1, 1, fd, ctypes.c_long(0))
        n = (size + PAGE - 1) // PAGE
        vec = (ctypes.c_ubyte * n)()
        libc.mincore(ctypes.c_void_p(base), ctypes.c_size_t(size), vec)
        resident = [i for i in range(n) if vec[i] & 1]
        dist = collections.Counter()
        for start in range(0, len(resident), 65536):
            chunk = resident[start:start + 65536]
            for i in chunk:
                ctypes.c_ubyte.from_address(base + i * PAGE).value
            pages = (ctypes.c_void_p * len(chunk))(*[base + i * PAGE for i in chunk])
            status = (ctypes.c_int * len(chunk))()
            libc.syscall(SYS_MOVE_PAGES, 0, ctypes.c_ulong(len(chunk)), pages, None, status, 0)
            dist.update(status[i] for i in range(len(chunk)))
        libc.munmap(ctypes.c_void_p(base), ctypes.c_size_t(size))
        return {'file': path, 'size': size, 'resident_pages': len(resident),
                'nodes': {str(k): v for k, v in sorted(dist.items())}}
    finally:
        os.close(fd)


evict = '--evict' in sys.argv
for path in [a for a in sys.argv[1:] if a != '--evict']:
    before = nodes(path)
    if evict:
        fd = os.open(path, os.O_RDONLY)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        os.close(fd)
        before['after_evict'] = nodes(path).get('resident_pages')
    print(json.dumps(before))
