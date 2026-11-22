# MoodyCam

A Kodi add-on for UniFi Protect. When a camera sees a person, a package, a
vehicle, an animal, motion, or someone rings the doorbell, MoodyCam pops that
camera up in a corner of the screen for a few seconds, over whatever you're
watching. Press any button to close it early.

## Install

First, in Kodi: Settings → System → Add-ons → turn on **Unknown sources**
(confirm the warning).

### Option A: from the MoodyCam repository (recommended, updates itself)

1. **Add the source.** Settings → File manager → Add source → `<None>` →
   type this address exactly, then OK:

   ```
   https://moodyjim.github.io/moodycam/
   ```

   Name it `moodycam` and press OK.
2. **Install the repository.** Add-ons → Install from zip file → `moodycam`
   → `repository.moodycam-x.x.x.zip`.
3. **Install MoodyCam.** Add-ons → Install from repository → MoodyCam
   Repository → Services → MoodyCam → Install.

Kodi now keeps MoodyCam up to date on its own.

### Option B: from a zip file

**[⬇ Download the latest version (service.moodycam.zip)](https://github.com/moodyjim/moodycam/releases/latest/download/service.moodycam.zip)**

Get the zip onto the Kodi device (download it there, copy it on a USB stick,
or put it on a network share), then Add-ons → Install from zip file → pick
`service.moodycam.zip`. To update, download the latest zip and install it
again. Your settings are kept.

> Use the link above, not GitHub's green "Code → Download ZIP" button. That
> zip has the wrong folder name inside, and Kodi won't install it properly.

## Setup

1. **Make an API key.** On the UniFi console that runs Protect (UNVR, UDM,
   Cloud Key, ...): Settings → Control Plane → Integrations → create an API
   key. Copy it.
2. **Check the network.** The Kodi device must be able to reach the Protect
   console on TCP port 443. If they're on different networks or VLANs (for
   example Kodi on an IoT network and the cameras on a security network),
   add a firewall rule that allows it.
