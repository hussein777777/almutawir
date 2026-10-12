/** @odoo-module ignore **/
/* Small progressive enhancements for the property marketplace pages. */
(function () {
    "use strict";

    function init() {
        // Sort dropdown submits its form
        document.querySelectorAll(".o_rp_autosubmit").forEach(function (select) {
            select.addEventListener("change", function () {
                select.form.submit();
            });
        });

        // Listing gallery: open the photo viewer on the clicked photo
        document.querySelectorAll(".o_rp_gallery_item[data-slide]").forEach(function (link) {
            link.addEventListener("click", function (ev) {
                ev.preventDefault();
                var index = parseInt(link.dataset.slide, 10) || 0;
                var items = document.querySelectorAll("#o_rp_gallery_carousel .carousel-item");
                items.forEach(function (item, i) {
                    item.classList.toggle("active", i === index);
                });
            });
        });

        // Portal form: show sale / rent specific fields
        var purposeRadios = document.querySelectorAll(".o_rp_purpose_radio");
        function togglePurpose() {
            var checked = document.querySelector(".o_rp_purpose_radio:checked");
            var isRent = checked && checked.value === "rent";
            document.querySelectorAll(".o_rp_sale_only").forEach(function (node) {
                node.classList.toggle("d-none", isRent);
            });
            document.querySelectorAll(".o_rp_rent_only").forEach(function (node) {
                node.classList.toggle("d-none", !isRent);
            });
        }
        if (purposeRadios.length) {
            purposeRadios.forEach(function (radio) {
                radio.addEventListener("change", togglePurpose);
            });
            togglePurpose();
        }

        // Portal form: preview selected photos before upload
        document.querySelectorAll(".o_rp_photo_input").forEach(function (input) {
            var preview = input.parentElement.querySelector(".o_rp_photo_preview");
            input.addEventListener("change", function () {
                if (!preview) {
                    return;
                }
                preview.textContent = "";
                Array.prototype.forEach.call(input.files, function (file) {
                    if (!file.type.startsWith("image/")) {
                        return;
                    }
                    var img = document.createElement("img");
                    img.src = URL.createObjectURL(file);
                    img.alt = file.name;
                    img.onload = function () {
                        URL.revokeObjectURL(img.src);
                    };
                    preview.appendChild(img);
                });
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
