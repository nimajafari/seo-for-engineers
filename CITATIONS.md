# Citations

Every primary source cited in *SEO for Engineers* is listed here, organized
by chapter, with the specific claim or section it supports. This index is
the operational form of the book's "Note on Sources" promise. If you read
a claim in the book and want to verify it, this is where to start.

Links to Google documentation are direct deep links rather than top-level
pages, so they point at the specific guidance being cited. When a link
moves, the move is logged in `CHANGELOG.md` and the entry here is updated.

## Volume 1, Code and Craft

### Chapter 1, Crawling as a Distributed System

Foundational paper.

- Brin, S. and Page, L. (1998). *The Anatomy of a Large-Scale Hypertextual
  Web Search Engine.* Stanford University.
  https://snap.stanford.edu/class/cs224w-readings/Brin98Anatomy.pdf

Google crawler infrastructure documentation.

- *Overview of Google crawlers and fetchers.*
  https://developers.google.com/crawling/docs/crawlers-fetchers/overview-google-crawlers
  
- *Google's common crawlers.*
  https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers

- *Verify Google crawlers and fetchers.*
  https://developers.google.com/crawling/docs/crawlers-fetchers/verify-google-requests

- *Googlebot IP ranges.*
  https://developers.google.com/static/search/apis/ipranges/googlebot.json

- *Common crawlers IP ranges.*
  https://developers.google.com/static/crawling/ipranges/common-crawlers.json

Crawl budget and crawl scheduling.

- Illyes, G. (2017). *What Crawl Budget Means for Googlebot.*
  https://developers.google.com/search/blog/2017/01/what-crawl-budget-means-for-googlebot

- *Large site owner's guide to managing your crawl budget.*
  https://developers.google.com/crawling/docs/crawl-budget

robots.txt and crawl directives.

- *How Google interprets the robots.txt specification.*
  https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec

Rendering and evergreen Googlebot.

- *The new evergreen Googlebot.* May 2019.
  https://developers.google.com/search/blog/2019/05/the-new-evergreen-googlebot

Google Search Essentials.

- *Google Search Essentials.*
  https://developers.google.com/search/docs/essentials

### Chapter 2, The Rendering Pipeline

- *Understand the JavaScript SEO basics.*
  https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics

- *The new evergreen Googlebot.* (Also cited in Chapter 1.)
  
- *URL Inspection tool.* Search Console Help.
  https://support.google.com/webmasters/answer/9012289

- *Bing announces evergreen Bingbot.* October 2019.
  https://blogs.bing.com/webmaster/october-2019/The-new-evergreen-Bingbot-simplifying-SEO-by-leveraging-Microsoft-Edge

- *About Applebot.* Apple Support.
  https://support.apple.com/en-us/119829

### Chapter 3, Indexing, Canonicalization, and Duplicate Detection

- *Consolidate duplicate URLs with canonicalization.*
  https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls

- *301 redirects.*
  https://developers.google.com/search/docs/crawling-indexing/301-redirects

- *Canonicalization and de-duplication of URLs.* March 2019.
  https://developers.google.com/search/blog/2019/03/canonicalization-and-de-duplication-of

- *Search Quality Rater Guidelines.*
  https://services.google.com/fh/files/misc/hsw-sqrg.pdf

- *Introduction to structured data markup in Google Search.*
  https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data

- *Index Coverage report.*
  https://support.google.com/webmasters/answer/7440203

- *URL Inspection API.*
  https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect

### Chapter 4, Ranking Signals That Engineering Controls

Page Experience and Core Web Vitals.

- *Timing for the Page Experience update.* November 2020.
  https://developers.google.com/search/blog/2020/11/timing-for-page-experience

- *Core Web Vitals.* web.dev.
  https://web.dev/articles/vitals

- *Chrome User Experience Report.*
  https://developer.chrome.com/docs/crux/

- *CrUX API.*
  https://developer.chrome.com/docs/crux/api/

HTTPS as a ranking signal.

- *HTTPS as a ranking signal.* August 2014.
  https://developers.google.com/search/blog/2014/08/https-as-ranking-signal

Mobile-first indexing.

