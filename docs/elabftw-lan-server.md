# Run eLabFTW on your local network

This guide sets up an eLabFTW server on a Linux machine in your lab so that everyone on the lab network (or VPN) can use it, both in the browser and through the Claude Code assistant ([claude-code-setup.md](claude-code-setup.md)).

It follows the official installation guide (https://doc.elabftw.net/docs/install/) and adds the choices that matter on a local network. Expect 1–2 hours, mostly spent getting a hostname and certificate.

> **Not the same as `dev/docker-compose.yml`.** That file in this repository starts a throwaway test instance whose data disappears when it stops. Don't use it for real lab data.

## Overview

1. Get a machine, a fixed address and a hostname
2. Get a TLS certificate for that hostname
3. Install Docker and `elabctl`
4. Generate and edit the configuration
5. Start eLabFTW and create the database
6. Create the first (Sysadmin) account and the teams
7. Check access from another computer
8. Hand out the settings to colleagues
9. Set up backups and updates

## Step 1: Machine, address and hostname

**The machine.** You need a 64-bit Linux server or VM that stays on.

| Lab size | RAM | CPU |
|---|---|---|
| Minimum | 2 GB | 2 cores |
| Small lab (recommended) | 4 GB | 4 cores |

Add disk space for uploaded files. Photos and instrument data add up quickly.

**A fixed IP address.** Ask your network admin for a static IP or a DHCP reservation, for example `192.168.1.50`. If the address changes, everyone's connection breaks.

**A hostname.** Ask IT for a DNS name pointing to that IP, for example `elab.lab.example.org`. eLabFTW's installer refuses to continue without a domain name, and certificates are issued for names, so a hostname is required here, not optional.

If your organization has no internal DNS, you can add a line to the `hosts` file on every client (`/etc/hosts`, or `C:\Windows\System32\drivers\etc\hosts` on Windows):

```
192.168.1.50  elab.lab.example.org
```

This only works for a handful of machines.

**This hostname decides two settings:**

- `SITE_URL` on the server (step 4)
- `ELABFTW_URL` for every colleague's assistant: `https://elab.lab.example.org`

If you serve eLabFTW on a port other than 443, both must include the port, e.g. `https://elab.lab.example.org:3148`.

## Step 2: TLS certificate

eLabFTW only runs over HTTPS, and the assistant checks the certificate by default. Pick the first option that's available to you:

| Option | When | What colleagues set `ELABFTW_VERIFY_SSL` to |
|---|---|---|
| **A. Certificate from IT** | Your organization issues certificates (most universities do) | Nothing if it's from a public CA. Otherwise the path to the organization's CA file, which IT can give you |
| **B. Let's Encrypt with DNS challenge** | The hostname lives in a public DNS zone you can edit, even though the server itself is internal | Nothing |
| **C. Your own small CA** (e.g. [mkcert](https://github.com/FiloSottile/mkcert)) | None of the above; small group | Path to your CA file (`rootCA.pem`), which you hand out |
| D. Self-signed by the container (`GENERATE_TLS_CERT=true`) | Quick tests only | `false`. This turns off certificate checks and exposes API keys on the network, so don't use it for real data |

For A, B and C you end up with two files:

- **certificate**: PEM file containing, in this order, the server certificate, the intermediate certificate(s), and the root (often called `fullchain.pem`)
- **private key**: e.g. `privkey.pem`

The certificate must be issued for the exact hostname from step 1. Otherwise both browsers and the assistant reject it.

**Option C with mkcert**, run on a trusted admin machine:

```sh
mkcert -install                       # creates your CA (once)
mkcert elab.lab.example.org           # creates elab.lab.example.org.pem and -key.pem
mkcert -CAROOT                        # prints the folder containing rootCA.pem
```

Distribute `rootCA.pem` (never `rootCA-key.pem`) to colleagues. They import it into their browser/OS and use its path as `ELABFTW_VERIFY_SSL`.

**Option B** depends on your DNS provider. See the certbot DNS plugins: https://eff-certbot.readthedocs.io/en/stable/using.html#dns-plugins. Let's Encrypt certificates expire after 90 days, so set up renewal as described in https://doc.elabftw.net/docs/install/installation/tls.

## Step 3: Install Docker and elabctl

1. Install **Docker Engine with the Compose plugin** following https://docs.docker.com/engine/install/. On Ubuntu, don't use the snap package or the old `docker-compose` package. Check that it worked:

   ```sh
   docker compose version
   ```

2. Install `elabctl`, the official helper script:

   ```sh
   curl -sL --fail --show-error https://get.elabftw.net -o elabctl && chmod +x elabctl
   sudo mv elabctl /usr/local/bin/
   ```

## Step 4: Generate and edit the configuration

1. Run the wizard:

   ```sh
   sudo elabctl install
   ```

   Answer:

   - *Installing on a server?* → **yes**
   - *Does a domain name point to this server?* → **yes**
   - *Domain name* → `elab.lab.example.org` (hostname only, no `https://`)
   - *Should the eLabFTW container handle HTTPS?* → **yes**

   This creates `/etc/elabftw.yml`, with a random `SECRET_KEY` and database passwords already filled in, and data folders under `/var/elabftw`.

2. Put the certificate files in place:

   ```sh
   sudo mkdir -p /etc/elabftw-certs
   sudo cp fullchain.pem /etc/elabftw-certs/cert.pem
   sudo cp privkey.pem   /etc/elabftw-certs/key.pem
   sudo chown root:101 /etc/elabftw-certs/*.pem   # 101 = the container's web user
   sudo chmod 644 /etc/elabftw-certs/cert.pem
   sudo chmod 640 /etc/elabftw-certs/key.pem
   ```

3. Create the cache folder the configuration expects:

   ```sh
   sudo mkdir -p /var/cache/elabftw
   sudo chown 101:101 /var/cache/elabftw
   ```

4. Edit `/etc/elabftw.yml` (`sudo nano /etc/elabftw.yml`). The file is heavily commented. Change these lines in the `web` service:

   ```yaml
   environment:
       - SITE_URL=https://elab.lab.example.org     # set by the wizard; check it
       - DISABLE_HTTPS=false
       # comment out the two Let's Encrypt lines:
       #- TLS_CERT_PATH=/etc/letsencrypt/live/<YOUR-DOMAIN>/fullchain.pem
       #- TLS_KEY_PATH=/etc/letsencrypt/live/<YOUR-DOMAIN>/privkey.pem
       # and use the "normal certs" lines instead:
       - TLS_CERT_PATH=/etc/elabftw/certs/cert.pem
       - TLS_KEY_PATH=/etc/elabftw/certs/key.pem

   ports:
       - '443:8080'          # host port 443; if you change it, add the port to SITE_URL too

   volumes:
       # comment out the two /etc/letsencrypt/... lines, and add:
       - /etc/elabftw-certs:/etc/elabftw/certs:ro
   ```

   (With option B's Let's Encrypt certificates, keep the Let's Encrypt lines instead, replace `<YOUR-DOMAIN>`, and skip step 4.2.)

   Leave `SECRET_KEY` and the passwords as generated. `DB_PASSWORD` and `MYSQL_PASSWORD` must stay identical.

## Step 5: Start eLabFTW and create the database

```sh
sudo elabctl start
sudo elabctl initialize      # first time only: creates the database structure
sudo elabctl status
```

If the web container keeps restarting, check `sudo docker logs elabftw`. A wrong certificate path or file permissions are the usual cause.

## Step 6: First account and teams

1. Browse to `https://elab.lab.example.org/register.php`. **The first account created becomes Sysadmin**, so do this right away.
2. In the **Sysadmin panel**: create your team(s) and review the registration settings, such as whether new accounts need admin validation.
3. Ask colleagues to register (or create their accounts) and add them to the right team.

## Step 7: Check access from another computer

From a colleague's computer on the lab network:

1. Open `https://elab.lab.example.org`. You should see a padlock with no certificate warning (for options A and B, or for option C once the CA is imported).
2. Test the API with a key (created as in step 4 of [claude-code-setup.md](claude-code-setup.md)):

   ```sh
   curl -H "Authorization: YOUR_API_KEY" https://elab.lab.example.org/api/v2/users/me
   # option C: add --cacert rootCA.pem
   ```

   You should get JSON containing your name.

If the page doesn't load at all:

- **Firewall**: allow TCP 443 on the server, e.g. `sudo ufw allow 443/tcp`. Note that ports published by Docker can bypass `ufw`, so don't assume `ufw` alone limits access (see https://docs.docker.com/engine/network/packet-filtering-firewalls/).
- **Network**: the client must be on the lab network or VPN.

Never forward port 443 from your internet router to this server. It's meant to be reachable only internally.

## Step 8: Hand out the settings

Give each colleague:

| Setting | Value |
|---|---|
| `ELABFTW_URL` | `https://elab.lab.example.org` (the same value as `SITE_URL`) |
| `ELABFTW_VERIFY_SSL` | Nothing for options A (public CA) and B; the CA file for option A (internal CA) and C |
| CA file | `rootCA.pem` / the organization CA, if applicable |
| `ELABFTW_API_KEY` | **Not from you.** Each person creates their own in eLabFTW, so changes are recorded under their own name |

and a link to [claude-code-setup.md](claude-code-setup.md).

## Step 9: Backups and updates

All data lives in `/var/elabftw` (database and uploads), plus your configuration in `/etc/elabftw.yml` and the certificates.

- **Backups**: install `borgbackup` and configure `elabctl backup` following https://doc.elabftw.net/docs/install/backups. Run it daily (cron or a systemd timer) and test a restore once.
- **Updates**: read the release notes, then:

  ```sh
  sudo elabctl update
  ```

- **Certificates**: note the expiry date and renew before it, otherwise everyone gets locked out.

## Quick reference

| Thing | Where |
|---|---|
| Configuration | `/etc/elabftw.yml` |
| Data (database + uploads) | `/var/elabftw` |
| Certificates | `/etc/elabftw-certs` |
| Start / stop / status | `sudo elabctl start` / `stop` / `status` |
| Logs | `sudo docker logs elabftw` |
| Official docs | https://doc.elabftw.net |
