# Digital Product Kit

Sell an ebook, a template pack or any file on your own website, with your own Stripe account. One command buys the domain, builds the sales page, sets up checkout and emails every buyer their download.

No Gumroad cut, no monthly platform fee, and nothing to do by hand after a sale.

```
./new_product.py --name "The Houseplant Handbook" --price 19 --file handbook.pdf \
    --domain houseplanthandbook.com --seller "Maya Green" --buy
```

**What that one command does**

1. Buys `houseplanthandbook.com` at GoDaddy (it asks you first and tells you the price)
2. Creates the product in your Stripe account
3. Points the domain at your server
4. Sets up order emails from `orders@houseplanthandbook.com`
5. Puts a sales page and a thank-you page on the domain
6. Turns on HTTPS (the padlock in the browser)

When someone buys, they land on a thank-you page with a download button, and they get an email with their private download link.

**What it costs you**

| | |
| --- | --- |
| Server (DigitalOcean) | $6 a month |
| Domain (GoDaddy) | about $10 for the first year |
| Stripe | Stripe's normal fee on each sale, nothing else |
| Order emails (Resend) | Free for 1 domain and up to 100 emails a day |
| This kit | Free |

---

## The easy way: let your AI set it up

Copy this whole box into Claude, ChatGPT or any AI assistant. Fill in the three lines at the bottom first.

```text
I want to sell a digital product (like an ebook) on my own website using
Digital Product Kit: https://github.com/samalgrow/digital-product-kit

Read that repo's README first, then walk me through setting it up. I am not
technical, so please follow these rules:

1. Give me one step at a time. Tell me exactly what to click or type, and wait
   for me to say "done" before the next step.
2. Never ask me to paste a password, API key or token into this chat.
   new_product.py asks for keys in the server terminal and never saves them,
   so I will run that command and type the keys in myself.
3. Before anything that costs money (the server, buying the domain, turning on
   live payments), tell me the price and wait for my OK.
4. Start in Stripe test mode. Only switch to real payments after I have done a
   test purchase that worked, start to finish.
5. If something fails, ask me to paste the error message (never a key), then
   use the README's "If something goes wrong" section.
6. Follow SECURITY.md in the repo. Don't turn off the firewall, fail2ban or
   the SSH settings to fix a problem, and don't run anything as root.

If you can run commands on my server yourself (for example Claude Code), you
can run them for me, but still follow the rules above.

What I'm selling:
Price:
Domain I want (or "help me pick one"):
```

---

## Doing it yourself, step by step

This takes about 30 minutes. You don't need to know how to code. You will copy and paste a few commands.

You'll make 4 accounts along the way: **DigitalOcean** (the server), **GoDaddy** (the domain), **Stripe** (the payments) and **Resend** (the order emails).

### Step 1: Get a server on DigitalOcean

The server is a small computer that stays on all the time and runs your shop.

