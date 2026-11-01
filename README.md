# Arcadyan 5G modem reboot for Home Assistant

Automatically reboots an Arcadyan 5G modem when your internet goes down. These
modems are often sold under an internet provider's brand. It's one short `curl`
script and one automation blueprint, so there's nothing to install from HACS and no
cloud service involved.

> **Status:** the script has rebooted a real modem, run from a computer on the same
> network. Arcadyan makes many models, so check yours with the dry run in step 5.
> The Home Assistant steps have only been tested against a simulated modem so far.
> If you try it, please
> [open an issue](https://github.com/petruknw/ha-arcadyan-aus-modem-reboot/issues) and say whether
> it worked.

## Set up

### 1. Add the script

Save [`arcadyan_modem_reboot.sh`](arcadyan_modem_reboot.sh) in your Home Assistant `config`
folder, next to `configuration.yaml`. From a Home Assistant terminal:

```bash
curl -o /config/arcadyan_modem_reboot.sh https://raw.githubusercontent.com/petruknw/ha-arcadyan-aus-modem-reboot/main/arcadyan_modem_reboot.sh
```

### 2. Add your password

Add this to `secrets.yaml`, using the password on the modem's label, or your own
if you changed it:

```yaml
arcadyan_modem_password: "your password"
```

The script reads it from there, so it never appears in a command.

### 3. Add the command

Add this to `configuration.yaml`:

```yaml
shell_command:
  arcadyan_modem_reboot: sh /config/arcadyan_modem_reboot.sh
```

If you keep scripts in a subfolder, use that path here instead. `bash` works in
place of `sh` too.

If your modem isn't at `192.168.1.1`, use
`MODEM_HOST=192.168.0.1 sh /config/arcadyan_modem_reboot.sh` instead.

### 4. Restart Home Assistant

Restart Home Assistant so it loads the new command. The test reboot and the
automation below won't work until you do.

### 5. Check the login

Log out of the modem's web page first, because it allows one admin at a time. Then
run this from a Home Assistant terminal. It logs in and out and doesn't reboot:

```bash
sh /config/arcadyan_modem_reboot.sh --dry-run
```

To test a real reboot, run `shell_command.arcadyan_modem_reboot` from
**Developer tools > Actions**. The internet drops for a minute or two.

### 6. Create the automation

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fpetruknw%2Fha-arcadyan-aus-modem-reboot%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Farcadyan_modem%2Freboot_when_offline.yaml)

Import the blueprint, create an automation from it, and choose:

- **Internet connectivity sensor or group:** anything that's on while the internet
  works, such as a [Ping](https://www.home-assistant.io/integrations/ping/) sensor
  or a group of them.
- **Minutes offline before rebooting:** 5 by default.
- **Minutes to wait before another reboot is allowed:** 30 by default, which stops
  it rebooting in a loop.

If you use a group, leave its **All entities** option off. The group then turns off
only when every target fails, so one unreachable target can't trigger a reboot.

## Block devices on the Wi-Fi

This is optional and separate from the reboot steps above. A Home Assistant
integration gives each device a switch, and turning it on adds that device to the
modem's Wi-Fi block list. The rest of the list stays as it is, and it doesn't reboot
the modem.

> **Status:** adding to and removing from the block list has worked on a real modem,
> but the integration itself has only been tested against a simulated modem so far.

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=petruknw&repository=ha-arcadyan-aus-modem-reboot&category=integration)

1. Add this repository to HACS with the button above, or add
   `https://github.com/petruknw/ha-arcadyan-aus-modem-reboot` as a custom repository
   of type **Integration**.
2. Download **Arcadyan 5G modem** in HACS, then restart Home Assistant.
3. Log out of the modem's web page, go to **Settings > Devices & services > Add
   integration**, search for **Arcadyan 5G modem**, and enter your password.
4. Open the integration, choose **Configure > Add a device**, and enter its name and
   MAC address. Each device gets a **Block** switch.

Before you rely on it:

- **Changes are slow:** the modem can take about a minute to answer, and something
  restarts for every change, so expect a brief interruption.
- **Main Wi-Fi only:** the modem's filter page doesn't cover guest networks.
- **Use the address your network sees:** phones and tablets often use a private
  address for each network, and it can change if the device resets it.
- **It only covers this Wi-Fi:** a device with mobile data stays online.
- **One admin at a time:** Home Assistant logs in every 5 minutes to read the list.
  If that overlaps with the reboot script, the script can fail with "someone else is
  logged in". The integration's own reboot action below waits its turn.
- **Allow lists:** the integration won't change anything while the modem is using an
  allow list, because a wrong one would take other devices off the Wi-Fi.

### Reboot from the integration

The integration also adds a **Reboot modem** action, which any automation can use
instead of the script. It uses the password you gave the integration, so it needs no
script, `shell_command` or `secrets.yaml` entry:

```yaml
actions:
  - action: arcadyan_modem.reboot
```

This action has only been tested against a simulated modem so far. The blueprint
still uses the script.

## Troubleshooting

Failures appear in the Home Assistant log as a failed `shell_command`. To see the
message, run the script from a terminal.

| Message | What to do |
| --- | --- |
| someone else is logged in | Log out of the modem's web page, or wait 10 minutes for it to time out. |
| the modem login is locked | Wait a minute. The modem locks after 5 wrong passwords. |
| the modem rejected the password | Check `arcadyan_modem_password` in `secrets.yaml`. |
| no password found | Check `arcadyan_modem_password` in `/config/secrets.yaml`. |

A refused reboot also prints the modem's reply. The reply to a reboot request
doesn't prove it worked, so if the script says `Reboot sent.` but the modem stays
up, please open an issue and include the `--dry-run` output, after checking it for
private details.

## How it works

1. `GET /` returns the login page, with a token hidden in an inline 1x1 GIF. It
   answers 403 until you log in, which is normal.
2. `POST /cgi-bin/luci/admin/` logs in using the token and hashed credentials,
   where each hash is `sha512(md5hex(value))` and the username is fixed.
3. `GET /system_r.htm` provides the 32-character session token, in the first inline
   GIF on the page.
4. `POST /apply_abstract.cgi` sends that token with `submit_button=index.htm` and
   `action=reboot`.

The script makes one login attempt each time it runs, so it won't lock the modem by
retrying. The modem only offers plain HTTP, so run this on a network you trust.

## Disclaimer

This is an unofficial project and isn't affiliated with or endorsed by Arcadyan or
any internet provider. Use it at your own risk. It is released under the
[MIT licence](LICENSE).
