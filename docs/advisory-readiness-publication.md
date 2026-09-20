<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Advisory readiness transition publication

VDP V3 forwards each team's current producer readiness on a boolean change,
not only at the five-second heartbeat. The existing target observer and main
VISS loop remain the only routes; no extra socket, credential or queue is added.

Only a matching successful VISS Set reply acknowledges that availability
publication. This is never proof of a warning being applied. One Set may be
in flight per endpoint. Attempts are at least 100 ms apart; a rejected reply
or two-second response timeout imposes a one-second retry delay. A retry uses
the latest observed readiness, never a retained transition queue. Peers have
independent state/timers, and a new VISS attachment republishes current values.
An unchanged value has a five-second heartbeat after its successful reply.

Canonical schema, producer expiry (15 seconds), negative/future-date checks,
Gateway authority, request/status correlation and warning leases are unchanged.
An unavailable target observer immediately makes both current producer values
false. There is no debounce, fabricated readiness or Cloud dependency. Normal
short reconnection may remain visible; the fix removes the five-second stale
status amplification, not truthful reporting of a real interruption.

Tests cover false-first and true-first renewal ordering, peer isolation,
heartbeat, genuine loss/recovery, stale/malformed/future data, pending writes,
rejection/timeout/late ACK, send exceptions, bounded bursts and reconnect.
Local tests do not establish live deployment qualification.
