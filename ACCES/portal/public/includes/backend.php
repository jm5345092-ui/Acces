<?php
// Backend Node (Railway) que ya usan las apps Android — mismo que sirve /api/login,
// /api/hosts y /turn-credentials. El portal PHP es solo una vista sobre esta API.
// Las páginas con JS (ver.php, conectar.php, host.php) también leen esta constante,
// así que es el único lugar donde cambiar la URL del backend. En Railway se puede
// sobreescribir con la variable de entorno BACKEND_BASE_URL sin tocar el código.
define('BACKEND_BASE_URL', getenv('BACKEND_BASE_URL') ?: 'https://server-production-6372.up.railway.app');

/**
 * Llama a la API del backend Node. Devuelve ['status' => int, 'body' => array|null].
 * $token, si se pasa, se manda como Authorization: Bearer <token>.
 */
function backend_request(string $method, string $path, ?array $data = null, ?string $token = null): array
{
    $ch = curl_init(BACKEND_BASE_URL . $path);
    $headers = ['Content-Type: application/json'];
    if ($token) {
        $headers[] = 'Authorization: Bearer ' . $token;
    }

    curl_setopt_array($ch, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_TIMEOUT => 10,
    ]);
    if ($data !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    }

    $raw = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    return ['status' => $status, 'body' => $raw ? json_decode($raw, true) : null];
}