- *Announcing mobile-first indexing for the whole web.* March 2020.
  https://developers.google.com/search/blog/2020/03/announcing-mobile-first-indexing-for

PageRank and link architecture.

- Brin and Page (1998). (Also cited in Chapter 1.)

Structured data validation.

- *Rich Results Test.*
  https://search.google.com/test/rich-results

- *Schema.org Validator.*
  https://validator.schema.org/

E-E-A-T framework.

- *Search Quality Rater Guidelines.* (Also cited in Chapter 3.)

### Chapter 5, JavaScript Rendering and the Crawlability Challenge

Rendering taxonomy.

- *Rendering on the Web.* web.dev.
  https://web.dev/articles/rendering-on-the-web

Google's JavaScript SEO guidance.

- *Understand the JavaScript SEO basics.* (Also cited in Chapter 2.)
  
- *Mobile sites and mobile-first indexing.*
  https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing

Speculation Rules API and prerender deprecation.

- *Remove support for `<link rel="prerender">`.* Chrome Platform Status.
  https://chromestatus.com/feature/5702647521583104

Validation and diagnostics.

- *URL Inspection tool.* (Also cited in Chapter 2.)
  
- *Rich Results Test.* (Also cited in Chapter 4.)

Lighthouse CI.

- *Lighthouse CI documentation.*
  https://github.com/GoogleChrome/lighthouse-ci

### Chapter 6, Core Web Vitals as an Engineering Discipline

LCP and INP guidance.

- *Optimize Largest Contentful Paint.* web.dev.
  https://web.dev/articles/optimize-lcp

- *Interaction to Next Paint.* web.dev.
  https://web.dev/articles/inp

- *Cumulative Layout Shift.* web.dev.
  https://web.dev/articles/cls

Resource hints.

- *fetchpriority.* web.dev.
  https://web.dev/articles/fetch-priority

- *fetchpriority browser support.* caniuse.com.
  https://caniuse.com/mdn-html_elements_img_fetchpriority

- *Choose the right image format.* web.dev.
  https://web.dev/articles/choose-the-right-image-format

Web Vitals library and extension.

- *web-vitals library.* GitHub.
  https://github.com/GoogleChrome/web-vitals

- *Web Vitals Chrome extension.* Chrome Web Store.
  https://chrome.google.com/webstore/detail/web-vitals/ahfhijdlegdabablpippeagghigmibma

Lighthouse CI.

- *Lighthouse CI documentation.* (Also cited in Chapter 5.)

bfcache.

- *Back/forward cache.* web.dev.
  https://web.dev/articles/bfcache

Font metric overrides.

- *Fontpie.* GitHub.
  https://github.com/pixel-point/fontpie

Core Web Vitals report.

- *Core Web Vitals report.* Search Console Help.
  https://support.google.com/webmasters/answer/9205520

### Chapter 7, Semantic HTML and Information Architecture for Machines

HTML specifications.

- *HTML Living Standard, Sections, the nav element.* WHATWG.
  https://html.spec.whatwg.org/multipage/sections.html#the-nav-element

- *HTML Living Standard, Grouping content, the main element.* WHATWG.
  https://html.spec.whatwg.org/multipage/grouping-content.html#the-main-element

- *ARIA in HTML.* W3C.
  https://www.w3.org/TR/html-aria/

Google guidance on document structure.

- *How Search Works.* Google.
  https://developers.google.com/search/docs/fundamentals/how-search-works

- *Title links and snippets.*
  https://developers.google.com/search/docs/appearance/title-link

- *Introducing Passage Indexing.* November 2020.
  https://developers.google.com/search/blog/2020/11/introducing-passage-indexing

- *Google image SEO best practices.*
  https://developers.google.com/search/docs/appearance/google-images

- *Video SEO best practices.*
  https://developers.google.com/search/docs/appearance/video

Link qualification.

- *Qualify outbound links.*
  https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links

- *Evolving "nofollow", new ways to identify the nature of links.* September 2019.
  https://developers.google.com/search/blog/2019/09/evolving-nofollow-new-ways-to-identify

- *A note on unsupported rel-attributes in Google Search.* September 2019.
  https://developers.google.com/search/blog/2019/09/the-rel-prev-and-next-day

