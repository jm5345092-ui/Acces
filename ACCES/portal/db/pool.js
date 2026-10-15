const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

// Sin este listener, un error en un cliente IDLE del pool (p.ej. ECONNRESET si la red
// a Postgres se cae un instante) queda como excepción no capturada y mata el proceso
// entero (server.js o worker.js) — ya nos pasó una vez. Solo se loguea y se descarta:
// el pool reemplaza el cliente roto por su cuenta en la siguiente query.
pool.on('error', (err) => {
  console.error('[DB Pool] Error en cliente idle (recuperable):', err.message);
});

module.exports = { pool };
