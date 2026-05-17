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
