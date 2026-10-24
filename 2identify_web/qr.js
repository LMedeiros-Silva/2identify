// Projector page: the QR encodes PUBLIC_PANEL_URL, or the address this page was opened on.
async function publicUrl() {
  try {
    const response = await fetch("/api/public/config", { cache: "no-store" });
    if (response.ok) return (await response.json()).public_url || location.origin;
  } catch {
    // Fall back to the page's own address.
  }
  return location.origin;
}

const url = await publicUrl();
document.getElementById("qr-image").src = `/api/public/qr.svg?url=${encodeURIComponent(url)}`;
document.getElementById("qr-url").textContent = url.replace(/^https?:\/\//, "");
// A QR for localhost would open nothing on the audience's phones.
const host = new URL(url).hostname;
document.getElementById("qr-local").hidden = !/^(localhost|127\.|\[::1\]$|0\.0\.0\.0$)/.test(host);
