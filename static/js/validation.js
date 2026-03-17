document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("applicationForm");
    if (form) {
        form.addEventListener("submit", function (event) {
            const requiredFields = form.querySelectorAll("[required]");
            let valid = true;
            requiredFields.forEach(field => {
                const value = field.type === "checkbox" ? field.checked : field.value.trim();
                if (!value) {
                    field.classList.add("is-invalid");
                    valid = false;
                } else {
                    field.classList.remove("is-invalid");
                }
            });
            if (!valid) {
                event.preventDefault();
                alert("Please complete all required fields before submitting.");
            }
        });
    }
});
