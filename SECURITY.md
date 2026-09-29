# Keeping your shop safe

This guide covers every part of the setup: your accounts, your keys, the server, the shop itself, using an AI on the server, and what to do if something goes wrong. Read the short version first. Everything below it explains the why and the extra steps.

## The short version

- [ ] Turn on two-factor login (an authenticator app or passkey, not text messages) for your **email**, **Stripe**, **GoDaddy**, **Resend**, **DigitalOcean** and **GitHub**.
- [ ] Use a password manager and a different password for every account.
- [ ] Run `sudo ./harden.sh` on a fresh server before `./install.sh`.
- [ ] Never put API keys in `.env`, in a chat, in a screenshot or in a message. The kit asks for them when it needs them and forgets them straight after.
- [ ] After setup, delete the GoDaddy token (or give it a short expiry) and the full-access Resend key. The shop keeps working without them.
- [ ] Back up the `data` folder.
- [ ] If anything looks wrong, follow "If something goes wrong" at the bottom, in order.

---

## Why anyone would bother with a small shop

Attackers mostly aren't after your ebook money. They're after what your accounts can do:

- **Your domain.** With your DNS they can send your buyers to their own checkout, or send emails "from you" to your customers.
- **Your email sending.** Your domain has a good reputation, so phishing sent through it lands in inboxes.
- **Your Stripe account.** They can use it to test stolen cards, or add their own webhook to see your sales and customer emails.
- **Your server.** It gets used to attack others, or they copy your data and ask for money to give it back ("pay or we publish it").

Bots scan the whole internet for open servers all day. A new server usually gets its first login attempts within minutes. Assume you'll be found, and make sure there's nothing easy to take.

## 1. Your accounts come first

Your email account is the master key, because every other account can be reset through it. Protect it the most.

| Account | What to turn on |
| --- | --- |
| **Email** (the one on all your accounts) | Two-factor with an app or passkey. Check the recovery phone and email are yours. Look at "recent devices" and log out anything you don't recognise. |
| **Stripe** | Two-factor. If anyone else helps you, give them their own login with the smallest role, never your password. |
| **GoDaddy** | Two-factor. Keep **Domain Lock** on (it stops the domain being moved to another company). Keep a card on file only if you want the kit to buy domains. |
| **Resend** | Two-factor. |
| **DigitalOcean** | Two-factor. This account can see and control your whole server. |
| **GitHub** | Two-factor, if you fork or change the kit. |
| **Cloudflare** | Two-factor, if you use it for DNS. |

Use a password manager (1Password, Bitwarden or the one built into your browser) and never reuse a password. Most break-ins start with a password leaked from some other website.

## 2. Your keys

A key is a password for a program. Anyone holding one can do whatever that key is allowed to do, without your password or two-factor. So the rule is: **give each key the least power it needs, and keep it for the least time.**

### What the kit keeps on the server

| Stored in `data/` | What it can do if stolen | How bad |
| --- | --- | --- |
| Stripe webhook secret | Only check that a message came from Stripe. It can't read, charge, refund or move anything. | Low. Could be used to fake a purchase message to your own server and get a free download. |
| Resend send-only key | Send email from `orders@yourdomain.com` only. It can't read your emails, see other domains or change settings. | Medium. Could send fake emails from your domain until you delete it. |

The `data` folder can only be opened by the `shop` user. The shop service itself runs locked down: it can't change system files, can only write to `data`, and can only be reached through nginx.

**The kit keeps no Stripe API key on the server at all.** The Buy button is a Stripe Payment Link made during setup, so the running shop never needs to talk to Stripe.

### The keys you type in during setup

`new_product.py` asks for these every time you run it. They're hidden while you paste them, used, then forgotten. They are never written to disk.

