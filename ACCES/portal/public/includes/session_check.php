<?php
if (session_status() === PHP_SESSION_NONE) {
    session_start();
}

if (empty($_SESSION['owner_token'])) {
    header('Location: login.php');
    exit;
}

// Las páginas autenticadas llevan JS embebido (ver.php, host.php…). Sin esto, el navegador
// podía servir una versión vieja del HTML y ejecutar código desactualizado (p. ej. el borrado
// antiguo que "reaparecía"). Se fuerza a pedir siempre la versión actual.
header('Cache-Control: no-cache, no-store, must-revalidate');
header('Pragma: no-cache');
header('Expires: 0');
