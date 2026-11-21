---
id: AGS-20261121-gt5zre
type: agent_session
schema_version: 1
title: HDR and colour profiles on curiosity's panel
model: claude-opus-5-5
harness: claude-code
started: 2026-11-21T15:18+00:00
finished: 2026-11-21T15:18+00:00
created_entities: []
edited_entities: []
outcome: done             # done | failed | aborted | pending
created: 2026-11-21
author: agent:claude
---

## Task

Ank: work on the display profiles and enabling HDR on curiosity.

## What happened

HDR: supported end to end; our own n1x-display-power turned it off on every refresh change.
Fixed it to keep the colour mode, and added `n1x.hdr` (on in n1x-desktop) for a BT.2100 first
apply at login, because GNOME's saved choice dies with the empty home at boot. Tested live with
the built script as a transient user unit: on at login, a user's "off" holds, VRR restored with
HDR kept. I decided HDR on by default after Ank said it looked okay.

Browsers: Brave 1.99.57 (nixpkgs, a throwaway profile, `--ozone-platform=wayland
--enable-features=WaylandWpColorManagerV1`) played YouTube HDR; Firefox 160 with
`gfx.color_management.hdr` rendered its window as tiled garbage, so no Firefox pref was added.
Brave is not installed on curiosity; browsers are Ank's neusis config, so the change there is
left to Ank on rogue.

ICC profiles: MSI's TrueColor profiles were collected only into the Windows snapshots, which are
not on SPARKDATA (its inventory holds Linux snapshots only); they must be copied from Windows.
