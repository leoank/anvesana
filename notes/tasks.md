# Tasks

Loose todos not tied to a page. Anything tied to an experiment, run or material belongs on
that page instead.

- [ ] Speaker tuning for N1X (bbaum-pc-7), revisit later: (1) ask upstream (dcemin-nv alsa-ucm-conf PR 862 / alsa-devel) whether Realtek/MSI will publish rt1320 .dat firmware; (2) measure with a calibrated USB mic (UMIK-1): log sweeps on Windows (MSI tuning active) and Linux from 5-9 positions, fit EQ = Windows/Linux ratio into the Speakers (DSP) filter-chain, level sweeps to set high-pass and limiter; (3) only if protection params are wanted: decode RTKDAT_1462.dat from a live kernel memory dump or Ghidra, validate against measurements before loading, keep it in nix/local (never git)
- [ ] External displays on curiosity, when back at the office with the monitors: (1) USB-C monitor shows nothing: at boot ucsi_acpi logs 'GET_CURRENT_CAM command failed' and no DisplayPort alt mode registers on either port; record a plug on each port (udev drm/typec, typec partner altmodes, journal) and note the monitor model; (2) HDMI works but GNOME mirror mode does not: try it and note how it fails; check whether the HDMI monitor shares a mode with the 3840x2400 (16:10) panel
