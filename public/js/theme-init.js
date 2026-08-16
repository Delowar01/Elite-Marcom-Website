/* Runs synchronously before first paint to prevent a flash of the wrong theme.

   Three things decide what a visitor sees, in this order:

     1. their own choice, if they have ever used the toggle (localStorage);
     2. the site default an admin picked, baked onto <html> at publish time;
     3. the device's own preference, falling back to dark.

   The visitor's choice comes first on purpose: an admin sets what a *new*
   visitor sees, never what a returning one has already asked for. A page with
   no data-default-theme — the shipped files before a publish, and the admin
   panel — takes step 3, which is exactly how the site has always behaved. */
(function () {
  var root = document.documentElement;
  var theme = "";
  try {
    var saved = localStorage.getItem("em-theme");
    if (saved === "light" || saved === "dark") theme = saved;
  } catch (e) { /* private mode: fall through to the site default */ }
  if (!theme) {
    var preferred = root.getAttribute("data-default-theme");
    if (preferred === "light" || preferred === "dark") theme = preferred;
  }
  if (!theme) {
    theme = "dark";
    try {
      if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
        theme = "light";
      }
    } catch (e) { /* keep dark */ }
  }
  root.setAttribute("data-theme", theme);
})();
