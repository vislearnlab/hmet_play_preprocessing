# Multi-Camera Recording Setup — Design Spec (Draft for Team Review)

**Project:** Multi-camera behavioral experiment recording setup
**Application:** Long-duration (~1-hour) adult–toddler interaction tracking
**Platform:** Windows 11 Pro (x64)
**Output format:** Matroska (`.mkv`)
**Status:** Draft for discussion. Several technical claims are unverified — see [Claims to verify](#claims-to-verify-before-finalizing) before treating any numbers as settled.

---

## ⚠️ Claims to verify before finalizing

These items are carried over from the original note but look questionable. They materially affect hardware choice, storage budget, and sync design, so confirm each against Orbbec's official documentation before committing.

1. **Femto Bolt "uncompressed 4K RGB" claim.** The note contrasts the Bolt (allegedly raw/uncompressed color) against the Mega (compressed). The Bolt's RGB path uses standard color stream formats (e.g. MJPEG/NV12) rather than truly uncompressed 4K, so the "encoding artifacts blur finger boundaries" argument for choosing Bolt over Mega may not hold. Verify actual RGB stream formats for both.
2. **Throughput figures (200–350 GB per camera per hour).** These look far too high for 15 fps at 1024×1024 depth + 4K color. If the real number is a fraction of this, the entire storage plan (scratch disk size, archiving chain) should be re-scoped. Recompute from actual per-frame sizes.
3. **Sync hardware names and offset values.** "Orbbec Multi-Camera Sync Hub Pro," the "dongle" naming, and the specific 160 µs / 320 µs offsets should be checked against Orbbec's actual multi-camera sync product line and documented exposure-delay ranges.
4. **Reolink integration.** A consumer security camera can serve as a contextual/backup channel, but treating it as cleanly integrable into a *synchronized scientific* pipeline understates timestamp-alignment problems. Decide explicitly whether it is synced or just a loose reference channel.

---

## 1. Hardware selection

### 1.1 Primary depth sensor — Femto Bolt vs. Femto Mega

Proposed choice: **Orbbec Femto Bolt**, on the following reasoning (items 1 and 2 flagged above):

- **Data fidelity** *(verify)* — Bolt streams depth and color via host-side pipelines; the note claims this avoids the Mega's on-device compression and associated artifacts on fine object/finger boundaries.
- **Thermal behavior** — Bolt offloads processing to the host PC rather than an onboard processor in a sealed enclosure, which the note argues reduces thermal-throttling and dropped-frame risk over continuous 1-hour sessions.
- **Platform** — the depth engine depends on Windows/Linux libraries; **macOS is not supported**. Plan for Windows (or Linux) hosts only.

### 1.2 Auxiliary — Reolink 4K camera *(see flag 4)*

- **Role:** secondary wide-angle contextual channel for session timestamps, annotation verification, and environment backup.
- **Setup:** Ethernet to the local switch; native Reolink client running in the background. H.265 compression keeps its footprint small relative to the depth streams.
- **Open question:** confirm whether this channel needs frame-level sync with the depth cameras or is acceptable as a loosely-aligned reference.

---

## 2. Camera layout & occlusion strategy

### 2.1 Three-camera arrangement

Goal: minimize body occlusion (e.g. adult torso blocking the toddler's hands) using three depth sensors:

1. **Camera 1 — Top-down anchor.** Mounted directly above the interaction table, facing straight down. Tracks hand trajectories and grip with no torso interference.
2. **Camera 2 — Adult side.** Tripod at ~adult shoulder height (≈4.5–5 ft), left-side offset angle on the table.
3. **Camera 3 — Toddler side.** Low tripod at ~toddler eye level (≈2.5–3 ft), right-side offset angle for facial profile and fine gestures.

```
          [Camera 1: Top-down, ceiling mount]
                          |
                          v
   [Camera 2: Left]  -->  Adult   Toddler  <--  [Camera 3: Right]
```

### 2.2 Workstation & control-room layout

- **Workstation:** place the Windows tower inside the testing room next to the cameras; connect with short (~2 m) USB-C cables to avoid long-run USB noise/dropouts.
- **Control bridge:** run a single Cat6 line through a wall conduit to the adjacent room.
- **Remote control:** operate via Windows Remote Desktop from a laptop in the quiet room — launch capture, monitor streams, and check disk logging without entering the testing area.

---

## 3. Storage & bandwidth

### 3.1 Data budget *(numbers unverified — see flag 2)*

| Metric | Single camera | 3-camera array (1 hr) |
|---|---|---|
| Throughput | ~200–350 GB/hr *(verify)* | ~600 GB–1.0 TB *(verify)* |
| Frame rate | 15 fps | 15 fps |
| Depth mode | WFOV_UNBINNED (1024×1024) | WFOV_UNBINNED (1024×1024) |
| Color mode | 2160p (4K) | 2160p (4K) |

Recompute the throughput row from measured per-frame sizes before sizing disks.

### 3.2 Storage rules

1. **Write locally, never to NAS during capture.** Recording live to network storage risks saturating the link and dropping frames.
2. **Dedicated scratch disk.** Capture to an internal PCIe Gen 4 NVMe SSD with sustained writes comfortably above the real (verified) throughput; the note cites >1500 MB/s.
3. **Archive after the session.** Once files are committed/locked, move folders over the LAN to shared network storage for archival.

---

## 4. Multi-camera synchronization *(hardware names & offsets unverified — see flag 3)*

Rationale: overlapping time-of-flight IR emitters can interfere, creating blind spots and noise, so the cameras should be hardware-synced with staggered firing.

### 4.1 Components *(verify against Orbbec's actual sync product line)*

- 1× Orbbec multi-camera sync hub
- 3× sync cables/adapters
- 3× Cat5e/Cat6 cables used only as low-voltage trigger lines (not network data)

### 4.2 Wiring

1. Connect all three Bolts to separate USB root hubs (e.g. via a multi-channel PCIe USB expansion card).
2. Designate **Camera 1 (top-down) as master** into the hub's primary/in port.
3. Designate **Cameras 2 and 3 as subordinates** off the hub's secondary/out ports.

### 4.3 Trigger offsets *(specific values unverified)*

- Master fires at the start of the frame window.
- Subordinate 2: offset delay ≈160 µs.
- Subordinate 3: offset delay ≈320 µs.

Confirm both the need for staggering and the exact permissible offset values in Orbbec's documentation.

---

## Discussion questions for the team

- Are we committed to Bolt, or should we re-run the Bolt-vs-Mega comparison once the RGB-format and throughput claims are verified?
- What is the real per-session data volume, and does it change our scratch-disk and archival plan?
- Is the Reolink a synced channel or a loose reference? Who owns aligning it in post?
- Do we actually need hardware sync at these offsets, or is software timestamp alignment sufficient for our analyses?