3. **Enter the address and key.** Add-ons → My add-ons → Services →
   MoodyCam → Configure → Connection. Enter the console's IP address (or
   domain name, see [the certificate setting](#check-the-security-certificate))
   and paste the API key. Typing a long key with a remote is painful, so on
   CoreELEC or LibreELEC you can
   [set it over SSH](#set-the-address-and-key-over-ssh) instead.
4. **Test it.** Configure → Tools → **List my cameras** (checks the
   connection and shows your camera names), then **Show a test pop-up**.

That's it. MoodyCam runs in the background whenever Kodi is on.

## Full-screen view

MoodyCam can also show your cameras full screen, up to 9 at once: one
camera fills the screen, 2 sit side by side, 3–4 make a 2×2 grid and 5–9 a
3×3 grid. It shows the cameras from **Cameras to watch**, in the order you
typed them, or all cameras if that's blank. Pictures refresh at the
**Picture refresh** rate.

**Opening it**
- From Kodi: Add-ons → Program add-ons → **MoodyCam**.
- From a skin's menu or a button: have it run
  `RunScript(service.moodycam,fullscreen)`.
- Over SSH (CoreELEC/LibreELEC):
  `kodi-send --action="RunScript(service.moodycam,fullscreen)"`

**Remote control**
- **Arrow keys**: move the red highlight between cameras.
- **OK / Select**: show the highlighted camera on its own, full screen.
- **Back**: from a single camera, return to the grid; from the grid, close
  the view.

Anything playing is paused while the view is open and resumes when you close
it. Corner pop-ups are switched off while the view is open (the cameras are
already on screen). If a camera can't be reached, its tile says
**Unavailable** and the others keep working.

## Settings

**Connection**
- **Protect address**: the console's IP address or domain name.
- **API key**: the key from step 1 of Setup.
- **Check the security certificate**: leave off unless you use a domain
  name with a real certificate. [Details below.](#check-the-security-certificate)

**Alerts**
- **Cameras to watch**: camera names separated by commas, exactly as shown
  by Tools → List my cameras. Leave blank to watch all cameras.
- **Pop up for**: which detections trigger a pop-up. Person, Package and
  Doorbell ring are on by default; Vehicle, Animal and Any motion are off
  (motion can be very frequent).
- **Wait before the same camera pops up again**: stops one camera from
  popping up over and over (default 60 seconds).
- **Quiet hours**: no pop-ups between the start and end hour, for example
  23 to 7 overnight.

**Pop-up**
- **Stay on screen**: how long the pop-up stays up (default 25 seconds).
- **Position** and **Size**: which corner, and small, medium or large.
- **Picture refresh**: how often the picture updates (default once a
  second).
- **High-quality pictures**: sharper, but slower to load.
- **Pause what's playing while it's up**: pauses video during the pop-up
  and resumes it afterwards.

**Tools**
- **Show a test pop-up** and **List my cameras**: see Setup step 4.
- **Log every event**: for troubleshooting (see below).

### Check the security certificate

The connection to UniFi Protect is always encrypted. This setting decides
whether MoodyCam also checks that it's talking to the real console before
sending your API key.

- **Off (default):** right for almost everyone. UniFi consoles come with a
  self-signed certificate that no device trusts, so checking it would always
  fail. The small risk is that a device already on your home network could
  pretend to be the console and read the API key.
- **On:** use this if you reach Protect through a domain name with a proper
  certificate (for example from Let's Encrypt), either on the console itself
  or on a reverse proxy in front of it. Enter the domain name, not an IP
  address, as the Protect address.

With a reverse proxy, Kodi connects to the proxy rather than the console.
The firewall must allow Kodi to reach the **proxy** on TCP 443, the proxy
needs WebSocket support turned on, and the domain name must resolve to the
proxy's address on the Kodi device's network.

If you turn it on and get a certificate or SSL error, turn it back off and
use the console's IP address.

### Set the address and key over SSH

On **CoreELEC** or **LibreELEC** you can paste the key from a computer
instead of typing it with the remote. (Android Kodi usually has no SSH, so
use the settings screen there.)

1. Turn on SSH on the Kodi box (CoreELEC/LibreELEC settings → Services →
   SSH), then connect from your computer: `ssh root@<kodi-box-ip>`.
2. Paste this whole block and press Enter:

   ```sh
   (
     F=/storage/.kodi/userdata/addon_data/service.moodycam/settings.xml
     printf 'UniFi Protect address (e.g. 192.168.1.10): '; read -r HOST
     printf 'API key (hidden as you type): '; stty -echo; read -r KEY; stty echo; echo
     if [ -z "$HOST" ] || [ -z "$KEY" ]; then echo "Both are needed. Nothing changed."; exit 1; fi
     esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
     systemctl stop kodi
     mkdir -p "${F%/*}"
     OLD=""
     if [ -f "$F" ]; then
       cp "$F" "$F.bak"
       OLD=$(grep '<setting id=' "$F" | grep -v -e 'id="host"' -e 'id="api_key"')
     fi
     {
       echo '<settings version="2">'
       [ -n "$OLD" ] && echo "$OLD"
       printf '    <setting id="host">%s</setting>\n' "$(esc "$HOST")"
       printf '    <setting id="api_key">%s</setting>\n' "$(esc "$KEY")"
       echo '</settings>'
     } > "$F"
     systemctl start kodi
     echo "Saved. Kodi is restarting with the new settings."
   )
   ```

3. Type the Protect address, press Enter, paste the API key, press Enter.

Kodi restarts and MoodyCam connects. Your other MoodyCam settings are kept,
and the previous file is saved as `settings.xml.bak`. The key isn't saved in
your shell history.

## Troubleshooting

- **"Could not reach UniFi Protect"** or a timeout: the Kodi device can't
  reach the console. Check the address and the firewall rule (Setup step 2).
- **"UniFi rejected the API key"**: the key is wrong or was deleted. Make a
  new one and enter it again.
- **Certificate or SSL error**: turn off "Check the security certificate",
  or see [that section](#check-the-security-certificate).
- **A camera never pops up**: check its name under Alerts → Cameras to
  watch (or leave that blank), that the detection type is turned on, and
  that it isn't quiet hours.
- **"Could not connect to repository"** right after adding the source:
  restart Kodi and try again.

For more detail, look in `kodi.log` for lines starting with
`[service.moodycam]`. Turning on Tools → **Log every event** also logs
every message UniFi sends.

## License

MIT. See [LICENSE](LICENSE).
