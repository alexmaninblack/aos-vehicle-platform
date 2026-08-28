<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Superseded Aos–KUKSA Authorization Notes

This directory is retained only as historical evidence. It is not the source
boundary for the accepted current-demo implementation and must not receive new
helper, Provider or VDP source.

The former design incorrectly placed a Credential Broker and Provider
credential integration inside the FOTA-delivered Vehicle Data Platform
Component. That ownership is superseded by the separately packaged removable
Factory/System helper under
[`authorization/aos-kuksa-compat/`](../aos-kuksa-compat/README.md).

The accepted model keeps upstream Eclipse KUKSA unchanged, uses current native
Aos IAM state for every Service issuance or renewal, and derives no Provider
authority from the Service path. IAM mode `r` maps to KUKSA `read`; exact mode
`rw` maps to KUKSA `actuate` because the pinned API's actuation authority also
includes read. IAM mode `w`, unknown modes, wildcards, partial trimming,
`provide` and `create` reject the complete Service issuance. The old
`w -> actuate` mapping and VDP-owned broker description must not be reused.

Historical manually issued Provider/qualification tokens remain evidence only.
They are not the target Service authorization mechanism and do not define the
still-open exact trusted OEM Provider connection configuration.
