const express = require('express');
const { createDb } = require('./db');

function createApp(dbPath = ':memory:') {
  const app = express();
  const db = createDb(dbPath);

  app.use(express.json());

  // Handle malformed JSON
  app.use((err, _req, res, next) => {
    if (err.type === 'entity.parse.failed') {
      return res.status(400).json({ error: 'Invalid JSON' });
    }
    next(err);
  });

  const VALID_PRIORITIES = ['low', 'medium', 'high', 'critical'];

  function validateTask(body, partial = false) {
    const errors = [];

    if (!partial) {
      if (!body || typeof body.title !== 'string' || body.title.trim() === '') {
        errors.push('title is required and must be a non-empty string');
      }
      if (!body || !VALID_PRIORITIES.includes(body.priority)) {
        errors.push(`priority is required and must be one of: ${VALID_PRIORITIES.join(', ')}`);
      }
    } else {
      if ('title' in body && (typeof body.title !== 'string' || body.title.trim() === '')) {
        errors.push('title must be a non-empty string');
      }
      if ('priority' in body && !VALID_PRIORITIES.includes(body.priority)) {
        errors.push(`priority must be one of: ${VALID_PRIORITIES.join(', ')}`);
      }
    }

    return errors;
  }

  // GET /api/tasks/stats — must be before :id route
  app.get('/api/tasks/stats', (_req, res) => {
    const rows = db.prepare(
      `SELECT priority, COUNT(*) as count FROM tasks GROUP BY priority`
    ).all();

    const stats = { low: 0, medium: 0, high: 0, critical: 0 };
    for (const row of rows) {
      stats[row.priority] = row.count;
    }
    stats.total = Object.values(stats).reduce((a, b) => a + b, 0);

    res.json(stats);
  });

  // GET /api/tasks
  app.get('/api/tasks', (_req, res) => {
    const tasks = db.prepare('SELECT * FROM tasks ORDER BY id ASC').all();
    res.json(tasks);
  });

  // POST /api/tasks
  app.post('/api/tasks', (req, res) => {
    const errors = validateTask(req.body);
    if (errors.length) {
      return res.status(422).json({ errors });
    }

    const { title, description = '', priority } = req.body;
    const result = db.prepare(
      `INSERT INTO tasks (title, description, priority) VALUES (?, ?, ?)`
    ).run(title.trim(), description, priority);

    const task = db.prepare('SELECT * FROM tasks WHERE id = ?').get(result.lastInsertRowid);
    res.status(201).json(task);
  });

  // PUT /api/tasks/:id
  app.put('/api/tasks/:id', (req, res) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id < 1) {
      return res.status(400).json({ error: 'Invalid task ID' });
    }

    const existing = db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
    if (!existing) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const errors = validateTask(req.body, true);
    if (errors.length) {
      return res.status(422).json({ errors });
    }

    const title = req.body.title !== undefined ? req.body.title.trim() : existing.title;
    const description = req.body.description !== undefined ? req.body.description : existing.description;
    const priority = req.body.priority !== undefined ? req.body.priority : existing.priority;

    db.prepare(
      `UPDATE tasks SET title = ?, description = ?, priority = ?, updated_at = datetime('now') WHERE id = ?`
    ).run(title, description, priority, id);

    const task = db.prepare('SELECT * FROM tasks WHERE id = ?').get(id);
    res.json(task);
  });

  // DELETE /api/tasks/:id
  app.delete('/api/tasks/:id', (req, res) => {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id < 1) {
      return res.status(400).json({ error: 'Invalid task ID' });
    }

    const result = db.prepare('DELETE FROM tasks WHERE id = ?').run(id);
    if (result.changes === 0) {
      return res.status(404).json({ error: 'Task not found' });
    }

    res.status(204).end();
  });

  // Attach db for cleanup
  app._db = db;

  return app;
}

module.exports = { createApp };
