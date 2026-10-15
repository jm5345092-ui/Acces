package com.webapp.shell;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Message;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;

/**
 * Pantalla única: un WebView a pantalla completa que carga la URL configurada
 * en res/values/config.xml (start_url).
 */
public class MainActivity extends Activity {

    private static final int REQ_FILE_CHOOSER = 1001;

    private WebView webView;
    private ProgressBar progress;
    private ValueCallback<Uri[]> fileCallback;
    private String startUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        progress = findViewById(R.id.progress);
        startUrl = getString(R.string.start_url);

        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setLoadWithOverviewMode(true);
        ws.setUseWideViewPort(true);
        ws.setSupportZoom(false);
        ws.setBuiltInZoomControls(false);
        ws.setSupportMultipleWindows(true);
        ws.setJavaScriptCanOpenWindowsAutomatically(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        ws.setCacheMode(WebSettings.LOAD_DEFAULT);

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new Client());
        webView.setWebChromeClient(new Chrome());
        webView.setDownloadListener((url, ua, disposition, mime, length) -> openExternal(Uri.parse(url)));

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
        } else {
            webView.loadUrl(startUrl);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onDestroy() {
        if (webView != null) webView.destroy();
        super.onDestroy();
    }

    /** http/https se cargan dentro de la app; el resto (tel:, mailto:, whatsapp:, intent:) van al sistema. */
    private void handleUrl(Uri uri) {
        String scheme = uri.getScheme();
        if ("http".equals(scheme) || "https".equals(scheme)) {
            webView.loadUrl(uri.toString());
        } else {
            openExternal(uri);
        }
    }

    private void openExternal(Uri uri) {
        try {
            Intent intent;
            if ("intent".equals(uri.getScheme())) {
                intent = Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME);
                try {
                    startActivity(intent);
                } catch (ActivityNotFoundException e) {
                    String fallback = intent.getStringExtra("browser_fallback_url");
                    if (fallback != null) webView.loadUrl(fallback);
                }
                return;
            }
            intent = new Intent(Intent.ACTION_VIEW, uri);
            startActivity(intent);
        } catch (Exception ignored) {
            // No hay app que atienda el enlace: no hacemos nada.
        }
    }

    private void showErrorPage(String failedUrl) {
        webView.loadUrl("file:///android_asset/error.html?u=" + Uri.encode(failedUrl));
    }

    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            String scheme = uri.getScheme();
            if ("http".equals(scheme) || "https".equals(scheme) || "file".equals(scheme)) {
                return false; // se carga dentro del WebView
            }
            openExternal(uri);
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            progress.setProgress(0);
            progress.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            progress.setVisibility(View.GONE);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame()) {
                showErrorPage(request.getUrl().toString());
            }
        }
    }

    private class Chrome extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            progress.setProgress(newProgress);
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            try {
                startActivityForResult(params.createIntent(), REQ_FILE_CHOOSER);
            } catch (ActivityNotFoundException e) {
                fileCallback = null;
                return false;
            }
            return true;
        }

        /** Enlaces con target="_blank" o window.open(): se abren en el mismo WebView. */
        @Override
        public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, Message resultMsg) {
            WebView temp = new WebView(view.getContext());
            temp.setWebViewClient(new WebViewClient() {
                @Override
                public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                    handleUrl(request.getUrl());
                    return true;
                }
            });
            WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
            transport.setWebView(temp);
            resultMsg.sendToTarget();
            return true;
        }
    }
}
