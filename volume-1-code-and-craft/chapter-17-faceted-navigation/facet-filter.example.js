/**
 * facet-filter.example.js
 *
 * Reference implementation of Strategy 3 from Chapter 17 of
 * SEO for Engineers, Volume 1: the "JavaScript-rendered filters /
 * History API middle ground" pattern.
 *
 * The point of this pattern is a deliberate asymmetry. Filter
 * controls are <button> elements carrying data-facet / data-value
 * attributes, NOT <a href> links. Googlebot follows <a href> links
 * and reads XHR responses it observes during rendering, but it does
 * not click buttons or type into inputs, so it never discovers the
 * filtered URL as a crawlable link. Meanwhile real users still get a
 * shareable, bookmarkable URL (via history.pushState) and a working
 * back button (via the popstate handler). The filtered URL space is
 * therefore invisible to the crawler by construction, not by a
 * fragile robots.txt or noindex rule.
 *
 * The crucial discipline (see the chapter's "Asymmetry Risk"
 * section): the set of crawlable URLs is a product-level constraint.
 * If any later feature renders the filter state into an <a href>, a
 * sitemap entry, or an ItemList, the URLs become crawlable again and
 * this strategy silently fails. Keep facet controls link-free.
 *
 * Expected markup (controls are buttons, never <a href>):
 *
 *   <div id="facets">
 *     <button type="button" data-facet="color" data-value="black">
 *       Black (127)
 *     </button>
 *     <button type="button" data-facet="size" data-value="10">
 *       Size 10 (54)
 *     </button>
 *   </div>
 *   <div id="results"><!-- rendered result list --></div>
 *
 * Reference: SEO for Engineers, Volume 1, Chapter 17, Strategy 3.
 */

/**
 * Apply a single facet to the current URL and re-render the results.
 *
 * Updates the address bar via history.pushState (so the view is
 * shareable and bookmarkable) without triggering a full navigation,
 * then asks the data layer to fetch and render the filtered set.
 *
 * @param {string} facet  The facet name, e.g. "color".
 * @param {string} value  The facet value, e.g. "black".
 */
export function applyFilter(facet, value) {
  const url = new URL(window.location.href);
  url.searchParams.set(facet, value);

  // pushState records a history entry so the back button works and
  // the URL is shareable; it does not issue an HTTP request and does
  // not create a crawlable link.
  history.pushState({ facet, value }, "", url);

  fetchAndRenderFilteredResults(url.searchParams);
}

/**
 * Wire up event delegation and back/forward handling. Call once on
 * page load. A single listener on the container handles every facet
 * button, including buttons added to the DOM later.
 *
 * @param {object} [options]
 * @param {string} [options.controlsSelector="#facets"]  Container
 *   whose [data-facet][data-value] buttons drive filtering.
 */
export function initFacetFilters({ controlsSelector = "#facets" } = {}) {
  const controls = document.querySelector(controlsSelector);
  if (controls) {
    controls.addEventListener("click", (event) => {
      const button = event.target.closest("[data-facet][data-value]");
      if (button && controls.contains(button)) {
        applyFilter(button.dataset.facet, button.dataset.value);
      }
    });
  }

  // Re-render when the user navigates back/forward through the
  // filter history. Without this, the back button changes the URL
  // but leaves the stale result set on screen.
  window.addEventListener("popstate", () => {
    fetchAndRenderFilteredResults(new URL(window.location.href).searchParams);
  });
}

/**
 * Fetch the filtered result set and render it into the page.
 *
 * This is the application-specific boundary: replace the body with a
 * call to your own JSON endpoint and your own rendering. It must NOT
 * emit <a href> links to filtered URLs, or the crawler-invisibility
 * property of this whole strategy is lost.
 *
 * @param {URLSearchParams} searchParams  Active facet selection.
 * @returns {Promise<void>}
 */
export async function fetchAndRenderFilteredResults(searchParams) {
  const response = await fetch(`/api/products?${searchParams.toString()}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`filter fetch failed: ${response.status}`);
  }
  const data = await response.json();

  // Application-specific rendering goes here. Render data.items into
  // #results using buttons/text, never <a href> to filtered URLs.
  void data;
}
