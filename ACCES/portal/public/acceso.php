<?php
// Valida la secuencia de la capa de acceso del lado del servidor.
// Si es correcta, otorga un permiso temporal en la sesión que login.php exige.
session_start();
header('Content-Type: application/json');

// ===== Secuencia secreta (4 símbolos, en orden). Cámbiala aquí. =====
$secret = ['₿', '€', '$', '£'];

$data = json_decode(file_get_contents('php://input'), true);
$seq = (is_array($data) && isset($data['seq']) && is_array($data['seq'])) ? $data['seq'] : [];

if ($seq === $secret) {
    $_SESSION['gate_passed'] = true;
    echo json_encode(['ok' => true]);
} else {
    unset($_SESSION['gate_passed']);
    echo json_encode(['ok' => false]);
}