Linting and tooling.

- *eslint-plugin-jsx-a11y.* GitHub.
  https://github.com/jsx-eslint/eslint-plugin-jsx-a11y

### Chapter 8, Meta Tags, Canonical Tags, and Head Management

Google guidance on meta and link elements.

- *Title links and snippets.* (Also cited in Chapter 7.)
  
- *Robots meta tag, data-nosnippet, and X-Robots-Tag specifications.*
  https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag

- *Consolidate duplicate URLs with canonicalization.* (Also cited in Chapter 3.)
  
- *Mobile sites and mobile-first indexing.* (Also cited in Chapter 5.)
  
- *A note on unsupported rel-attributes in Google Search.* (Also cited in Chapter 7.)

Open Graph and X (Twitter) Cards.

- *The Open Graph protocol.* ogp.me.
  https://ogp.me/

- *Facebook Sharing Debugger.*
  https://developers.facebook.com/tools/debug

- *LinkedIn Post Inspector.*
  https://www.linkedin.com/post-inspector/

Framework metadata APIs.

- *Next.js Metadata API.*
  https://nextjs.org/docs/app/api-reference/functions/generate-metadata

- *Next.js Middleware.*
  https://nextjs.org/docs/app/api-reference/file-conventions/middleware

- *Nuxt useHead and useSeoMeta.*
  https://nuxt.com/docs/getting-started/seo-meta

- *Angular Meta and Title services.*
  https://angular.dev/api/platform-browser/Meta
  
- *SvelteKit svelte:head.*
  https://svelte.dev/docs/svelte/svelte-head

Open Graph image generation.

- *@vercel/og.* Vercel documentation.
  https://vercel.com/docs/functions/og-image-generation


### Chapter 9, Structured Data at Scale

Schema.org vocabulary.

- *Schema.org.*
  https://schema.org/

Google general structured data guidance.

- *Introduction to structured data markup in Google Search.* (Also cited in Chapter 3.)

- *General structured data guidelines and policies.*
  https://developers.google.com/search/docs/appearance/structured-data/sd-policies

- *Search Gallery (current supported rich result types).*
  https://developers.google.com/search/docs/appearance/structured-data/search-gallery

- *Latest Google Search documentation updates.*
  https://developers.google.com/search/updates

Per-type Google documentation referenced in the chapter.

- *Product structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/product

- *Article structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/article

- *BreadcrumbList structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/breadcrumb

- *LocalBusiness structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/local-business

- *Organization structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/organization

- *VideoObject structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/video
- *Recipe structured data.*
- 
  https://developers.google.com/search/docs/appearance/structured-data/recipe

- *Event structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/event

Discussion forums and Q&A structured data update.

- *Discussion forum structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/discussion-forum

- *Q&A page structured data.*
  https://developers.google.com/search/docs/appearance/structured-data/qapage

- *Google Adds AI & Bot Labels To Forum, Q&A Structured Data.*
  Search Engine Journal, March 24, 2026.
  https://www.searchenginejournal.com/google-adds-ai-bot-labels-to-forum-qa-structured-data/570425/

Deprecation announcements.

- *Simplifying the search results page.* Google Search Central Blog,
  June 12, 2025.
  https://developers.google.com/search/blog/2025/06/simplifying-search-results

- *Practice Problems deprecation.* Google Search Central documentation
  changelog, November 2025.
  https://developers.google.com/search/docs/appearance/structured-data/practice-problems

- *FAQ structured data deprecation notice.*
  https://developers.google.com/search/docs/appearance/structured-data/faqpage

Validation and tooling.

- *Rich Results Test.* (Also cited in Chapter 4.)

- *Schema.org Validator.* (Also cited in Chapter 3.)

- *schema-dts TypeScript types.* Google, GitHub.
  https://github.com/google/schema-dts

Framework documentation.

- *Next.js JSON-LD guide.*
  https://nextjs.org/docs/app/guides/json-ld

- *Nuxt SEO and meta tags.* (Also cited in Chapter 8.)

- *Angular Meta and Title services.* (Also cited in Chapter 8.)

- *SvelteKit svelte:head.* (Also cited in Chapter 8.)

