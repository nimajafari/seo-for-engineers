const TRACKING_PARAMS = [
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
  'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
  'gclid', 'gclsrc', 'dclid', 'wbraid', 'gbraid',
  'fbclid', 'fb_ref', 'fb_source',
  'msclkid',
  'mc_cid', 'mc_eid',
  'twclid', 'li_fat_id', 'igshid',
  'yclid', '_openstat',
  'ref', 'source', '_ga', '_gl', 'mkt_tok', 'oly_anon_id',
  'hsCtaTracking', '_hsenc', '_hsmi',
  'ck_subscriber_id', 'vero_id', 'sb_referer_host',
];

const TRACKING_PARAM_SET = new Set(TRACKING_PARAMS);

export default {
  async fetch(request) {
    // Only GET/HEAD are safe to 301-redirect. Other methods (POST,
    // PUT, PATCH, DELETE) would have their body silently dropped by
    // most clients on a 301, so we pass them through unchanged.
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return fetch(request);
    }

    const url = new URL(request.url);

    if (!url.search) {
      return fetch(request);
    }

    const toDelete = [];
    for (const [name] of url.searchParams) {
      if (TRACKING_PARAM_SET.has(name)) {
        toDelete.push(name);
      }
    }

    if (toDelete.length === 0) {
      return fetch(request);
    }

    for (const name of toDelete) {
      url.searchParams.delete(name);
    }

    const cleanUrl = url.toString();

    // Short max-age so a TRACKING_PARAMS update propagates within an
    // hour. A 301 is already cached aggressively by browsers; pinning
    // it for a full day compounds that and slows rollback.
    return new Response(null, {
      status: 301,
      headers: {
        'Location': cleanUrl,
        'Cache-Control': 'public, max-age=3600',
      },
    });
  },
};