# n1x-pen: the pen's pressure feel on GNOME, without typing gsettings paths.
#
# GNOME keeps two settings per stylus (org.gnome.desktop.peripherals.tablet.stylus, stored
# under /org/gnome/desktop/peripherals/stylus/<id>/):
#   pressure-range [min, max]   the part of the pen's physical range that maps to 0..100 %;
#                               a lower max reaches full pressure with a lighter touch
#                               (applied in libinput, so every app sees it)
#   pressure-curve [x1, y1, x2, y2]   a Bezier curve on top of that; Settings' "tip feel"
#                               slider only covers part of it
# A stylus gets its <id> the first time GNOME sees it; until then the ELAN panel's
# serial-less pen is expected at default-04f3:4516 (mutter: default-<vendor>:<product>).
#
# The live image forgets dconf at every boot, so `n1x-pen save` keeps the current choice on
# SPARKDATA and the n1x-pen user service applies it at each login (and to a stylus GNOME
# first sees later in the session).

set -u
# The settings live in the desktop user's dconf. Under sudo, dconf would write root's (and
# GNOME never sees it: `sudo n1x-pen soft` did nothing on 2026-11-11), so go back to the
# user who ran sudo, on their session bus.
# `record` is the exception: it reads the pen's input device, which needs root.
if [ "${1:-}" = record ]; then
  [ "$(id -u)" = 0 ] || { echo "run with sudo: sudo n1x-pen record" >&2; exit 2; }
  dev=
  for e in /sys/class/input/event*; do
    case $(cat "$e/device/name" 2>/dev/null) in *Stylus*) dev=/dev/input/${e##*/}; break ;; esac
  done
  [ -n "$dev" ] || { echo "no stylus input device found" >&2; exit 1; }
  out=/tmp
  mountpoint -q /mnt/sparkdata && out=/mnt/sparkdata/bootlogs/$(cat /proc/sys/kernel/hostname)
  mkdir -p "$out"
  f=$out/pen-record-$(date +%Y%m%d_%H%M%S).yml
  echo "Recording $dev for 20 s: draw a few slow, light strokes, then a few normal ones."
  timeout -s INT 20 libinput record -o "$f" "$dev"
  echo "written to $f"
  exit 0
fi
if [ "$(id -u)" = 0 ]; then
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    uid=$(id -u "$SUDO_USER")
    exec sudo -u "$SUDO_USER" env DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
      XDG_RUNTIME_DIR="/run/user/$uid" "$0" "$@"
  fi
  echo "run n1x-pen as the desktop user, not root (no sudo needed)" >&2; exit 2
fi
DIR=/org/gnome/desktop/peripherals/stylus/
GUESS=default-04f3:4516/
CONF=/mnt/sparkdata/config/n1x-pen.conf

usage() {
  cat <<'EOF'
n1x-pen                       show the stylus settings and the saved choice
n1x-pen PRESET                default | soft | softer | softest | feather
n1x-pen range MIN MAX         e.g. `n1x-pen range 0 40` (0..100, MIN < MAX)
n1x-pen curve X1 Y1 X2 Y2     e.g. `n1x-pen curve 0 80 20 100` (0..100)
n1x-pen save                  keep the current setting across reboots (SPARKDATA; asks sudo)
n1x-pen forget                drop the saved setting
sudo n1x-pen record           20 s of raw pen events to SPARKDATA (for skipping strokes)
Presets (range; curve):
  default  [0, 100]; [0, 0, 100, 100]     the hardware as is
  soft     [0, 70];  [0, 30, 70, 100]
  softer   [0, 50];  [0, 50, 50, 100]
  softest  [0, 35];  [0, 75, 25, 100]
  feather  [0, 25];  [0, 90, 10, 100]
EOF
}

# Stylus entries GNOME has created, plus the expected one for the ELAN pen.
entries() {
  { dconf list "$DIR" 2>/dev/null | grep '/$'; echo "$GUESS"; } | sort -u
}

num() { [[ $1 =~ ^[0-9]+$ ]] && [ "$1" -le 100 ]; }

set_values() {   # $1 range "[a, b]", $2 curve "[a, b, c, d]"
  local e
  for e in $(entries); do
    dconf write "$DIR${e}pressure-range" "$1" || return 1
    dconf write "$DIR${e}pressure-curve" "$2" || return 1
  done
  echo "pressure-range $1, pressure-curve $2 (on: $(entries | tr '\n' ' '))"
  if [ "$(entries)" = "$GUESS" ]; then
    echo "note: GNOME has stored nothing for the pen yet, so this went to the expected entry"
    echo "      ($GUESS). If the pen feels the same, move Settings > Wacom Tablet > Stylus >"
    echo "      Tip Pressure Feel once (that creates the pen's real entry) and run this again."
  fi
}

current() {      # range and curve of the first entry that has them
  local e r c
  for e in $(entries); do
    r=$(dconf read "$DIR${e}pressure-range"); c=$(dconf read "$DIR${e}pressure-curve")
    if [ -n "$r$c" ]; then echo "${r:-[0, 100]}|${c:-[0, 0, 100, 100]}"; return; fi
  done
  echo "[0, 100]|[0, 0, 100, 100]"
}

preset() {
  case $1 in
    default) set_values "[0, 100]" "[0, 0, 100, 100]" ;;
    soft)    set_values "[0, 70]"  "[0, 30, 70, 100]" ;;
    softer)  set_values "[0, 50]"  "[0, 50, 50, 100]" ;;
    softest) set_values "[0, 35]"  "[0, 75, 25, 100]" ;;
    feather) set_values "[0, 25]"  "[0, 90, 10, 100]" ;;
    *) return 2 ;;
  esac
}

