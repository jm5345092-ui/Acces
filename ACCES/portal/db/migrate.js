const fs = require('fs');
const path = require('path');
const { pool } = require('./pool');

/** Crea las tablas si no existen. Seguro de correr en cada arranque del servidor. */
async function migrate() {
  const sql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');
  await pool.query(sql);
}

module.exports = { migrate };
