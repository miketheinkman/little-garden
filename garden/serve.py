"""Serve the family pilot on loopback or the chosen home network interface."""
import ipaddress
import json
import os
import subprocess
import sys


def address_for(interface):
    if interface == "localhost":
        return "127.0.0.1"
    addresses = subprocess.check_output(
        ["ip", "-j", "-4", "address", "show", "dev", interface, "scope", "global"],
        text=True,
    )
    home_networks = [ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    for device in json.loads(addresses):
        for address in device["addr_info"]:
            ip = ipaddress.ip_address(address["local"])
            if any(ip in subnet for subnet in home_networks):
                return str(ip)
    raise SystemExit(f"Waiting for a private IPv4 address on {interface}")


if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    address = address_for(sys.argv[1])
    os.environ["DJANGO_SETTINGS_MODULE"] = "garden.local_settings"
    os.environ["GARDEN_LOCAL_PILOT"] = "1"
    os.environ["GARDEN_HOSTS"] = f"localhost,127.0.0.1,{address}"
    execute_from_command_line(["manage.py", "runserver", f"{address}:8137", "--insecure", "--noreload"])
