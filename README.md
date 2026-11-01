# Arcadyan 5G modem for Home Assistant

Reboot an Arcadyan 5G modem and block devices from its Wi-Fi, with no cloud service.

> **Status:** rebooting and blocking have worked on a real modem, but this integration
> has only been tested against a simulated one, and other models may not work.

## Install

You need [HACS](https://hacs.xyz) and Home Assistant 2026.2 or newer.

1. Add this repository to HACS:

   [![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=petruknw&repository=ha-arcadyan-aus-modem&category=integration)

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

[![Open your Home Assistant instance and import this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fpetruknw%2Fha-arcadyan-aus-modem%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Farcadyan_modem%2Freboot_when_offline.yaml)

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

- Changes can take minutes, and part of the modem restarts each time, which can
  interrupt other devices.
- It only covers the main Wi-Fi, so guest networks and mobile data aren't blocked.
- The switches won't change anything if the modem is set to an allow list.

## Troubleshooting

The modem allows one admin at a time, and Home Assistant logs in every 5 minutes. If
switches go unavailable or an action says someone else is logged in, log out of the
modem's web page or wait 10 minutes. If the modem refuses the login, Home Assistant
stops checking and asks for the password again.

## Disclaimer

This is an unofficial project and isn't affiliated with Arcadyan or any internet
provider. The modem only offers plain HTTP, so use it on a network you trust. Use it
at your own risk under the [MIT licence](LICENSE).
