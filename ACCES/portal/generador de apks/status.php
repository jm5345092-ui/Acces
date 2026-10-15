<?php
// Devuelve en JSON el estado de una compilación (lo consulta index.php cada pocos segundos).
require_once __DIR__ . '/lib/functions.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

$slug = preg_replace('/[^a-z0-9_]/', '', $_GET['job'] ?? '');
$info = $slug ? job_info($slug) : null;
if (!$info) {
    http_response_code(404);
    echo json_encode(['error' => 'Job no encontrado']);
    exit;
}

$log = '';
$logFile = JOBS_DIR . "/$slug/build.log";
if (is_file($logFile)) {
    $log = (string)file_get_contents($logFile);
    if (strlen($log) > 6000) $log = '...' . substr($log, -6000);
    // Parte del log lo escribe cmd.exe en la codificación de consola (CP850); lo normalizamos a UTF-8
    if (!mb_check_encoding($log, 'UTF-8')) $log = mb_convert_encoding($log, 'UTF-8', 'CP850');
}

echo json_encode([
    'slug'     => $slug,
    'name'     => $info['name'],
    'status'   => $info['status'],
    'log'      => $log,
    'apk'      => $info['apk_exists'] ? "apks/$slug.apk" : null,
    'apk_size' => $info['apk_size'],
], JSON_UNESCAPED_UNICODE);
