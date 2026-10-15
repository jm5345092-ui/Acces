<?php
// Called by the webserver SPA (AppShell) on mount and on bfcache restore
// (pageshow) to confirm the admin session is still actually valid — the
// Apache-level gate in webserver-proxy.conf only catches the cookie being
// entirely absent; this catches a present-but-logged-out/unauthenticated
// session too.
session_start();
header('Content-Type: application/json');
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');
echo json_encode(['authenticated' => !empty($_SESSION['owner_token'])]);
