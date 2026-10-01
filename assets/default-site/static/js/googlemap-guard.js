/* Loads the djangocms-googlemap script only after the Google Maps API has loaded, and shows the
 * fallback notice when it cannot (offline, blocked, invalid key). Without this the plugin script
 * runs on window load and throws "google is not defined". */
(function () {
  'use strict';
  var me = document.currentScript;
  var pluginJs = me && me.getAttribute('data-plugin-js');

  function showFallback() {
    var maps = document.querySelectorAll('.js-djangocms-googlemap');
    for (var i = 0; i < maps.length; i++) {
      var note = maps[i].querySelector('.site-map-notice');
      var box = maps[i].querySelector('.js-djangocms-googlemap-container');
      if (note) { note.hidden = false; }
      if (box) { box.hidden = true; }
    }
  }

  var failed = false;
  window.site_gmap_failed = function () { failed = true; showFallback(); };
  // Called by Google when the key is invalid or the API rejects it.
  window.gm_authFailure = window.site_gmap_failed;

  window.site_gmap_ready = function () {
    if (failed || !window.google || !window.google.maps) { return window.site_gmap_failed(); }
    if (window.djangocms_googlemap && window.djangocms_googlemap.__loaded) {
      return window.djangocms_googlemap.InitMap();
    }
    if (!pluginJs) { return; }
    var s = document.createElement('script');
    s.src = pluginJs;
    s.onload = function () {
      window.djangocms_googlemap = window.djangocms_googlemap || {};
      window.djangocms_googlemap.__loaded = true;
      if (window.djangocms_googlemap.InitMap) { window.djangocms_googlemap.InitMap(); }
    };
    document.head.appendChild(s);
  };
})();
