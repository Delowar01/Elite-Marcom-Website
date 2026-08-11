/* Runs synchronously before first paint to prevent a flash of the wrong theme. */
(function () {
  var theme = "dark";
  try {
    var saved = localStorage.getItem("em-theme");
    if (saved === "light" || saved === "dark") theme = saved;
    else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) theme = "light";
  } catch (e) { /* keep dark default */ }
  document.documentElement.setAttribute("data-theme", theme);
})();
