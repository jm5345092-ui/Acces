// Uso: node db/create-owner.js <usuario> <contraseña>
// Crea (o actualiza la contraseña de) una cuenta de técnico en la tabla `owners`.
const bcrypt = require('bcryptjs');
const { pool } = require('./pool');
const { migrate } = require('./migrate');

async function main() {
  const [, , username, password] = process.argv;
  if (!username || !password) {
    console.error('Uso: node db/create-owner.js <usuario> <contraseña>');
    process.exit(1);
  }

  await migrate();
  const passwordHash = await bcrypt.hash(password, 10);
  await pool.query(
    `INSERT INTO owners (username, password_hash) VALUES ($1, $2)
     ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash`,
    [username, passwordHash]
  );
  console.log(`Cuenta "${username}" lista.`);
  await pool.end();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
