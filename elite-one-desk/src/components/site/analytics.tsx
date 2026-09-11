"use client";

import Script from "next/script";

type Props = {
  ga4Id: string;
  gtmId: string;
  metaPixelId: string;
  nonce?: string;
};

/**
 * Nothing here loads unless an owner has entered the id in the Analytics
 * screen. No id is hard-coded, and each service is independent — configuring
 * GA4 does not silently pull in Tag Manager.
 *
 * Every tag is `afterInteractive`, so third-party JavaScript never competes
 * with the first paint.
 */
export function Analytics({ ga4Id, gtmId, metaPixelId, nonce }: Props) {
  return (
    <>
      {ga4Id ? (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ga4Id)}`}
            strategy="afterInteractive"
            nonce={nonce}
          />
          <Script id="eod-ga4" strategy="afterInteractive" nonce={nonce}>
            {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}
gtag('js',new Date());gtag('config','${ga4Id}',{anonymize_ip:true});`}
          </Script>
        </>
      ) : null}

      {gtmId ? (
        <Script id="eod-gtm" strategy="afterInteractive" nonce={nonce}>
          {`(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});
var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';
j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','${gtmId}');`}
        </Script>
      ) : null}

      {metaPixelId ? (
        <Script id="eod-meta-pixel" strategy="afterInteractive" nonce={nonce}>
          {`!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,
'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init','${metaPixelId}');fbq('track','PageView');`}
        </Script>
      ) : null}
    </>
  );
}
