/** @odoo-module ignore **/
/* Property Portal maps (Leaflet + OpenStreetMap, no API key needed).
 *  .o_rp_map[data-markers]   -> price pins with popup cards
 *  .o_rp_map_picker          -> click to set latitude / longitude inputs
 */
(function () {
    "use strict";

    var DEFAULT_CENTER = [30.0444, 31.2357]; // Cairo

    function addTiles(map) {
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(map);
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = text;
        }
        return node;
    }

    function popupContent(marker) {
        var card = el("a", "o_rp_popup");
        card.href = marker.url;
        if (marker.img) {
            var img = el("img");
            img.src = marker.img;
            img.alt = "";
            card.appendChild(img);
        }
        var body = el("div", "o_rp_popup_body");
        body.appendChild(el("div", "o_rp_popup_price", marker.price));
        body.appendChild(el("div", "o_rp_popup_title", marker.title));
        body.appendChild(el("div", "o_rp_popup_loc", marker.location));
        var specs = el("div", "o_rp_popup_specs");
        [["fa-bed", marker.beds], ["fa-bath", marker.baths],
         ["fa-arrows-alt", marker.area && marker.area !== "0" ? marker.area + " m²" : ""]].forEach(function (spec) {
            if (!spec[1]) {
                return;
            }
            var item = el("span");
            item.appendChild(el("i", "fa " + spec[0]));
            item.appendChild(document.createTextNode(" " + spec[1]));
            specs.appendChild(item);
        });
        body.appendChild(specs);
        card.appendChild(body);
        return card;
    }

    function priceIcon(marker) {
        var span = el("span", null, marker.price);
        return L.divIcon({
            className: "o_rp_pin" + (marker.premium ? " o_rp_pin_premium" : ""),
            html: span.outerHTML,
            iconSize: null,
        });
    }

    function initMarkersMap(node) {
        var markers = [];
        try {
            markers = JSON.parse(node.dataset.markers || "[]");
        } catch (e) {
            markers = [];
        }
        var map = L.map(node, { scrollWheelZoom: false });
        addTiles(map);
        var bounds = [];
        markers.forEach(function (marker) {
            L.marker([marker.lat, marker.lng], { icon: priceIcon(marker) })
                .addTo(map)
                .bindPopup(popupContent(marker), { maxWidth: 260, minWidth: 220 });
            bounds.push([marker.lat, marker.lng]);
        });
        if (bounds.length === 1) {
            map.setView(bounds[0], parseInt(node.dataset.zoom || "15", 10));
        } else if (bounds.length) {
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
        } else {
            map.setView(DEFAULT_CENTER, 10);
        }
        map.on("click", function () {
            map.scrollWheelZoom.enable();
        });
    }

    function initPicker(node) {
        var latInput = document.querySelector(node.dataset.latInput);
        var lngInput = document.querySelector(node.dataset.lngInput);
        var locationSelect = document.querySelector(node.dataset.locationSelect);
        var map = L.map(node, { scrollWheelZoom: false });
        addTiles(map);
        var pin = null;

        function setPin(lat, lng, pan) {
            if (pin) {
                pin.setLatLng([lat, lng]);
            } else {
                pin = L.marker([lat, lng], {
                    draggable: true,
                    icon: L.divIcon({ className: "o_rp_pin o_rp_pin_dot", html: "<span></span>", iconSize: null }),
                }).addTo(map);
                pin.on("dragend", function () {
                    var p = pin.getLatLng();
                    write(p.lat, p.lng);
                });
            }
            if (pan) {
                map.setView([lat, lng], Math.max(map.getZoom() || 0, 15));
            }
        }
        function write(lat, lng) {
            latInput.value = lat.toFixed(7);
            lngInput.value = lng.toFixed(7);
        }
        function locationCenter() {
            var option = locationSelect && locationSelect.selectedOptions[0];
            var lat = option && parseFloat(option.dataset.lat);
            var lng = option && parseFloat(option.dataset.lng);
            return lat && lng ? [lat, lng] : null;
        }

        var lat = parseFloat(latInput.value);
        var lng = parseFloat(lngInput.value);
        if (lat && lng) {
            setPin(lat, lng, false);
            map.setView([lat, lng], 15);
        } else {
            map.setView(locationCenter() || DEFAULT_CENTER, locationCenter() ? 13 : 10);
        }
        map.on("click", function (ev) {
            setPin(ev.latlng.lat, ev.latlng.lng, false);
            write(ev.latlng.lat, ev.latlng.lng);
        });
        if (locationSelect) {
            locationSelect.addEventListener("change", function () {
                var center = locationCenter();
                if (center && !pin) {
                    map.setView(center, 13);
                }
            });
        }
        [latInput, lngInput].forEach(function (input) {
            input.addEventListener("change", function () {
                var a = parseFloat(latInput.value);
                var b = parseFloat(lngInput.value);
                if (a && b) {
                    setPin(a, b, true);
                }
            });
        });
    }

    function init() {
        if (!window.L) {
            return;
        }
        document.querySelectorAll(".o_rp_map:not(.o_rp_map_ready)").forEach(function (node) {
            node.classList.add("o_rp_map_ready");
            if (node.classList.contains("o_rp_map_picker")) {
                initPicker(node);
            } else {
                initMarkersMap(node);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