### Chapter 10, Internal Linking as a Graph Problem

Foundational paper and Google guidance on link architecture.

- Brin and Page (1998). (Also cited in Chapters 1 and 4.)

- *Importance of link architecture.* Google Search Central Blog, October 2008.
  https://developers.google.com/search/blog/2008/10/importance-of-link-architecture

- *Make your links crawlable.*
  https://developers.google.com/search/docs/crawling-indexing/links-crawlable

- *Sitelinks.*
  https://developers.google.com/search/docs/appearance/sitelinks

Pagination guidance.

- *Pagination best practices for Google.*
  https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading

- *Pagination with rel="next" and rel="prev".* Google Search Central Blog, September 2011.
  https://developers.google.com/search/blog/2011/09/pagination-with-relnext-and-relprev

- *A note on unsupported rel-attributes in Google Search.* (Also cited in Chapter 7.)

Independent research and industry data referenced in the chapter.

- *2.5 Million Internal Links Study, How Websites Link Their Content.* LinkStorm.
  https://linkstorm.io/studies/internal-links-study

- *The State of Pagination and Infinite Scroll.* Adam Gent, BrightonSEO April 2019. DeepCrawl.
  https://www.slideshare.net/DeepCrawl/the-state-of-pagination-infinite-scroll-brightonseo-april-2019-adam-gent

- *State of Pagination in eCommerce, the SilkFred case study.* Orit Mutznik, BrightonSEO 2020.
  https://www.lumar.io/blog/best-practice/state-of-pagination-in-ecommerce/
  
- *How does Google pagination crawling work in 2025?* Journey Further, 2025.
  https://www.journeyfurther.com/articles/how-does-google-handle-pagination-links-in-2025

2024 Google API leak.

- Fishkin, R. (2024). *An anonymous source shared thousands of leaked
  Google Search API documents with me.* SparkToro.
  https://sparktoro.com/blog/an-anonymous-source-shared-thousands-of-leaked-google-search-api-documents-with-me-everyone-in-seo-should-see-them

Graph analysis tooling.

- *NetworkX, network analysis in Python.*
  https://networkx.org/


### Chapter 11, Internationalization and Multilingual SEO Engineering

Google guidance on international and multilingual sites.

- *Managing multi-regional and multilingual sites.*
  https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites

- *Tell Google about localized versions of your page.*
  https://developers.google.com/search/docs/specialty/international/localized-versions

- *The International Targeting report is deprecated.* Search Console Help.
  https://support.google.com/webmasters/answer/12474899

ISO standards referenced in the chapter.

- *ISO 639-1, codes for the representation of names of languages.*
  https://www.iso.org/iso-639-language-code

- *ISO 3166-1 Alpha-2, codes for the representation of names of
  countries and their subdivisions.*
  https://www.iso.org/iso-3166-country-codes.html

Independent research and industry data.

- Stox, P. (2023). *Over 67% of Domains Using Hreflang Have Issues,
  Study of 374,756 Domains.* Ahrefs. BrightonSEO September 15, 2023.
  https://ahrefs.com/blog/hreflang-study/

Frontend i18n libraries referenced in the chapter.

- *next-intl, internationalization for Next.js.* https://next-intl.dev/

- *react-i18next.* https://react.i18next.com/

- *vue-i18n.* https://vue-i18n.intlify.dev/

- *Angular localize.* https://angular.dev/guide/i18n

CDN edge routing platforms referenced in the chapter.

- *Cloudflare Workers.* https://developers.cloudflare.com/workers/

- *AWS CloudFront Functions.*
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-functions.html
  
- *Fastly Compute.* https://docs.fastly.com/products/compute


### Chapter 12, URL Design as an Engineering Discipline

Google guidance on URL structure and site moves.

- *Keep a simple URL structure.*
  https://developers.google.com/search/docs/crawling-indexing/url-structure

- *Move a site with URL changes.*
  https://developers.google.com/search/docs/crawling-indexing/site-move-with-url-changes

- *Move a site without URL changes (changing hosting).*
  https://developers.google.com/search/docs/crawling-indexing/site-move-no-url-changes

