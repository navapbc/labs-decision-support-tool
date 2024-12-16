const addScriptToHeader = (src) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true; // Optional: Load the script asynchronously

    document.head.appendChild(script);
}

addScriptToHeader("https://cdnjs.cloudflare.com/ajax/libs/uswds/3.8.1/js/uswds.min.js")

MutationObserver = window.MutationObserver || window.WebKitMutationObserver;

let observer = new MutationObserver(function (mutations, observer) {
    let accordionItems = document.getElementsByClassName("accordion_item")
    for (let i = 0; i < accordionItems.length; i++) {
        accordionItems[i].addEventListener("click", function () {
            const data_id = this.dataset.id
            const accordionButton = document.querySelector(`[aria-controls="${data_id}"]`)
            accordionButton.setAttribute("aria-expanded", "true");
            const accordionBody = document.getElementById(data_id)
            accordionBody.removeAttribute("hidden");
        });
    }
});

observer.observe(document.body, {
    subtree: true,
    attributes: true
});