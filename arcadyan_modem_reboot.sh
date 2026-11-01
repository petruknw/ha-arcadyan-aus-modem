#!/bin/sh
# Reboots an Arcadyan 5G modem.
# https://github.com/petruknw/ha-arcadyan-aus-modem-reboot
#
# Usage: sh arcadyan_modem_reboot.sh [--dry-run]
#   --dry-run logs in, shows how the Reboot page sends its request, and logs out.
#
# The password comes from ARCADYAN_MODEM_PASSWORD, then arcadyan_modem_password in a
# secrets.yaml next to this script or in /config, then a prompt.
# Set MODEM_HOST if the modem isn't at 192.168.1.1.

set -eu

base="http://${MODEM_HOST:-192.168.1.1}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() {
    echo "arcadyan_modem_reboot: $1" >&2
    exit 1
}

request() {
    curl -sS -m 20 -b "$work/cookies" -c "$work/cookies" -b popup=1 -e "$base/" "$@"
}

# The token follows a fixed 78-character 1x1 GIF. Use the first GIF on the page,
# like the page's own code: admin pages have a second one with a different value.
page_token() {
    grep -o 'src="data:image/gif;base64,[^"]*' "$1" | head -n 1 | cut -c 84- |
        base64 -d
}

# sha512(md5hex(value)), the page's do_encode(value, true).
credential() {
    printf %s "$1" | md5sum | cut -d ' ' -f 1 | tr -d '\n' |
        sha512sum | cut -d ' ' -f 1
}

read_password() {
    password=${ARCADYAN_MODEM_PASSWORD:-}
    for secrets in "$(dirname "$0")/secrets.yaml" /config/secrets.yaml; do
        if [ -z "$password" ] && [ -f "$secrets" ]; then
            password=$(sed -n "s/^arcadyan_modem_password:[[:space:]]*//p" "$secrets" |
                tr -d '\r' | sed "s/[[:space:]]*$//; s/^\"\(.*\)\"$/\1/; s/^'\(.*\)'$/\1/")
        fi
    done
    if [ -z "$password" ] && [ -t 0 ]; then
        printf 'Modem password: ' >&2
        stty -echo
        IFS= read -r password || true
        stty echo
        echo >&2
    fi
    [ -n "$password" ] || fail "no password found"
}

login() {
    # Pages that need a login answer 403 with the login page, so 403 is normal.
    request -o "$work/page" "$base/"
    token=$(page_token "$work/page")
    [ -n "$token" ] || fail "no login token in the modem's page"

    url=$(printf 'token=%s&nextp=index.htm&luci_password=%s&luci_username=%s' \
        "$token" "$(credential "$password")" "$(credential optus)" |
        request -L -o "$work/login" -w '%{url_effective}' --data @- \
            "$base/cgi-bin/luci/admin/")

    status=$(request -o "$work/reboot_page" -w '%{http_code}' "$base/system_r.htm")
    [ "$status" = 200 ] && return

    flag=$(printf %s "$url" | sed -n 's/.*[?&]err=\([0-9]*\).*/\1/p')
    [ -n "$flag" ] || flag=$(sed -n 's/.*var flag *= *\([0-9]*\).*/\1/p' "$work/login" | head -n 1)
    case "$flag" in
        1) fail "the modem rejected the password" ;;
        2) fail "someone else is logged in to the modem" ;;
        7) fail "the modem login is locked, try again in a minute" ;;
        *) fail "login failed (status $status)" ;;
    esac
}

logout() {
    request -o /dev/null "$base/logout.htm" || true
}

case "${1:-}" in
    "" | --dry-run) ;;
    *) fail "usage: sh $0 [--dry-run]" ;;
esac

read_password
login

if [ "${1:-}" = "--dry-run" ]; then
    echo "Login OK. Nothing was rebooted."
    echo "Token length: $(page_token "$work/reboot_page" | wc -c | tr -d ' ')"
    awk '/function doConfirm/ { lines = 17 } lines > 0 { print; lines-- }' \
        "$work/reboot_page" | cut -c 1-300
    logout
    exit 0
fi

# The modem may drop the connection as it goes down.
status=$(printf 'token=%s&submit_button=index.htm&action=reboot' \
    "$(page_token "$work/reboot_page")" |
    request -o "$work/reply" -w '%{http_code}' --data @- "$base/apply_abstract.cgi") ||
    status=dropped

case "$status" in
    200 | dropped) echo "Reboot sent." ;;
    *)
        head -c 400 "$work/reply" >&2
        echo >&2
        logout
        fail "the modem refused the reboot (status $status)"
        ;;
esac