- *Change of Address tool.* Search Console Help.
  https://support.google.com/webmasters/answer/9370220

- *Spring cleaning, the URL Parameters tool.* Google Search Central Blog, March 28, 2022.
  https://developers.google.com/search/blog/2022/03/url-parameters-tool-deprecated

RFC and Unicode references.

- *RFC 3986, Uniform Resource Identifier (URI), Generic Syntax.* IETF.
  https://datatracker.ietf.org/doc/html/rfc3986

- *Unicode Normalization Forms.* Unicode Standard Annex #15.
  https://unicode.org/reports/tr15/

Slug pattern examples referenced in the chapter.

- *Stack Overflow URL pattern.*

- *unidecode, ASCII transliteration of Unicode text.* PyPI.
  https://pypi.org/project/Unidecode/


### Chapter 13, HTTP Fundamentals for SEO

Google guidance on HTTP responses and redirects.

- *301 redirects.* (Also cited in Chapter 3.)
  Cited for: redirect chain limits (Googlebot follows up to 10
  redirects), and the canonical mechanism for transferring ranking
  signals between URLs.

- *Do 404s hurt my site?* Google Search Central Blog, May 2011.
  https://developers.google.com/search/blog/2011/05/do-404s-hurt-my-site
  Cited for: Google's published position that 404 responses for
  legitimately removed URLs are correct behavior and do not damage
  site rankings.

- *Robots meta tag, data-nosnippet, and X-Robots-Tag specifications.*
  (Also cited in Chapter 8.)
  Cited for: the rule that conflicts between HTML meta robots and
  HTTP X-Robots-Tag are resolved by taking the most restrictive
  directive, and the use of X-Robots-Tag for non-HTML resources.

- *Understand the JavaScript SEO basics.* (Also cited in Chapter 2.)
  Cited for: Google's withdrawal of dynamic rendering as a
  recommendation. The remaining documentation describes dynamic
  rendering in the past tense as a workaround, not a long-term
  solution, with SSR, SSG, or hydration as the current recommendations.

- *HTTPS as a ranking signal.* (Also cited in Chapter 4.)
  Cited for: HTTPS as a confirmed ranking signal since 2014.

- *HTTPS issues in Search Console.* Google Search Console Help.
  https://support.google.com/webmasters/answer/6073543
  
- *Secure your site with HTTPS.* Google Search Central.
  https://developers.google.com/search/docs/advanced/security/https
  Both cited for: Google's framing of certificate validity failures
  as causing crawl failures, and the impact chain from TLS handshake
  failure to coverage loss.

HTTP specifications.

- *RFC 9110, HTTP Semantics.* IETF.
  https://datatracker.ietf.org/doc/html/rfc9110
  Cited for: the current authoritative reference for HTTP status
  code semantics, redirect types, and response header behavior.

- *RFC 8297, An HTTP Status Code for Indicating Hints (103 Early Hints).* IETF.
  https://datatracker.ietf.org/doc/html/rfc8297
  Cited for: the Early Hints specification, including the 103
  status code semantics and the rule that Link headers delivered
  in Early Hints permit speculative subresource fetching.

- *Cloudflare Early Hints documentation.*
  https://developers.cloudflare.com/cache/advanced-configuration/early-hints
  Cited for: the CDN-level automatic Early Hints implementation
  pattern, where the CDN learns preload candidates from prior
  request analysis.

- *Remove HTTP/2 Server Push.* Chrome Platform Status.
  https://chromestatus.com/feature/6302414934114304
  Cited for: the Chrome 106 (October 2022) removal of HTTP/2
  Server Push support, with the documented reasoning around cache
  mismatch, timing, complexity, and bandwidth competition.

TLS, certificate, and PKI references.

- *RFC 5280, Internet X.509 Public Key Infrastructure Certificate
  and Certificate Revocation List (CRL) Profile.* IETF.
  https://datatracker.ietf.org/doc/html/rfc5280
  Cited for: the CRL specification, the CRL Distribution Point
  certificate extension, and the X.509 chain validation model.

- *RFC 6066, Transport Layer Security (TLS) Extensions, Section 8.*
  IETF.
  https://datatracker.ietf.org/doc/html/rfc6066#section-8
  Cited for: the TLS Certificate Status Request extension that
  underpins OCSP stapling.

