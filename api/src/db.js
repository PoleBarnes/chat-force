const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

function createDb(dbPath) {
  const db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  runMigrations(db);
  return db;
}

function runMigrations(db) {
  const migrationsDir = path.join(__dirname, '..', 'migrations');

  db.exec(`
    CREATE TABLE IF NOT EXISTS _migrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);

  const applied = new Set(
    db.prepare('SELECT name FROM _migrations').all().map(r => r.name)
  );

  const files = fs.readdirSync(migrationsDir)
    .filter(f => f.endsWith('.sql'))
    .sort();

  const runMigration = db.transaction((name, sql) => {
    db.exec(sql);
    db.prepare('INSERT INTO _migrations (name) VALUES (?)').run(name);
  });

  for (const file of files) {
    if (!applied.has(file)) {
      const sql = fs.readFileSync(path.join(migrationsDir, file), 'utf8');
      runMigration(file, sql);
    }
  }
}

module.exports = { createDb };