1. Sign up at [digitalocean.com](https://www.digitalocean.com) and add a card.
2. Click **Create**, then **Droplets**.
3. Pick these options:
   - **Region:** the one closest to most of your buyers
   - **Image:** Ubuntu 24.04 (LTS)
   - **Size:** Basic, Regular, **$6/month** (1 GB memory)
   - **Authentication:** Password. Make it long and write it down somewhere safe.
4. Click **Create Droplet** and wait a minute.
5. Open your new Droplet and click **Console** (top right). A black window opens in your browser. That's your server. Every command below gets pasted into this window.

> Tip: to paste into the console, right-click and choose Paste, or press Ctrl+Shift+V.

### Step 2: Make your user

The shop should never run as `root` (the all-powerful user). Paste this to make a normal user called `shop`:

```
adduser shop
```

It asks you to pick a password for `shop`. Pick a strong one that doesn't contain the word "shop" (Ubuntu rejects those) and write it down. Then press Enter through the other questions (name, room number and so on).

Then give `shop` admin rights and switch to it:

```
usermod -aG sudo shop
su - shop
```

From now on you're working as `shop`.

### Step 3: Lock the server down and install the kit

```
git clone https://github.com/samalgrow/digital-product-kit.git
cd digital-product-kit
sudo ./harden.sh
```

When it asks for a password, type the `shop` password. Nothing shows while you type, which is normal. It asks you to confirm with `y`, then:

- installs security updates, and turns on automatic ones
- turns on a firewall that only allows web traffic and logins
- bans anyone who keeps guessing passwords
- switches off password logins over the internet

From now on you log in with the **Console** button on DigitalOcean. If it asks which user, type `shop` (root logins are switched off). If the Console ever won't let you in, the **Recovery Console** under Access always works. [SECURITY.md](SECURITY.md) explains all of it, and how to add an SSH key if you prefer a terminal.

Then install the kit:

```
./install.sh
```

It asks for the email where customer replies should go. After a minute you'll see `Service running on port 8750`.

### Step 4: Get your keys

Keys are like passwords that let the kit use your accounts. **You don't save them anywhere on the server.** The command in Step 6 asks for them each time, uses them, and forgets them. Keep them in your password manager.

| Key | Where to get it |
| --- | --- |
| **Stripe** | Sign up at [stripe.com](https://stripe.com). Open [dashboard.stripe.com/test/apikeys](https://dashboard.stripe.com/test/apikeys) and copy the **Secret key**. It starts with `sk_test_`. That's test mode: no real money moves. (Safer: a restricted key, see [SECURITY.md](SECURITY.md).) |
| **Resend** | Sign up at [resend.com](https://resend.com). Go to **API Keys**, click **Create API Key**, and pick **Full access**. It starts with `re_`. |
| **GoDaddy** | Sign in at [godaddy.com](https://www.godaddy.com) and make sure a card is saved on your account (that's how the domain gets paid for). Then open [developer.godaddy.com/personal-access-token](https://developer.godaddy.com/personal-access-token) and create a token that can manage domains and DNS and register domains. Give it a short expiry. |

Already have your domain on **Cloudflare** instead? Make a token at [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) with the "Edit zone DNS" template and use that instead of GoDaddy. The kit can't buy domains through Cloudflare, only use ones you already have there.

### Step 5: Put your file on the server

The easiest way is a download link. Upload your PDF to Dropbox, copy its share link, change the `dl=0` at the end to `dl=1`, and run:

```
curl -L -o handbook.pdf "https://www.dropbox.com/...your-link...?dl=1"
```

Do the same for a cover image if you have one (`-o cover.jpg`). Check it worked with `ls -lh`, which should list your file with its size.

<details>
<summary>Or copy it straight from your computer</summary>

On your own computer, open Terminal (Mac) or PowerShell (Windows) and run:

```
scp handbook.pdf shop@YOUR_SERVER_IP:~/digital-product-kit/
```

`YOUR_SERVER_IP` is the number on your Droplet's page, like `164.90.12.34`. This needs an SSH key, because `harden.sh` switched off password logins. [SECURITY.md](SECURITY.md) shows how to add one in 2 minutes.
</details>

### Step 6: Run the command

Change the words in quotes to your own, then paste it:

```
./new_product.py --name "The Houseplant Handbook" --price 19 \
    --file handbook.pdf --cover cover.jpg \
    --domain houseplanthandbook.com --seller "Maya Green" \
    --description "Keep every plant in your home alive, even if you've killed a cactus." \
    --buy
```

| Part | What it means |
| --- | --- |
| `--name` | The product's title |
| `--price` | The price, like `19` or `19.99` |
| `--file` | The file buyers get. Use `--file` again to give them more than one. |
| `--cover` | A cover image for the sales page (optional) |
| `--domain` | The website address. One product per domain. |
| `--seller` | Your name. It shows on the page and in the order email. |
| `--description` | A line or two under the title (optional) |
| `--buy` | Buy the domain if you don't own it yet |
| `--currency` | `usd` unless you add this, e.g. `--currency gbp` |

First it asks for your keys, one at a time. Paste each one (right-click, or Ctrl+Shift+V) and press Enter. Nothing shows on screen while you paste, which is on purpose.

```
  Stripe secret key (sk_...):
  Resend API key, full access (re_...):
  GoDaddy token (or press Enter to use Cloudflare):
```

If the domain isn't yours yet, it shows the price and asks before buying:

```
1. Domain
  houseplanthandbook.com costs $9.79 for the first year, then $14.99/year.
  Buy it with the card on your GoDaddy account? [y/N]
```

Type `y` and press Enter to buy it. This is a real purchase, even while Stripe is in test mode. Anything else stops without buying. If the name is taken, it stops and charges nothing.

Then it works through the rest by itself. It finishes with:

```
Live: https://houseplanthandbook.com  (TEST mode, pay with 4242 4242 4242 4242)
Your keys were not saved on this server.
```

A brand new domain can take a few minutes to start working everywhere. If a step fails because of that, wait 10 minutes and run the exact same command again. It picks up where it left off and never buys anything twice.

### Step 7: Test it

1. Open your domain in your browser and click **Buy now**.
2. Pay with the test card `4242 4242 4242 4242`, any future date, any 3 numbers for the CVC, and **your own email**.
3. Check that you land on the thank-you page, the download works, and the email arrives (look in spam the first time).

No real money moves in test mode.

### Step 8: Start taking real money

1. In Stripe, finish setting up your account (business details and a bank account for payouts).
2. Turn off test mode and copy your live **Secret key** from [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys). It starts with `sk_live_`.
3. Run your Step 6 command again (you can leave off `--buy`) and paste the `sk_live_` key when it asks for the Stripe key.
4. Buy your own product once with a real card, then refund yourself in Stripe.
5. Go through the checklist at the top of [SECURITY.md](SECURITY.md). It takes 10 minutes.

That's it. You're selling.

---

## Everyday things

**Change the price, text, cover or files:** run your Step 6 command again with the new values. It updates what's there and never makes duplicates.

**Add another product:** run the command again with a new `--name` and a new `--domain`. The free Resend plan covers 1 domain, so a second product needs Resend's paid plan.

**Make the page look different:** the sales page is `templates/index.html`, one plain HTML file. Edit it, then run your Step 6 command again.

**See your sales:** in your Stripe dashboard, like any other Stripe payment.

**Update the kit:** `cd ~/digital-product-kit && git pull && ./install.sh`

**Back up your orders:** everything is in the `data` folder. See [SECURITY.md](SECURITY.md) for a one-line backup.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| `... is not in your GoDaddy account` | Add `--buy` to the command, or check you typed the domain right. |
| `... is taken` | Someone owns that domain. Pick another name. |
| `Set SUPPORT_EMAIL in .env first` | Run `nano .env`, put your email after `SUPPORT_EMAIL=`, save with Ctrl+O, Enter, Ctrl+X. |
| `Remove these from .env` | You have keys saved in `.env` from an older version. Delete those lines with `nano .env`. The command asks for keys instead. |
| `That doesn't look like a ...` | The key you pasted is incomplete or the wrong one. Copy it again. |
| `certbot failed` | The new domain hasn't spread yet. Wait 10 to 30 minutes and run the command again. |
| `HTTP 401` or `HTTP 403` | A key is wrong or missing a permission. Make a new one and run the command again. |
| `Resend is still checking the records` | Normal for a new domain. Emails start once it says Verified at [resend.com/domains](https://resend.com/domains), usually within an hour. |
| Paid, but no download shows up | Look at the last lines of the service log: `sudo journalctl -u digital-product-kit -n 30` |
| Can't log in over SSH any more | That's `harden.sh` switching off password logins. Use the **Console** button on DigitalOcean, or add an SSH key ([SECURITY.md](SECURITY.md)). |
| The email never arrives | Check spam, and check [resend.com/emails](https://resend.com/emails) to see if it was sent. |

When you ask anyone for help (a person or an AI), paste the error message but **never** any key.

## Security

Read [SECURITY.md](SECURITY.md). It covers your accounts, every key, the server, using an AI on the server, backups, and exactly what to do if something goes wrong.

The short version of what the kit does:

- **No powerful keys on the server.** Stripe, GoDaddy and full Resend keys are typed in during setup and never saved. The running shop holds no Stripe key at all, only a webhook secret and a Resend key that can only send email from your domain.
- **The server is locked down** by `harden.sh`: firewall, fail2ban, automatic security updates, no root login, no password logins.
- **Payments can't be faked**, and a file is only sent once the money has actually arrived.
- **Download links are random and unguessable**, and your files aren't on the public website.
- **Buyer emails and orders** sit in `data/`, which only `shop` can read.

## How it works

```
buyer  ->  yourdomain.com         the sales page (nginx)
       ->  Buy now                Stripe Payment Link (Stripe's own checkout page)
       ->  paid                   Stripe tells your server, it saves the order
                                  and emails the download link (Resend)
       ->  thank-you page         shows the download button straight away
```

The server only receives Stripe's "paid" message and hands out downloads. It's about 180 lines of Python in `kit/server.py`, plus `new_product.py`, which does the setup. Orders are kept in a small SQLite database in `data/kit.db`.

---

Built by the team at [Algrow](https://algrow.online), tools for YouTube creators. MIT licensed, so use it however you want.
