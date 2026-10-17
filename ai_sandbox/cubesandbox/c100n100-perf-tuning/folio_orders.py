#!/usr/bin/env python3
"""Report the page-cache folio sizes backing files (read-only; root required).

usage: folio_orders.py FILE...
           folio_orders.py --experiment DIR   (temp-file readahead experiment, file removed after)
For each resident 4K page (mincore) the page is touched through a private read-only
mapping (minor fault, no IO), its PFN read from /proc/self/pagemap and its flags from
/proc/kpageflags. A page with neither COMPOUND_HEAD nor COMPOUND_TAIL is an order-0 folio;
otherwise the folio size is counted as head + following contiguous tail PFNs.
"""
import collections
import ctypes
import json
import os
import struct
import sys

libc = ctypes.CDLL(None, use_errno=True)
libc.mmap.restype = ctypes.c_void_p
PAGE = 4096
KPF_HEAD, KPF_TAIL, KPF_THP = 1 << 15, 1 << 16, 1 << 22
MADV = {'none': None, 'hugepage': 14, 'random': 1}


def mapped(path, size):
    fd = os.open(path, os.O_RDONLY)
    base = libc.mmap(None, ctypes.c_size_t(size), 1, 1, fd, ctypes.c_long(0))  # PROT_READ, MAP_SHARED
    os.close(fd)
    return base


def folio_sizes(path):
    size = os.stat(path).st_size
    base = mapped(path, size)
    n = (size + PAGE - 1) // PAGE
    vec = (ctypes.c_ubyte * n)()
    libc.mincore(ctypes.c_void_p(base), ctypes.c_size_t(size), vec)
    resident = [i for i in range(n) if vec[i] & 1]
    # Unbuffered reads: a buffered reader would serve stale pagemap entries cached before
    # the corresponding page was touched.
    pagemap = os.open('/proc/self/pagemap', os.O_RDONLY)
    kflags = os.open('/proc/kpageflags', os.O_RDONLY)
    pfn_flags = {}
    for i in resident:
        ctypes.c_ubyte.from_address(base + i * PAGE).value
        entry = struct.unpack('Q', os.pread(pagemap, 8, ((base + i * PAGE) // PAGE) * 8))[0]
        if not entry >> 63 & 1:
            continue
        pfn = entry & ((1 << 55) - 1)
        pfn_flags[i] = (pfn, struct.unpack('Q', os.pread(kflags, 8, pfn * 8))[0])
    os.close(pagemap)
    os.close(kflags)
    libc.munmap(ctypes.c_void_p(base), ctypes.c_size_t(size))
    hist = collections.Counter()   # folio size in KiB -> number of 4K pages in such folios
    thp_pages = 0
    i_sorted = sorted(pfn_flags)
    idx = 0
    while idx < len(i_sorted):
        i = i_sorted[idx]
        pfn, fl = pfn_flags[i]
        if fl & KPF_THP:
            thp_pages += 1
        if not fl & (KPF_HEAD | KPF_TAIL):
            hist[4] += 1
            idx += 1
            continue
        # walk a run of the same compound folio: head (or a tail if head is not resident) + tails
        run = 1
        while idx + run < len(i_sorted):
            j = i_sorted[idx + run]
            pj, fj = pfn_flags[j]
            if j - i == run and pj - pfn == run and fj & KPF_TAIL:
                run += 1
            else:
                break
        hist[run * 4] += run
        idx += run
    total = sum(hist.values())
    return {'file': path, 'resident_pages': len(resident), 'mapped_pages': total,
            'order0_pct': round(100 * hist.get(4, 0) / total, 1) if total else None,
            'pages_by_folio_kib': {str(k): v for k, v in sorted(hist.items())}, 'thp_flag_pages': thp_pages}


def experiment(directory):
    path = os.path.join(directory, 'folio-experiment.tmp')
    size = 64 << 20
    with open(path, 'wb') as f:
        chunk = os.urandom(1 << 20)
        for _ in range(size >> 20):
            f.write(chunk)
        f.flush()
        os.fsync(f.fileno())
    results = []
    try:
        for mode in ('none', 'hugepage', 'random'):
            fd = os.open(path, os.O_RDONLY)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            os.close(fd)
            base = mapped(path, size)
            if MADV[mode] is not None:
                libc.madvise(ctypes.c_void_p(base), ctypes.c_size_t(size), MADV[mode])
            for off in range(0, size, PAGE):          # sequential read faults, like a guest touching memory
                ctypes.c_ubyte.from_address(base + off).value
            libc.munmap(ctypes.c_void_p(base), ctypes.c_size_t(size))
            r = folio_sizes(path)
            r['mode'] = 'mmap read, madvise=' + mode
            results.append(r)
    finally:
        fd = os.open(path, os.O_RDONLY)
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        os.close(fd)
        os.unlink(path)
    return results


if sys.argv[1] == '--experiment':
    for r in experiment(sys.argv[2]):
        print(json.dumps(r))
else:
    for p in sys.argv[1:]:
        print(json.dumps(folio_sizes(p)))
