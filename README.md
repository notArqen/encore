# encore · apple music discord presence
> a small, event-driven macOS helper that shows what's playing in Apple's Music.app as a real Discord "Listening to" status — the integration Apple never built and Discord never offered.
---
## table of contents
- [overview](#overview)
- [features](#features)
- [getting started](#getting-started)
- [usage](#usage)
- [technical notes](#technical-notes)
- [license](#license)
---
## overview
**encore** is a lightweight background process for macOS that bridges Music.app and Discord's Rich Presence. it launches when Music opens, clears itself when Music quits, and updates the instant a track changes, pauses, or resumes — no polling, no timers spinning in the background eating your battery for no reason.

---
## features
### presence
- shows track title, artist, and album art on your Discord profile as a "Listening to" status
- updates immediately on track change, pause, and resume
- falls back to a static logo when an album isn't in the iTunes catalog (local rips, bootlegs, that one EP your friend put on Bandcamp)
### lifecycle
- starts tracking the moment Music.app launches — including if Music was already open before this helper started
- clears your Discord status and goes idle the moment Music.app quits
- runs quietly in the background at login via a `launchd` LaunchAgent, if you want it to
### efficiency
- entirely event-driven — built on `NSWorkspace` and `NSDistributedNotificationCenter`, the same native macOS mechanisms apps use to watch each other without polling
- a 45-second AppleScript resync exists only as a correctness safety net for a documented quirk where Music's notifications occasionally drop a beat — it is not how the app actually stays in sync
- near-zero idle footprint: no loop, no constant CPU wake-ups, nothing running when Music isn't
### setup
- one Python script (`setup.py`) walks you through everything — Discord Client ID, dependency install, and login auto-start — no manual file editing required
---
## getting started
encore is a handful of plain Python files plus one setup script. there's no build step and no packaging — you run it with the Python that's already on your Mac.

### prerequisites
- macOS (this relies on `AppKit`/`Foundation` and AppleScript — there is no other-OS version, because there is no other-OS Music.app)
- Python 3.10+
- the Discord desktop app, not the web client (Rich Presence talks to it over a local socket)
- a free Discord Application — [discord.com/developers/applications](https://discord.com/developers/applications) — `setup.py` walks you through this part too

### installing
```bash
# clone the repo
git clone https://github.com/YOUR_USERNAME/encore
cd encore

# run the guided setup
python3 setup.py
```
`setup.py` will:
1. walk you through creating a Discord Application and grabbing its Client ID
2. write your Client ID and a couple of cosmetic settings into `config.py`
3. install `pypresence` and `pyobjc-framework-Cocoa` for you
4. generate a `launchd` LaunchAgent with the correct paths for your machine, and offer to install + load it on the spot

no JSON to hand-edit, no `$PATH` archaeology. answer a few prompts and it's running.

### running it manually
if you'd rather skip the LaunchAgent for now and just try it:
```bash
python3 main.py
```
open Music, play something, check Discord. `Ctrl-C` to stop.
---
## usage
### normal operation
once set up, you don't interact with encore directly. open Music, your status appears. change tracks, it updates. quit Music, it clears. that's the entire interface.
### checking it's running
```bash
launchctl list | grep com.user.applemusicdiscordrpc
```
### logs
```bash
cat /tmp/applemusicdiscordrpc.out.log
cat /tmp/applemusicdiscordrpc.err.log
```
### uninstalling the LaunchAgent
```bash
launchctl unload ~/Library/LaunchAgents/com.user.applemusicdiscordrpc.plist
rm ~/Library/LaunchAgents/com.user.applemusicdiscordrpc.plist
```
---
## technical notes
- **lifecycle detection** — `NSWorkspace` notifications (`NSWorkspaceDidLaunchApplicationNotification` / `...DidTerminateApplicationNotification`) catch Music.app opening and closing. an initial check on startup covers the case where encore launches after Music already is.
- **now-playing detection** — `NSDistributedNotificationCenter` listens for `com.apple.Music.playerInfo`, which Music broadcasts on every track change, play, and pause. this is undocumented by Apple, so the full payload is logged once on first receipt so you can verify the key names on your macOS version.
- **resync safety net** — that notification has had reliability issues on some macOS versions. a 45-second AppleScript query corrects any drift if a notification was missed. it is *not* the primary mechanism, by design — see the comments in `main.py` if you're tempted to "simplify" this into a polling loop. don't.
- **artwork** — looked up via the free iTunes Search API (artist + album, no auth) and cached on disk so repeated tracks don't re-trigger a network call. falls back to a static asset you upload once in the Discord Developer Portal.
- **Rich Presence transport** — `pypresence` over Discord's local IPC socket. no bot token, no OAuth, nothing that touches your Discord account credentials.
- **permissions** — the AppleScript fallback only ever talks to Music.app (a normal Automation permission, prompted once). nothing in this project touches Accessibility.
---
## license
[Apache 2.0](LICENSE) — open, permissive, and honest about it.
---
<p align="center">built with care.</p>
