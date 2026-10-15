<?php
session_start();

// Clear the session data, then expire the session cookie itself — without
// this, session_destroy() alone wipes server-side data but leaves the
// PHPSESSID cookie in the browser, and some caches/back-button states can
// still look "logged in" until that cookie is gone too.
$_SESSION = [];
if (ini_get('session.use_cookies')) {
    $params = session_get_cookie_params();
    setcookie(
        session_name(),
        '',
        time() - 42000,
        $params['path'],
        $params['domain'],
        $params['secure'],
        $params['httponly']
    );
}
session_destroy();

header('Cache-Control: no-cache, no-store, must-revalidate');
header('Pragma: no-cache');
header('Expires: 0');
header('Location: index.php');
exit;
