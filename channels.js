// The dashboard tiles. Channels play their broadcaster's own HLS stream in watch.html, because the
// channels' websites are too heavy for the TV's 2017 browser. Stream hosts were picked for certificates
// the TV trusts (DigiCert G2, Starfield G2); it rejects Let's Encrypt ISRG X1.
// Source of the stream addresses: https://github.com/iptv-org/iptv (countries/tr.m3u), official CDNs only.
// TRT uses its 720p rendition: the TV screen is 720p, and its full list includes a 1440p stream some players reject.
// The daioncdn/ercdn streams send no CORS headers, so a desktop browser won't play them; the TV's own player may.
var CHANNELS = [
  { id: 'youtube',  name: 'YouTube',   color: '#e62117', url: 'https://www.youtube.com/tv' },
  { id: 'trt1',     name: 'TRT 1',     color: '#1d4fa3', stream: 'https://tv-trt1.medya.trt.com.tr/master_720.m3u8' },
  { id: 'atv',      name: 'ATV',       color: '#c8102e', stream: 'https://rnttwmjcin.turknet.ercdn.net/lcpmvefbyo/atv/atv_1080p.m3u8' },
  { id: 'kanald',   name: 'Kanal D',   color: '#0a6ebd', stream: 'https://demiroren.daioncdn.net/kanald/kanald.m3u8?app=kanald_web&ce=3' },
  { id: 'startv',   name: 'Star TV',   color: '#6a1b9a', stream: 'https://dogus.daioncdn.net/startv/startv_720p.m3u8?app=a20ac41e-bdc3-4aa1-934d-26b484480ac9&ce=3&sid=8l4w3lst4co5' },
  { id: 'tv8',      name: 'TV8',       color: '#2e7d32', stream: 'https://tv8.daioncdn.net/tv8/tv8.m3u8?app=7ddc255a-ef47-4e81-ab14-c0e5f2949788&ce=3' },
  { id: 'ntv',      name: 'NTV',       color: '#37474f', stream: 'https://dogus.daioncdn.net/ntv/ntv.m3u8?app=ntv_web' },
  { id: 'trthaber', name: 'TRT Haber', color: '#00838f', stream: 'https://tv-trthaber.medya.trt.com.tr/master_720.m3u8' },
  { id: 'trtmuzik', name: 'TRT Müzik', color: '#ad1457', stream: 'https://tv-trtmuzik.medya.trt.com.tr/master_720.m3u8' },
  { id: 'trtcocuk', name: 'TRT Çocuk', color: '#ef6c00', stream: 'https://tv-trtcocuk.medya.trt.com.tr/master_720.m3u8' }
];
