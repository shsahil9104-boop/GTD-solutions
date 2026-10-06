"""Google Maps script for GTD (standalone: not wired into the booking form).

Shows two search boxes (pickup and drop, with Google place suggestions), a map with the driving route,
and the distance and travel time. Use the distance (km) in GTD's "Approx. distance" field.

Setup (Google Cloud console):
  1. Create an API key and enable "Maps JavaScript API", "Places API (New)" and "Routes API".
  2. Restrict the key to your website addresses (HTTP referrers), e.g. http://localhost:8501/* and your live domain.
  3. Put the key in the environment variable GOOGLE_MAPS_API_KEY, or in .streamlit/secrets.toml as:
         GOOGLE_MAPS_API_KEY = "your-key"

Use it in any Streamlit page:
    import gmaps
    gmaps.trip_map()                      # default: India, 480 px high
    gmaps.trip_map(height=600, region="in")
"""
import json
import os
from html import escape

import streamlit as st
import streamlit.components.v1 as components

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#17201e}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px}
@media(max-width:600px){.row{grid-template-columns:1fr}}
label{display:block;font-size:13px;font-weight:600;margin-bottom:4px}
gmp-place-autocomplete{width:100%}
#info{margin:0 0 10px;padding:12px 16px;border-radius:12px;background:#0f3b36;color:#fff;font-size:15px}
#info b{color:#f2b01e;font-size:18px}
#map{height:__MAP_HEIGHT__px;border-radius:16px;border:1px solid #e5e1d6}
</style></head><body>
<div class="row">
  <div><label>Pickup location</label><div id="from"></div></div>
  <div><label>Drop location</label><div id="to"></div></div>
</div>
<div id="info">Search a pickup and a drop location to see the route.</div>
<div id="map"></div>
<script>
let map, points = {from: null, to: null}, markers = {}, lines = [];
const info = document.getElementById("info");