- *RFC 6125, Representation and Verification of Domain-Based
  Application Service Identity Within Internet Public Key
  Infrastructure Using X.509 Certificates.* IETF.
  https://datatracker.ietf.org/doc/html/rfc6125
  Cited for: the deprecation of Common Name (CN) based hostname
  matching in favor of Subject Alternative Name (SAN) only.

- *RFC 6960, X.509 Internet Public Key Infrastructure Online
  Certificate Status Protocol, OCSP.* IETF.
  https://datatracker.ietf.org/doc/html/rfc6960
  Cited for: the OCSP specification including request/response
  format, the good/revoked/unknown status values, and the
  latency and privacy properties that motivated stapling.

- *RFC 7633, X.509v3 Transport Layer Security (TLS) Feature
  Extension.* IETF.
  https://datatracker.ietf.org/doc/html/rfc7633
  Cited for: the Must-Staple extension specification (OID
  1.3.6.1.5.5.7.1.24) and its hard-fail semantics.

- Langley, A. (2012). *Revocation checking and Chrome's CRL.*
  https://www.imperialviolet.org/2012/02/05/crlsets.html
  Cited for: the foundational analysis of OCSP latency (median
  ~300ms, mean close to 1 second) and the soft-fail problem that
  motivated Chrome's move away from live OCSP checks.

- *OCSP stapling.* Wikipedia.
  https://en.wikipedia.org/wiki/OCSP_stapling
  Cited for: the documented Apache historical failure pattern of
  discarding a cached good response on temporary failure rather
  than serving it.

- Cloudflare (2017). *High-reliability OCSP stapling and why it matters.*
  https://blog.cloudflare.com/high-reliability-ocsp-stapling/
  Cited for: the engineering writeup on Must-Staple deployment risk
  and the patterns required for reliable OCSP stapling at scale.

- Jafari, N. and Mansouri, M. *CRL vs OCSP Explained, Complete Guide
  to Stapling and Must-Staple.* OxyPlug.
  https://www.oxyplug.com/optimization/crl-ocsp-certificate-revocation-methods/
  Author's own work, cited for: the timing experiments showing OCSP
  validation averaging approximately 134ms and CRL download
  averaging approximately 458ms in real-world handshake measurements.

CA/Browser Forum and ecosystem changes 2024-2026.

- *Ballot SC-081v3, Introduce Schedule of Reducing Validity and Data
  Reuse Periods.* CA/Browser Forum, April 11, 2025.
  https://cabforum.org/2025/04/11/ballot-sc081v3-introduce-schedule-of-reducing-validity-and-data-reuse-periods/
  Cited for: the phased reduction of TLS certificate validity to
  200 days (March 15, 2026), 100 days (March 15, 2027), and 47
  days (March 15, 2029), with corresponding reductions in domain
  control validation reuse periods to 10 days by 2029.

- Let's Encrypt (2024). *Ending OCSP Support in 2025.*
  https://letsencrypt.org/2024/12/05/ending-ocsp/
  Cited for: the announced timeline of OCSP Must-Staple issuance
  blocked for new accounts on January 30, 2025, OCSP URLs dropped
  from certificates on May 7, 2025, and OCSP responders fully
  decommissioned on August 6, 2025.

- Let's Encrypt (2025). *OCSP Service Has Reached End of Life.*
  https://letsencrypt.org/2025/08/06/ocsp-service-has-reached-end-of-life/
  Cited for: confirmation that Let's Encrypt's OCSP service was
  fully shut down on August 6, 2025, and the operational
  justifications including approximately 340 billion OCSP requests
  per month at the service's peak.

- Mozilla (2025). *CRLite, Fast, private, and comprehensive
  certificate revocation checking in Firefox.*
  https://hacks.mozilla.org/2025/08/crlite-fast-private-and-comprehensive-certificate-revocation-checking-in-firefox/
  Cited for: the enabling of CRLite for all Firefox desktop users
  starting in Firefox 137 (April 1, 2025), with 12-hour update
  intervals and local-only revocation checking.

