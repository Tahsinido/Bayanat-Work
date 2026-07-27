# Opening local folders from Bayanat (Windows)

Field Data locations and sites can store a link to data kept outside Bayanat,
for example:

```
D:\Projects\VR\Karabal Event.16.17.04.2025
\\nas01\evidence\sinjar
```

Clicking **Open** on such a path does nothing on its own, because **browsers
refuse to follow `file://` links from a page served over `http://`**. This is a
deliberate security rule in Chrome, Edge and Firefox and cannot be switched off
from the web page side.

This folder contains a small helper that gives the browser a legitimate way to
ask Windows to open the folder for you.

## Install

Double-click:

```
Install Bayanat folder opener.cmd
```

or run:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

No administrator rights are needed - it writes only to
`HKCU:\Software\Classes`, which affects your account alone.

Then **restart your browser**. The first time you press **Open**, the browser
asks whether to allow the external application; allow it (and tick "always" if
offered).

## Remove

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
```

## How it works

The **Open** button turns the stored path into a `bayanat-open:` link. Windows
matches that scheme to `open-path.ps1`, which decodes the path and asks
Explorer to show it.

## What it will and will not do

The handler can be triggered by any web page, not only Bayanat, so it is
deliberately narrow:

- a **folder** is opened in Explorer
- a **file** is *revealed* using `explorer /select,` - Explorer highlights it in
  its folder rather than running it, which matters for `.exe`, `.bat` and `.lnk`
- a path that does not exist is refused with a message
- anything that is not a drive path (`D:\...`) or UNC path (`\\server\...`) is
  refused

It never executes the target, never passes the path through a shell, and never
uses `Invoke-Expression`. The worst a hostile page can do is make an Explorer
window appear, or confirm whether a given path exists on your machine. If that
residual risk is unacceptable in your environment, do not install it and use
the **Copy** button instead.

## If you would rather not install anything

Every link also has a **Copy** button. Press it and paste into the File Explorer
address bar. Pressing **Open** on a local path copies it as well, so if the
helper is missing you still have the path on your clipboard.

## Other machines

This is per-machine and per-user. Anyone else using Bayanat who wants
click-to-open needs to run the installer on their own computer, and the path
has to exist there too - `D:\Projects\...` means *their* `D:` drive. For data
shared across a team, a UNC path (`\\server\share\...`) or an `https://` link
to a web file browser travels better; `https://` links open directly with no
helper at all.