async function initMap() {
  const {Map} = await google.maps.importLibrary("maps");
  const {PlaceAutocompleteElement} = await google.maps.importLibrary("places");
  const {AdvancedMarkerElement} = await google.maps.importLibrary("marker");
  const {Route} = await google.maps.importLibrary("routes");

  map = new Map(document.getElementById("map"), {
    center: {lat: 23.0225, lng: 72.5714}, zoom: 11, mapId: "DEMO_MAP_ID", mapTypeControl: false, streetViewControl: false
  });

  async function drawRoute() {
    if (!points.from || !points.to) return;
    try {
      const {routes} = await Route.computeRoutes({
        origin: points.from, destination: points.to, travelMode: "DRIVING",
        fields: ["path", "distanceMeters", "durationMillis", "viewport"]
      });
      lines.forEach(l => l.setMap(null));
      const r = routes[0];
      lines = r.createPolylines();
      lines.forEach(l => l.setMap(map));
      if (r.viewport) map.fitBounds(r.viewport);
      const km = (r.distanceMeters / 1000).toFixed(1), mins = Math.round(r.durationMillis / 60000);
      info.innerHTML = "Distance: <b>" + km + " km</b> &nbsp;|&nbsp; Drive time: <b>" +
        (mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + " min" : mins + " min") + "</b>";
      window.parent.postMessage({type: "gtd-route", km: Number(km), minutes: mins}, "*");
    } catch (e) {
      info.textContent = "Could not get a route. Check that the Routes API is enabled for your key.";
      console.error(e);
    }
  }

  async function picked(key, place) {
    await place.fetchFields({fields: ["displayName", "formattedAddress", "location"]});
    points[key] = place.location;
    if (markers[key]) markers[key].map = null;
    markers[key] = new AdvancedMarkerElement({map, position: place.location, title: place.displayName});
    if (!(points.from && points.to)) map.setCenter(place.location);
    drawRoute();
  }

  ["from", "to"].forEach(key => {
    const box = new PlaceAutocompleteElement({includedRegionCodes: ["__REGION__"]});
    document.getElementById(key).appendChild(box);
    // newer and older versions of the Maps library use different event names; listen for both
    box.addEventListener("gmp-select", e => picked(key, e.placePrediction.toPlace()));
    box.addEventListener("gmp-placeselect", e => picked(key, e.place));
  });
}
window.initMap = initMap;
</script>
<script async src="https://maps.googleapis.com/maps/api/js?key=__API_KEY__&v=weekly&loading=async&callback=initMap"></script>
</body></html>"""


def _api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        try:
            key = st.secrets.get("GOOGLE_MAPS_API_KEY")
            if not key:
                for k in st.secrets:  # key pasted under a [section]
                    sub = st.secrets[k]
                    if hasattr(sub, "get") and sub.get("GOOGLE_MAPS_API_KEY"):
                        key = sub["GOOGLE_MAPS_API_KEY"]
                        break
        except Exception:
            key = None
    return str(key).strip() if key else None


def trip_map(height=480, region="in"):
    """Render the pickup/drop map. region = 2-letter country code to favour in suggestions."""
    key = _api_key()
    if not key:
        st.warning("Add GOOGLE_MAPS_API_KEY (environment variable or .streamlit/secrets.toml) to show the map.")
        return
    html = (HTML.replace("__MAP_HEIGHT__", str(int(height)))
            .replace("__REGION__", escape(region.lower()))
            .replace("__API_KEY__", escape(key)))
    components.html(html, height=int(height) + 140)


BOOKING_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#17201e}
#info{margin:0 0 10px;padding:12px 16px;border-radius:12px;background:#0f3b36;color:#fff;font-size:15px}
#info b{color:#f2b01e;font-size:18px}
#map{height:__MAP_HEIGHT__px;border-radius:16px;border:1px solid #e5e1d6}
#bar{display:flex;gap:10px;align-items:center;margin-top:8px;font-size:13px;color:#555}
button{border:0;border-radius:10px;padding:8px 14px;background:#f2b01e;color:#17201e;font-weight:600;cursor:pointer}
</style></head><body>
<div id="info">Loading route...</div>
<div id="map"></div>
<div id="bar"><button id="center" type="button">Show my location</button><span id="me">Finding your live location...</span></div>
<script>
const ORIGIN = __ORIGIN__, DEST = __DEST__;
const info = document.getElementById("info"), meInfo = document.getElementById("me");
let map, meMarker = null, lastPos = null, AdvancedMarkerElement;

function showMe(pos) {
  lastPos = {lat: pos.coords.latitude, lng: pos.coords.longitude};
  if (!meMarker) {
    const dot = document.createElement("div");
    dot.style.cssText = "width:16px;height:16px;border-radius:50%;background:#1a73e8;border:3px solid #fff;box-shadow:0 0 0 2px #1a73e8";
    meMarker = new AdvancedMarkerElement({map, position: lastPos, content: dot, title: "You are here"});
  } else {
    meMarker.position = lastPos;
  }
  meInfo.textContent = "Your live location is the blue dot.";
}

async function initMap() {
  const {Map} = await google.maps.importLibrary("maps");
  const marker = await google.maps.importLibrary("marker");
  AdvancedMarkerElement = marker.AdvancedMarkerElement;
  const {Route} = await google.maps.importLibrary("routes");
  map = new Map(document.getElementById("map"), {
    center: {lat: 23.0225, lng: 72.5714}, zoom: 11, mapId: "DEMO_MAP_ID", mapTypeControl: false, streetViewControl: false
  });

  if (navigator.geolocation) {
    navigator.geolocation.watchPosition(showMe,
      () => { meInfo.textContent = "Allow location access in your browser to see yourself on the map."; },
      {enableHighAccuracy: true, maximumAge: 5000});
  } else {
    meInfo.textContent = "Your browser can't share its location.";
  }
  document.getElementById("center").addEventListener("click", () => {
    if (lastPos) { map.panTo(lastPos); map.setZoom(15); }
  });

  try {
    const {routes} = await Route.computeRoutes({
      origin: ORIGIN, destination: DEST, travelMode: "DRIVING",
      fields: ["path", "distanceMeters", "durationMillis", "viewport"]
    });
    const r = routes[0];
    r.createPolylines().forEach(l => l.setMap(map));
    if (r.viewport) map.fitBounds(r.viewport);
    const a = r.path[0], b = r.path[r.path.length - 1];
    [[a, "A", "Pickup"], [b, "B", "Drop"]].forEach(([p, label, title]) => {
      const pin = new marker.PinElement({glyph: label, background: "#0f3b36", glyphColor: "#ffffff", borderColor: "#0f3b36"});
      new AdvancedMarkerElement({map, position: {lat: p.lat, lng: p.lng}, content: pin.element, title: title});
    });
    const km = (r.distanceMeters / 1000).toFixed(1), mins = Math.round(r.durationMillis / 60000);
    info.innerHTML = "Distance: <b>" + km + " km</b> &nbsp;|&nbsp; Drive time: <b>" +
      (mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + " min" : mins + " min") + "</b>";
  } catch (e) {
    info.textContent = "Could not draw the route. Check that the Routes API is enabled for your key.";
    console.error(e);
  }
}
window.initMap = initMap;
</script>
<script async src="https://maps.googleapis.com/maps/api/js?key=__API_KEY__&v=weekly&loading=async&callback=initMap"></script>
</body></html>"""