- *Chromium CRLSets.* Chromium Projects.
  https://www.chromium.org/Home/chromium-security/crlsets/
  Cited for: Chrome's curated CRLSets mechanism as a narrow,
  emergency-focused revocation distribution channel rather than
  comprehensive coverage.

- *HSTS Preload List.* Google.
  https://hstspreload.org
  Cited for: the Chromium HSTS preload list, which hardcodes HTTPS
  enforcement into the browser for participating domains.

Diagnostic tooling.

- *SSL Labs SSL Server Test.* Qualys.
  https://www.ssllabs.com/ssltest/
  Cited for: the standard external diagnostic for chain
  completeness, certificate configuration, and TLS handshake
  details, including the explicit "Chain issues" flag.

### Chapter 14, Sitemaps as a Backend Responsibility

Sitemap protocol and specifications.

- *Sitemaps XML format.* Sitemaps.org.
  https://www.sitemaps.org/protocol.html
  Cited for: the canonical protocol specification, the `<urlset>` and
  `<sitemapindex>` schemas, the 50,000-URL and 50 MB size limits, and
  the W3C datetime requirement for `<lastmod>`.

- *RFC 3339, Date and Time on the Internet, Timestamps.* IETF.
  https://datatracker.ietf.org/doc/html/rfc3339
  Cited for: the ISO 8601 subset that the sitemap protocol uses for
  `<lastmod>` and related datetime fields.

Google's sitemap documentation.

- *Sitemaps, overview.* Google Search Central.
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview
  Cited for: Google's framing of sitemaps as a discovery aid, the
  explicit statement that submission does not guarantee crawling or
  indexing, and the criteria for which site profiles benefit most from
  sitemaps.

- *Build and submit a sitemap.* Google Search Central.
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
  Cited for: the direct statement that *"Google ignores `<priority>`
  and `<changefreq>` values"* and uses `<lastmod>` only when
  consistently and verifiably accurate, plus the definition of
  "significant update" as a change to the main content, structured
  data, or links (and not, for example, the copyright date).

- *Sitemaps, lastmod and ping.* Google Search Central blog (June 2023).
  https://developers.google.com/search/blog/2023/06/sitemaps-lastmod-ping
  Cited for: the formal deprecation of the sitemap ping endpoint and
  the corresponding reaffirmation of `<lastmod>` as the freshness
  signal Google trusts when accurate.

- *Create a news sitemap.* Google Search Central.
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
  Cited for: the two-day (48-hour) eligibility window for news
  articles, the 1,000-URL per-file cap, the required `<news:news>`
  schema, and the `<news:publication_date>` format requirements.

- *Video sitemaps.* Google Search Central.
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/video-sitemaps
  Cited for: the `<video:video>` extension schema, the distinction
  between `<video:content_loc>` and `<video:player_loc>`, and the
  metadata fields Google uses to surface videos in search.

- *Image sitemaps.* Google Search Central.
  https://developers.google.com/search/docs/crawling-indexing/sitemaps/image-sitemaps
  Cited for: the `<image:image>` extension schema, and the current
  guidance that well-marked-up images in crawlable pages typically do
  not require a separate image sitemap.

- *Search Console API, Sitemaps resource.* Google Search Central.
  https://developers.google.com/webmaster-tools/v1/sitemaps
  Cited for: the API endpoints for `sitemaps.submit`, `sitemaps.get`,
  and `sitemaps.list`, and the response fields used in the monitoring
  example (`lastSubmitted`, `lastDownloaded`, `warnings`, `errors`,
  `contents`).

- *Indexing API quickstart.* Google Search Central.
  https://developers.google.com/search/apis/indexing-api/v3/quickstart
  Cited for: the restriction of the Indexing API to job posting and
  live-streaming video content types, which is the basis of the
  chapter's argument that the Indexing API is not a general-purpose
  sitemap replacement.

Engineering tooling referenced in the chapter.

- *lxml, the etree.xmlfile incremental writer.* lxml documentation.
  https://lxml.de/api.html#incremental-xml-generation
  Cited for: the streaming XML writer used in the Python sitemap
  worker example, which is the canonical pattern for generating
  sitemaps over the 50,000-URL limit without loading the full URL set
  into memory.