val() {          # $1 key path, $2 GNOME's default when unset
  local v
  v=$(dconf read "$1")
  echo "${v:-$2 (default)}"
}

show() {
  local e
  echo "stylus entries (${DIR}):"
  for e in $(entries); do
    printf '  %-24s range %-20s curve %s\n' "$e" \
      "$(val "$DIR${e}pressure-range" "[0, 100]")" \
      "$(val "$DIR${e}pressure-curve" "[0, 0, 100, 100]")"
  done
  if [ -r "$CONF" ]; then
    echo "saved ($CONF): $(tr '\n' ' ' < "$CONF")"
  else
    echo "saved: nothing (the live image starts from GNOME's defaults)"
  fi
}

load_conf() {    # sets R and C from the saved file
  R=$(sed -n 's/^range=//p' "$CONF" 2>/dev/null); C=$(sed -n 's/^curve=//p' "$CONF" 2>/dev/null)
  [ -n "$R" ] && [ -n "$C" ]
}

case ${1:-show} in
  show) show ;;
  -h|--help|help) usage ;;
  default|soft|softer|softest|feather) preset "$1" ;;
  range)
    if ! { [ $# = 3 ] && num "$2" && num "$3" && [ "$2" -lt "$3" ]; }; then usage; exit 2; fi
    set_values "[$2, $3]" "$(current | cut -d'|' -f2)" ;;
  curve)
    if ! { [ $# = 5 ] && num "$2" && num "$3" && num "$4" && num "$5"; }; then usage; exit 2; fi
    set_values "$(current | cut -d'|' -f1)" "[$2, $3, $4, $5]" ;;
  save)
    cur=$(current)
    sudo mkdir -p "${CONF%/*}" &&
      printf 'range=%s\ncurve=%s\n' "${cur%%|*}" "${cur#*|}" | sudo tee "$CONF" >/dev/null &&
      echo "saved to $CONF: $(tr '\n' ' ' < "$CONF")" ;;
  forget) sudo rm -f "$CONF" && echo "removed $CONF" ;;
  # For the user service: apply the saved choice now, then to each stylus GNOME adds later.
  apply)
    load_conf || { echo "nothing saved in $CONF"; exit 0; }
    set_values "$R" "$C"
    seen=" $(entries | tr '\n' ' ') "
    dconf watch "$DIR" | while read -r _; do
      for e in $(entries); do
        case $seen in *" $e "*) continue ;; esac
        seen="$seen$e "
        dconf write "$DIR${e}pressure-range" "$R"; dconf write "$DIR${e}pressure-curve" "$C"
        echo "new stylus $e: pressure-range $R, pressure-curve $C"
      done
    done ;;
  *) usage; exit 2 ;;
esac
