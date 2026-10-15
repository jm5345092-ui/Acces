<?php
// Símbolos de monedas del mundo que flotan y rebotan suavemente en el fondo.
$coins = ['$', '€', '£', '¥', '₹', '₽', '₩', '₿', '¢', '₺', '₴', '₦', '₫', '₱', '₲', '₡', '฿', '₪'];
?>
<div class="bg-decor" aria-hidden="true">
    <div class="scanlines"></div>
    <div class="coins">
        <?php foreach ($coins as $i => $c): ?>
            <span class="coin coin--<?= $i + 1 ?>"><?= $c ?></span>
        <?php endforeach; ?>
    </div>
</div>
