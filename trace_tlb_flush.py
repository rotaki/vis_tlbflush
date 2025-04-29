#!/usr/bin/env python3
#
# trace_tlb_flush.py – send every tlb:tlb_flush tracepoint to Telegraf/InfluxDB
#
# Prereqs:
#   • root privileges
#   • BCC/BPF (apt install bpfcc-tools python3-bcc on Ubuntu)
#   • Telegraf socket_listener on UDP/8089 with data_format="influx"
#
from bcc import BPF
import socket, time, os, sys
BOOT2EPOCH_NS = time.time_ns() - time.monotonic_ns()   # << NEW

# ──────────────────────────────────── User settings ──────────────────────────
UDP_ADDR = ("127.0.0.1", 8089)  # Telegraf [[inputs.socket_listener]]

# ──────────────────────────── UDP helper + escaping ─────────────────────────-
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(UDP_ADDR)

def esc_tag(s: str) -> str:
    """Escape ,  =  and space – illegal in tag keys/values."""
    return s.replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")

def esc_field_string(s: str) -> str:
    """Escape quotes and backslashes inside a string field."""
    return s.replace("\\", "\\\\").replace('"', '\\"')

# ───────────────────────────── eBPF program source ───────────────────────────
bpf_text = r"""
#include <uapi/linux/ptrace.h>

struct event_t {
    u64 ts;
    u32 cpu;
    u32 reason;
    char comm[16];
};

BPF_RINGBUF_OUTPUT(events, 256 * 1024);   /* 256 KiB */

TRACEPOINT_PROBE(tlb, tlb_flush)
{
    struct event_t *e = events.ringbuf_reserve(sizeof(*e));
    if (!e)
        return 0;

    e->ts     = bpf_ktime_get_ns();
    e->cpu    = bpf_get_smp_processor_id();
    e->reason = args->reason;
    bpf_get_current_comm(&e->comm, sizeof(e->comm));

    events.ringbuf_submit(e, 0);
    return 0;
}
"""

# ───────────────────────────── userspace consumer ────────────────────────────
reason_lookup = {
    0: "TLB_FLUSH_ON_TASK_SWITCH",
    1: "TLB_REMOTE_SHOOTDOWN",
    2: "TLB_LOCAL_SHOOTDOWN",
    3: "TLB_LOCAL_MM_SHOOTDOWN",
    4: "TLB_REMOTE_SEND_IPI",
}

print("time-s   CPU  ID  REASON")

start_ns, bpf = None, BPF(text=bpf_text)
fmt = "{:8.3f}  {:<3}  {:<2}  {}"

def handle_event(ctx, data, size):
    global start_ns
    e = bpf["events"].event(data)

    if e.reason == 0:
        # skip task-switch events
        return

    # ─── console pretty-print (optional) ────────────────────────────────────
    if start_ns is None:
        start_ns = e.ts
    rel = (e.ts - start_ns) / 1e9
    print(fmt.format(rel, e.cpu, e.reason,
                     reason_lookup.get(e.reason, "UNKNOWN")),
          e.comm.decode(errors="replace").rstrip("\0"))

    # ─── build Influx Line Protocol record ──────────────────────────────────
    comm = e.comm.decode(errors="replace").rstrip("\0") or "unknown"

    tagset   = f"cpu={e.cpu},comm={esc_tag(comm)}"
    fieldset = (
        f"reason={e.reason}i,"
        f'reason_str="{esc_field_string(reason_lookup.get(e.reason, "UNKNOWN"))}"'
    )
    ts_epoch = e.ts + BOOT2EPOCH_NS   # ← NEW

    lp = f"tlb_flush,{tagset} {fieldset} {ts_epoch}"   # ← space before field-set

    print(lp.encode())
    
    try:
        sent = sock.send(lp.encode())
        if sent != len(lp):
            print("⚠️  partial UDP send", file=sys.stderr)
    except Exception as ex:
        print("⚠️  UDP send failed:", ex, file=sys.stderr)

# attach ring-buffer consumer
bpf["events"].open_ring_buffer(handle_event)

try:
    while True:
        bpf.ring_buffer_poll()   # blocks until at least one event
except KeyboardInterrupt:
    pass
