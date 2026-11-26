# First alpha host

Use a fresh Linode for the alpha. The home pilot remains a separate installation. Alpha family progress is durable from the first invitation. This guide prepares a private application endpoint for a host-managed HTTPS proxy. Complete the public launch checks in the [deployment punchlist](../ALPHA-PUNCHLIST.md) before enrollment.

## Provision and verify access

1. Recover or create the Linode account, enable MFA, save recovery codes offline and verify the billing address for alerts. Check the actual plan's CPU, memory, disk, region and monthly price before ordering. Aim for two vCPUs and 8 GB total for PostgreSQL and Django together.
2. Use a supported Ubuntu LTS image and register the operator's SSH **public** key. In the Linode firewall, allow SSH from the operator's trusted address and default-deny other inbound traffic, including IPv6. Attach the firewall when creating the VM. Keep web ingress closed during setup. Confirm access to the provider console and verify the SSH host key fingerprint there before accepting it.
3. In the first administrative session create a named Linux operator, give it sudo access, and install the operator's public key. For example, on Ubuntu use `adduser gardenops`, `usermod -aG sudo gardenops`, and install the public key in that account's `.ssh/authorized_keys` with the directory mode 700, file mode 600 and owner gardenops. Keep the original session open.
4. From a **second terminal** sign in using that key and run `sudo -v`. Then save the following as /etc/ssh/sshd_config.d/00-little-garden.conf from the verified session. Run `sudo sshd -t`, inspect the effective values with `sudo sshd -T`, and reload with `sudo systemctl reload ssh`. Open a third connection and verify sudo again before closing the original sessions.

   ```text
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PubkeyAuthentication yes
   ```

5. Enable automatic OS security updates, choose a reboot window, and test recovery after reboot. Install Docker Engine and the Compose plugin using Docker's signed Ubuntu repository. Retain sudo control of the Docker daemon. Check disk space, swap policy, and container log rotation. Verify the Linode firewall and host rules together, including after Docker starts. [Docker on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) · [Docker and host firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

## Prepare the private backend

Run from a clean checkout of the release on the new host. Keep the Compose environment file in an owner-only directory outside the checkout, with mode 600. Start from [env.example](env.example). Generate the signing key and each of the two database passwords independently with a password manager or `openssl rand -hex 48`. Keep recovery copies in the operators' password manager. Use a release-specific tag such as `little-garden-alpha:<git-commit>`. Configure the verified sender and authenticated STARTTLS credentials for the mail provider. Changing database passwords after initialization requires rotating the PostgreSQL roles as well as updating the environment file.

Use the same environment file and volume name for every release. Record the name in the restore runbook. Create the empty external volume **once**, during first provisioning. For recovery or a subsequent deployment, verify the existing volume's identity and backup before starting the app.

```sh
# First provisioning only, using the volume name in env.example.
sudo docker volume create little-garden-alpha-family-data
```

Use a release image built from a clean Git checkout. Set `ALPHA_ENV` to the absolute path of the private environment file. The shell function uses the production Compose file consistently.

```sh
alpha() { sudo docker compose --env-file "$ALPHA_ENV" -f deploy/alpha/compose.yaml "$@"; }
alpha config --quiet
alpha build web
alpha up -d --wait db
alpha run --rm --no-deps web python manage.py check --deploy
alpha run --rm --no-deps web python manage.py migrate --noinput
alpha up -d web
alpha run --rm web python manage.py createsuperuser
```

The release bundles curriculum and static files. Image creation validates the recorded lesson audio. Gunicorn checks for unapplied migrations on startup. The app role owns its tables and has schema creation rights without PostgreSQL superuser, role-creation, or database-creation rights. The database uses an external volume and has no published port. The web listener binds only to host loopback on port 8138 by default. Co-view frames use temporary storage shared by the three workers.

The image explicitly selects the hosted settings for both Gunicorn and management commands. The checkout CLI selects local settings for development and the LAN pilot. Setting GARDEN_DEV=0 selects hosted settings outside the pilot.

The production profile redirects HTTP to HTTPS, accepts the configured hostname, sets secure session and CSRF cookies, and initially enables HSTS for one hour on that hostname. Review Django's subdomain and preload advisories separately when every relevant hostname is ready for long-lived HTTPS. The local reverse proxy must **overwrite** the forwarded scheme with the verified connection scheme, preserve the canonical Host, and accept origin traffic only via the intended Cloudflare path. Test reset links and cross-household caching through the public hostname before opening web ingress to families. [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) · [Cloudflare origin authentication](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/)

## Rehearse on a workstation

From the repository root, run `python3 qa/alpha_smoke.py` with local Docker access. It builds the release, creates a randomly named test database volume, verifies empty initialization, exercises the loopback HTTP endpoint and static audio, recreates the containers, and checks that its test parent persists. It removes its own containers and volume on completion. The rehearsal uses a reserved example hostname and dummy SMTP settings. Public TLS, real email delivery, offsite restore, and VPS reboot require separate checks.