OSM_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#17201e}
#info{margin:0 0 10px;padding:12px 16px;border-radius:12px;background:#0f3b36;color:#fff;font-size:15px}
#info b{color:#f2b01e;font-size:18px}
#map{height:__MAP_HEIGHT__px;border-radius:16px;border:1px solid #e5e1d6}
#bar{display:flex;gap:10px;align-items:center;margin-top:8px;font-size:13px;color:#555}
button{border:0;border-radius:10px;padding:8px 14px;background:#f2b01e;color:#17201e;font-weight:600;cursor:pointer}
.pin{width:26px;height:26px;border-radius:50%;background:#0f3b36;color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)}
.me{width:16px;height:16px;border-radius:50%;background:#1a73e8;border:3px solid #fff;box-shadow:0 0 0 2px #1a73e8}
</style></head><body>
<div id="info">Loading route...</div>
<div id="map"></div>
<div id="bar"><button id="center" type="button">Show my location</button><span id="me">Finding your live location...</span></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const ORIGIN = __ORIGIN__, DEST = __DEST__;
const info = document.getElementById("info"), meInfo = document.getElementById("me");
const map = L.map("map").setView([23.0225, 72.5714], 11);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"}).addTo(map);
let meMarker = null, lastPos = null;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// try the full address first, then drop the most specific part until something is found
async function geocode(q) {
  const parts = q.split(",").map(s => s.trim()).filter(Boolean);
  for (let i = 0; i <= parts.length - 2; i++) {
    const text = parts.slice(i).join(", ");
    const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&q=" + encodeURIComponent(text));
    const j = await r.json();
    if (j.length) return [parseFloat(j[0].lat), parseFloat(j[0].lon)];
    await sleep(1100);
  }
  throw new Error("Address not found: " + q);
}
function pin(label) { return L.divIcon({className: "", html: '<div class="pin">' + label + '</div>', iconSize: [26, 26], iconAnchor: [13, 13]}); }

if (navigator.geolocation) {
  navigator.geolocation.watchPosition(pos => {
    lastPos = [pos.coords.latitude, pos.coords.longitude];
    if (!meMarker) meMarker = L.marker(lastPos, {icon: L.divIcon({className: "", html: '<div class="me"></div>', iconSize: [16, 16], iconAnchor: [8, 8]}), title: "You are here"}).addTo(map);
    else meMarker.setLatLng(lastPos);
    meInfo.textContent = "Your live location is the blue dot.";
  }, () => { meInfo.textContent = "Allow location access in your browser to see yourself on the map."; },
  {enableHighAccuracy: true, maximumAge: 5000});
} else {
  meInfo.textContent = "Your browser can't share its location.";
}
document.getElementById("center").addEventListener("click", () => { if (lastPos) map.setView(lastPos, 15); });

(async () => {
  try {
    const a = await geocode(ORIGIN);
    await sleep(1100);
    const b = await geocode(DEST);
    L.marker(a, {icon: pin("A"), title: "Pickup"}).addTo(map);
    L.marker(b, {icon: pin("B"), title: "Drop"}).addTo(map);
    map.fitBounds([a, b], {padding: [40, 40]});
    const url = "https://router.project-osrm.org/route/v1/driving/" + a[1] + "," + a[0] + ";" + b[1] + "," + b[0] + "?overview=full&geometries=geojson";
    const res = await (await fetch(url)).json();
    if (!res.routes || !res.routes.length) throw new Error("no route");
    const r = res.routes[0];
    const line = L.geoJSON(r.geometry, {style: {color: "#0f3b36", weight: 5, opacity: 0.85}}).addTo(map);
    map.fitBounds(line.getBounds(), {padding: [40, 40]});
    const km = (r.distance / 1000).toFixed(1), mins = Math.round(r.duration / 60);
    info.innerHTML = "Distance: <b>" + km + " km</b> &nbsp;|&nbsp; Drive time: <b>" +
      (mins >= 60 ? Math.floor(mins / 60) + " h " + (mins % 60) + " min" : mins + " min") + "</b>";
  } catch (e) {
    info.textContent = "Could not draw the route: " + e.message;
    console.error(e);
  }
})();
</script></body></html>"""


def _js(value):
    return json.dumps(value).replace("</", "<\\/")


def booking_map(origin, destination, height=420):
    """Map for one booking: the driving route from `origin` to `destination` (address texts) and the viewer's live location."""
    key = _api_key()
    # With a Google Maps key use Google; without one fall back to the free OpenStreetMap map.
    template = BOOKING_HTML if key else OSM_HTML
    html = (template.replace("__MAP_HEIGHT__", str(int(height)))
            .replace("__ORIGIN__", _js(origin)).replace("__DEST__", _js(destination))
            .replace("__API_KEY__", escape(key or "")))
    components.html(html, height=int(height) + 110)