| Key | What it can do | How to make it safer |
| --- | --- | --- |
| **Stripe secret key** | Almost everything in your Stripe account: products, refunds, customer details, webhooks. | Make a **restricted key** instead at [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys) with only these set to **Write**: Products, Prices, Payment Links, Webhook Endpoints. Everything else set to None. The kit accepts it the same way. |
| **Resend full-access key** | Everything in Resend, including adding domains and making keys. | Delete it at [resend.com/api-keys](https://resend.com/api-keys) after setup, and make a new one next time you add a product. The send-only key the kit made keeps working. |
| **GoDaddy token** | Change DNS on every domain you own, and **buy domains with your card**. | Give it the shortest expiry GoDaddy offers, or delete it after setup. It's only needed while `new_product.py` runs. |
| **Cloudflare token** | Change DNS. | Limit it to the one zone (domain) you're using, and give it an expiry. |

Never:

- put these keys in `.env` (the kit refuses to run if you do)
- paste them into a chat with a person or an AI
- save them in a note on your desktop
- commit them to GitHub

If you think a key was seen by anyone, delete it where you made it and make a new one. It takes a minute.

## 3. The server

`sudo ./harden.sh` does the basics for you on a fresh server:

- **Security updates** installed now, and automatically every day from then on.
- **Firewall** that only lets in SSH (logins), HTTP and HTTPS. Every other port is closed.
- **fail2ban**, which bans an IP address for an hour after 5 failed logins.
- **SSH locked to keys only.** Nobody can log in with a password over the internet, and nobody can log in as `root` at all.

After that, you log in either through your provider's web console (DigitalOcean: open the Droplet, click **Console**, log in as `shop`) or with an SSH key.

### Setting up an SSH key (optional, recommended if you use a terminal)

On your own computer (Terminal on Mac, PowerShell on Windows):

```
ssh-keygen -t ed25519
```

Press Enter for the default location, and set a passphrase. Then show the public half:

```
cat ~/.ssh/id_ed25519.pub
```

On the server, as `shop`, paste that one line into this file:

```
mkdir -p ~/.ssh && chmod 700 ~/.ssh && nano ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
```

Now `ssh shop@YOUR_SERVER_IP` works from your computer without a password. **Add keys from two devices** (for example your laptop and a second computer) so losing one doesn't lock you out, and test that both work before logging out.

If you ever lock yourself out, DigitalOcean's **Recovery Console** (Droplet page, Access) always works, because it isn't SSH.

### Going further (optional)

- **Tailscale.** Install [Tailscale](https://tailscale.com) on the server and your devices, then close port 22 to the internet (`sudo ufw delete allow OpenSSH` and `sudo ufw allow in on tailscale0`). Your server's login door then only exists on your private network. Test Tailscale SSH works before closing the port.
- **Only allow Cloudflare in front.** If you put your domain behind Cloudflare's proxy, you can set the firewall to accept web traffic only from [Cloudflare's IP ranges](https://www.cloudflare.com/ips/), so nobody can reach the server directly. Change the kit's DNS records to proxied first, and keep port 80 open to Cloudflare for certificate renewals.
- **Separate server per project.** Don't run other experiments on the shop's server. If a test app gets broken into, it takes everything else on that machine with it.

### Logs

- nginx records every request in `/var/log/nginx/access.log`. Ubuntu keeps 14 days and deletes older ones by itself.
- The shop's own log: `sudo journalctl -u digital-product-kit -n 100`
- fail2ban's bans: `sudo fail2ban-client status sshd`
- Who logged in: `last -n 20`

### Backups

Everything that matters is in `~/digital-product-kit/data`: your orders, buyer emails and the files you sell. Copy it off the server regularly:

```
scp -r shop@YOUR_SERVER_IP:~/digital-product-kit/data ./shop-backup-$(date +%F)
```

Or turn on DigitalOcean's automatic backups for the Droplet (a small monthly fee). Keep backups somewhere private, because they contain customer emails.

## 4. The shop itself

What the kit already does:

- **Payments can't be faked.** Every "payment done" message from Stripe is checked against the webhook secret. Anything else is rejected.
- **A file is only sent once the money has actually arrived**, including slow bank payments.
- **Download links are long random codes** that can't be guessed, and they stop working after a year.
- **Your files aren't on the public website.** Only the download links can fetch them.
- **Requests are rate limited** to 10 a second per visitor, so nobody can hammer the downloads or the webhook.
- **The pages send security headers:** HTTPS only, no embedding in other sites, and scripts only from your own domain.
- **No Stripe key on the server**, and email keys that can only send from one domain.

Things to know:

- **A buyer can share their download link.** It works for anyone who has it until it expires. For expensive products, shorten the expiry by changing `expiry_days` in `data/kit.db`, or ask the kit's issues page for a per-product setting.
- **Card testing.** Criminals sometimes use public checkout pages to test stolen cards with small purchases. Stripe Radar (on by default) blocks most of it. If you see lots of failed payments in Stripe, turn on stricter Radar rules or raise your price floor.
- **Chargebacks.** Keep a clear refund policy on your page. A refund costs you less than a $15 chargeback fee. The download count on each order is proof the buyer got the file.

## 5. Using Claude or another AI on your server

An AI assistant that can run commands on your server is very helpful, and it deserves the same care as giving someone your keyboard.

- **Run it as the `shop` user, never as root.** It can then only touch the shop, not the whole server.
- **It can read everything `shop` can**, including `.env` and `data/kit.db` (your buyers' emails). That's why the kit keeps no powerful keys there.
- **Read commands before approving them**, especially anything with `sudo`, `curl ... | bash`, `rm`, `ufw`, `ssh` or changes to `/etc`. Don't turn on "approve everything automatically" for sudo.
- **Type setup keys into the terminal prompt yourself.** Don't paste them into the AI chat, where they get stored in its history.
- **Don't let it disable the firewall, fail2ban or the SSH settings** to "fix" a problem. If a fix needs that, it's the wrong fix.
- **If it installs something new**, ask it what it is and why, and whether that opens a port.

## 6. Your buyers' data

The kit stores each buyer's email address and what they bought. That's personal data, so:

- Say on your page that you use the email to deliver the purchase.
- If someone asks you to delete their data, you can:

  ```
  sqlite3 ~/digital-product-kit/data/kit.db "DELETE FROM orders WHERE email = 'them@example.com'"
  ```

  Delete them in Stripe too (Customers).
- Don't copy the order list into other tools unless you need to, and never email it around.

## 7. If something goes wrong

Signs to look out for:

- emails from Stripe, GoDaddy or Resend about changes you didn't make
- a domain that suddenly shows a different page
- a webhook you don't recognise in Stripe
- emails in Resend's log you didn't send
- a message asking for money

Work through this **in order**:

1. **Your email account first.** Change its password, check two-factor is on, and log out all other sessions.
2. **Delete every key.** Stripe (API keys and restricted keys), Resend (all API keys), GoDaddy (tokens), Cloudflare (tokens). Make new ones later.
3. **Check your domain.** At GoDaddy, make sure the DNS records point to your server's IP and nothing was added. Make sure Domain Lock is still on.
4. **Check Stripe.** Look at Developers, then Webhooks, and delete any endpoint you didn't make. Check your payout bank account is still yours, and check Team for unknown users.
5. **Check Resend** for emails you didn't send.
6. **Rebuild the server instead of cleaning it.** Make a new Droplet, run `harden.sh` and `install.sh`, restore `data` from your backup, run `new_product.py` again with your new keys, then destroy the old Droplet. You can't trust a server that someone else got into.
7. **If buyer data was taken**, tell your buyers what happened. Depending on where you and they live, you may also have to tell your data protection authority (in the UK and EU, within 72 hours).
8. **Never pay a ransom.** There's no guarantee you get anything back, and it marks you as someone who pays. Your backup is the fix.

---

Found a security problem in the kit itself? Please don't post it publicly. Open a GitHub issue that just says "security report" and we'll reach out, or DM the maintainer on X.
