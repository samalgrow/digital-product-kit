// Embedded checkout: every link to /buy opens Stripe's pay box on this page instead of
// sending the buyer to another site. Without JavaScript, /buy still works: the server
// sends the buyer to Stripe's own checkout page.
(function () {
  var KEY = "{{PUBLISHABLE_KEY}}";
  var stripeReady = null;
  var overlay = null;
  var checkout = null;

  function loadStripe() {
    if (!stripeReady) {
      stripeReady = new Promise(function (resolve, reject) {
        var s = document.createElement("script");
        s.src = "https://js.stripe.com/endive/stripe.js";
        s.onload = function () { resolve(Stripe(KEY)); };
        s.onerror = function () { stripeReady = null; reject(); };
        document.head.appendChild(s);
      });
    }
    return stripeReady;
  }

  function addStyles() {
    var css = document.createElement("style");
    css.textContent =
      ".dpk-overlay{position:fixed;inset:0;z-index:2147483000;background:rgba(0,0,0,.55);" +
      "overflow-y:auto;padding:24px 12px}" +
      ".dpk-box{position:relative;max-width:560px;margin:0 auto;background:#fff;" +
      "border-radius:12px;padding:44px 8px 8px;min-height:240px}" +
      ".dpk-close{position:absolute;top:8px;right:10px;border:0;background:none;" +
      "font-size:30px;line-height:1;cursor:pointer;color:#333;padding:4px 10px}" +
      ".dpk-wait{text-align:center;color:#666;font:16px system-ui,sans-serif;padding:60px 0}";
    document.head.appendChild(css);
  }

  function close() {
    if (checkout) { checkout.destroy(); checkout = null; }
    if (overlay) { overlay.remove(); overlay = null; }
    document.documentElement.style.overflow = "";
  }

  function open(fallbackUrl) {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "dpk-overlay";
    overlay.innerHTML = '<div class="dpk-box" role="dialog" aria-modal="true" aria-label="Checkout">' +
      '<button type="button" class="dpk-close" aria-label="Close">&times;</button>' +
      '<div id="dpk-checkout"><p class="dpk-wait">Loading secure checkout…</p></div></div>';
    document.body.appendChild(overlay);
    document.documentElement.style.overflow = "hidden";
    overlay.querySelector(".dpk-close").onclick = close;
    overlay.onclick = function (e) { if (e.target === overlay) close(); };

    loadStripe().then(function (stripe) {
      return stripe.createEmbeddedCheckoutPage({
        fetchClientSecret: function () {
          return fetch("/checkout-session", { method: "POST" })
            .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
            .then(function (d) { return d.clientSecret; });
        }
      });
    }).then(function (c) {
      if (!overlay) { c.destroy(); return; }
      checkout = c;
      document.getElementById("dpk-checkout").innerHTML = "";
      c.mount("#dpk-checkout");
    }).catch(function () {
      // Stripe.js blocked or the session failed: Stripe's own page still works.
      location.href = fallbackUrl;
    });
  }

  addStyles();
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href="/buy"]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    open(a.href);
  });
})();
