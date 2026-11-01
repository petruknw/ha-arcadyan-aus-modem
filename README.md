# Arcadyan 5G modem for Home Assistant

Reboot an Arcadyan 5G modem and block devices from its Wi-Fi, from Home Assistant.
These modems are often sold under an internet provider's brand. Everything stays on
your network, with no cloud service.

- **Reboot modem action:** use it in any automation, for example when your internet
  drops or on a schedule.
- **Block switches:** add a device by its MAC address, and its switch blocks it from
  the main Wi-Fi.

> **Status:** reboots and block list changes have both worked on a real modem, but
> not yet through this integration, which has only been tested against a simulated
> modem. Arcadyan makes many models, so yours may not work. If you try it, please
> [open an issue](https://github.com/petruknw/ha-arcadyan-aus-modem-reboot/issues)
> and say how it went.

## Install

You need [HACS](https://hacs.xyz) and Home Assistant 2026.2 or newer.

1. Add this repository to HACS:

   [![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=petruknw&repository=ha-arcadyan-aus-modem-reboot&category=integration)

2. Download **Arcadyan 5G modem** in HACS, then restart Home Assistant.
3. Log out of the modem's web page, because it allows one admin at a time.
4. Go to **Settings > Devices & services > Add integration** and search for
   **Arcadyan 5G modem**.
5. Enter the modem's address and password. The password is on the modem's label,
   unless you changed it.

## Reboot the modem

To test it, run **Reboot modem** from **Developer tools > Actions**. The internet
drops for a minute or two.

To reboot automatically when the internet drops, import the blueprint and create an
automation from it:

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fpetruknw%2Fha-arcadyan-aus-modem-reboot%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Farcadyan_modem%2Freboot_when_offline.yaml)

Then choose:

- **Internet connectivity sensor or group:** anything that's on while the internet
  works, such as a [Ping](https://www.home-assistant.io/integrations/ping/) sensor or
  a group of them. If you use a group, leave its **All entities** option off, so one
  unreachable target can't trigger a reboot.
- **Minutes offline before rebooting:** 5 by default.
- **Minutes to wait before another reboot is allowed:** 30 by default, which stops it
  rebooting in a loop.

For anything else, such as a schedule, call the `arcadyan_modem.reboot` action from
your own automation.

## Block a device

1. Open the integration and choose **Configure > Add a device**.
2. Enter a name and the MAC address your network sees. Phones and tablets often use
   a private address for each network, and it can change if the device resets it.
3. Turn on the device's **Block** switch.

Other entries on the modem's block list stay as they are. Removing a device from the
integration also takes it off the block list.

Blocking has some limits:

- **It's slow:** the modem can take minutes to apply a change, and part of it restarts
  each time, which can interrupt other devices. The switch only changes once the
  modem shows the change.
- **It only covers the main Wi-Fi:** guest networks aren't filtered, and a device with
  mobile data stays online.
- **It only uses a block list:** if the modem is set to an allow list, the switches
  refuse to change anything, because a wrong one could take other devices offline.

If your modem has no compatible filter page, the switches show as unavailable and
rebooting still works.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Another user is logged in to the modem | Log out of the modem's web page, or wait 10 minutes for it to time out. |
| The modem login is locked | Wait a minute. The modem locks after 5 wrong passwords. |
| Home Assistant asks for the password again | The modem refused the login, so checks stop until you enter the current password. |
| The modem didn't confirm the change | The change may still be applying. Wait a few minutes, then check the switch. |
| Switches are unavailable | Home Assistant couldn't check the modem, or your modem has no compatible filter page. |

Home Assistant logs in to the modem every 5 minutes to read the block list. While
you're on the modem's web page, switches keep their last state for about 15 minutes.

## Security

The modem's web page only offers plain HTTP, so use this on a network you trust. The
integration stores the password in Home Assistant.

## Disclaimer

This is an unofficial project and isn't affiliated with or endorsed by Arcadyan or
any internet provider. Use it at your own risk. It's released under the
[MIT licence](LICENSE).
